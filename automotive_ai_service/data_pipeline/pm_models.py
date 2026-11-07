"""Train and evaluate the two candidate models the dataset audit found trainable.

    python -m data_pipeline.pm_models                 # both
    python -m data_pipeline.pm_models --only scania
    python -m data_pipeline.pm_models --only airpath

Neither candidate can serve the assessment endpoint, and this module cannot
make one eligible: ``eligible_for_inference`` is hard-coded False. See
``DEPLOYMENT_BLOCKERS`` for the reasons. Each run writes evaluation.json,
config.json and pipeline.joblib under trained_models/experiments/<name>/ and
updates the model registry's ``experiments`` section.

Leakage controls
  scania  - official vehicle-disjoint train/validation/test files (verified at
            run time). Threshold chosen on validation only. Test is scored
            once. time_step and study length are not features: both reveal how
            training rows were sampled.
  airpath - fault runs exist only on Cycle_RDE_Eifel and Cycle_RDE_Eifel2, so
            training uses Eifel and testing uses the separately driven Eifel2.
            Healthy-only cycles the model never saw measure false alarms.
"""
import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, classification_report, confusion_matrix, f1_score,
    precision_recall_curve, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

from data_pipeline.status import MODEL_REGISTRY_PATH, _read_json, _write_json_atomic


SERVICE_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = SERVICE_ROOT / "data" / "raw"
OUTPUT_ROOT = SERVICE_ROOT / "trained_models" / "experiments"
RANDOM_STATE = 42

SCANIA_NAME = "scania_component_x_repair_window_v1"
AIRPATH_NAME = "diesel_airpath_fault_classifier_v1"

# A repair within this many time steps of a readout is the positive class. The
# value is the published class boundary: labels 1-4 all fall within 48 steps.
SCANIA_HORIZON = 48
SCANIA_MAX_POSITIVE_ROWS_PER_VEHICLE = 3
SCANIA_MAX_NEGATIVE_ROWS_PER_VEHICLE = 2
# Minimum performance before a benchmark counts as having learned anything.
SCANIA_BENCHMARK_MIN_PR_AUC_LIFT = 2.0
AIRPATH_TRAIN_CYCLE = "Cycle_RDE_Eifel"
AIRPATH_TEST_CYCLE = "Cycle_RDE_Eifel2"
AIRPATH_ROW_STRIDE = 5

DEPLOYMENT_BLOCKERS = {
    SCANIA_NAME: [
        "'Component X' is anonymized, so it cannot be mapped to any of the eight assessment categories.",
        "Inputs are anonymized heavy-truck histogram counters that this fleet does not collect.",
        "Trained on heavy trucks; not validated on the passenger cars, SUVs, vans and motorcycles in this fleet.",
    ],
    AIRPATH_NAME: [
        "Faults are injected, on data with no documented source, so scores do not establish real-world performance.",
        "Inputs are standardized with an unknown reference and include EGR and turbo signals an inspection does not record.",
        "All faulted runs share one route, so the holdout does not test generalization to other routes.",
    ],
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binary_report(y_true, score, threshold):
    predicted = (score >= threshold).astype(int)
    matrix = confusion_matrix(y_true, predicted, labels=[0, 1])
    return {
        "records": int(len(y_true)),
        "positives": int(y_true.sum()),
        "threshold": round(float(threshold), 6),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 4),
        "pr_auc": round(float(average_precision_score(y_true, score)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, score)), 4),
        "confusion_matrix": {
            "true_negative": int(matrix[0, 0]), "false_positive": int(matrix[0, 1]),
            "false_negative": int(matrix[1, 0]), "true_positive": int(matrix[1, 1]),
        },
        "false_negative_rate": round(float(matrix[1, 0] / max(1, matrix[1].sum())), 4),
    }


def threshold_for_fbeta(y_true, score, beta=2.0):
    """Validation threshold weighted towards recall: a missed repair costs more than a false alarm."""
    precision, recall, thresholds = precision_recall_curve(y_true, score)
    precision, recall = precision[:-1], recall[:-1]
    fbeta = (1 + beta ** 2) * precision * recall / np.maximum(beta ** 2 * precision + recall, 1e-12)
    return float(thresholds[int(np.argmax(fbeta))])


