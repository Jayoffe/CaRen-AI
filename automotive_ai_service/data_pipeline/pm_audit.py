"""Dataset audit for the predictive maintenance module.

    python -m data_pipeline.pm_audit            # rediscover data/raw (slow: reads all 2.5 GB)
    python -m data_pipeline.pm_audit --cached   # reuse data/processed/pm_audit/discovery.json

Measured facts come from data_pipeline.discovery and are recomputed on each run.
The category and reasoning for each dataset are reviewed judgements in
``ASSESSMENTS``. A dataset with no entry is reported as unreviewed and fails the
test in ai_api/test_assessment.py, so new data cannot be skipped silently.

Writes data/reports/pm_dataset_inventory.json and pm_dataset_suitability.md.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from data_pipeline.dataset_rules import DATASET_RULES
from data_pipeline.discovery import discover
from data_pipeline.status import MODEL_REGISTRY_PATH, _read_json


SERVICE_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = SERVICE_ROOT / "data" / "raw"
REPORT_ROOT = SERVICE_ROOT / "data" / "reports"
CACHE_PATH = SERVICE_ROOT / "data" / "processed" / "pm_audit" / "discovery.json"
INDEX_ROOT = SERVICE_ROOT / "data" / "processed" / "knowledge_index"

CATEGORIES = {
    "predictive_maintenance": "1. Predictive maintenance",
    "fault_classification": "2. Fault classification",
    "diagnostic_knowledge": "3. Diagnostic knowledge",
    "condition_assessment": "4. Condition assessment",
    "supplementary_synthetic": "5. Supplementary or synthetic",
    "unsuitable": "6. Unsuitable",
}
COMPONENTS = ["Engine", "Battery and Electrical", "Brakes", "Transmission", "Suspension and Steering", "Tires and Wheels", "Cooling System", "Air Conditioning"]

# category, identifiers present, whether real outcomes exist, components named, and why.
ASSESSMENTS = {
    "scania_component_x": {
        "category": "predictive_maintenance",
        "identifiers": "vehicle_id and time_step; splits are vehicle-disjoint (verified)",
        "real_outcomes": "Yes: time to repair of one component (train_tte) and class labels by time window. Heavy trucks.",
        "components": [],
        "suitable_for": "A predictive maintenance benchmark only.",
        "reason": "The only local dataset with real time-to-event repair outcomes per vehicle. 'Component X' is anonymized, so it cannot be claimed for any of the eight categories, and its inputs are anonymized truck counters this fleet does not collect. Provenance is inferred: no documentation or licence is in the folder.",
    },
    "nasa_battery": {
        "category": "predictive_maintenance",
        "identifiers": "Cell ID and cycle number; byte-identical copies must not cross splits",
        "real_outcomes": "Yes, for laboratory 18650 cells: capacity fade to a documented end-of-life threshold.",
        "components": [],
        "suitable_for": "Laboratory cell degradation research.",
        "reason": "Real outcomes, but for small laboratory cells under controlled cycling. It does not represent a 12 V starter battery, an alternator or a vehicle environment, so it gives no predictive capability for Battery and Electrical.",
    },
    "main_df_standardized": {
        "category": "fault_classification",
        "identifiers": "drive_cycle only; no vehicle identifier, no timestamp",
        "real_outcomes": "No. Faults are injected (sensor drift, valve clog), not failures that occurred.",
        "components": ["Engine"],
        "suitable_for": "Research classification of injected air-path faults.",
        "reason": "Correction to the earlier audit, which called these labels undocumented: metadata.json and cycles.json at the root of data/raw define every fault class and drive cycle. Labels are usable, but they are injected on data with no named source, all faults share one route, and the inputs are standardized signals an inspection does not record.",
    },
    "enginefaultdb": {
        "category": "fault_classification",
        "identifiers": "None: no acquisition-run identifier",
        "real_outcomes": "Laboratory fault classes on one engine; numeric class meanings are not documented locally.",
        "components": ["Engine"],
        "suitable_for": "Nothing until run identifiers and class names are obtained.",
        "reason": "Labelled, but any split would mix rows from one run, which leaks, and the classes cannot be named. Not trained.",
    },
    "engine_condition_tables": {
        "category": "fault_classification",
        "identifiers": "None",
        "real_outcomes": "Unknown: a binary label whose meaning is undocumented.",
        "components": ["Engine"],
        "suitable_for": "Experiment only (existing, not served).",
        "reason": "No source, licence, units or engine grouping. raw_data.csv is the union of train.csv and test.csv. The existing experiment barely beats its baseline.",
    },
    "diesel_obd_pid_dtc": {
        "category": "fault_classification",
        "identifiers": "No per-row vehicle column; README lists 8 vehicles",
        "real_outcomes": "Stored fault codes per vehicle, not repairs. Codes are constant per vehicle, so they identify the vehicle rather than a changing fault state.",
        "components": ["Engine"],
        "suitable_for": "Experiment only (existing, not served).",
        "reason": "A model would learn which vehicle a row came from. Over three quarters of workbook rows are exact duplicates per the earlier inventory.",
    },
    "obdex": {
        "category": "diagnostic_knowledge",
        "identifiers": "Fault code",
        "real_outcomes": "Not applicable: reference data.",
        "components": COMPONENTS,
        "suitable_for": "Exact fault-code lookup. In production use through the knowledge index.",
        "reason": "CC0 reference of generic fault codes with causes and symptoms. It explains a code; it does not establish that a vehicle has that fault or predict anything. Tire coverage is thin because few codes concern tires.",
    },
    "automotive_fault_flowcharts": {
        "category": "diagnostic_knowledge",
        "identifiers": "None",
        "real_outcomes": "Not applicable: diagnostic steps.",
        "components": ["Engine", "Battery and Electrical", "Brakes", "Transmission", "Suspension and Steering", "Tires and Wheels", "Cooling System", "Air Conditioning"],
        "suitable_for": "Symptom guidance, shown as unverified reference.",
        "reason": "99 symptom-to-steps entries including Air Conditioning (8) and Cooling (8). Diagnostic instructions are not fault records. Its source is not verified locally, so results are labelled as such. Coverage of suspension (steering only) and tires (3 entries) is thin.",
    },
    "honda_motorcycle_masterparts": {
        "category": "diagnostic_knowledge",
        "identifiers": "Part number",
        "real_outcomes": "No.",
        "components": [],
        "suitable_for": "Exact part-number lookup in chat.",
        "reason": "A parts list for one motorcycle brand. It says nothing about condition or failure.",
    },
    "vehicle_service_records": {
        "category": "supplementary_synthetic",
        "identifiers": "slno is a row number, not a vehicle; no dates",
        "real_outcomes": "No. It records service items done at a visit, not failures.",
        "components": ["Engine", "Brakes", "Transmission"],
        "suitable_for": "Service-item statistics only.",
        "reason": "Recorded workshop data, not synthetic, and the closest thing to maintenance history, but it holds no condition ratings, with no vehicle identity or chronology, and a service visit does not establish a failure. service_need_v1, v2 and v3 were trained on it and all failed their acceptance criteria.",
    },
    "ev_predictive_maintenance_15min": {
        "category": "supplementary_synthetic",
        "identifiers": "Timestamps, but columns are statistically independent",
        "real_outcomes": "No. The failure and RUL columns are independent of the signals.",
        "components": ["Battery and Electrical", "Brakes", "Tires and Wheels"],
        "suitable_for": "Nothing beyond the earlier signal audit.",
        "reason": "Named after predictive maintenance and has the right column names, but the earlier audit found no learnable signal (|r| < 0.005 and no autocorrelation), which indicates generated values.",
    },
    "hyundai_component_readings": {
        "category": "supplementary_synthetic",
        "identifiers": "No stable identifier",
        "real_outcomes": "No. The anomaly flag is uncorrelated with the readings.",
        "components": ["Engine", "Brakes", "Tires and Wheels"],
        "suitable_for": "Nothing beyond the earlier signal audit.",
        "reason": "Has brake pad thickness and tire pressure columns, but values are uniform and unrelated to the labels. Naming these components does not give predictive capability.",
    },
    "cvffad": {
        "category": "supplementary_synthetic",
        "identifiers": "vehicle_id and dates, on generated records",
        "real_outcomes": "No. Its records carry source='generated'.",
        "components": ["Engine", "Battery and Electrical", "Brakes", "Transmission", "Suspension and Steering", "Tires and Wheels", "Cooling System", "Air Conditioning"],
        "suitable_for": "Experiment only (existing, not served).",
        "reason": "Fault events look like failure history, but they are generated. Its README DOI is a placeholder and its licence file is absent. Using it would present fabricated histories as evidence.",
    },
    "ai4i_2020": {
        "category": "supplementary_synthetic",
        "identifiers": "Product ID",
        "real_outcomes": "No. Documented as synthetic.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "Synthetic milling-machine failures. Machine tool wear is not interchangeable with vehicle components.",
    },
    "auto_repair_orders": {
        "category": "supplementary_synthetic",
        "identifiers": "Vehicle and order IDs, on a generated sample",
        "real_outcomes": "No. Service completion in a generated sample.",
        "components": [],
        "suitable_for": "A schema reference for outcome tables, nothing else.",
        "reason": "238 orders with reserved example.org emails and generated names. A completed work order does not confirm a component failure.",
    },
    "dtc_chat_sft": {
        "category": "supplementary_synthetic",
        "identifiers": "None",
        "real_outcomes": "No.",
        "components": [],
        "suitable_for": "User questions only, as chat routing test cases.",
        "reason": "Templated instruction-tuning conversations. Answers contain unrelated text and are not used.",
    },
    "vehicle_diagnostic_sample": {
        "category": "unsuitable",
        "identifiers": "None",
        "real_outcomes": "No.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "Self-described generated diagnostics with random measurements. Indexing it would present fabricated results as reference facts.",
    },
    "carobd_toyota_etios": {
        "category": "unsuitable",
        "identifiers": "File and session; one vehicle",
        "real_outcomes": "No fault or repair labels.",
        "components": [],
        "suitable_for": "Unsupervised sensor anomaly research (existing experiment, not served).",
        "reason": "Real telemetry from one 2014 Toyota Etios with no outcomes. Unusual sensor readings are not confirmed faults, so it supports none of the four AI tasks in production.",
    },
    "kit_obd_seat_leon": {
        "category": "unsuitable",
        "identifiers": "File and session; one vehicle",
        "real_outcomes": "No. Tags describe road and traffic conditions.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "Real, well documented telemetry from one Seat Leon, without any fault or maintenance outcome.",
    },
    "navarra_motorcycle_telemetry": {
        "category": "unsuitable",
        "identifiers": "boot_id; one motorcycle; no calendar dates",
        "real_outcomes": "No.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "Race-track telemetry from one prepared motorcycle. It cannot be used to infer road-fleet maintenance. One raw log (LOG00010.MBL) is empty, as its README documents.",
    },
    "experimental_energy": {
        "category": "unsuitable",
        "identifiers": "None",
        "real_outcomes": "No.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "No documented vehicle, units, labels, source or licence, and substantial missing values.",
    },
    "levin_open_data": {
        "category": "unsuitable",
        "identifiers": "Not available",
        "real_outcomes": "Not available.",
        "components": [],
        "suitable_for": "Not used.",
        "reason": "Documentation and notebooks only. The measurement export is not present locally.",
    },
}

# capability coverage for each component: what the data actually supports today.
COVERAGE = {
    "Engine": {"predictive": "None", "fault": "Research only: injected air-path faults", "knowledge": True, "condition": "None"},
    "Battery and Electrical": {"predictive": "None: NASA covers laboratory cells only", "fault": "None", "knowledge": True, "condition": "None"},
    "Brakes": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
    "Transmission": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
    "Suspension and Steering": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
    "Tires and Wheels": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
    "Cooling System": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
    "Air Conditioning": {"predictive": "None", "fault": "None", "knowledge": True, "condition": "None"},
}


def knowledge_counts():
    """Fault codes and flowcharts per assessment category, counted from the built index."""
    from ai_api.assessment_service import FLOWCHART_CATEGORIES, dtc_category, load_catalog

    names = {category["key"]: category["name"] for category in load_catalog()["categories"]}
    codes = Counter()
    flowcharts = Counter()
    unmapped = 0
    with (INDEX_ROOT / "chunks.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            chunk = json.loads(line)
            if chunk["source_type"] == "dtc_reference":
                category = dtc_category(chunk["title"])
                if category:
                    codes[names[category]] += 1
                elif chunk["metadata"].get("dtc_system") == "powertrain":
                    codes["Engine"] += 1
                else:
                    unmapped += 1
            elif chunk["source_type"] == "diagnostic_flowchart":
                category = FLOWCHART_CATEGORIES.get(chunk["metadata"].get("category"))
                if category:
                    flowcharts[names[category]] += 1
    return dict(codes), dict(flowcharts), unmapped


def summarize(records):
    grouped = defaultdict(list)
    for record in records:
        grouped[record["dataset_id"]].append(record)

    rules = {rule["dataset_id"]: rule for rule in DATASET_RULES}
    datasets = []
    for dataset_id, files in sorted(grouped.items()):
        rule = rules.get(dataset_id, {})
        assessment = ASSESSMENTS.get(dataset_id)
        unique = [record for record in files if "duplicate_of" not in record]
        tabular = [record for record in unique if record.get("rows") is not None and record.get("format") in {"delimited", "parquet", "excel", "json", "yaml"}]
        largest = max(tabular, key=lambda record: record.get("rows", 0), default=None)
        missing = sum(sum((record.get("missing_values") or {}).values()) for record in tabular)
        datasets.append({
            "dataset_id": dataset_id,
            "name": rule.get("name", dataset_id),
            "source": rule.get("provenance", "Unreviewed"),
            "license": rule.get("license", "Unknown"),
            "data_nature": rule.get("data_nature", "unreviewed"),
            "files": len(files),
            "unique_files": len(unique),
            "exact_duplicate_files": len(files) - len(unique),
            "bytes": sum(record["bytes"] for record in files),
            "formats": dict(Counter(record.get("format", "unknown") for record in files)),
            "records": sum(record.get("rows", 0) for record in tabular),
            "largest_table": {"path": largest["path"], "rows": largest.get("rows"), "columns": len(largest.get("columns") or [])} if largest else None,
            "missing_values": missing,
            "duplicate_rows": sum(record.get("duplicate_rows") or 0 for record in tabular),
            "problem_files": [{"path": record["path"], "issue": record.get("issue")} for record in files if record.get("profile_status") in {"error", "empty", "unsupported"}],
            "category": assessment["category"] if assessment else "unreviewed",
            "identifiers": assessment["identifiers"] if assessment else "Unreviewed",
            "real_outcomes": assessment["real_outcomes"] if assessment else "Unreviewed",
            "components_named": assessment["components"] if assessment else [],
            "suitable_for": assessment["suitable_for"] if assessment else "Unreviewed",
            "reason": assessment["reason"] if assessment else "No review recorded; add an entry to ASSESSMENTS.",
        })
    return datasets


def model_rows():
    registry = _read_json(MODEL_REGISTRY_PATH, {})
    rows = []
    served = registry.get("maintenance_model") or {}
    metrics = served.get("metrics") or {}
    rows.append(["service_need_v3 (" + str(served.get("model_version")) + ")", served.get("task"), served.get("status"), served.get("eligible_for_inference"),
                 f"Balanced accuracy {metrics.get('balanced_accuracy')}, macro-F1 {metrics.get('macro_f1')}", served.get("reason")])
    for name, entry in (registry.get("experiments") or {}).items():
        metric_text = ""
        experiment_metrics = entry.get("metrics") or {}
        if name == "scania_component_x_repair_window_v1":
            test = experiment_metrics["gradient_boosting"]["test"]
            metric_text = f"Test PR-AUC {test['pr_auc']} (prevalence 0.0281), ROC-AUC {test['roc_auc']}, precision {test['precision']}, recall {test['recall']}, F1 {test['f1']}, false negatives {test['confusion_matrix']['false_negative']} of {test['positives']}"
        elif name == "diesel_airpath_fault_classifier_v1":
            best = experiment_metrics["gradient_boosting"]
            metric_text = f"Macro-F1 {best['macro_f1']}, faults missed as healthy {best['fault_missed_as_healthy_rate']}, false alarms on unseen healthy cycles {best['false_alarm_rate_on_held_out_healthy_cycles']}"
        rows.append([name, entry.get("task"), entry.get("status"), entry.get("eligible_for_inference"), metric_text or "See data/reports/experiments_evaluation.json", entry.get("reason")])
    return rows


def escape(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(escape(cell) for cell in row) + " |" for row in rows]
    return lines


def write_report(records, datasets):
    codes, flowcharts, unmapped = knowledge_counts()
    unclassified = [record["path"] for record in records if record["dataset_id"] == "unclassified"]
    lines = [
        "# Predictive maintenance dataset suitability",
        "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d} by `python -m data_pipeline.pm_audit`. Raw files were only read.",
        "",
        f"- Files discovered under `data/raw/`: **{len(records)}** ({sum(record['bytes'] for record in records) / 1024 ** 3:.2f} GiB)",
        f"- Files with no dataset rule: **{len(unclassified)}**",
        f"- Datasets: **{len(datasets)}**",
        "",
        "## Verdict",
        "",
        "**No dataset supports predicting failures for any of the eight categories on this fleet.** Predictive capability stays unavailable, and the assessment endpoint reports `Insufficient Data`.",
        "",
        "Stage 1 screening does not depend on any of these datasets. It uses explainable rules, plus the fault-code and flowchart references for diagnostic knowledge.",
        "",
        "## Coverage of the eight assessment categories",
        "",
        "A component name appearing in a dataset is not counted as capability.",
        "",
    ]
    lines += table(
        ["Component", "Predictive maintenance", "Fault classification", "Diagnostic knowledge", "Condition assessment data"],
        [[name, COVERAGE[name]["predictive"], COVERAGE[name]["fault"], f"{codes.get(name, 0)} fault codes, {flowcharts.get(name, 0)} flowcharts", COVERAGE[name]["condition"]] for name in COMPONENTS],
    )
    lines += ["", f"Powertrain codes with no more specific keyword are counted under Engine. {unmapped} body, chassis and network codes map to no category; they are still found by exact lookup.", "",
              "No local dataset has real inspection ratings, so condition assessment rests on the assessor's rating and the screening rules until the fleet collects its own records.", "", "## Datasets by category", ""]

    for key, title in CATEGORIES.items():
        members = [dataset for dataset in datasets if dataset["category"] == key]
        lines += [f"### {title}", ""]
        if not members:
            lines += ["None.", ""]
        for dataset in members:
            table_text = f"{dataset['largest_table']['rows']:,} rows and {dataset['largest_table']['columns']} columns in `{dataset['largest_table']['path']}`" if dataset["largest_table"] else "no tabular records"
            lines += [
                f"**{dataset['name']}** (`{dataset['dataset_id']}`)",
                "",
                f"- Why this category: {dataset['reason']}",
                f"- Suitable for: {dataset['suitable_for']}",
                f"- Real outcomes: {dataset['real_outcomes']}",
                f"- Identifiers and time: {dataset['identifiers']}",
                f"- Size: {dataset['files']} files ({dataset['exact_duplicate_files']} exact duplicates), {dataset['bytes'] / 1024 ** 2:,.1f} MiB. Largest table: {table_text}.",
                f"- Data quality: {dataset['missing_values']:,} missing values and {dataset['duplicate_rows']:,} duplicate rows across unique tables. Unreadable or empty files: {len(dataset['problem_files'])}" + (f" ({', '.join(item['path'] for item in dataset['problem_files'][:3])})." if dataset["problem_files"] else "."),
                f"- Source: {dataset['source']}",
                f"- Licence: {dataset['license']}",
                "",
            ]
    unreviewed = [dataset for dataset in datasets if dataset["category"] == "unreviewed"]
    if unreviewed:
        lines += ["### Unreviewed", ""] + [f"- `{dataset['dataset_id']}`" for dataset in unreviewed] + [""]

    lines += ["## Model registry", ""]
    lines += table(["Model", "Task", "Status", "Eligible for production", "Results", "Why"], model_rows())
    lines += ["", "No model is eligible for inference. `service_need_v3` remains `evaluated_rejected`; it was not renamed or changed.", ""]
    (REPORT_ROOT / "pm_dataset_suitability.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true", help="Reuse the last discovery result.")
    arguments = parser.parse_args()
    if arguments.cached:
        records = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    else:
        records = discover(RAW_ROOT)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(records, default=str), encoding="utf-8")
    datasets = summarize(records)
    (REPORT_ROOT / "pm_dataset_inventory.json").write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files_discovered": len(records),
        "unclassified_files": [record["path"] for record in records if record["dataset_id"] == "unclassified"],
        "datasets": datasets,
    }, indent=2, default=str), encoding="utf-8")
    write_report(records, datasets)
    print(f"{len(records)} files, {len(datasets)} datasets; unreviewed: {[d['dataset_id'] for d in datasets if d['category'] == 'unreviewed']}")


if __name__ == "__main__":
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "automotive_ai.settings")
    import django
    django.setup()
    main()
