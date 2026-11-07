# Predictive maintenance dataset suitability

Generated 2026-11-07 by `python -m data_pipeline.pm_audit`. Raw files were only read.

- Files discovered under `data/raw/`: **480** (2.47 GiB)
- Files with no dataset rule: **0**
- Datasets: **22**

## Verdict

**No dataset supports predicting failures for any of the eight categories on this fleet.** Predictive capability stays unavailable, and the assessment endpoint reports `Insufficient Data`.

Stage 1 screening does not depend on any of these datasets. It uses explainable rules, plus the fault-code and flowchart references for diagnostic knowledge.

## Coverage of the eight assessment categories

A component name appearing in a dataset is not counted as capability.

| Component | Predictive maintenance | Fault classification | Diagnostic knowledge | Condition assessment data |
|---|---|---|---|---|
| Engine | None | Research only: injected air-path faults | 4894 fault codes, 35 flowcharts | None |
| Battery and Electrical | None: NASA covers laboratory cells only | None | 1076 fault codes, 14 flowcharts | None |
| Brakes | None | None | 326 fault codes, 9 flowcharts | None |
| Transmission | None | None | 877 fault codes, 16 flowcharts | None |
| Suspension and Steering | None | None | 95 fault codes, 1 flowcharts | None |
| Tires and Wheels | None | None | 19 fault codes, 3 flowcharts | None |
| Cooling System | None | None | 550 fault codes, 8 flowcharts | None |
| Air Conditioning | None | None | 189 fault codes, 8 flowcharts | None |

Powertrain codes with no more specific keyword are counted under Engine. 1507 body, chassis and network codes map to no category; they are still found by exact lookup.

No local dataset has real inspection ratings, so condition assessment rests on the assessor's rating and the screening rules until the fleet collects its own records.

## Datasets by category

### 1. Predictive maintenance

**NASA Li-ion Battery Aging Datasets** (`nasa_battery`)

- Why this category: Real outcomes, but for small laboratory cells under controlled cycling. It does not represent a 12 V starter battery, an alternator or a vehicle environment, so it gives no predictive capability for Battery and Electrical.
- Suitable for: Laboratory cell degradation research.
- Real outcomes: Yes, for laboratory 18650 cells: capacity fade to a documented end-of-life threshold.
- Identifiers and time: Cell ID and cycle number; byte-identical copies must not cross splits
- Size: 48 files (5 exact duplicates), 200.0 MiB. Largest table: no tabular records.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: NASA Ames Prognostics Center of Excellence.
- Licence: No licence statement in the local bundle.

**SCANIA Component X (operational readouts, specifications, time-to-event, labels)** (`scania_component_x`)

- Why this category: The only local dataset with real time-to-event repair outcomes per vehicle. 'Component X' is anonymized, so it cannot be claimed for any of the eight categories, and its inputs are anonymized truck counters this fleet does not collect. Provenance is inferred: no documentation or licence is in the folder.
- Suitable for: A predictive maintenance benchmark only.
- Real outcomes: Yes: time to repair of one component (train_tte) and class labels by time window. Heavy trucks.
- Identifiers and time: vehicle_id and time_step; splits are vehicle-disjoint (verified)
- Size: 10 files (1 exact duplicates), 1,575.4 MiB. Largest table: 1,122,452 rows and 107 columns in `train_operational_readouts.csv`.
- Data quality: 481,376 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No documentation file is present locally. File names, columns and split sizes match the published SCANIA Component X dataset (Lindgren et al., 2024), but that attribution is inferred, not stated by these files.
- Licence: Not documented locally; verify against the original publication before redistribution.

### 2. Fault classification

**Diesel Vehicle OBD-II PID Dataset (ANCEL ELITE 610)** (`diesel_obd_pid_dtc`)

- Why this category: A model would learn which vehicle a row came from. Over three quarters of workbook rows are exact duplicates per the earlier inventory.
- Suitable for: Experiment only (existing, not served).
- Real outcomes: Stored fault codes per vehicle, not repairs. Codes are constant per vehicle, so they identify the vehicle rather than a changing fault state.
- Identifiers and time: No per-row vehicle column; README lists 8 vehicles
- Size: 21 files (10 exact duplicates), 28.3 MiB. Largest table: 118,477 rows and 26 columns in `OBD-Dataset-main/MASTER_TRAIN_X.xlsx`.
- Data quality: 0 missing values and 116,937 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: README documents 8 named vehicles; DTC columns are constant per vehicle, so they identify the vehicle rather than a time-varying fault state.
- Licence: README claims CC BY 4.0; no separate licence file.