def save_result(name, result, model, config):
    folder = OUTPUT_ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, folder / "pipeline.joblib", compress=3)
    _write_json_atomic(folder / "config.json", config)
    _write_json_atomic(folder / "evaluation.json", result)

    registry = _read_json(MODEL_REGISTRY_PATH, {"schema_version": 1})
    registry.setdefault("experiments", {})[name] = {
        "status": result["validation_status"],
        "model_name": name,
        "model_version": result["model_version"],
        "task": result["task"],
        "capability": result["capability"],
        "dataset": result["dataset"],
        "dataset_sources": result["dataset_sources"],
        "trained_at": result["trained_at"],
        "eligible_for_inference": False,
        "validation_status": result["validation_status"],
        "metrics": result["metrics"],
        "reason": " ".join(result["deployment_blockers"]),
        "known_limitations": result["deployment_blockers"] + result["limitations"],
        "artifact_path": f"trained_models/experiments/{name}/pipeline.joblib",
        "artifact_sha256": sha256_file(folder / "pipeline.joblib"),
        "evaluation_report_path": f"trained_models/experiments/{name}/evaluation.json",
        "evaluation_report_sha256": sha256_file(folder / "evaluation.json"),
    }
    _write_json_atomic(MODEL_REGISTRY_PATH, registry)


def environment():
    return {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__}


# ---------------------------------------------------------------------------
# SCANIA Component X: repair within 48 time steps of a readout
# ---------------------------------------------------------------------------

def read_readouts(path, vehicles=None):
    columns = pd.read_csv(path, nrows=0).columns.tolist()
    dtypes = {column: "float32" for column in columns if column != "vehicle_id"}
    dtypes["vehicle_id"] = "int32"
    frames = []
    for chunk in pd.read_csv(path, dtype=dtypes, chunksize=500_000):
        frames.append(chunk if vehicles is None else chunk[chunk["vehicle_id"].isin(vehicles)])
    frame = pd.concat(frames, ignore_index=True).sort_values(["vehicle_id", "time_step"], kind="stable")
    sensors = [column for column in frame.columns if column not in ("vehicle_id", "time_step")]
    # Forward fill within one vehicle only: a readout may use its own past, never its future.
    frame[sensors] = frame.groupby("vehicle_id", sort=False)[sensors].ffill()
    return frame.reset_index(drop=True), sensors


def spec_codes(path):
    frame = pd.read_csv(path).set_index("vehicle_id")
    return frame.apply(lambda column: pd.to_numeric(column.astype(str).str.replace("Cat", "", regex=False), errors="coerce"))


def scania_features(rows, sensors, specs):
    """Counters per time step plus specifications. Time itself is deliberately excluded."""
    steps = rows["time_step"].clip(lower=1.0).to_numpy(dtype="float32")[:, None]
    rates = rows[sensors].to_numpy(dtype="float32") / steps
    joined = specs.reindex(rows["vehicle_id"].to_numpy()).to_numpy(dtype="float32")
    return np.hstack([rates, joined])


def scania_training_rows(readouts, tte, generator):
    tte = tte.set_index("vehicle_id")
    study = tte["length_of_study_time_step"].reindex(readouts["vehicle_id"]).to_numpy()
    repaired = tte["in_study_repair"].reindex(readouts["vehicle_id"]).to_numpy() == 1
    remaining = study - readouts["time_step"].to_numpy()

    # A censored vehicle's last 48 steps have an unknown outcome, so they get no label.
    labels = np.full(len(readouts), -1, dtype="int8")
    labels[remaining > SCANIA_HORIZON] = 0
    labels[repaired & (remaining <= SCANIA_HORIZON)] = 1

    picked = []
    for _, positions in readouts.groupby("vehicle_id", sort=False).indices.items():
        positives = positions[labels[positions] == 1]
        negatives = positions[labels[positions] == 0]
        if len(positives):
            picked.append(generator.choice(positives, min(len(positives), SCANIA_MAX_POSITIVE_ROWS_PER_VEHICLE), replace=False))
        if len(negatives):
            picked.append(generator.choice(negatives, min(len(negatives), SCANIA_MAX_NEGATIVE_ROWS_PER_VEHICLE), replace=False))
    picked = np.sort(np.concatenate(picked))
    return readouts.iloc[picked].reset_index(drop=True), labels[picked].astype(int), int((labels == -1).sum())


