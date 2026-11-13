"""Runs a question set through the production chat flow and scores every answer automatically.

    python scripts/stress_test.py <questions.jsonl> <results.jsonl> [--today YYYY-MM-DD] [--fixture path] [--summary path]

Flow per question: AI planner -> Back-End ChatRetrieval (real PHP code, on a fixture database) -> grounded answer.
Conversation memory writes are rolled back, so db.sqlite3 is never changed.

A question row: {"id", "family", "category", "style", "template", "split", "role", "message", "check", "expect", "history"}
  check:  must (groups: any word of each group), must_not, intent_in, lead (fact in the first line), no_hedge
  expect: kind (answer|refuse|notfound|abstain|clarify|smalltalk), intents, tools (optional)
  history: earlier messages of the same conversation (optional)

Reported: accuracy overall, per category and per distinct wording; wrong answers; unanswered; false positives (answered
when it should have refused, abstained or said not found); false negatives (refused or abstained when it should have
answered); intent and retrieval accuracy; security violations; crashes; latency.
"""
import argparse
import datetime
import json
import logging
import os
import statistics
import sys
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automotive_ai.settings")

parser = argparse.ArgumentParser()
parser.add_argument("questions")
parser.add_argument("results")
parser.add_argument("--today")
parser.add_argument("--fixture")
parser.add_argument("--summary")
args = parser.parse_args()
questions_path, results_path = Path(args.questions).resolve(), Path(args.results).resolve()
summary_path = Path(args.summary).resolve() if args.summary else None
fixture_path = Path(args.fixture).resolve() if args.fixture else None
os.chdir(ROOT)

import django  # noqa: E402

django.setup()
logging.disable(logging.CRITICAL)
from django.db import transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

import chat_pipeline  # noqa: E402
from ai_api.assistant import answer_chat  # noqa: E402

if args.today:
    frozen = datetime.date.fromisoformat(args.today)
    mock.patch.object(timezone, "localdate", lambda *a, **k: frozen).start()
    os.environ["CHAT_TEST_TODAY"] = args.today
    chat_pipeline.RETRIEVAL_CLI = ROOT / "scripts" / "stress_retrieval_cli.php"

FIXTURE = fixture_path or chat_pipeline.FIXTURE_DB
USERS = chat_pipeline.DEFAULT_USERS
ABSTAIN = ("I can only answer from this system's data", "This policy is not recorded in the system. Please confirm", "I couldn't work out which records")
HEDGES = ["closest match i found", "i'm not sure", "i am not sure", "might be", "i think", "probably", "i couldn't work out", "could you rephrase"]


def backend(requests):
    return chat_pipeline.backend(requests, fixture_path=FIXTURE)


def leak_strings():
    """What a customer must never see: other people's names, plate numbers and company-wide totals, from the fixture."""
    db = json.loads(Path(FIXTURE).read_text(encoding="utf-8"))
    me = USERS["customer"]
    leaks = [u["full_name"] for u in db.get("users", []) if u["id"] != me]
    leaks += [c["plate_number"] for c in db.get("cars", []) if c.get("plate_number")]
    booked = sum(float(r["total_amount"]) for r in db.get("reservations", []) if r["status"] in ("pending", "confirmed", "completed"))
    cost = sum(float(m.get("cost") or 0) for m in db.get("maintenance_records", []))
    return leaks + [f"{booked:,.0f}", f"{cost:,.0f}"]


LEAKS = leak_strings()
questions = [json.loads(line) for line in open(questions_path, encoding="utf-8")]
started = time.time()
vocab = {role: backend([{"op": "vocabulary", "is_admin": role == "admin"}])[0] for role in ("admin", "customer")}


def request(q, conversation=None):
    role = q["role"]
    return dict(viewer_role=role, conversation_id=conversation, conversation_scope=f"{role}:{USERS[role]}", retrieval_protocol=1, vocabulary=vocab[role])


def viewer(q):
    return {"role": q["role"], "user_id": USERS[q["role"]]}