**Engine condition sensor tables (raw_data/train/test)** (`engine_condition_tables`)

- Why this category: No source, licence, units or engine grouping. raw_data.csv is the union of train.csv and test.csv. The existing experiment barely beats its baseline.
- Suitable for: Experiment only (existing, not served).
- Real outcomes: Unknown: a binary label whose meaning is undocumented.
- Identifiers and time: None
- Size: 3 files (0 exact duplicates), 2.5 MiB. Largest table: 19,535 rows and 7 columns in `raw_data.csv`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No source documentation. raw_data.csv is the exact union of train.csv and test.csv.
- Licence: Not documented locally.

**EngineFaultDB** (`enginefaultdb`)

- Why this category: Labelled, but any split would mix rows from one run, which leaks, and the classes cannot be named. Not trained.
- Suitable for: Nothing until run identifiers and class names are obtained.
- Real outcomes: Laboratory fault classes on one engine; numeric class meanings are not documented locally.
- Identifiers and time: None: no acquisition-run identifier
- Size: 3 files (0 exact duplicates), 5.1 MiB. Largest table: 55,999 rows and 15 columns in `EngineFaultDB-main/EngineFaultDB-main/EngineFaultDB_Final.csv`.
- Data quality: 0 missing values and 1 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Laboratory engine test bench repository.
- Licence: GPL-3.0 licence file present.

**Diesel engine air-path fault set (main_df_standardized, metadata.json, cycles.json)** (`main_df_standardized`)

- Why this category: Correction to the earlier audit, which called these labels undocumented: metadata.json and cycles.json at the root of data/raw define every fault class and drive cycle. Labels are usable, but they are injected on data with no named source, all faults share one route, and the inputs are standardized signals an inspection does not record.
- Suitable for: Research classification of injected air-path faults.
- Real outcomes: No. Faults are injected (sensor drift, valve clog), not failures that occurred.
- Identifiers and time: drive_cycle only; no vehicle identifier, no timestamp
- Size: 3 files (0 exact duplicates), 98.8 MiB. Largest table: 1,572,243 rows and 21 columns in `main_df_standardized.parquet`.
- Data quality: 1,572,210 missing values and 136 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: metadata.json defines the 18 signals and all 10 fault_type values and cycles.json defines the drive cycles (the signal names and fault values match the parquet columns). Faults are injected, e.g. 'manipulated when MAF fault is active', on a standardized signal set; no source, author or licence is present locally.
- Licence: Not documented locally.

### 3. Diagnostic knowledge

**Automotive fault diagnosis flowcharts (AKTC/oBike et al.)** (`automotive_fault_flowcharts`)

- Why this category: 99 symptom-to-steps entries including Air Conditioning (8) and Cooling (8). Diagnostic instructions are not fault records. Its source is not verified locally, so results are labelled as such. Coverage of suspension (steering only) and tires (3 entries) is thin.
- Suitable for: Symptom guidance, shown as unverified reference.
- Real outcomes: Not applicable: diagnostic steps.
- Identifiers and time: None
- Size: 5 files (0 exact duplicates), 0.3 MiB. Largest table: 99 rows and 4 columns in `automotive_faults_aktc_obike_et_al.json`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Compiled diagnostic flowcharts; source attribution in the file name only.
- Licence: Not documented locally.

**Honda (AHM) motorcycle master parts list, Sep 2025 update 19** (`honda_motorcycle_masterparts`)

- Why this category: A parts list for one motorcycle brand. It says nothing about condition or failure.
- Suitable for: Exact part-number lookup in chat.
- Real outcomes: No.
- Identifiers and time: Part number
- Size: 1 files (0 exact duplicates), 1.8 MiB. Largest table: 61,970 rows and 3 columns in `masterparts.xlsx`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Dealer price-list style export; no licence file.
- Licence: Not documented locally.

**OBDex generic OBD-II DTC and PID reference** (`obdex`)