def last_readouts(readouts):
    return readouts.groupby("vehicle_id", sort=False).tail(1).reset_index(drop=True)


def train_scania():
    generator = np.random.default_rng(RANDOM_STATE)
    files = {
        "train_readouts": RAW_ROOT / "train_operational_readouts.csv", "train_tte": RAW_ROOT / "train_tte.csv",
        "train_specifications": RAW_ROOT / "train_specifications.csv",
        "validation_readouts": RAW_ROOT / "validation_operational_readouts.csv", "validation_labels": RAW_ROOT / "validation_labels.csv",
        "validation_specifications": RAW_ROOT / "validation_specifications.csv",
        "test_readouts": RAW_ROOT / "test_operational_readouts.csv", "test_labels": RAW_ROOT / "test_labels.csv",
        "test_specifications": RAW_ROOT / "test_specifications.csv",
    }
    tte = pd.read_csv(files["train_tte"])
    validation_labels = pd.read_csv(files["validation_labels"]).set_index("vehicle_id")["class_label"]
    test_labels = pd.read_csv(files["test_labels"]).set_index("vehicle_id")["class_label"]

    overlap = (set(tte.vehicle_id) & set(validation_labels.index)) | (set(tte.vehicle_id) & set(test_labels.index)) | (set(validation_labels.index) & set(test_labels.index))
    if overlap:
        raise ValueError(f"Vehicle splits overlap: {len(overlap)} vehicles appear in more than one split.")

    specs = pd.concat([spec_codes(files[f"{part}_specifications"]) for part in ("train", "validation", "test")])
    train_readouts, sensors = read_readouts(files["train_readouts"])
    training_rows, y_train, unlabeled = scania_training_rows(train_readouts, tte, generator)
    X_train = scania_features(training_rows, sensors, specs)
    del train_readouts

    def holdout(name, labels):
        readouts, _ = read_readouts(files[f"{name}_readouts"])
        final = last_readouts(readouts)
        classes = labels.reindex(final["vehicle_id"]).to_numpy()
        if np.isnan(classes.astype(float)).any():
            raise ValueError(f"{name}: a vehicle has readouts but no label.")
        return scania_features(final, sensors, specs), classes.astype(int)

    X_validation, class_validation = holdout("validation", validation_labels)
    X_test, class_test = holdout("test", test_labels)
    y_validation, y_test = (class_validation > 0).astype(int), (class_test > 0).astype(int)

    candidates = {
        "prevalence_baseline": DummyClassifier(strategy="prior"),
        "logistic_regression": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0, class_weight="balanced", random_state=RANDOM_STATE),
    }
    metrics = {}
    fitted = {}
    for name, model in candidates.items():
        model.fit(X_train, y_train)
        fitted[name] = model
        validation_score = model.predict_proba(X_validation)[:, 1]
        threshold = 0.5 if name == "prevalence_baseline" else threshold_for_fbeta(y_validation, validation_score)
        test_score = model.predict_proba(X_test)[:, 1]
        metrics[name] = {
            "validation": binary_report(y_validation, validation_score, threshold),
            "test": binary_report(y_test, test_score, threshold),
        }
        metrics[name]["test"]["recall_by_label_window"] = {
            f"class_{label}": round(float((test_score[class_test == label] >= threshold).mean()), 4)
            for label in sorted(set(class_test)) if label > 0
        }

    # The model served as a benchmark is chosen on validation, not on test.
    best_name = max(["logistic_regression", "gradient_boosting"], key=lambda name: metrics[name]["validation"]["pr_auc"])
    prevalence = float(y_test.mean())
    best_test = metrics[best_name]["test"]
    lift = best_test["pr_auc"] / prevalence if prevalence else 0
    learned = lift >= SCANIA_BENCHMARK_MIN_PR_AUC_LIFT

    result = {
        "model_name": SCANIA_NAME,
        "model_version": f"{SCANIA_NAME}_{datetime.now(timezone.utc):%Y%m%d}",
        "task": "Repair of anonymized Component X within 48 time steps of a truck's last readout",
        "capability": "predictive_maintenance_benchmark",
        "dataset": "SCANIA Component X (inferred attribution; no documentation present locally)",
        "dataset_sources": {key: path.name for key, path in files.items()},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": "benchmark_learned_signal_not_deployable" if learned else "evaluated_rejected",
        "eligible_for_inference": False,
        "selected_estimator": best_name,
        "split": {
            "type": "official vehicle-disjoint files (verified: no vehicle in two splits)",
            "train_vehicles": int(len(tte)), "validation_vehicles": int(len(validation_labels)), "test_vehicles": int(len(test_labels)),
            "train_rows": int(len(y_train)), "train_positive_rows": int(y_train.sum()),
            "train_readouts_without_known_outcome_excluded": unlabeled,
        },
        "preprocessing": [
            "Forward fill within each vehicle only",
            "Each counter divided by time_step, removing dependence on vehicle age",
            "Vehicle specifications as ordinal category codes",
            f"Censored vehicles' last {SCANIA_HORIZON} steps excluded: their outcome is unknown",
            f"Up to {SCANIA_MAX_POSITIVE_ROWS_PER_VEHICLE} positive and {SCANIA_MAX_NEGATIVE_ROWS_PER_VEHICLE} negative readouts per vehicle",
        ],
        "class_imbalance": "class_weight='balanced' during fitting; threshold chosen on validation using F2 to favour recall",
        "metrics": metrics,
        "acceptance": {
            "benchmark_min_pr_auc_lift_over_prevalence": SCANIA_BENCHMARK_MIN_PR_AUC_LIFT,
            "test_prevalence": round(prevalence, 4),
            "test_pr_auc_lift": round(lift, 2),
            "learned_signal": learned,
            "deployment_gate_passed": False,
        },
        "deployment_blockers": DEPLOYMENT_BLOCKERS[SCANIA_NAME],
        "limitations": [
            "Model scores are uncalibrated and are not failure probabilities.",
            "Time steps are anonymized units, so the horizon cannot be stated in days or kilometres.",
        ],
        "environment": environment(),
    }
    config = {
        "random_state": RANDOM_STATE, "horizon": SCANIA_HORIZON, "features": sensors + list(specs.columns),
        "max_positive_rows_per_vehicle": SCANIA_MAX_POSITIVE_ROWS_PER_VEHICLE,
        "max_negative_rows_per_vehicle": SCANIA_MAX_NEGATIVE_ROWS_PER_VEHICLE,
        "estimators": {name: str(model) for name, model in candidates.items()},
        "source_sha256": {path.name: sha256_file(path) for path in files.values()},
    }
    save_result(SCANIA_NAME, result, fitted[best_name], config)
    return result


