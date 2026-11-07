"""Tests for category-specific models. ALL RECORDS HERE ARE SYNTHETIC, generated for pipeline
tests only. They use a temporary registry and model folder and never reach the real ones."""
import json
import os
import random
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .assessment_service import AssessmentValidationError, analyze_assessment, load_catalog, screen_component
from .category_models import (
    FEATURE_SCHEMA_VERSION, InsufficientTrainingData, RegistryError, assessment_features, category_availability,
    chronological_split, evaluate_records, predictions_for_assessment, promote_model, record_label, revoke_model,
    train_category, wilson_lower_bound,
)


REAL_REGISTRY = Path(__file__).resolve().parents[1] / "models" / "model_registry.json"


def record(outcome_id, **fields):
    base = {
        "outcome_id": outcome_id, "assessment_id": outcome_id, "vehicle_id": 1 + outcome_id % 6, "plate_number": f"SYNTH-{outcome_id % 6}",
        "category_key": "brakes", "assessed_on": "2026-01-01", "odometer_km": 1000, "odometer_flag": "none", "rating": "good",
        "result": "no_fault_found", "mechanic_confirmed": "not_checked", "verification_status": "verified",
        "outcome_date": "2026-02-01", "outcome_mileage_km": 1500,
    }
    base.update(fields)
    return base


def qualifying_records(count=40):
    return [record(index, result="confirmed_failure" if index % 2 else "no_fault_found", outcome_date=(date(2026, 2, 1) + timedelta(days=index)).isoformat()) for index in range(1, count + 1)]


def synthetic_rows(category="brakes", count=160, signal=True, seed=7):
    """SYNTHETIC. With signal, a low rating is followed by a fault; without it, labels are coin flips."""
    generator = random.Random(seed)
    rows = []
    start = date(2024, 1, 1)
    for index in range(count):
        assessed = start + timedelta(days=index * 3)
        fault = generator.random() < 0.5
        if signal:
            rating = generator.choice(["poor", "critical"]) if fault else generator.choice(["excellent", "good"])
        else:
            rating = generator.choice(["excellent", "good", "fair", "poor"])
        outcome = assessed + timedelta(days=generator.randint(5, 40))
        vehicle = 1 + index % 12
        rows.append({
            "outcome_id": index + 1, "assessment_id": index + 1, "vehicle_id": vehicle, "plate_number": f"SYNTH-{vehicle}", "category_key": category,
            "assessed_on": assessed.isoformat(), "odometer_km": 10000 + index * 100, "previous_odometer_km": None, "odometer_flag": "none", "rating": rating,
            "result": "confirmed_failure" if fault else "no_fault_found", "mechanic_confirmed": "confirmed", "verification_status": "verified",
            "outcome_date": outcome.isoformat(), "outcome_mileage_km": 10500 + index * 100,
            "assessment": {
                "assessment_id": index + 1, "vehicle": {"id": vehicle, "age_years": 3}, "assessed_on": assessed.isoformat(),
                "odometer_km": 10000 + index * 100, "components": {category: {"rating": rating}},
            },
        })
    return rows


