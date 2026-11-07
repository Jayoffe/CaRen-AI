# Predictive maintenance gap resolution: final report

Date: 2026-11-07. Updated the same day: mechanic accounts were removed at your request, so administrators conduct all assessments. Nothing has been committed. Changes are in the working trees of Back-End, Front-End and automotive_ai_service.

**Predictive maintenance is not operational, and no model is eligible for production.** What now works is condition-based screening, fault-code lookup, the assessment workflow, and the collection of real outcomes needed for a future model.

## 1. Gaps and their status

| Gap | Status | Result |
|---|---|---|
| Dataset audit | Done | 480 files, 22 datasets, none unclassified |
| Assessment endpoint | Done | `POST /api/assessment/analyze/` |
| Stage 1: condition-based screening | Done | 88 explainable rules, plus rating, trend and service-history checks |
| Stage 2: historical data capture | Done | `assessment_outcomes`, linked to assessment and component |
| Stage 3: outcome feedback | Done | Original recommendation preserved; only verified outcomes count; no automatic retraining |
| Predictive model | **Unavailable** | No suitable data; reports `Insufficient Data` |
| Air Conditioning in 3D | Done | Selectable assembly in both coded car models; not on motorcycles |
| Mechanic role | Removed at your request | Administrators conduct assessments; a mechanic is recorded by name on outcomes |
| Vehicle profile | Done | Three new `cars` columns; `current_mileage` reused |
| Five-level ratings | Done | New scale alongside legacy data, which is not converted |
| Processing without a queue | Done | Synchronous, with retry and duplicate prevention |
| Eight categories | Done | Questionnaire, database, rules, endpoint and 3D |
| Monthly reassessment | Partial | Status shown on page load. **No scheduler or notifications exist** |
| Vehicle #9 | Reported, unchanged | See section 12 |

## 2. Datasets discovered

Full detail for each dataset, including size, quality, identifiers, source and licence: `data/reports/pm_dataset_suitability.md`. Machine-readable version: `pm_dataset_inventory.json`. Regenerate with `python -m data_pipeline.pm_audit`.

The earlier audit was incomplete in two ways, both corrected:

- The SCANIA Component X files were not classified at all.
- `main_df_standardized.parquet` was called undocumented, but `metadata.json` and `cycles.json` define its labels. `metadata.json` had been wrongly attributed to the motorcycle dataset.

The older `dataset_manifest.*` reports were not regenerated and still reflect the earlier inventory.

## 3. Suitability and component coverage

| Category | Datasets |
|---|---|
| Predictive maintenance | SCANIA Component X, NASA battery. Real outcomes, but neither maps to a fleet component |
| Fault classification | Diesel air-path set, EngineFaultDB, engine condition tables, diesel OBD |
| Diagnostic knowledge | OBDex, fault flowcharts, Honda parts list |
| Condition assessment | None |
| Supplementary or synthetic | Service records, EV 15-minute, Hyundai readings, CVFFAD, AI4I, repair orders, DTC chat |
| Unsuitable | carOBD, KIT Seat Leon, Navarra motorcycle, experimental energy, LEVIN, generated diagnostic text |

| Component | Predictive | Fault classification | Fault codes | Flowcharts |
|---|---|---|---|---|
| Engine | None | Research only | 4,894 | 35 |
| Battery and Electrical | None (NASA is laboratory cells) | None | 1,076 | 14 |
| Brakes | None | None | 326 | 9 |
| Transmission | None | None | 877 | 16 |
| Suspension and Steering | None | None | 95 | 1 |
| Tires and Wheels | None | None | 19 | 3 |
| Cooling System | None | None | 550 | 8 |
| Air Conditioning | None | None | 189 | 8 |

Powertrain codes with no more specific keyword are counted under Engine. Another 1,507 codes map to no category but are still found by exact lookup. Suspension and tires have little symptom guidance, so most of their symptoms return none; the rules still run.

## 4. Models trained

Both were trained by `python -m data_pipeline.pm_models`, which writes the configuration, source hashes and evaluation next to each model.

