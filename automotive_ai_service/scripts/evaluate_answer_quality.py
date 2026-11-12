"""Score chat answer quality against data/evaluation/answer_quality_v1.json.

    python scripts/evaluate_answer_quality.py [--label NAME] [--out DIR]

Runs every case through ai_api.assistant.answer_chat (the function behind /api/chat/),
turn by turn in one conversation, and scores eight metrics:

  accuracy           required facts present (each "include" group matched)
  relevance          answered from an accepted topic, no off-topic terms ("exclude")
  conciseness        within the case's word limit
  context_awareness  follow-up turns answered without repeating the previous answer
  safety             safety cases contain an immediate safety instruction
  hallucination      no figures stated where the knowledge has none ("no_numbers"),
                     and unrelated questions are declined, not answered
  retrieval          the answering knowledge document is one of the accepted topics
  consistency        every paraphrase in a group resolves to the same topic

and leakage (internal source labels or file names in the text) on every turn.
Conversation memory writes are rolled back. Results go to data/reports/answer_quality_<label>.json and .md.
"""
import argparse
import json
import os
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automotive_ai.settings")

import django  # noqa: E402

django.setup()

from django.db import transaction  # noqa: E402

from ai_api.assistant import answer_chat  # noqa: E402

CASES_PATH = SERVICE_ROOT / "data" / "evaluation" / "answer_quality_v1.json"
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:psi|bar|kpa|nm|n·m|lb|ft|l|liters?|litres?|quarts?|km|kms|kilometers?|kilometres?|miles?|months?|years?)\b", re.IGNORECASE)


def words(text):
    return re.findall(r"[A-Za-z0-9'’-]+", text)


def kind_of(response):
    data = response.get("data") or {}
    if response.get("status") == "needs_data":
        return "needs_data"
    if data.get("abstained") or response.get("intent") == "unknown":
        return "abstain"
    if response.get("intent") == "clarification_needed" or data.get("clarification_needed"):
        return "clarify"
    if response.get("intent") == "dtc_lookup":
        return "dtc"
    return "answer"


def topic_of(response):
    return (response.get("data") or {}).get("knowledge_id")


def overlap(previous, current):
    """Share of the current answer's 5-word sequences already present in the previous answer."""
    def grams(text):
        tokens = [token.casefold() for token in words(text)]
        return {tuple(tokens[index:index + 5]) for index in range(max(0, len(tokens) - 4))}
    current_grams = grams(current)
    return len(current_grams & grams(previous)) / len(current_grams) if current_grams else 0.0


def ask(message, conversation_id):
    return answer_chat(message, viewer_role="customer", conversation_id=conversation_id,
                       conversation_scope="customer:quality-eval", retrieval_protocol=1)


def score_turn(turn, response, previous_answer, config):
    answer = response.get("answer") or ""
    text = answer.casefold()
    result = {"message": turn["message"], "answer": answer, "words": len(words(answer)), "kind": kind_of(response),
              "topic": topic_of(response), "checks": {}}
    checks = result["checks"]
    expected = turn.get("expect", "answer")
    if expected != "any":
        checks["expected_kind"] = result["kind"] == expected
    if turn.get("include"):
        checks["accuracy"] = all(any(option.casefold() in text for option in group) for group in turn["include"])
    if turn.get("topics"):
        checks["retrieval"] = result["topic"] in turn["topics"]
    if turn.get("topics") or turn.get("exclude"):
        checks["relevance"] = checks.get("retrieval", True) and not any(term.casefold() in text for term in turn.get("exclude", []))
    if turn.get("max_words"):
        checks["conciseness"] = result["words"] <= turn["max_words"]
    if turn.get("safety"):
        checks["safety"] = any(phrase in text for phrase in config["safety_phrases"])
    if turn.get("no_numbers"):
        checks["hallucination"] = not NUMBER.search(answer)
    if expected == "abstain":
        checks["hallucination"] = result["kind"] == "abstain"
    if turn.get("not_repeating_previous") and previous_answer is not None:
        result["overlap_with_previous"] = round(overlap(previous_answer, answer), 3)
        # A narrowed-down list may reuse a few cause names; repeating most of the previous answer fails.
        checks["context_awareness"] = result["overlap_with_previous"] < 0.5 and checks.get("retrieval", True)
    checks["no_leakage"] = not any(term.casefold() in text for term in config["leakage_terms"])
    result["passed"] = all(checks.values())
    return result


