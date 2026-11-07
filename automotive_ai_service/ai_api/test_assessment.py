import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .assessment_service import (
    AssessmentValidationError, analyze_assessment, dtc_category, load_catalog,
    lookup_fault_codes, screen_component, symptom_guidance, validate_payload,
)
from .rag import KnowledgeIndexUnavailable
from data_pipeline.dataset_rules import DATASET_RULES
from data_pipeline.pm_audit import ASSESSMENTS, COVERAGE


CATEGORIES = ["engine", "battery_electrical", "brakes", "transmission", "suspension_steering", "tires_wheels", "cooling", "air_conditioning"]
REGISTRY = Path(__file__).resolve().parents[1] / "models" / "model_registry.json"


def payload(**components):
    return {"assessment_id": 7, "vehicle": {"id": 2}, "assessed_on": "2026-11-07", "odometer_km": 32500, "components": components}


class CatalogTests(SimpleTestCase):
    def test_all_eight_categories_are_defined(self):
        self.assertEqual([category["key"] for category in load_catalog()["categories"]], CATEGORIES)

    def test_catalog_copies_are_identical(self):
        here = Path(__file__).resolve().parent / "assessment_catalog.json"
        backend = Path(__file__).resolve().parents[2] / "Back-End" / "app" / "libraries" / "assessment_catalog.json"
        if not backend.exists():
            self.skipTest("Back-End is not checked out next to this service.")
        self.assertEqual(here.read_bytes(), backend.read_bytes())

    def test_every_rule_refers_to_a_real_field(self):
        catalog = load_catalog()
        for rule in catalog["rules"]:
            category = catalog["_categories"][rule["category"]]
            when = rule["when"]
            if when["kind"] == "symptom":
                self.assertIn(when["key"], {item["key"] for item in category["symptoms"]}, rule["id"])
            elif when["kind"] == "answer":
                self.assertIn(when["question"], {item["key"] for item in category["questions"]}, rule["id"])
            else:
                self.assertIn(when["key"], {item["key"] for item in category["measurements"]}, rule["id"])
            self.assertTrue(rule["observation"] and rule["reason"] and rule["action"], rule["id"])