def safe(message, **kw):
    t0 = time.perf_counter()
    try:
        return answer_chat(message, **kw), (time.perf_counter() - t0) * 1000
    except Exception as exc:  # a crash is a failure, not a stop
        return {"answer": f"CRASH: {type(exc).__name__}: {exc}", "intent": "crash"}, (time.perf_counter() - t0) * 1000


def turn(q, message, conversation):
    first_reply, ms = safe(message, **request(q, conversation))
    if first_reply.get("status") != "needs_data":
        return first_reply, first_reply, ms
    results = backend([{"op": "execute", "viewer": viewer(q), "plan": first_reply["plan"]}])[0]
    final_reply, ms2 = safe(message, retrieval={"plan": first_reply["plan"], "results": results, "data_as_of": "fixture"}, **request(q, conversation))
    return final_reply, first_reply, ms + ms2


first, final, timing = {}, {}, {}
plain = [q for q in questions if not q.get("history")]
for q in plain:
    first[q["id"]], timing[q["id"]] = safe(q["message"], **request(q))
needs = [q for q in plain if first[q["id"]].get("status") == "needs_data"]
retrieved = {}
for start in range(0, len(needs), 500):
    chunk = needs[start:start + 500]
    answers = backend([{"op": "execute", "viewer": viewer(q), "plan": first[q["id"]]["plan"]} for q in chunk])
    retrieved.update({q["id"]: res for q, res in zip(chunk, answers)})
for q in plain:
    r = first[q["id"]]
    if q["id"] in retrieved:
        r, ms = safe(q["message"], retrieval={"plan": r["plan"], "results": retrieved[q["id"]], "data_as_of": "fixture"}, **request(q))
        timing[q["id"]] += ms
    final[q["id"]] = r
for q in (q for q in questions if q.get("history")):
    with transaction.atomic():  # memory writes never reach db.sqlite3
        conversation = str(uuid.uuid4())
        for earlier in q["history"]:
            turn(q, earlier, conversation)
        final[q["id"]], first[q["id"]], timing[q["id"]] = turn(q, q["message"], conversation)
        transaction.set_rollback(True)


def check(q, r):
    c, answer, intent = q["check"], str(r.get("answer") or ""), r.get("intent")
    low = answer.casefold()
    if intent == "crash":
        return "crash"
    for group in c.get("must") or []:
        if not any(word.casefold() in low for word in group):
            return "missing " + "|".join(group)
    for word in c.get("must_not") or []:
        if word.casefold() in low:
            return "contains " + word
    if c.get("intent_in") and intent not in c["intent_in"]:
        return f"intent {intent} not in {c['intent_in']}"
    head = answer.split("\n", 1)[0].casefold()
    for group in c.get("lead") or []:
        if not any(word.casefold() in head for word in group):
            return "not first: " + "|".join(group)
    if c.get("no_hedge"):
        for phrase in HEDGES:
            if phrase in low:
                return "hedged: " + phrase
    return None


def outcome(r, problem):
    if problem is None:
        return "correct"
    if problem == "crash":
        return "crash"
    answer = str(r.get("answer") or "")
    if r.get("intent") in ("unknown", "permission_denied", "clarification_needed") or any(text in answer for text in ABSTAIN):
        return "unanswered"
    return "wrong"