**`scania_component_x_repair_window_v1`: predicts repair of anonymized Component X within 48 time steps of a truck's last readout.** Official vehicle-disjoint split, checked at run time. 23,550 training, 5,046 validation and 5,045 test vehicles. Threshold chosen on validation, favouring recall.

| Test set (142 positives of 5,045) | Prevalence baseline | Logistic regression | Gradient boosting (selected) |
|---|---|---|---|
| PR-AUC | 0.0281 | 0.0314 | 0.0443 |
| ROC-AUC | 0.500 | 0.489 | 0.653 |
| Precision | 0 | 0.028 | 0.034 |
| Recall | 0 | 0.993 | 0.937 |
| F1 | 0 | 0.054 | 0.065 |
| False negatives | 142 | 1 | 9 |
| False positives | 0 | 4,901 | 3,815 |

Result: **rejected**. PR-AUC is 1.57 times the base rate, below the 2-times gate set before the run. It catches most repairs only by flagging most trucks. It was deliberately not tuned further, because it could not be deployed even if it improved.

**`diesel_airpath_fault_classifier_v1`: classifies ten documented air-path conditions.** Trained on drive `Cycle_RDE_Eifel`, tested on `Cycle_RDE_Eifel2`.

| Test set (130,942 rows) | Majority baseline | Logistic regression | Gradient boosting (selected) |
|---|---|---|---|
| Accuracy | 0.100 | 0.742 | 0.856 |
| Macro-F1 | 0.018 | 0.736 | 0.855 |
| Faults missed as healthy | 0 | 0.061 | 0.049 |
| False alarms on healthy cycles it had not seen | 1.000 | 0.523 | **0.427** |

Result: **research only**. The 0.855 overstates real performance: both drives follow the same route, and the 43% false-alarm rate on other cycles shows the model does not generalize. Per-class results and confusion matrices are in each `evaluation.json`.

## 5. Models rejected or inactive

| Model | Status | Why not used |
|---|---|---|
| `service_need_v3` | `evaluated_rejected` (unchanged, verified) | Failed its acceptance criteria |
| `scania_component_x_repair_window_v1` | `evaluated_rejected` | Weak signal; anonymized component; truck counters not collected here |
| `diesel_airpath_fault_classifier_v1` | `research_only_not_deployable` | Injected faults; no source; poor generalization; inputs not collected |
| `engine_condition_experiment` | Not served | Undocumented label |
| `cvffad_fault_system_experiment` | Not served | Generated data |
| `diesel_dtc_presence_experiment` | Not served | Label identifies the vehicle |
| `carobd_sensor_anomaly_v1` | Unsupervised experiment | No confirmed outcomes |
| `nasa_battery_cell_rul_1p4ah` | Experiment | Laboratory cells only |
| `synthetic_signal_audit` | Excluded | No learnable signal |

Existing registry entries were verified unchanged. `pm_models.py` hard-codes `eligible_for_inference: False`, and a test enforces it.

## 6. Python endpoints

`POST /api/assessment/analyze/` (also without the trailing slash), protected by `X-AI-Service-Key`. It does not touch the fleet database. `/api/capabilities/` now also describes this endpoint.

Request:

```json
{
  "assessment_id": 7,
  "vehicle": {"id": 2, "make": "...", "age_years": 5},
  "assessed_on": "2026-11-07",
  "odometer_km": 32500,
  "previous_odometer_km": 32000,
  "components": {
    "brakes": {
      "rating": "good",
      "answers": {"pedal_firm": "no"},
      "symptoms": ["pedal_to_floor"],
      "measurements": {"front_pad_mm": 1.5, "rear_pad_mm": "unknown"},
      "fault_codes": ["C0035"],
      "last_maintenance_date": "2026-10-01",
      "notes": "..."
    }
  },
  "previous_assessment": {"assessed_on": "...", "components": {"brakes": {"rating": "good", "screening_status": "monitor"}}},
  "maintenance_history": []
}
```

Response, with all eight categories always returned:

