
# Equipment Failure Risk Analytics — Synthetic Industrial Data

A reproducible, locally runnable reference implementation for generating industrial equipment data, validating it, estimating equipment risk, and evaluating decisions against separately stored synthetic ground truth.

> **Candidate note:** Review, run, test, and understand every part before submission. This project uses synthetic data only. Do not include secrets or credentials in the repository.

## Features

- Deterministic ID conventions and fixed-seed synthetic data generation.
- Plant → production line → machine → sensor hierarchy.
- Timestamped telemetry over a configurable period, with operating states, drift, sensor faults, and pre-failure patterns.
- Maintenance work orders, failure events, parts, technicians, and replacement-part bridge records.
- Separate `ground_truth.csv` for injected anomalies / expected labels; it is not used as a risk-model input.
- Explicit validation for primary keys, foreign keys, enum values, date ordering, duplicate telemetry, unit/range anomalies, and zero-filled gaps.
- Rule-based risk scoring with explainable factors and measurable precision/recall/F1 metrics.
- Risk scoring ignores invalid sensor references, out-of-range values, zero-imputed gaps, and shutdown/maintenance readings; it considers elevated temperature/vibration/current, upward drift, and variability.
- CSV, JSON, and SQLite/SQL output.
- Repeatability checks using stable row counts and SHA-256 hashes.
- Small starter mode for fast iteration and a configurable larger dataset.

## Requirements

- Python 3.10+
- Install dependencies:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start (recommended first)

Generate a starter dataset and run validation/evaluation:

```bash
python -m equipment_risk.cli generate --scale starter --seed 20261022 --out data/starter
python -m equipment_risk.cli validate --input data/starter
python -m equipment_risk.cli evaluate --input data/starter
```

## Larger run

The full target in the challenge brief is 3 plants, 12 lines, 100 machines, 500 sensors, 90 days, and 1–3 million telemetry readings. Generate one million readings with:

```bash
python -m equipment_risk.cli generate --scale full --readings 1000000 --days 90 --seed 20261022 --out data/full
```

For a larger run, try `--readings 3000000`. Memory and runtime depend on the computer. Start with `starter` and increase scale after validating the pipeline.

## Output layout

- `plants.csv`, `production_lines.csv`, `machines.csv`, `sensors.csv`
- `operating_shifts.csv`, `technicians.csv`, `parts.csv`
- `telemetry_events.csv`, `maintenance_work_orders.csv`, `failure_events.csv`
- `work_order_parts.csv` (many-to-many bridge)
- `ground_truth.csv` (separate evaluation labels; do not use as model input)
- `risk_assessments.csv` (risk score, decision, explainable factors)
- `data_dictionary.md`, `source_manifest.json`, `validation_summary.json`
- `checksums.json`, `run_metadata.json`, `equipment_risk.sqlite`

## Design assumptions

- The risk score is a transparent rule-based baseline, not a validated industrial safety model.
- Synthetic failures are generated from documented, seeded rules and linked to pre-failure telemetry patterns.
- Some negative scenarios are deliberately written to `ground_truth.csv` and represented as issue records rather than silently corrupting unrelated entities.
- `zero_gap` edge cases are explicitly flagged in ground truth and are validated as anomalies.
- “Failure before symptom” is generated only as a labelled exception scenario; it is not treated as a valid normal sequence.
- Risk labels are based on known synthetic failure windows. Ground truth is kept separate from input features.
- A public demo or hosted service is not required by the brief.

## Validation and evaluation

```bash
python -m equipment_risk.cli validate --input data/starter
python -m equipment_risk.cli evaluate --input data/starter
python -m equipment_risk.cli reproducibility --scale starter --seed 20261022
```

The evaluation command reports confusion-matrix counts, precision, recall, F1, and risk-decision counts against the separately stored synthetic ground truth. These results measure this synthetic scenario only; they are not evidence of real-world predictive performance.

## Suggested review checklist

1. Run the starter commands from a clean environment.
2. Inspect the generated CSV files and SQLite tables.
3. Read `equipment_risk/generator.py`, `risk.py`, and `validation.py`.
4. Run `pytest`.
5. Regenerate twice with the same seed and compare checksums.
6. Record any observed limitations honestly in your submission notes.


## Risk scoring logic and current baseline result

The risk engine is an explainable heuristic, not a trained predictive model. For each machine it scores configured temperature, vibration, and current exceedances; upward drift in time-ordered sensor readings; and high variability as a supporting signal. Sensor contributions and total score are capped, and decisions are `LOW` (<20), `MEDIUM` (20–39.99), or `HIGH` (>=40). Unknown sensors, impossible ranges, zero-imputed records, and readings during shutdown/maintenance are excluded from risk evidence and are handled separately by validation.

A local starter evaluation with seed `20261022`, 20 machines, 12,000 telemetry rows, and 90 days produced precision **0.5833**, recall **0.5833**, and F1 **0.5833** at the machine level (7 true positives, 5 false positives, 5 false negatives). These are synthetic-data results only, not real-world performance. Thresholds should be selected based on operational cost of missed failures versus unnecessary inspections; do not claim the heuristic is production-validated.