- Why this category: CC0 reference of generic fault codes with causes and symptoms. It explains a code; it does not establish that a vehicle has that fault or predict anything. Tire coverage is thin because few codes concern tires.
- Suitable for: Exact fault-code lookup. In production use through the knowledge index.
- Real outcomes: Not applicable: reference data.
- Identifiers and time: Fault code
- Size: 45 files (0 exact duplicates), 21.0 MiB. Largest table: 3,705 rows and 0 columns in `OBDex-main/data/generic/P0xxx_enriched.yaml`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: github.com/foerbsnavi/obdex
- Licence: Data CC0 1.0 (LICENSE-DATA); code MIT.

### 4. Condition assessment

None.

### 5. Supplementary or synthetic

**AI4I 2020 Predictive Maintenance (UCI)** (`ai4i_2020`)

- Why this category: Synthetic milling-machine failures. Machine tool wear is not interchangeable with vehicle components.
- Suitable for: Not used.
- Real outcomes: No. Documented as synthetic.
- Identifiers and time: Product ID
- Size: 1 files (0 exact duplicates), 0.5 MiB. Largest table: 10,000 rows and 14 columns in `ai4i+2020+predictive+maintenance+dataset/ai4i2020.csv`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: UCI ML Repository, documented as synthetic industrial data.
- Licence: CC BY 4.0.

**Auto repair orders, parts and invoices (relational, v1)** (`auto_repair_orders`)

- Why this category: 238 orders with reserved example.org emails and generated names. A completed work order does not confirm a component failure.
- Suitable for: A schema reference for outcome tables, nothing else.
- Real outcomes: No. Service completion in a generated sample.
- Identifiers and time: Vehicle and order IDs, on a generated sample
- Size: 7 files (0 exact duplicates), 0.1 MiB. Largest table: 323 rows and 6 columns in `auto-repair-orders-parts-and-invoices-dataset-v1-csv-order_parts.csv`.
- Data quality: 48 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Customer e-mails use the reserved example.org domain and names are generator output; treated as a synthetic relational sample.
- Licence: Not documented locally.

**Chinese Vehicle Fleet Fault Association Dataset (CVFFAD)** (`cvffad`)

- Why this category: Fault events look like failure history, but they are generated. Its README DOI is a placeholder and its licence file is absent. Using it would present fabricated histories as evidence.
- Suitable for: Experiment only (existing, not served).
- Real outcomes: No. Its records carry source='generated'.
- Identifiers and time: vehicle_id and dates, on generated records
- Size: 10 files (4 exact duplicates), 49.7 MiB. Largest table: 29,431 rows and 33 columns in `fault_events.csv`.
- Data quality: 33,208 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Its own records carry source='generated'; the README DOI is a placeholder and the referenced licence file is absent. Root copies are byte-identical to the folder copies.
- Licence: README claims CC BY-NC-SA 4.0; licence file absent.

**DTC diagnostic chat examples (train/validation parquet)** (`dtc_chat_sft`)

- Why this category: Templated instruction-tuning conversations. Answers contain unrelated text and are not used.
- Suitable for: User questions only, as chat routing test cases.
- Real outcomes: No.
- Identifiers and time: None
- Size: 2 files (0 exact duplicates), 0.1 MiB. Largest table: 85 rows and 6 columns in `train-00000-of-00001.parquet`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No source documentation. Assistant answers are templated and contain truncated, unrelated 'technical context' text, so they are not used as reference answers; only user questions are used.
- Licence: Not documented locally.

**EV Predictive Maintenance Dataset (15-minute)** (`ev_predictive_maintenance_15min`)

- Why this category: Named after predictive maintenance and has the right column names, but the earlier audit found no learnable signal (|r| < 0.005 and no autocorrelation), which indicates generated values.
- Suitable for: Nothing beyond the earlier signal audit.
- Real outcomes: No. The failure and RUL columns are independent of the signals.
- Identifiers and time: Timestamps, but columns are statistically independent
- Size: 1 files (0 exact duplicates), 88.6 MiB. Largest table: 175,393 rows and 30 columns in `EV_Predictive_Maintenance_Dataset_15min.csv`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No source documentation. Columns are statistically independent of each other and of the labels (|r| < 0.005, lag-1 autocorrelation 0), which indicates independently generated random values.
- Licence: Not documented locally.

**Hyundai component readings (cars_hyundai.csv)** (`hyundai_component_readings`)