class ScreeningTests(SimpleTestCase):
    def test_every_rating_level(self):
        expected = {
            "excellent": "no_concerns_recorded", "good": "no_concerns_recorded", "fair": "monitor", "poor": "attention",
            "critical": "critical", "not_applicable": "not_applicable", "unknown": "insufficient_data", "not_assessed": "not_assessed",
        }
        for rating, status in expected.items():
            self.assertEqual(screen_component("engine", {"rating": rating})[1], status, rating)

    def test_missing_rating_is_not_excellent(self):
        result = analyze_assessment(payload())["components"]
        self.assertEqual(len(result), 8)
        for component in result:
            self.assertEqual(component["observed_condition"]["rating"], "not_assessed")
            self.assertIsNone(component["observed_condition"]["score"])
            self.assertEqual(component["screening_status"], "not_assessed")

    def test_no_concerns_never_claims_healthy(self):
        component = analyze_assessment(payload(engine={"rating": "excellent"}))["components"][0]
        self.assertEqual(component["screening_status"], "no_concerns_recorded")
        self.assertIn("not a statement that the component is healthy", component["explanation"])

    def test_critical_brake_observation_is_a_safety_warning_that_explains_itself(self):
        result = analyze_assessment(payload(brakes={"rating": "good", "symptoms": ["pedal_to_floor"]}))
        warning = result["safety_warnings"][0]
        self.assertEqual(warning["rule_id"], "brakes.pedal_to_floor")
        self.assertEqual(warning["component_name"], "Brakes")
        self.assertTrue(warning["observation"] and warning["reason"] and warning["recommended_action"])
        self.assertEqual(result["components"][2]["screening_status"], "critical")

    def test_tire_rules(self):
        findings, status, _ = screen_component("tires_wheels", {"rating": "good", "measurements": {"tread_depth_min_mm": 1.2}})
        self.assertEqual(status, "critical")
        self.assertIn("1.2 mm", findings[0]["observation"])
        findings, status, _ = screen_component("tires_wheels", {"symptoms": ["tire_bulge"]})
        self.assertEqual((findings[0]["rule_id"], status), ("tires.bulge", "critical"))
        self.assertEqual(screen_component("tires_wheels", {"rating": "good", "measurements": {"tread_depth_min_mm": 2.5}})[1], "attention")
        self.assertEqual(screen_component("tires_wheels", {"rating": "good", "measurements": {"tread_depth_min_mm": 6}})[1], "no_concerns_recorded")

    def test_overheating_rules(self):
        self.assertEqual(screen_component("cooling", {"symptoms": ["overheating"]})[1], "critical")
        self.assertEqual(screen_component("cooling", {"rating": "good", "measurements": {"coolant_temperature_c": 125}})[1], "critical")

    def test_unknown_and_na_measurements_do_not_trigger_rules(self):
        findings = screen_component("tires_wheels", {"rating": "good", "measurements": {"tread_depth_min_mm": "unknown", "tire_pressure_min_psi": "not_applicable"}})[0]
        self.assertEqual(findings, [])

    def test_zero_reading_is_a_real_value(self):
        self.assertEqual(screen_component("tires_wheels", {"measurements": {"tread_depth_min_mm": 0}})[1], "critical")

    def test_rating_drop_compares_with_previous_assessment(self):
        findings = screen_component("engine", {"rating": "fair"}, {"rating": "excellent"})[0]
        self.assertIn("trend.rating_drop", [finding["rule_id"] for finding in findings])

    def test_prior_problem_is_not_treated_as_resolved(self):
        findings, status, _ = screen_component("brakes", {"rating": "not_assessed"}, {"rating": "poor"})
        self.assertEqual((findings[0]["rule_id"], status), ("trend.prior_problem_not_rechecked", "attention"))

    def test_finding_under_a_good_rating_is_not_hidden_by_an_empty_assessment(self):
        findings, status, _ = screen_component("brakes", {}, {"rating": "good", "screening_status": "critical"})
        self.assertEqual((findings[0]["rule_id"], status), ("trend.prior_problem_not_rechecked", "attention"))
        self.assertIn("critical finding", findings[0]["observation"])
        self.assertEqual(screen_component("brakes", {"rating": "good"}, {"rating": "good", "screening_status": "critical"})[0], [])

    def test_problem_after_recent_service(self):
        findings = screen_component("engine", {"rating": "poor", "last_maintenance_date": "2026-11-01"}, None, "2026-11-07")[0]
        self.assertIn("history.problem_after_recent_service", [finding["rule_id"] for finding in findings])

    def test_data_sufficiency(self):
        self.assertEqual(screen_component("engine", {"rating": "good"})[2]["status"], "partial")
        answers = {"starts_normally": "yes", "idles_smoothly": "yes", "oil_level_ok": "yes"}
        self.assertEqual(screen_component("engine", {"rating": "good", "answers": answers})[2]["status"], "sufficient")
        self.assertEqual(screen_component("engine", {"rating": "unknown"})[2]["status"], "insufficient")
        self.assertEqual(screen_component("engine", {})[2]["status"], "not_assessed")
        self.assertEqual(screen_component("air_conditioning", {"rating": "not_applicable"})[2]["status"], "not_applicable")

    def test_odometer_decrease_is_flagged_and_zero_is_valid(self):
        data = payload()
        data["odometer_km"], data["previous_odometer_km"] = 100, 500
        self.assertEqual(analyze_assessment(data)["safety_warnings"][0]["rule_id"], "odometer.decrease")
        data["odometer_km"], data["previous_odometer_km"] = 0, None
        self.assertEqual(analyze_assessment(data)["safety_warnings"], [])


def contract_cases():
    """One case per rule at its threshold, plus every rating, trend and data-state branch."""
    catalog = load_catalog()
    cases = []
    for category in catalog["categories"]:
        key = category["key"]
        for rating in catalog["_ratings"]:
            cases.append({"key": key, "component": {"rating": rating}})
            cases.append({"key": key, "component": {"rating": rating}, "previous": {"rating": "poor", "screening_status": "attention"}})
            cases.append({"key": key, "component": {"rating": rating}, "previous": {"rating": "good", "screening_status": "critical"}})
            cases.append({"key": key, "component": {"rating": rating}, "previous": {"rating": "excellent", "screening_status": "no_concerns_recorded"}})
        cases.append({"key": key, "component": {"rating": "poor", "last_maintenance_date": "2026-11-01"}, "assessed_on": "2026-11-07"})
        cases.append({"key": key, "component": {"rating": "poor", "last_maintenance_date": "2026-01-01"}, "assessed_on": "2026-11-07"})
        cases.append({"key": key, "component": {"notes": "Seen"}})
        cases.append({"key": key, "component": {"rating": "good", "answers": {question["key"]: "yes" for question in category["questions"]}}})
        cases.append({"key": key, "component": {"rating": "good", "answers": {question["key"]: "unknown" for question in category["questions"]}}})
        for measurement in category["measurements"]:
            cases.append({"key": key, "component": {"rating": "good", "measurements": {measurement["key"]: "unknown"}}})
    for rule in catalog["rules"]:
        key = rule["category"]
        when = rule["when"]
        if when["kind"] == "symptom":
            cases.append({"key": key, "component": {"rating": "good", "symptoms": [when["key"]]}})
        elif when["kind"] == "answer":
            cases.append({"key": key, "component": {"rating": "good", "answers": {when["question"]: when["equals"]}}})
        else:
            for bound in ("lt", "lte", "gt", "gte"):
                if bound in when:
                    for value in (when[bound] - 0.5, when[bound], when[bound] + 0.5):
                        cases.append({"key": key, "component": {"rating": "good", "measurements": {when["key"]: value}}})
    return cases