rows, stats = [], defaultdict(Counter)
security, intent_hits, retrieval_hits, latency = [], Counter(), Counter(), []
for q in questions:
    r, plan = final[q["id"]], first[q["id"]].get("plan") or {}
    problem = check(q, r)
    expect = q.get("expect") or {}
    kind = expect.get("kind")
    result = outcome(r, problem)
    leak = None
    if q["role"] == "customer":
        leak = next((word for word in LEAKS if word.casefold() in str(r.get("answer") or "").casefold()), None)
    if leak or (q.get("category") == "security" and problem):
        security.append({"id": q["id"], "message": q["message"], "problem": problem or f"leak {leak}", "answer": str(r.get("answer"))[:300]})
    tools = [item["tool"] for item in plan.get("retrievals", [])]
    got_intent = plan.get("intent") or r.get("intent")
    intent_ok = None
    if expect.get("intents"):
        intent_ok = got_intent in expect["intents"] or r.get("intent") in expect["intents"]
        intent_hits[intent_ok] += 1
    retrieval_ok = None
    if expect.get("tools") is not None:
        tool_ok = set(expect["tools"]) <= set(tools) if expect["tools"] else not tools
        # A retrieval only counts as correct if the expected facts also reached the answer.
        retrieval_ok = bool(tool_ok and not (problem and problem.startswith("missing")))
        retrieval_hits[retrieval_ok] += 1
    false_positive = bool(problem) and kind in ("refuse", "notfound", "abstain")
    false_negative = bool(problem) and kind in ("answer", None) and result == "unanswered"
    latency.append(timing[q["id"]])
    rows.append({**{k: q.get(k) for k in ("id", "family", "category", "style", "template", "split", "role", "message")}, "ok": problem is None, "problem": problem,
                 "outcome": result, "false_positive": false_positive, "false_negative": false_negative, "leak": leak, "intent_ok": intent_ok, "retrieval_ok": retrieval_ok,
                 "intent": r.get("intent"), "plan": f"{plan.get('intent')}/{plan.get('purpose')}" if plan else None, "tools": tools, "ms": round(timing[q["id"]], 1),
                 "answer": r.get("answer")})
    for key in (q.get("category") or q.get("family"), f"family:{q.get('family')}", f"style:{q.get('style')}" if q.get("style") else None):
        if key:
            stats[key][result] += 1
with open(results_path, "w", encoding="utf-8") as handle:
    for row in rows:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def percent(part, whole):
    return round(100 * part / whole, 2) if whole else None


total = Counter(row["outcome"] for row in rows)
n = len(rows)
wordings = defaultdict(list)
for row in rows:
    wordings[row.get("template") or row["family"] + "|" + row["message"].casefold()].append(row["ok"])
ms = sorted(latency)
summary = {
    "questions": n, "correct": total["correct"], "accuracy_percent": percent(total["correct"], n), "wrong": total["wrong"], "unanswered": total["unanswered"],
    "crashes": total["crash"], "distinct_wordings": len(wordings),
    "accuracy_per_wording_percent": percent(sum(sum(v) / len(v) for v in wordings.values()), len(wordings)),
    "false_positives": sum(r["false_positive"] for r in rows), "false_negatives": sum(r["false_negative"] for r in rows),
    "intent_accuracy_percent": percent(intent_hits[True], sum(intent_hits.values())), "intent_scored": sum(intent_hits.values()),
    "retrieval_accuracy_percent": percent(retrieval_hits[True], sum(retrieval_hits.values())), "retrieval_scored": sum(retrieval_hits.values()),
    "security_violations": len(security), "security_detail": security[:20],
    "latency_ms": {"mean": round(statistics.mean(ms), 1), "p50": round(ms[n // 2], 1), "p95": round(ms[int(n * .95)], 1), "max": round(ms[-1], 1)} if ms else {},
    "seconds": round(time.time() - started), "today": args.today, "fixture": Path(FIXTURE).name,
    "by_group": {k: {"n": sum(v.values()), "accuracy_percent": percent(v["correct"], sum(v.values())), "wrong": v["wrong"], "unanswered": v["unanswered"], "crash": v["crash"]}
                 for k, v in sorted(stats.items())},
}
if summary_path:
    summary_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: v for k, v in summary.items() if k not in ("by_group", "security_detail")}, indent=1))
for key, value in summary["by_group"].items():
    if not key.startswith("family:"):
        print(f"  {key:26s} n={value['n']:6d}  {value['accuracy_percent']:6.2f}%  wrong={value['wrong']:4d} unanswered={value['unanswered']:4d}")
print("below 100%:", ", ".join(f"{k[7:]} {v['accuracy_percent']:.0f}%" for k, v in summary["by_group"].items() if k.startswith("family:") and v["accuracy_percent"] < 100))
