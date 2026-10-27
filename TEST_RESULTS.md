# Verification record (2026-10-27)

Environment: local Python environment with project requirements installed.

- `PYTHONPATH=. pytest -q`: **5 passed**.
- `python -m equipment_risk.cli reproducibility --scale starter --seed 20261022`: **checksums_match = true** for generated CSV outputs across two runs.
- Starter smoke run: seed `20261022`, 20 machines, 12,000 telemetry readings, 90 days.
- Validation: `valid = true`; 5 expected injected anomaly observations were reported and there were no unexpected anomalies.
- Machine-level synthetic evaluation: 12 labelled failure machines; 12 HIGH-risk predictions; TP=7, FP=5, FN=5; precision=0.5833, recall=0.5833, F1=0.5833.

These metrics are only for this deterministic synthetic test scenario. They do not establish real-world predictive performance. The full one-million-to-three-million-reading run was not executed as part of this smoke verification.