class CrossLanguageContractTests(SimpleTestCase):
    def test_php_and_python_screening_agree(self):
        script = Path(__file__).resolve().parents[2] / "Back-End" / "tests" / "assessment_screening_dump.php"
        laragon = sorted(Path("C:/laragon/bin/php").glob("php-*/php.exe")) if Path("C:/laragon/bin/php").exists() else []
        php = os.environ.get("PHP_BINARY") or shutil.which("php") or (str(laragon[-1]) if laragon else None)
        if not script.exists() or not php:
            self.skipTest("PHP or the Back-End is not available.")
        cases = contract_cases()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "cases.json"
            path.write_text(json.dumps(cases), encoding="utf-8")
            output = subprocess.run([php, str(script), str(path)], capture_output=True, text=True, encoding="utf-8", check=True).stdout
        results = json.loads(output)
        self.assertEqual(len(results), len(cases))
        for case, php_result in zip(cases, results):
            findings, status, sufficiency = screen_component(case["key"], case["component"], case.get("previous"), case.get("assessed_on"))
            self.assertEqual(php_result["screening_status"], status, case)
            self.assertEqual(php_result["data_sufficiency"], sufficiency["status"], case)
            self.assertEqual(php_result["missing_questions"], sufficiency["missing_questions"], case)
            self.assertEqual(php_result["findings"], findings, case)


class NoFabricationTests(SimpleTestCase):
    def test_no_percentages_horizons_or_models_are_reported(self):
        result = analyze_assessment(payload(brakes={"rating": "critical"}, cooling={"rating": "good"}))
        self.assertEqual(result["predictive_capability"]["status"], "unavailable")
        for component in result["components"]:
            self.assertIsNone(component["confidence"])
            self.assertIsNone(component["prediction_horizon"])
            self.assertIsNone(component["ai_model"])
            self.assertEqual(component["predictive_status"], "Insufficient Data")
        text = json.dumps(result)
        for word in ("probability", "remaining_useful_life", "failure_date", "risk_score"):
            self.assertNotIn(word, text)

    def test_no_registered_model_is_eligible_for_inference(self):
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(registry["maintenance_model"]["status"], "evaluated_rejected")
        self.assertFalse(registry["maintenance_model"]["eligible_for_inference"])
        for name, entry in registry["experiments"].items():
            self.assertFalse(entry["eligible_for_inference"], name)


class KnowledgeTests(SimpleTestCase):
    def test_known_fault_code_uses_the_exact_reference(self):
        fault = lookup_fault_codes(["p0118"], "cooling")[0]
        self.assertTrue(fault["found"])
        self.assertIn("Coolant", fault["title"])
        self.assertEqual(fault["reference_category"], "cooling")

    def test_unknown_fault_code_is_not_guessed(self):
        fault = lookup_fault_codes(["P9ZZZ"], "engine")[0]
        self.assertFalse(fault["found"])
        self.assertIsNone(fault["title"])

    def test_code_recorded_under_another_category_is_marked(self):
        self.assertTrue(lookup_fault_codes(["P0118"], "engine")[0]["recorded_under_other_category"])

    def test_category_hint_is_empty_when_unclear(self):
        self.assertIsNone(dtc_category("Generic network message"))

    def test_weakly_related_flowcharts_are_not_offered(self):
        self.assertEqual(symptom_guidance("brakes", ["Pedal sinks to the floor"]), [])
        self.assertIn("AC", symptom_guidance("air_conditioning", ["Blows warm air"])[0]["title"])
        self.assertEqual(symptom_guidance("engine", []), [])

    def test_knowledge_outage_keeps_screening(self):
        with patch("ai_api.assessment_service.load_index", side_effect=KnowledgeIndexUnavailable("gone")):
            result = analyze_assessment(payload(brakes={"symptoms": ["pedal_to_floor"], "fault_codes": ["C0035"]}))
        self.assertEqual(result["processing"]["status"], "completed_without_knowledge")
        self.assertEqual(result["safety_warnings"][0]["rule_id"], "brakes.pedal_to_floor")
        self.assertEqual(result["components"][2]["identified_faults"], [])


