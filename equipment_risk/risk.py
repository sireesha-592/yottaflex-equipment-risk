"""Explainable, deterministic baseline risk scoring.

Only validated telemetry and sensor configuration are used. Failure labels and
maintenance outcomes are deliberately not model inputs.
"""
from __future__ import annotations

import pandas as pd


def assess_risk(
    telemetry: pd.DataFrame,
    sensors: pd.DataFrame,
    machines: pd.DataFrame,
) -> pd.DataFrame:
    columns = ["machine_id", "risk_score", "decision", "factors", "evaluated_at"]
    if telemetry.empty:
        return pd.DataFrame([
            {"machine_id": mid, "risk_score": 0.0, "decision": "LOW",
             "factors": "no_telemetry", "evaluated_at": ""}
            for mid in machines["machine_id"]
        ], columns=columns)

    parsed_ts = pd.to_datetime(telemetry["timestamp"], utc=True, errors="coerce")
    latest = parsed_ts.max()
    evaluated_at = latest.isoformat() if pd.notna(latest) else ""

    # Bad sensor references, impossible values and zero-imputed gaps must not
    # be interpreted as evidence of machine degradation.
    valid = telemetry[telemetry["sensor_id"].isin(set(sensors["sensor_id"]))].copy()
    valid["timestamp"] = pd.to_datetime(valid["timestamp"], utc=True, errors="coerce")
    valid["value"] = pd.to_numeric(valid["value"], errors="coerce")
    if "is_zero_imputed" in valid:
        zero_imputed = valid["is_zero_imputed"].astype(str).str.lower().isin(["true", "1", "yes"])
        valid = valid[~zero_imputed]

    sensor_cols = ["sensor_id", "machine_id", "min_value", "max_value", "nominal_value", "sensor_type"]
    valid = valid.merge(sensors[sensor_cols], on=["sensor_id", "machine_id"], how="inner")
    valid = valid[
        valid["value"].notna()
        & valid["timestamp"].notna()
        & valid["value"].between(valid["min_value"], valid["max_value"])
    ].copy()

    # Readings collected while stopped are not degradation evidence. They are
    # still preserved in source data and handled by validation.
    if "operating_state" in valid:
        valid = valid[~valid["operating_state"].astype(str).str.upper().isin(["SHUTDOWN", "MAINTENANCE"])]

    sensor_rules = {
        # threshold_delta, base points
        "TEMP": (8.0, 24.0),
        "VIB": (2.0, 30.0),
        "CURRENT": (8.0, 18.0),
    }
    scores = []
    for mid in machines["machine_id"]:
        rows = valid[valid["machine_id"] == mid]
        score = 0.0
        factors: list[str] = []
        if rows.empty:
            factors.append("no_valid_operating_telemetry")
        else:
            for _, group in rows.groupby("sensor_id"):
                typ = str(group["sensor_type"].iloc[0]).upper()
                if typ not in sensor_rules:
                    continue
                delta, points = sensor_rules[typ]
                nominal = float(group["nominal_value"].iloc[0])
                threshold = nominal + delta
                peak = float(group["value"].max())
                exceedances = group[group["value"] > threshold]
                if not exceedances.empty:
                    # A single spike contributes less than repeated elevated
                    # readings; cap each sensor's contribution for stability.
                    persistence = min(1.0, len(exceedances) / max(3.0, 0.03 * len(group)))
                    score += points * (0.65 + 0.35 * persistence)
                    factors.append({"TEMP": "temperature_elevation", "VIB": "vibration_elevation",
                                    "CURRENT": "current_elevation"}[typ])
                # Sustained drift: compare early and late readings in time order.
                ordered = group.sort_values("timestamp")
                if len(ordered) >= 8:
                    chunk = max(2, len(ordered) // 4)
                    early = float(ordered["value"].iloc[:chunk].median())
                    late = float(ordered["value"].iloc[-chunk:].median())
                    drift_limit = max(delta * 0.45, abs(nominal) * 0.06)
                    if late - early > drift_limit:
                        score += 10.0
                        factors.append(f"{typ.lower()}_upward_drift")
                # High spread is a supporting signal, never sufficient alone.
                std = float(group["value"].std()) if len(group) > 1 else 0.0
                if pd.notna(std) and std > max(abs(nominal) * 0.20, 1.0):
                    score += 5.0
                    factors.append("high_variability")

        score = round(min(100.0, score), 2)
        decision = "HIGH" if score >= 40 else "MEDIUM" if score >= 20 else "LOW"
        scores.append({
            "machine_id": mid,
            "risk_score": score,
            "decision": decision,
            "factors": ";".join(sorted(set(factors))) or "no_triggered_rules",
            "evaluated_at": evaluated_at,
        })
    return pd.DataFrame(scores, columns=columns)