```json
{
  "status": "success",
  "assessment_id": 7,
  "vehicle_id": 2,
  "processing": {"status": "completed", "processed_at": "...", "catalog_version": "...", "knowledge_index": "available", "message": null},
  "predictive_capability": {"status": "unavailable", "label": "Insufficient Data", "reason": "...", "registered_model_status": "evaluated_rejected"},
  "safety_warnings": [{"rule_id": "...", "component_name": "Brakes", "observation": "...", "reason": "...", "recommended_action": "..."}],
  "components": [{
    "component_key": "brakes",
    "component_name": "Brakes",
    "observed_condition": {"rating": "good", "score": 4, "label": "Good"},
    "screening_status": "critical",
    "findings": [],
    "identified_symptoms": [],
    "identified_faults": [],
    "diagnostic_guidance": [],
    "evidence_used": [],
    "explanation": "...",
    "recommended_action": "...",
    "data_sufficiency": {"status": "partial", "missing_questions": []},
    "ai_model": null,
    "knowledge_used": true,
    "predictive_status": "Insufficient Data",
    "confidence": null,
    "prediction_horizon": null
  }]
}
```

Errors: 400 for invalid JSON, 401 for a bad key, 405 for GET, 422 with `errors` for an invalid payload, and 500 with no internal details. If the knowledge index is unavailable, screening still returns with `processing.status = completed_without_knowledge`.

## 7. Database changes

Migrations `013_create_vehicle_assessments.php` and `014_remove_mechanic_role.php`, together equivalent to `database/vehicle_assessments.sql`. **Both applied to `car_rental_db`.** Before/after diffs showed existing vehicles, user role counts and inspection count unchanged.

- `users.role` is back to `admin` and `customer`. 013 added `mechanic`; 014 removed it.
- `cars` gains `acquisition_date`, `usage_frequency` and `previous_maintenance_date`.
- `maintenance_component_types` gains `air-conditioning`.
- New tables: `vehicle_assessments`, `assessment_components`, `assessment_findings`, `assessment_ai_analyses`, `assessment_ai_findings`, `assessment_evidence`, `assessment_outcomes`.

Reused without change: `vehicle_component_inspections` (read as legacy history), `tblvehicle_maintenance` (read as service records), `maintenance_component_types`. `maintenance_data_records` was not reused for outcomes, because it has no link to an assessment or a recommendation.

## 8. Backend files

New: `app/controllers/VehicleAssessmentController.php`, `app/models/VehicleAssessmentModel.php`, `app/migrations/013_create_vehicle_assessments.php`, `app/migrations/014_remove_mechanic_role.php`, `app/config/assessment_catalog.json`, `database/vehicle_assessments.sql`, `database/vehicle-assessment.md`, `tests/vehicle_assessment_rules_test.php`, `tests/vehicle_assessment_http_test.php`, `tests/assessment_screening_dump.php`.

Modified: `app/config/routes.php`, `app/libraries/ComponentMaintenanceRules.php` (methods added, existing ones unchanged), `database/schema.sql`, `.gitignore`.

No file under `scheme/` changed. No `MY_Controller`, no new library, no direct PDO, and no `require_once` in application code. The PHP tests use `require_once`, as the existing tests do.

AI service, new: `ai_api/assessment_service.py`, `ai_api/assessment_catalog.json`, `ai_api/test_assessment.py`, `data_pipeline/pm_audit.py`, `data_pipeline/pm_models.py`, and the two model folders. Modified: `ai_api/views.py`, `ai_api/urls.py`, `data_pipeline/dataset_rules.py`, `data_pipeline/run_all.py`, `models/model_registry.json`.

## 9. Frontend files

New: `Services/API/assessmentAPI.js`, `Pages/Admin/Pages/AssessmentWorkspace.css`, and under `Pages/Admin/Components/maintenance3d/`: `AssessmentOverview.jsx`, `AssessmentWorkspace.jsx`, `assessmentStatus.js`.

Modified: `Pages/Admin/Pages/MaintenancePredictions.jsx`. `App.jsx` is back to its original state, and in `maintenance3d/`: `InspectionStage.jsx`, `VehicleModel.jsx`, `FortunerModel.jsx`, `rigs.js`, `status.js`.