def run(config):
    results, paraphrases = [], []
    with transaction.atomic():
        for case in config["cases"]:
            conversation_id = str(uuid.uuid4())
            previous = None
            turns = []
            for turn in case["turns"]:
                response = ask(turn["message"], conversation_id)
                turns.append(score_turn(turn, response, previous, config))
                previous = response.get("answer") or ""
            results.append({"id": case["id"], "category": case["category"], "type": case["type"], "turns": turns,
                            "passed": all(turn["passed"] for turn in turns)})
        for group in config.get("paraphrase_groups", []):
            topics = [topic_of(ask(message, str(uuid.uuid4()))) for message in group["messages"]]
            paraphrases.append({"topic": group["topic"], "messages": group["messages"], "resolved": topics,
                                "consistent": len(set(topics)) == 1, "correct": all(topic == group["topic"] for topic in topics)})
        transaction.set_rollback(True)
    return results, paraphrases


def summarize(results, paraphrases):
    metrics = defaultdict(lambda: [0, 0])
    for case in results:
        for turn in case["turns"]:
            for name, passed in turn["checks"].items():
                metrics[name][0] += int(passed)
                metrics[name][1] += 1
    metrics["consistency"] = [sum(group["consistent"] and group["correct"] for group in paraphrases), len(paraphrases)]
    by_category = defaultdict(lambda: [0, 0])
    by_type = defaultdict(lambda: [0, 0])
    for case in results:
        for bucket in (by_category[case["category"]], by_type[case["type"]]):
            bucket[0] += int(case["passed"])
            bucket[1] += 1
    all_turns = [turn for case in results for turn in case["turns"]]
    answered = [turn["words"] for turn in all_turns if turn["kind"] in {"answer", "dtc"}]
    rate = lambda pair: round(pair[0] / pair[1], 3) if pair[1] else None  # noqa: E731
    return {
        "cases": len(results), "cases_passed": sum(case["passed"] for case in results), "turns": len(all_turns),
        "metrics": {name: {"passed": pair[0], "total": pair[1], "rate": rate(pair)} for name, pair in sorted(metrics.items())},
        "by_category": {name: {"passed": pair[0], "total": pair[1]} for name, pair in sorted(by_category.items())},
        "by_type": {name: {"passed": pair[0], "total": pair[1]} for name, pair in sorted(by_type.items())},
        "answer_words": {"mean": round(sum(answered) / len(answered), 1) if answered else None,
                         "max": max(answered) if answered else None,
                         "median": sorted(answered)[len(answered) // 2] if answered else None},
    }


def write_reports(label, summary, results, paraphrases, out):
    out.mkdir(parents=True, exist_ok=True)
    payload = {"label": label, "summary": summary, "cases": results, "paraphrase_groups": paraphrases}
    (out / f"answer_quality_{label}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"# Answer quality: {label}", "",
             f"{summary['cases_passed']} of {summary['cases']} cases passed ({summary['turns']} turns).",
             f"Answer length: mean {summary['answer_words']['mean']} words, median {summary['answer_words']['median']}, max {summary['answer_words']['max']}.",
             "", "| Metric | Passed | Rate |", "|---|---|---|"]
    lines += [f"| {name} | {item['passed']}/{item['total']} | {item['rate']} |" for name, item in summary["metrics"].items()]
    lines += ["", "## Failed cases", ""]
    for case in results:
        if case["passed"]:
            continue
        for turn in case["turns"]:
            failed = [name for name, passed in turn["checks"].items() if not passed]
            if failed:
                lines.append(f"- **{case['id']}** \"{turn['message']}\" -> {turn['kind']}/{turn['topic']} ({turn['words']} words): failed {', '.join(failed)}")
    (out / f"answer_quality_{label}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", default="current")
    parser.add_argument("--out", default=str(SERVICE_ROOT / "data" / "reports"))
    args = parser.parse_args()
    config = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results, paraphrases = run(config)
    summary = summarize(results, paraphrases)
    write_reports(args.label, summary, results, paraphrases, Path(args.out))
    print(json.dumps(summary, indent=2))
    return 0 if summary["cases_passed"] == summary["cases"] else 1


if __name__ == "__main__":
    sys.exit(main())
