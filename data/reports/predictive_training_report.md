# Fleet predictive maintenance pipeline: report

Date: 2026-11-07. Nothing has been committed.

**The pipeline works, but no real model exists and predictions are not live for any category.** The real fleet has 3 vehicles and no assessments or outcomes, so every category shows `Insufficient Data`. All the models below were trained on synthetic data in a disposable database that has since been deleted.

## 1. Existing features reused

Assessment and outcome tables, the verification workflow, condition-based screening, the assessment endpoint, the model registry file and its accepted-status rules, `AiServiceClient`, the LavaLust query builder, migrations and response methods, and the overview page. `assessment_ai_findings` already had columns for model name, version and horizon.

## 2. New features

- Per-category data sufficiency, with a stated reason for every excluded record.
- Training data export built from the same payload the prediction endpoint receives.
- Per-category training, evaluation and registry entries, with an administrator review step.
- Predictions per category, stored with their model version.
- Model withdrawal.
- A dashboard for sufficiency, dataset review, training, evaluation and the registry.
- Validation on outcomes: duplicates, dates before the assessment, and mileage below the assessment odometer.
- Healthy results can now be recorded where nothing was flagged, so a future model does not only see problems.

## 3. Files created

Back-End: `app/migrations/015_add_predictive_training.php`, `tests/assessment_training_dump.php`.

AI service: `ai_api/category_models.py`, `ai_api/test_category_models.py`.

Front-End: `src/Pages/Admin/Components/maintenance3d/ModelTrainingPanel.jsx`.

## 4. Files modified

Back-End: `app/controllers/VehicleAssessmentController.php`, `app/models/VehicleAssessmentModel.php`, `app/libraries/ComponentMaintenanceRules.php`, `app/libraries/assessment_catalog.json`, `app/config/routes.php`, `database/schema.sql`, `database/vehicle_assessments.sql`, `database/vehicle-assessment.md`, `tests/vehicle_assessment_http_test.php`.

AI service: `ai_api/assessment_service.py`, `ai_api/assessment_catalog.json`, `ai_api/views.py`, `ai_api/urls.py`, `automotive_ai/settings.py`, `.gitignore`.

Front-End: `src/Services/API/assessmentAPI.js`, `AssessmentOverview.jsx`, `AssessmentWorkspace.jsx`, `AssessmentWorkspace.css`.

No file under `scheme/` changed. Existing project controllers and models outside the assessment feature did not change.

## 5. Database changes

Migration 015, applied to `car_rental_db`. Existing data was verified unchanged.

- `assessment_outcomes.outcome_date`
- `assessment_ai_findings.risk_level`, `model_score`, `prediction`
- New table `model_training_runs`

## 6. Pipeline architecture

1. **LavaLust** reads the database, judges eligibility, and exports eligible records.
2. **Python** re-checks every record independently and refuses to train if the category does not qualify. A test confirms PHP and Python reach the same decisions.
3. **Python** trains and evaluates, then writes `evaluation.json`, the model and a registry entry.
4. **An administrator** reviews a passed model and accepts it, or does not.
5. **The assessment endpoint** uses a model only if it is accepted, its files are unchanged, and it was built for the current questionnaire and feature version.

## 7. Evaluation method

- **Target:** a verified fault within 90 days of an assessment.
- **Split:** the latest 30% of assessments form the test set. Training uses only assessments whose outcomes were already known before the test period began. Assessments on the same date stay on one side.
- **Selection:** the threshold and algorithm are chosen on an earlier validation period, favouring recall.
- **Algorithms:** logistic regression always; a small random forest competes only from 100 training records.
- **Features:** only what was known on the assessment date. The same function builds features for training and prediction, and it never receives outcome fields.

## 8. Acceptance criteria

Set in `training_policy` before any training ran.

| Criterion | General | Safety-critical (brakes, tires, steering, cooling) |
|---|---|---|
| Faults in the test period | At least 5 | At least 5 |
| Healthy results in the test period | At least 5 | At least 5 |
| Recall | At least 0.70 | At least 0.85 |
| Recall, 95% lower bound | At least 0.50 | At least 0.60 |
| Precision | At least 0.50 | At least 0.50 |
| F1-score | At least 0.60 | At least 0.60 |
| PR-AUC | At least 1.25 times the fault rate | Same |
| Recall on vehicles unseen in training, when there are at least 3 such faults | Same as recall | Same as recall |

Accuracy is reported but is not a criterion.

## 9. Categories with sufficient data

**None.**

## 10. Categories that remain ineligible

**All eight.** Each has 0 of 30 eligible outcomes, 0 vehicles, 0 faults and 0 healthy results.

**Under the current policy, no category can ever qualify with this fleet.** It requires 5 vehicles, you have 3, and two of those have `DEMO-` plates, which are excluded. That leaves one countable vehicle.

## 11. Models trained

**No real models.** The real registry and model folder are untouched, which was verified by hash. On synthetic pipeline tests only:

| Category | Data | Recall | Precision | Result |
|---|---|---|---|---|
| Brakes | 200 records with a planted pattern | 1.00 | 1.00 | Passed, then accepted by the test |
| Engine | 200 records with coin-flip labels | 0.36 | 0.60 | Rejected |

These show the pipeline tells the two apart. They say nothing about real-world accuracy: the brakes pattern was planted, so a perfect score is expected.

## 12. Models accepted or rejected

No real model has been accepted or rejected. `service_need_v3`, Scania and the diesel air-path model remain ineligible.

## 13. Prediction endpoint status

Connected and working, and returning prediction unavailable for all eight categories because no accepted model exists. Screening runs either way.

## 14. Tests and results

| Suite | Result |
|---|---|
| Python, all of `ai_api` | 288 pass, 3 skipped (they need an accepted legacy model) |
| HTTP, AI service down | 42 of 42 |
| HTTP, AI service up | 95 of 95 |
| HTTP, synthetic training end to end | 55 of 55 |
| Browser (Edge, software WebGL) | 48 of 48 |
| Existing and new PHP suites | 5 of 5 |
| ESLint, whole frontend | 1 error, already present in `vite.config.js`, a file not changed here |
| Production build | Succeeds |

All 14 required checks are covered by these suites.

Not tested: real fleet data, real model accuracy, and a physical GPU. Evidence upload was tested over HTTP only.

## 15. Remaining limitations

- **Decisions for you:** whether to change the 5-vehicle minimum, and whether the `DEMO-` vehicles are real.
- **Rule reading:** "do not create additional backend helper methods" was read as no framework-level helpers or helper files. The feature's logic is in methods on the assessment controller and model and on the existing rules library. Doing it with no new methods at all is not possible.
- **Fabricated records cannot be detected automatically.** Protection rests on human verification and plausibility checks.
- **Admins can verify outcomes they recorded,** so there is no independent check on the labels.
- **The label is simplified.** A healthy check soon after an assessment counts as healthy for the whole 90-day horizon. Failures after 90 days are excluded.
- **Unseen vehicles:** when every test vehicle also appears in training, the report says so, and performance on new vehicles stays unknown.
- **Scores are uncalibrated,** so only a risk level is shown, never a percentage.
- **Training runs in one request,** so progress shows only that it is running. Running it for one category at a time is enforced, and a dead run clears after 10 minutes.
- **Registry and model files must stay together.** `trained_models/category_models/` is ignored by git, so deploying elsewhere needs those files copied, or models report unavailable.
- **The older final report** still mentions `app/config/assessment_catalog.json` on line 182.