- Why this category: Has brake pad thickness and tire pressure columns, but values are uniform and unrelated to the labels. Naming these components does not give predictive capability.
- Suitable for: Nothing beyond the earlier signal audit.
- Real outcomes: No. The anomaly flag is uncorrelated with the readings.
- Identifiers and time: No stable identifier
- Size: 1 files (0 exact duplicates), 0.1 MiB. Largest table: 1,100 rows and 5 columns in `cars_hyundai.csv`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No source documentation. Values are uniformly distributed and uncorrelated with the anomaly label.
- Licence: Not documented locally.

**Vehicle Maintenance - Service Records (Honda/Toyota, India)** (`vehicle_service_records`)

- Why this category: Recorded workshop data, not synthetic, and the closest thing to maintenance history, but it holds no condition ratings, with no vehicle identity or chronology, and a service visit does not establish a failure. service_need_v1, v2 and v3 were trained on it and all failed their acceptance criteria.
- Suitable for: Service-item statistics only.
- Real outcomes: No. It records service items done at a visit, not failures.
- Identifiers and time: slno is a row number, not a vehicle; no dates
- Size: 1 files (0 exact duplicates), 0.1 MiB. Largest table: 1,139 rows and 24 columns in `Vehicle Maintenance- Service Records.csv`.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Public Kaggle-style export; no local source or licence file. Records are internally consistent with manufacturer service schedules (e.g. 60,000 km major service).
- Licence: Not documented locally; verify before redistribution.

### 6. Unsuitable

**carOBD Toyota Etios OBD-II telemetry** (`carobd_toyota_etios`)

- Why this category: Real telemetry from one 2014 Toyota Etios with no outcomes. Unusual sensor readings are not confirmed faults, so it supports none of the four AI tasks in production.
- Suitable for: Unsupervised sensor anomaly research (existing experiment, not served).
- Real outcomes: No fault or repair labels.
- Identifiers and time: File and session; one vehicle
- Size: 153 files (0 exact duplicates), 85.2 MiB. Largest table: 7,516 rows and 27 columns in `carOBD-master/obdiidata/long2.csv`.
- Data quality: 295,424 missing values and 42,537 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: github.com/eron93br/carOBD
- Licence: README asks for citation; no formal licence.

**Experimental Energy Characterization (NEDC/WLTP)** (`experimental_energy`)

- Why this category: No documented vehicle, units, labels, source or licence, and substantial missing values.
- Suitable for: Not used.
- Real outcomes: No.
- Identifiers and time: None
- Size: 8 files (0 exact duplicates), 1.6 MiB. Largest table: 6,233 rows and 14 columns in `Experimental Energy Characterization/WLTP URBAN 2.csv`.
- Data quality: 270,070 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: No accompanying documentation.
- Licence: Not documented locally.

**KIT Automotive OBD-II Dataset (Seat Leon)** (`kit_obd_seat_leon`)

- Why this category: Real, well documented telemetry from one Seat Leon, without any fault or maintenance outcome.
- Suitable for: Not used.
- Real outcomes: No. Tags describe road and traffic conditions.
- Identifiers and time: File and session; one vehicle
- Size: 102 files (3 exact duplicates), 177.6 MiB. Largest table: 86,654 rows and 11 columns in `Automotive_Diagnostics-main/Automotive_Diagnostics-main/OBD-II-Dataset/2018-03-29_Seat_Leon_KA_RT_Stau.csv`.
- Data quality: 3,653 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: doi:10.35097/1130 (KIT); Automotive_Diagnostics-main is a notebook repository bundling the same CSVs.
- Licence: CC BY 4.0 per descriptive metadata.

**LEVIN open data (documentation only)** (`levin_open_data`)

- Why this category: Documentation and notebooks only. The measurement export is not present locally.
- Suitable for: Not used.
- Real outcomes: Not available.
- Identifiers and time: Not available
- Size: 13 files (0 exact duplicates), 0.6 MiB. Largest table: no tabular records.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Repository without the raw measurement export.
- Licence: Data CC BY-NC-SA per README; code MIT.

**Kawasaki Ninja 400 track telemetry (Circuito de Navarra)** (`navarra_motorcycle_telemetry`)

- Why this category: Race-track telemetry from one prepared motorcycle. It cannot be used to infer road-fleet maintenance. One raw log (LOG00010.MBL) is empty, as its README documents.
- Suitable for: Not used.
- Real outcomes: No.
- Identifiers and time: boot_id; one motorcycle; no calendar dates
- Size: 41 files (5 exact duplicates), 191.5 MiB. Largest table: 821,492 rows and 6 columns in `updates.csv`.
- Data quality: 360 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 1 (navarra_telemetry-raw/navarra_telemetry/raw/LOG00010.MBL).
- Source: Depositor README (CC BY 4.0, Electronics 15(12):2604).
- Licence: CC BY 4.0 per README.