class IsolatedRegistry(SimpleTestCase):
    """Every test gets its own registry and model folder."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        path = Path(self.folder.name)
        (path / "registry.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
        self.settings_override = override_settings(AI_MAINTENANCE_MODEL_REGISTRY_PATH=path / "registry.json", CATEGORY_MODEL_ROOT=path / "models", AI_SERVICE_API_KEY="test-key")
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.folder.cleanup)


class EligibilityTests(SimpleTestCase):
    def reasons(self, records):
        return {item["outcome_id"]: item["reason"] for item in evaluate_records(records)[1]}

    def test_fewer_than_the_minimum_cannot_qualify(self):
        summary = evaluate_records(qualifying_records(29))[2]
        self.assertEqual(summary["status"], "insufficient")
        self.assertEqual((summary["eligible"], summary["remaining"]), (29, 1))

    def test_enough_diverse_balanced_records_qualify(self):
        summary = evaluate_records(qualifying_records(40))[2]
        self.assertEqual(summary["status"], "sufficient")
        self.assertEqual((summary["faults"], summary["healthy"], summary["vehicles"]), (20, 20, 6))

    def test_unverified_are_excluded(self):
        for status in ("unverified", "rejected"):
            self.assertEqual(self.reasons([record(1, verification_status=status)]), {1: "not_verified"})

    def test_one_vehicle_does_not_qualify(self):
        records = [dict(item, vehicle_id=1) for item in qualifying_records(60)]
        summary = evaluate_records(records)[2]
        self.assertEqual(summary["status"], "insufficient")
        self.assertEqual(summary["vehicles"], 1)
        self.assertTrue(any("vehicles" in text for text in summary["blockers"]))
        self.assertTrue(any("One vehicle" in text for text in summary["blockers"]))

    def test_one_dominant_vehicle_does_not_qualify(self):
        records = qualifying_records(60)
        for item in records[:40]:
            item["vehicle_id"] = 1
        self.assertTrue(any("One vehicle" in text for text in evaluate_records(records)[2]["blockers"]))

    def test_all_faults_or_all_healthy_do_not_qualify(self):
        faults = [dict(item, result="confirmed_failure") for item in qualifying_records(40)]
        healthy = [dict(item, result="no_fault_found") for item in qualifying_records(40)]
        self.assertTrue(any("healthy" in text for text in evaluate_records(faults)[2]["blockers"]))
        self.assertTrue(any("faults" in text for text in evaluate_records(healthy)[2]["blockers"]))

    def test_healthy_outcomes_are_included(self):
        summary = evaluate_records([record(1, result="no_fault_found")])[2]
        self.assertEqual((summary["eligible"], summary["healthy"]), (1, 1))

    def test_labels(self):
        self.assertEqual(record_label({"result": "confirmed_failure"}), "fault")
        self.assertEqual(record_label({"result": "no_fault_found"}), "healthy")
        self.assertEqual(record_label({"result": "successful_repair", "mechanic_confirmed": "confirmed"}), "fault")
        self.assertIsNone(record_label({"result": "successful_repair", "mechanic_confirmed": "not_checked"}))
        self.assertIsNone(record_label({"result": "pending"}))

    def test_invalid_records_are_excluded_with_a_reason(self):
        cases = {
            "no_usable_label": {"result": "pending"},
            "demo_vehicle": {"plate_number": "DEMO-001"},
            "missing_odometer": {"odometer_km": None},
            "odometer_decrease": {"odometer_flag": "decrease"},
            "missing_outcome_date": {"outcome_date": None},
            "category_not_rated": {"rating": "not_assessed"},
            "outcome_before_assessment": {"outcome_date": "2025-12-01"},
            "no_lead_time": {"outcome_date": "2026-01-01"},
            "outside_horizon": {"outcome_date": "2026-06-01"},
            "invalid_mileage": {"outcome_mileage_km": 10},
        }
        for reason, fields in cases.items():
            self.assertEqual(self.reasons([record(1, **fields)]), {1: reason}, reason)

    def test_duplicates_are_excluded(self):
        same = [record(1, assessment_id=9), record(2, assessment_id=9, outcome_date="2026-02-03")]
        self.assertEqual(self.reasons(same), {2: "duplicate_outcome"})

    def test_conflicting_results_on_one_assessment_are_all_excluded(self):
        conflict = [record(1, assessment_id=9), record(2, assessment_id=9, result="confirmed_failure")]
        self.assertEqual(self.reasons(conflict), {1: "conflicting_outcomes", 2: "conflicting_outcomes"})

    def test_one_event_on_two_assessments_counts_once_from_the_nearest(self):
        rows = [record(1, assessment_id=1, vehicle_id=3, assessed_on="2026-01-01"), record(2, assessment_id=2, vehicle_id=3, assessed_on="2026-01-20")]
        eligible, excluded, _ = evaluate_records(rows)
        self.assertEqual([item["outcome_id"] for item in eligible], [2])
        self.assertEqual(excluded, [{"outcome_id": 1, "reason": "duplicate_event"}])

    def test_php_and_python_agree(self):
        script = Path(__file__).resolve().parents[2] / "Back-End" / "tests" / "assessment_training_dump.php"
        laragon = sorted(Path("C:/laragon/bin/php").glob("php-*/php.exe")) if Path("C:/laragon/bin/php").exists() else []
        php = os.environ.get("PHP_BINARY") or shutil.which("php") or (str(laragon[-1]) if laragon else None)
        if not script.exists() or not php:
            self.skipTest("PHP or the Back-End is not available.")
        invalid = [{"result": "pending"}, {"plate_number": "demo-1"}, {"odometer_km": None}, {"odometer_flag": "decrease"}, {"outcome_date": None}, {"rating": "unknown"},
                   {"outcome_date": "2025-12-01"}, {"outcome_date": "2026-01-01"}, {"outcome_date": "2026-06-01"}, {"outcome_mileage_km": 10}, {"verification_status": "unverified"}]
        cases = [[], qualifying_records(29), qualifying_records(40), [dict(item, vehicle_id=1) for item in qualifying_records(60)],
                 [record(1, assessment_id=9), record(2, assessment_id=9, outcome_date="2026-02-03")],
                 [record(1, assessment_id=9), record(2, assessment_id=9, result="confirmed_failure")],
                 [record(1, assessment_id=1, vehicle_id=3), record(2, assessment_id=2, vehicle_id=3, assessed_on="2026-01-20")],
                 [record(1, result="successful_repair", mechanic_confirmed="confirmed", outcome_date="2026-02-02"), record(2, result="successful_repair")]]
        cases += [[record(1, **fields)] for fields in invalid]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cases.json"
            path.write_text(json.dumps(cases), encoding="utf-8")
            output = subprocess.run([php, str(script), str(path)], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        for case, php_result in zip(cases, json.loads(output), strict=True):
            eligible, excluded, summary = evaluate_records(case)
            self.assertEqual(php_result["eligible"], [item["outcome_id"] for item in eligible], case)
            self.assertEqual(php_result["excluded"], excluded, case)
            php_summary = dict(php_result["summary"], excluded_by_reason=php_result["summary"]["excluded_by_reason"] or {})
            self.assertEqual(php_summary, summary, case)


class LeakageTests(SimpleTestCase):
    def test_split_is_chronological_and_purges_outcomes_known_later(self):
        rows = synthetic_rows(count=100)
        rows[10]["outcome_date"] = "2099-01-01"
        kept, held_out, start, purged = chronological_split(rows, 0.3)
        self.assertTrue(all(row["assessed_on"] < start and row["outcome_date"] < start for row in kept))
        self.assertTrue(all(row["assessed_on"] >= start for row in held_out))
        self.assertGreaterEqual(purged, 1)
        self.assertEqual(set(row["outcome_id"] for row in kept) & set(row["outcome_id"] for row in held_out), set())

    def test_same_day_assessments_stay_on_one_side(self):
        rows = [dict(row, assessed_on="2025-01-01") for row in synthetic_rows(count=10)] + synthetic_rows(count=10, seed=9)
        for index, row in enumerate(rows):
            row["outcome_id"] = index
        kept, held_out, _, _ = chronological_split(rows, 0.3)
        self.assertEqual({row["assessed_on"] for row in kept} & {row["assessed_on"] for row in held_out}, set())

    def test_features_cannot_see_the_outcome(self):
        row = synthetic_rows(count=1)[0]
        with_result = assessment_features("brakes", {**row["assessment"], "result": "confirmed_failure", "outcome_date": "2099-01-01", "failure_date": "2099-01-01"})
        self.assertEqual(with_result, assessment_features("brakes", row["assessment"]))

    def test_dates_after_the_assessment_are_treated_as_unknown(self):
        payload = {"assessment_id": 1, "assessed_on": "2026-01-01", "vehicle": {"id": 1, "acquisition_date": "2026-06-01", "previous_maintenance_date": "2026-06-01"}, "components": {"brakes": {"rating": "good"}}}
        values = assessment_features("brakes", payload)
        self.assertIsNone(values["days_owned"])
        self.assertIsNone(values["days_since_maintenance"])

    def test_missing_is_not_zero(self):
        values = assessment_features("brakes", {"assessment_id": 1, "assessed_on": "2026-01-01", "vehicle": {"id": 1}, "components": {"brakes": {}}})
        for name in ("rating_score", "odometer_km", "vehicle_age_years", "measure_front_pad_mm"):
            self.assertIsNone(values[name], name)


class TrainingGateTests(IsolatedRegistry):
    def test_training_refused_when_requirements_are_not_met(self):
        with self.assertRaises(InsufficientTrainingData):
            train_category("brakes", synthetic_rows(count=20))
        registry = json.loads(Path(self.folder.name, "registry.json").read_text(encoding="utf-8"))
        self.assertNotIn("category_models", registry)

    def test_unverified_rows_sent_directly_do_not_count(self):
        rows = synthetic_rows()
        for row in rows:
            row["verification_status"] = "unverified"
        with self.assertRaises(InsufficientTrainingData):
            train_category("brakes", rows)

    def test_mismatched_rows_are_rejected(self):
        rows = synthetic_rows()
        rows[0]["assessment"]["assessed_on"] = "2020-01-01"
        with self.assertRaises(AssessmentValidationError):
            train_category("brakes", rows)
        with self.assertRaises(AssessmentValidationError):
            train_category("wipers", [])

    def test_real_registry_is_untouched_by_this_suite(self):
        before = REAL_REGISTRY.read_bytes()
        train_category("engine", synthetic_rows("engine"))
        self.assertEqual(REAL_REGISTRY.read_bytes(), before)


class EvaluationTests(IsolatedRegistry):
    def test_model_without_signal_is_rejected_with_reasons(self):
        entry = train_category("brakes", synthetic_rows(signal=False))
        self.assertEqual(entry["status"], "evaluated_rejected")
        self.assertFalse(entry["eligible_for_inference"])
        self.assertFalse(entry["report"]["acceptance_criteria_passed"])
        self.assertTrue(entry["report"]["decision_reasons"])
        self.assertFalse(all(item["passed"] for item in entry["report"]["acceptance_criteria"]))

    def test_model_with_signal_passes_but_is_not_automatically_accepted(self):
        entry = train_category("brakes", synthetic_rows())
        self.assertEqual(entry["status"], "evaluated_pending")
        self.assertFalse(entry["eligible_for_inference"])
        self.assertFalse(category_availability()["brakes"]["available"])

    def test_report_has_everything_required(self):
        report = train_category("brakes", synthetic_rows())["report"]
        for field in ("model_name", "model_version", "category", "dataset", "periods", "methodology", "metrics", "false_negative_analysis", "acceptance_criteria", "status", "decision_reasons", "trained_at"):
            self.assertIn(field, report)
        self.assertEqual(report["dataset"]["vehicles"], 12)
        for field in ("precision", "recall", "f1", "accuracy", "confusion_matrix", "false_negative_rate"):
            self.assertIn(field, report["metrics"])
        self.assertLess(report["periods"]["training"][1], report["periods"]["test"][0])

    def test_test_rows_are_later_and_never_trained_on(self):
        report = train_category("brakes", synthetic_rows())["report"]
        self.assertEqual(report["metrics"]["records"], report["periods"]["test_rows"])
        self.assertEqual(report["periods"]["training_rows"] + report["periods"]["test_rows"] + report["periods"]["rows_purged_to_prevent_leakage"], report["dataset"]["rows"])

    def test_safety_categories_require_more_recall(self):
        engine = next(item for item in train_category("engine", synthetic_rows("engine"))["report"]["acceptance_criteria"] if item["name"] == "Recall")
        brakes = next(item for item in train_category("brakes", synthetic_rows())["report"]["acceptance_criteria"] if item["name"] == "Recall")
        self.assertEqual((engine["required"], brakes["required"]), ("at least 0.7", "at least 0.85"))

    def test_small_test_sets_cannot_prove_recall(self):
        self.assertLess(wilson_lower_bound(3, 3), 0.5)
        self.assertLess(wilson_lower_bound(5, 5), 0.6)
        self.assertGreater(wilson_lower_bound(7, 7), 0.6)

    def test_too_few_test_faults_means_rejection_even_if_perfect(self):
        rows = synthetic_rows()
        for row in rows[-48:]:
            row["result"], row["assessment"]["components"]["brakes"]["rating"], row["rating"] = "no_fault_found", "good", "good"
        for row in rows[-3:]:
            row["result"], row["assessment"]["components"]["brakes"]["rating"], row["rating"] = "confirmed_failure", "critical", "critical"
        entry = train_category("brakes", rows)
        self.assertEqual(entry["report"]["metrics"]["faults"], 3)
        self.assertEqual(entry["report"]["metrics"]["recall"], 1.0)
        self.assertEqual(entry["status"], "evaluated_rejected")
        self.assertTrue(any("Faults in the test period" in reason for reason in entry["report"]["decision_reasons"]))


class RegistryAndPredictionTests(IsolatedRegistry):
    def accepted(self, category="brakes"):
        entry = train_category(category, synthetic_rows(category))
        self.assertEqual(entry["status"], "evaluated_pending")
        return promote_model(category, entry["model_version"], 1)

    def payload(self, **brakes):
        return {"assessment_id": 5, "vehicle": {"id": 1, "age_years": 3}, "assessed_on": "2026-06-01", "odometer_km": 30000, "components": {"brakes": brakes}}

    def test_rejected_model_cannot_be_promoted_or_serve(self):
        entry = train_category("brakes", synthetic_rows(signal=False))
        with self.assertRaises(RegistryError):
            promote_model("brakes", entry["model_version"])
        self.assertFalse(predictions_for_assessment(self.payload(rating="good"))["brakes"]["available"])

    def test_categories_without_models_are_unavailable(self):
        result = analyze_assessment(self.payload(rating="good"))
        self.assertEqual(result["predictive_capability"]["status"], "unavailable")
        for component in result["components"]:
            self.assertIsNone(component["ai_model"])
            self.assertFalse(component["prediction"]["available"])
            self.assertEqual(component["predictive_status"], "Insufficient Data")

    def test_accepted_category_predicts_and_is_traceable(self):
        entry = self.accepted()
        result = analyze_assessment(self.payload(rating="critical"))
        brakes = next(item for item in result["components"] if item["component_key"] == "brakes")
        self.assertEqual(brakes["prediction"]["risk_level"], "elevated")
        self.assertEqual(brakes["ai_model"]["version"], entry["model_version"])
        self.assertEqual(brakes["prediction_horizon"], "90 days")
        self.assertEqual(brakes["predictive_status"], "Prediction available")
        self.assertTrue(brakes["prediction"]["explanation"])
        self.assertTrue(brakes["prediction"]["factors"])
        self.assertIsNone(brakes["confidence"])
        low = analyze_assessment(self.payload(rating="excellent"))
        self.assertEqual(next(item for item in low["components"] if item["component_key"] == "brakes")["prediction"]["risk_level"], "not_elevated")

    def test_categories_unlock_independently(self):
        self.accepted("brakes")
        train_category("engine", synthetic_rows("engine", signal=False))
        availability = category_availability()
        self.assertTrue(availability["brakes"]["available"])
        for key in ("engine", "tires_wheels", "battery_electrical", "transmission", "suspension_steering", "cooling", "air_conditioning"):
            self.assertFalse(availability[key]["available"], key)
        result = analyze_assessment(self.payload(rating="good"))
        self.assertEqual(result["predictive_capability"]["categories"], ["brakes"])

    def test_screening_runs_with_and_without_a_model(self):
        without = analyze_assessment(self.payload(rating="good", symptoms=["pedal_to_floor"]))
        self.accepted()
        with_model = analyze_assessment(self.payload(rating="good", symptoms=["pedal_to_floor"]))
        for result in (without, with_model):
            self.assertEqual(result["safety_warnings"][0]["rule_id"], "brakes.pedal_to_floor")

    def test_rejected_run_cannot_replace_an_accepted_model(self):
        entry = self.accepted()
        train_category("brakes", synthetic_rows(signal=False))
        self.assertEqual(category_availability()["brakes"]["active_version"], entry["model_version"])

    def test_passing_run_does_not_replace_the_active_model_until_reviewed(self):
        entry = self.accepted()
        newer = train_category("brakes", synthetic_rows(seed=11))
        self.assertEqual(category_availability()["brakes"]["active_version"], entry["model_version"])
        promote_model("brakes", newer["model_version"])
        self.assertEqual(category_availability()["brakes"]["active_version"], newer["model_version"])

    def test_revoking_returns_the_category_to_unavailable(self):
        self.accepted()
        revoke_model("brakes", "Fleet changed", 1)
        self.assertFalse(category_availability()["brakes"]["available"])
        self.assertFalse(predictions_for_assessment(self.payload(rating="good"))["brakes"]["available"])

    def test_tampered_artifact_is_refused(self):
        entry = self.accepted()
        artifact = Path(self.folder.name, "models", entry["artifact_path"])
        artifact.write_bytes(artifact.read_bytes() + b"x")
        state = category_availability()["brakes"]
        self.assertFalse(state["available"])
        self.assertIn("changed", state["reason"])

    def test_incompatible_versions_are_refused(self):
        self.accepted()
        with patch("ai_api.category_models.FEATURE_SCHEMA_VERSION", FEATURE_SCHEMA_VERSION + "x"):
            self.assertFalse(category_availability()["brakes"]["available"])
        catalog = dict(load_catalog(), version="other")
        with patch("ai_api.category_models.load_catalog", return_value=catalog):
            self.assertIn("questionnaire", category_availability()["brakes"]["reason"])

    def test_missing_inputs_give_unavailable_not_a_guess(self):
        self.accepted()
        self.assertFalse(predictions_for_assessment(self.payload())["brakes"]["available"])
        payload = self.payload(rating="good")
        payload["odometer_km"] = None
        self.assertFalse(predictions_for_assessment(payload)["brakes"]["available"])

    def test_model_failure_does_not_break_the_analysis(self):
        self.accepted()
        with patch("ai_api.category_models._load_artifact", side_effect=OSError("broken")):
            result = analyze_assessment(self.payload(rating="poor", symptoms=["pedal_to_floor"]))
        brakes = next(item for item in result["components"] if item["component_key"] == "brakes")
        self.assertFalse(brakes["prediction"]["available"])
        self.assertEqual(brakes["screening_status"], "critical")

    def test_no_percentage_or_probability_is_reported(self):
        self.accepted()
        text = json.dumps(analyze_assessment(self.payload(rating="poor"))["components"][2]["prediction"])
        self.assertNotIn("probability", text)
        self.assertNotIn("%", text)

    def test_rules_never_appear_as_a_model(self):
        component = analyze_assessment(self.payload(rating="critical", symptoms=["pedal_to_floor"]))["components"][2]
        self.assertEqual(component["screening_status"], "critical")
        self.assertIsNone(component["ai_model"])
        self.assertIsNone(component["prediction"]["risk_level"])


class EndpointTests(IsolatedRegistry):
    def post(self, path, body, key="test-key"):
        return Client().generic("POST", path, json.dumps(body), content_type="application/json", headers={"X-AI-Service-Key": key})

    def test_requires_the_api_key(self):
        self.assertEqual(self.post("/api/training/train/", {}, key="wrong").status_code, 401)

    def test_insufficient_data_returns_409_with_blockers(self):
        response = self.post("/api/training/train/", {"category": "brakes", "rows": []})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["blockers"])

    def test_invalid_category_returns_422(self):
        self.assertEqual(self.post("/api/training/train/", {"category": "wipers", "rows": []}).status_code, 422)

    def test_train_promote_list_and_revoke(self):
        trained = self.post("/api/training/train/", {"category": "brakes", "rows": synthetic_rows(), "requested_by": 1})
        self.assertEqual(trained.status_code, 200)
        version = trained.json()["model"]["model_version"]
        self.assertEqual(self.post("/api/training/promote/", {"category": "brakes", "version": "nope"}).status_code, 409)
        self.assertEqual(self.post("/api/training/promote/", {"category": "brakes", "version": version, "by": 1}).json()["model"]["status"], "evaluated_accepted")
        listed = Client().get("/api/training/models/", headers={"X-AI-Service-Key": "test-key"}).json()["categories"]
        self.assertEqual(len(listed), 8)
        self.assertTrue(next(item for item in listed if item["key"] == "brakes")["available"])
        self.assertEqual(self.post("/api/training/revoke/", {"category": "brakes"}).status_code, 409)
        self.assertEqual(self.post("/api/training/revoke/", {"category": "brakes", "reason": "Test"}).status_code, 200)


class RealStateTests(SimpleTestCase):
    def test_real_registry_has_no_accepted_model_from_synthetic_data(self):
        registry = json.loads(REAL_REGISTRY.read_text(encoding="utf-8"))
        for category, section in (registry.get("category_models") or {}).items():
            for entry in section["versions"]:
                self.assertFalse(entry["model_version"].startswith("synthetic"), category)

    def test_screening_function_is_still_exported(self):
        self.assertEqual(screen_component("engine", {"rating": "fair"})[1], "monitor")