The fleet card list is replaced by the overview table, which keeps search, selection and vehicle photos. `VehicleSelector.jsx` is now unused but was not deleted. The existing three-level inspection view moved to the admin Component records tab.

## 10. 3D components

Added `air-conditioning`: condenser, belt-driven compressor, three refrigerant lines and a cabin HVAC unit, in teal so it reads apart from the grey engine and cooling parts. It is a real, tagged assembly in `VehicleModel.jsx` and `FortunerModel.jsx`, with its own camera view, and maps to the `air_conditioning` category.

Clicking the geometry itself was tested, not only the hotspot, and it selects the component. All views now state: "Coded schematic, not a 3D scan of this vehicle. Internal parts are representative."

No GLB file exists, and none was added. The existing check falls back to the coded model when the file is missing. Vehicle #9 gets the generic SUV model, not the Fortuner one.

## 11. Tests and results

All were run against a disposable copy of the database, which has since been deleted, except where noted.

| Suite | Result |
|---|---|
| Python, all of `ai_api` | 239 tests pass, 3 skipped (they require an accepted model, and none exists) |
| PHP/Python screening agreement, across every rule at its threshold | Pass (part of the above) |
| HTTP workflow, AI service down | 42 of 42 |
| HTTP workflow, AI service up | 89 of 89 |
| Browser (Edge, software WebGL) as admin and customer | 31 of 31 |
| Existing PHP tests, plus the new rule tests | 5 of 5 suites |
| ESLint, assessment code and `App.jsx` | Clean |
| ESLint, whole frontend | 1 error, already present in `vite.config.js`, a file not changed here |
| Production build | Succeeds |

Browser testing found and fixed real defects the API tests could not: invisible headings on the light page, overlapping 3D labels, and an empty later assessment hiding an earlier critical finding.

Not tested:

- A physical GPU; 3D was tested with software rendering.
- These actions through the browser, though each passed over HTTP: evidence upload, marking as reviewed, verifying outcomes, and saving the vehicle profile.
- The screening thresholds against real vehicles.
- Concurrent submissions; the row lock was verified only through sequential duplicate and retry requests.

## 12. Limitations and remaining work

**Needs your decision**

- **Vehicle #9** is unchanged: make `Toyota Fortuner`, model `2024 model`, year `2026`, no mileage. The model field holds a year, it conflicts with the year field, the make includes the model name, and mileage is missing. The interface flags this. Submitting an assessment with an odometer reading will set its mileage, because that is a new reading and nothing is overwritten.
- **Questionnaire.** The project specification you referred to is not in the repository, so I wrote the questions, symptoms and measurements from the eight categories. Please compare them with your specification.
- **Thresholds.** Values such as 1.6 mm tread or 2 mm brake pads are general workshop guidance, not manufacturer limits. A mechanic should review `assessment_catalog.json`.

**Known limitations**

- Ratings are per category, so all four tires share one rating. Individual selection in 3D opens the shared category.
- No scheduler or notification exists. Reassessment status appears only when a page is opened.
- The assessor is whoever is signed in. If a workshop mechanic does the inspection and an administrator enters it, name the mechanic in the notes.
- An administrator can verify an outcome they recorded themselves, because the fleet has one administrator. There is no independent check, though `recorded_by` and `verified_by` both keep an audit trail.
- SCANIA attribution is inferred from file structure; no documentation or licence is in the folder. Many other datasets also lack licence files. Check these before redistributing.
- The catalog exists in two repositories and must be kept identical. A test fails if the copies differ.

**Requires real-world data**

- Predictive maintenance needs the fleet's own records: repeated assessments, confirmed failures and repairs with dates and mileage, per component, across many vehicles. The current fleet of 3 vehicles is far too small. The 30-event minimum per category is a starting point for evaluation, not proof a model would work.
- Calibrated confidence, prediction horizons and remaining useful life all stay unavailable until then.

**Before using it**

Restart the Python service and the backend so the new code loads.