# ---------------------------------------------------------------------------
# Diesel air-path fault classes, held out by drive
# ---------------------------------------------------------------------------

def train_airpath():
    source = RAW_ROOT / "main_df_standardized.parquet"
    frame = pd.read_parquet(source)
    documented = json.loads((RAW_ROOT / "metadata.json").read_text(encoding="utf-8"))["fault_types"]
    undocumented = set(frame["fault_type"].unique()) - set(documented)
    if undocumented:
        raise ValueError(f"Fault labels missing from metadata.json: {sorted(undocumented)}")

    features = [column for column in frame.columns if column not in ("drive_cycle", "fault_type", "flag")]
    train = frame[frame["drive_cycle"] == AIRPATH_TRAIN_CYCLE].iloc[::AIRPATH_ROW_STRIDE]
    test = frame[frame["drive_cycle"] == AIRPATH_TEST_CYCLE].iloc[::AIRPATH_ROW_STRIDE]
    unseen_healthy = frame[~frame["drive_cycle"].isin([AIRPATH_TRAIN_CYCLE, AIRPATH_TEST_CYCLE])].iloc[::AIRPATH_ROW_STRIDE]

    labels = sorted(frame["fault_type"].unique())
    candidates = {
        "majority_baseline": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=300, class_weight="balanced")),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, class_weight="balanced", random_state=RANDOM_STATE),
    }
    metrics = {}
    fitted = {}
    for name, model in candidates.items():
        model.fit(train[features].to_numpy(), train["fault_type"].to_numpy())
        fitted[name] = model
        predicted = model.predict(test[features].to_numpy())
        truth = test["fault_type"].to_numpy()
        faulty = truth != "Healthy"
        metrics[name] = {
            "test_records": int(len(test)),
            "accuracy": round(float((predicted == truth).mean()), 4),
            "macro_f1": round(float(f1_score(truth, predicted, average="macro", labels=labels, zero_division=0)), 4),
            "per_class": {
                label: {key: round(float(value), 4) for key, value in stats.items() if key != "support"}
                for label, stats in classification_report(truth, predicted, labels=labels, output_dict=True, zero_division=0).items()
                if label in labels
            },
            "confusion_matrix": {"labels": labels, "rows": confusion_matrix(truth, predicted, labels=labels).tolist()},
            "fault_missed_as_healthy_rate": round(float((predicted[faulty] == "Healthy").mean()), 4),
            "false_alarm_rate_on_held_out_healthy_cycles": round(float((model.predict(unseen_healthy[features].to_numpy()) != "Healthy").mean()), 4),
            "held_out_healthy_records": int(len(unseen_healthy)),
        }

    best_name = max(["logistic_regression", "gradient_boosting"], key=lambda name: metrics[name]["macro_f1"])
    result = {
        "model_name": AIRPATH_NAME,
        "model_version": f"{AIRPATH_NAME}_{datetime.now(timezone.utc):%Y%m%d}",
        "task": "Classify ten documented air-path conditions (healthy, MAF drift, MAP drift, EGR valve clog) from one row of signals",
        "capability": "fault_classification_research",
        "dataset": "main_df_standardized.parquet with metadata.json and cycles.json",
        "dataset_sources": {"signals": source.name, "label_definitions": "metadata.json", "cycle_definitions": "cycles.json"},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "validation_status": "research_only_not_deployable",
        "eligible_for_inference": False,
        "selected_estimator": best_name,
        "split": {
            "type": f"Train on {AIRPATH_TRAIN_CYCLE}; test on {AIRPATH_TEST_CYCLE}, plus false alarms on healthy cycles not used for fitting",
            "train_rows": int(len(train)), "test_rows": int(len(test)), "row_stride": AIRPATH_ROW_STRIDE,
        },
        "preprocessing": ["Signals used as supplied (already standardized)", f"Every {AIRPATH_ROW_STRIDE}th row, to reduce adjacent-row duplication", "'flag' excluded: 33 non-null values, undocumented"],
        "class_imbalance": "class_weight='balanced'",
        "metrics": metrics,
        "acceptance": {"deployment_gate_passed": False},
        "deployment_blockers": DEPLOYMENT_BLOCKERS[AIRPATH_NAME],
        "limitations": [
            "cycles.json states that Cycle_RDE_Eifel2 drives the same route as Cycle_RDE_Eifel, so test results overstate performance on new routes.",
            "If the supplied standardization used test rows, a small amount of leakage cannot be excluded.",
        ],
        "environment": environment(),
    }
    config = {
        "random_state": RANDOM_STATE, "features": features, "labels": labels, "train_cycle": AIRPATH_TRAIN_CYCLE,
        "test_cycle": AIRPATH_TEST_CYCLE, "row_stride": AIRPATH_ROW_STRIDE,
        "estimators": {name: str(model) for name, model in candidates.items()},
        "source_sha256": {source.name: sha256_file(source)},
    }
    save_result(AIRPATH_NAME, result, fitted[best_name], config)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=["scania", "airpath"])
    arguments = parser.parse_args()
    if arguments.only in (None, "airpath"):
        result = train_airpath()
        print(json.dumps({"model": AIRPATH_NAME, "selected": result["selected_estimator"], "metrics": {key: {k: v for k, v in value.items() if k in ("accuracy", "macro_f1", "fault_missed_as_healthy_rate", "false_alarm_rate_on_held_out_healthy_cycles")} for key, value in result["metrics"].items()}}, indent=2), flush=True)
    if arguments.only in (None, "scania"):
        result = train_scania()
        print(json.dumps({"model": SCANIA_NAME, "selected": result["selected_estimator"], "status": result["validation_status"], "acceptance": result["acceptance"], "test": {key: value["test"] for key, value in result["metrics"].items()}}, indent=2), flush=True)


if __name__ == "__main__":
    main()