class DatasetAuditTests(SimpleTestCase):
    def test_every_dataset_rule_has_a_reviewed_assessment(self):
        missing = {rule["dataset_id"] for rule in DATASET_RULES} - set(ASSESSMENTS)
        self.assertEqual(missing, set())

    def test_no_dataset_claims_predictive_capability_for_a_component(self):
        for dataset_id, assessment in ASSESSMENTS.items():
            if assessment["category"] == "predictive_maintenance":
                self.assertEqual(assessment["components"], [], dataset_id)
        for component, coverage in COVERAGE.items():
            self.assertTrue(coverage["predictive"].startswith("None"), component)

    def test_new_candidate_models_are_hard_coded_ineligible(self):
        text = (Path(__file__).resolve().parents[1] / "data_pipeline" / "pm_models.py").read_text(encoding="utf-8")
        self.assertIn('"eligible_for_inference": False', text)
        self.assertNotIn('"eligible_for_inference": True', text)


class ValidationTests(SimpleTestCase):
    def assert_invalid(self, data, fragment):
        with self.assertRaises(AssessmentValidationError) as raised:
            validate_payload(data)
        self.assertTrue(any(fragment in error for error in raised.exception.errors), raised.exception.errors)

    def test_rejections(self):
        self.assert_invalid([], "JSON object")
        self.assert_invalid({**payload(), "assessment_id": "7"}, "assessment_id")
        self.assert_invalid({**payload(), "vehicle": {}}, "vehicle.id")
        self.assert_invalid({**payload(), "assessed_on": "07/11/2026"}, "assessed_on")
        self.assert_invalid({**payload(), "odometer_km": -1}, "odometer_km")
        self.assert_invalid(payload(wipers={}), "unknown category")
        self.assert_invalid(payload(engine={"rating": 9}), "rating")
        self.assert_invalid(payload(engine={"rating": "great"}), "rating")
        self.assert_invalid(payload(engine={"symptoms": ["made_up"]}), "unknown symptom")
        self.assert_invalid(payload(engine={"answers": {"made_up": "yes"}}), "unknown question")
        self.assert_invalid(payload(engine={"answers": {"oil_level_ok": "maybe"}}), "invalid answer")
        self.assert_invalid(payload(brakes={"measurements": {"front_pad_mm": 500}}), "front_pad_mm")
        self.assert_invalid(payload(brakes={"measurements": {"front_pad_mm": True}}), "front_pad_mm")
        self.assert_invalid(payload(engine={"fault_codes": ["XYZ"]}), "invalid code")
        self.assert_invalid(payload(tires_wheels={"fault_codes": ["C0035"]}), "does not accept")
        self.assert_invalid(payload(engine={"last_maintenance_date": "soon"}), "last_maintenance_date")


@override_settings(AI_SERVICE_API_KEY="test-key")
class EndpointTests(SimpleTestCase):
    url = "/api/assessment/analyze/"

    def post(self, body, key="test-key"):
        return Client().generic("POST", self.url, body, content_type="application/json", headers={"X-AI-Service-Key": key})

    def test_valid_submission(self):
        response = self.post(json.dumps(payload(air_conditioning={"rating": "poor", "symptoms": ["not_cooling"]})))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["processing"]["status"], "completed")
        self.assertEqual(len(body["components"]), 8)
        self.assertEqual(body["components"][7]["screening_status"], "attention")

    def test_requires_api_key(self):
        self.assertEqual(self.post(json.dumps(payload()), key="wrong").status_code, 401)

    def test_invalid_json_and_payload(self):
        self.assertEqual(self.post("{not json").status_code, 400)
        response = self.post(json.dumps({"assessment_id": 1}))
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json()["errors"])

    def test_unexpected_error_returns_500_without_details(self):
        with patch("ai_api.views.analyze_assessment", side_effect=RuntimeError("secret detail")):
            response = self.post(json.dumps(payload()))
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.content.decode())

    def test_get_is_rejected(self):
        self.assertEqual(Client().get(self.url, headers={"X-AI-Service-Key": "test-key"}).status_code, 405)