**Generated vehicle diagnostic samples (VehicleDiagnosticSample.txt)** (`vehicle_diagnostic_sample`)

- Why this category: Self-described generated diagnostics with random measurements. Indexing it would present fabricated results as reference facts.
- Suitable for: Not used.
- Real outcomes: No.
- Identifiers and time: None
- Size: 1 files (0 exact duplicates), 1.1 MiB. Largest table: no tabular records.
- Data quality: 0 missing values and 0 duplicate rows across unique tables. Unreadable or empty files: 0.
- Source: Self-described generator output with random measurements; fault codes are not consistent with the stated systems.
- Licence: Not documented locally.

## Model registry

| Model | Task | Status | Eligible for production | Results | Why |
|---|---|---|---|---|---|
| service_need_v3 (service_need_v3_3a435be143) | service_need_at_visit | evaluated_rejected | False | Balanced accuracy 0.7429, macro-F1 0.5364 | Service-need model did not meet the acceptance criteria; see evaluation.json. |
| engine_condition_experiment | engine_condition_experiment | evaluated_not_served | False | See data/reports/experiments_evaluation.json | The meaning of engine_condition (0/1) is undocumented, there is no source or licence, and rows cannot be grouped by engine or vehicle, so held-out scores may overstate performance on new vehicles. The fleet database also holds none of these live sensor readings. |
| synthetic_signal_audit | synthetic_signal_audit | excluded_no_learnable_signal | False | See data/reports/experiments_evaluation.json | Models do not beat the prevalence baseline (ROC-AUC near 0.5, R-squared near 0): the labels are independent of every input, consistent with randomly generated data. Training on them would produce a model that outputs noise, so both datasets are excluded from every served model. |
| cvffad_fault_system_experiment | fault_system (7 systems) from operating readings and vehicle context | evaluated_not_served | False | See data/reports/experiments_evaluation.json | Every CVFFAD record is marked source='generated' and the dataset covers Chinese commercial trucks/vans with a placeholder DOI. Patterns learned from generated events must not be presented as real fleet risk. |
| diesel_dtc_presence_experiment | any active DTC (excluding P0000) from 11 OBD-II PIDs | evaluated_not_served | False | See data/reports/experiments_evaluation.json | DTCs are constant per vehicle, so labels identify the vehicle. With only one fault-free signature the vehicle-disjoint evaluation cannot support a fault detector; the fleet also has no live PID stream. |
| carobd_sensor_anomaly_v1 |  | evaluated_unsupervised_experiment | False | See data/reports/experiments_evaluation.json | Evaluated experiment kept from its own pipeline; not connected to fleet inference. |
| nasa_battery_cell_rul_1p4ah |  | evaluated_experiment | False | See data/reports/experiments_evaluation.json | Evaluated experiment kept from its own pipeline; not connected to fleet inference. |
| diesel_airpath_fault_classifier_v1 | Classify ten documented air-path conditions (healthy, MAF drift, MAP drift, EGR valve clog) from one row of signals | research_only_not_deployable | False | Macro-F1 0.8545, faults missed as healthy 0.0489, false alarms on unseen healthy cycles 0.4274 | Faults are injected, on data with no documented source, so scores do not establish real-world performance. Inputs are standardized with an unknown reference and include EGR and turbo signals an inspection does not record. All faulted runs share one route, so the holdout does not test generalization to other routes. |
| scania_component_x_repair_window_v1 | Repair of anonymized Component X within 48 time steps of a truck's last readout | evaluated_rejected | False | Test PR-AUC 0.0443 (prevalence 0.0281), ROC-AUC 0.6531, precision 0.0337, recall 0.9366, F1 0.065, false negatives 9 of 142 | 'Component X' is anonymized, so it cannot be mapped to any of the eight assessment categories. Inputs are anonymized heavy-truck histogram counters that this fleet does not collect. Trained on heavy trucks; not validated on the passenger cars, SUVs, vans and motorcycles in this fleet. |

No model is eligible for inference. `service_need_v3` remains `evaluated_rejected`; it was not renamed or changed.
