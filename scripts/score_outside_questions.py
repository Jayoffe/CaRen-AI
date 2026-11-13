"""Scores questions written by someone outside the project (data/evaluation/outside/README.md).

    python scripts/score_outside_questions.py <questions.csv>

Turns the CSV into the stress-test question format and runs it through the production chat flow with
scripts/stress_test.py (AI planner -> Back-End ChatRetrieval on the fixture database -> answer). The first
run of a file is sealed in data/evaluation/outside/seal.json; only that first score is a fair measure of
how the assistant handles unseen questions.
"""
import csv
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAL = ROOT / "data" / "evaluation" / "outside" / "seal.json"
FIXTURE_TODAY = "2026-11-01"  # the fixture database is written for this date
KINDS = {"answer", "refuse", "notfound", "abstain", "clarify", "smalltalk"}


def rows_from_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if (row.get("question") or "").strip()]
    examples = [row for row in rows if str(row.get("id", "")).startswith("example-")]
    if examples:
        sys.exit(f"Delete the {len(examples)} example row(s) (ids starting with 'example-') before scoring.")
    questions, problems = [], []
    for number, row in enumerate(rows, start=2):
        role = (row.get("role") or "customer").strip().casefold()
        kind = (row.get("expected_kind") or "answer").strip().casefold()
        if role not in ("customer", "admin"):
            problems.append(f"line {number}: role must be customer or admin")
        if kind not in KINDS:
            problems.append(f"line {number}: expected_kind must be one of {', '.join(sorted(KINDS))}")
        must = [[word.strip() for word in group.split("|") if word.strip()]
                for group in (row.get("must_mention") or "").split(";") if group.strip()]
        must_not = [word.strip() for word in (row.get("must_not_mention") or "").split(";") if word.strip()]
        questions.append({
            "id": (row.get("id") or f"row{number}").strip(), "family": (row.get("category") or "outside").strip() or "outside",
            "category": (row.get("category") or "outside").strip() or "outside", "style": "outside", "template": None,
            "split": "outside", "role": role, "message": row["question"].strip(), "history": None,
            "check": {"must": must, "must_not": must_not, "intent_in": None},
            "expect": {"kind": kind},
        })
    if problems:
        sys.exit("Fix these rows first:\n" + "\n".join(problems))
    ids = [q["id"] for q in questions]
    if len(set(ids)) != len(ids):
        sys.exit("Every row needs a different id.")
    return questions


def seal_status(path):
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    seals = json.loads(SEAL.read_text(encoding="utf-8")) if SEAL.exists() else {}
    name = Path(path).name
    if name not in seals:
        seals[name] = {"sha256": digest, "first_run": datetime.date.today().isoformat()}
        SEAL.write_text(json.dumps(seals, indent=2) + "\n", encoding="utf-8")
        return "FIRST RUN (sealed now): this score is the fair measure."
    if seals[name]["sha256"] != digest:
        return f"NOT A FIRST RUN: the file changed since it was sealed on {seals[name]['first_run']}."
    return f"NOT A FIRST RUN: this file was first scored on {seals[name]['first_run']}; later scores may reflect fixes made against it."


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    source = Path(sys.argv[1]).resolve()
    questions = rows_from_csv(source)
    if not questions:
        sys.exit("The file has no questions.")
    status = seal_status(source)
    jsonl = source.with_name(source.stem + "_questions.jsonl")
    jsonl.write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in questions), encoding="utf-8")
    results = source.with_name(source.stem + "_results.jsonl")
    summary = source.with_name(source.stem + "_summary.json")
    completed = subprocess.run([sys.executable, str(ROOT / "scripts" / "stress_test.py"), str(jsonl), str(results),
                                "--today", FIXTURE_TODAY, "--summary", str(summary)], cwd=ROOT)
    if completed.returncode:
        sys.exit(completed.returncode)
    data = json.loads(summary.read_text(encoding="utf-8"))
    print(f"\n{status}")
    print(f"{data['questions']} questions: {data['accuracy_percent']}% correct, {data['wrong']} wrong, {data['unanswered']} unanswered, "
          f"{data['crashes']} crashes, {data['security_violations']} privacy problems.")
    print(f"Every answer is in {results}; read the wrong and unanswered ones before fixing anything.")


if __name__ == "__main__":
    main()
