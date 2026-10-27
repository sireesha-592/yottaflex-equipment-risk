import tempfile
from pathlib import Path
import pandas as pd
from equipment_risk.generator import generate_dataset
from equipment_risk.validation import validate_dataset
from equipment_risk.evaluation import evaluate

def test_starter_generates_expected_files_and_relationships():
    with tempfile.TemporaryDirectory() as tmp:
        tables=generate_dataset(tmp,scale="starter",seed=20261022,readings=1000,days=30)
        assert len(tables["plants"]) == 3
        assert len(tables["machines"]) == 20
        assert len(tables["telemetry_events"]) == 1000
        assert (Path(tmp)/"ground_truth.csv").exists()
        assert (Path(tmp)/"equipment_risk.sqlite").exists()
        assert len(tables["risk_assessments"]) == len(tables["machines"])

def test_validation_detects_injected_edge_cases():
    with tempfile.TemporaryDirectory() as tmp:
        generate_dataset(tmp,scale="starter",seed=20261022,readings=1000,days=30)
        result=validate_dataset(tmp)
        assert result["issue_count"] > 0
        assert any("unknown sensor" in x for x in result["issues"])
        assert any("end-before-start" in x for x in result["issues"])

def test_evaluation_returns_metrics():
    with tempfile.TemporaryDirectory() as tmp:
        generate_dataset(tmp,scale="starter",seed=20261022,readings=1000,days=30)
        result=evaluate(tmp)
        assert "precision" in result and "recall" in result and "f1" in result

def test_risk_scores_are_explainable_and_bounded():
    from equipment_risk.risk import assess_risk
    machines = pd.DataFrame({"machine_id": ["MCH-1", "MCH-2"]})
    sensors = pd.DataFrame({
        "sensor_id": ["SNS-1-TEMP-01"], "machine_id": ["MCH-1"],
        "min_value": [0.0], "max_value": [120.0], "nominal_value": [70.0],
        "sensor_type": ["TEMP"],
    })
    telemetry = pd.DataFrame({
        "sensor_id": ["SNS-1-TEMP-01"] * 4,
        "machine_id": ["MCH-1"] * 4,
        "timestamp": ["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z",
                      "2026-01-01T02:00:00Z", "2026-01-01T03:00:00Z"],
        "value": [70.0, 82.0, 88.0, 91.0],
        "operating_state": ["RUNNING"] * 4,
        "is_zero_imputed": [False] * 4,
    })
    result = assess_risk(telemetry, sensors, machines).set_index("machine_id")
    assert 0 <= result.loc["MCH-1", "risk_score"] <= 100
    assert result.loc["MCH-1", "decision"] in {"LOW", "MEDIUM", "HIGH"}
    assert "temperature_elevation" in result.loc["MCH-1", "factors"]
    assert result.loc["MCH-2", "factors"] == "no_valid_operating_telemetry"


def test_risk_model_does_not_use_failure_or_ground_truth_columns():
    from equipment_risk.risk import assess_risk
    machines = pd.DataFrame({"machine_id": ["MCH-1"]})
    sensors = pd.DataFrame({
        "sensor_id": ["SNS-1-TEMP-01"], "machine_id": ["MCH-1"],
        "min_value": [0.0], "max_value": [120.0], "nominal_value": [70.0],
        "sensor_type": ["TEMP"],
    })
    base = pd.DataFrame({"sensor_id": ["SNS-1-TEMP-01"], "machine_id": ["MCH-1"],
                         "timestamp": ["2026-01-01T00:00:00Z"], "value": [70.0],
                         "operating_state": ["RUNNING"], "is_zero_imputed": [False]})
    a = assess_risk(base, sensors, machines)
    enriched = base.assign(ground_truth_label=1, failure_at="2026-01-01T00:00:00Z")
    b = assess_risk(enriched, sensors, machines)
    assert a[["risk_score", "decision", "factors"]].equals(b[["risk_score", "decision", "factors"]])
