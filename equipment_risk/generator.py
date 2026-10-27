from __future__ import annotations
import hashlib, json, os, sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd

PLANTS = 3
LINES = 12
MACHINES = 100
SENSORS = 500
SENSOR_TYPES = [
    ("TEMP", "C", 0.0, 120.0, 70.0),
    ("VIB", "mm/s", 0.0, 25.0, 4.0),
    ("PRESS", "bar", 0.0, 20.0, 8.0),
    ("CURRENT", "A", 0.0, 100.0, 25.0),
    ("RPM", "rpm", 0.0, 6000.0, 1800.0),
]
STATES = ["RUNNING", "IDLE", "SHUTDOWN", "MAINTENANCE"]

def _id(prefix, n, width=3):
    return f"{prefix}-{n:0{width}d}"

def generate_dataset(out_dir, scale="starter", seed=20261022, readings=None, days=90):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(int(seed))
    if scale == "starter":
        n_plants, n_lines, n_machines, n_sensors = 3, 6, 20, 60
        n_readings = int(readings or 12000)
        n_failures = 12
    elif scale == "full":
        n_plants, n_lines, n_machines, n_sensors = PLANTS, LINES, MACHINES, SENSORS
        n_readings = int(readings or 1_000_000)
        n_failures = 150
    else:
        raise ValueError("scale must be 'starter' or 'full'")

    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    plants = pd.DataFrame([{
        "plant_id": _id("PLT", i), "name": f"Plant {i}", "region": ["NORTH","SOUTH","WEST"][((i-1)%3)],
        "created_at": start.isoformat(), "lifecycle_state": "ACTIVE"
    } for i in range(1, n_plants+1)])

    # Distribute lines across plants; IDs embed parent IDs.
    lines = []
    for i in range(1, n_lines+1):
        plant = plants.iloc[(i-1) % n_plants]["plant_id"]
        lines.append({"line_id": f"LINE-{plant}-{((i-1)//n_plants)+1:03d}", "plant_id": plant,
                      "name": f"Production Line {i}", "lifecycle_state": "ACTIVE",
                      "effective_from": start.isoformat(), "effective_to": ""})
    lines = pd.DataFrame(lines)

    machines = []
    for i in range(1, n_machines+1):
        line = lines.iloc[(i-1) % len(lines)]["line_id"]
        machines.append({"machine_id": f"MCH-{line}-{((i-1)//len(lines))+1:03d}",
                         "line_id": line, "machine_type": ["PUMP","MOTOR","COMPRESSOR","CONVEYOR"][i%4],
                         "commissioned_at": (start - timedelta(days=int(rng.integers(180, 1800)))).isoformat(),
                         "lifecycle_state": "ACTIVE"})
    machines = pd.DataFrame(machines)

    sensors = []
    for i in range(n_sensors):
        m = machines.iloc[i % len(machines)]["machine_id"]
        typ, unit, lo, hi, normal = SENSOR_TYPES[i % len(SENSOR_TYPES)]
        seq = i // len(machines) + 1
        sensors.append({"sensor_id": f"SNS-{m}-{typ}-{seq:02d}", "machine_id": m,
                        "sensor_type": typ, "unit": unit, "min_value": lo, "max_value": hi,
                        "nominal_value": normal, "installed_at": start.isoformat(),
                        "lifecycle_state": "ACTIVE"})
    sensors = pd.DataFrame(sensors)

    techs = pd.DataFrame([{"technician_id": _id("TECH", i), "name": f"Technician {i}",
                           "skill_group": ["MECHANICAL","ELECTRICAL","INSTRUMENTATION"][i%3],
                           "active": True} for i in range(1, 11)])
    parts = pd.DataFrame([{"part_id": _id("PART", i), "part_name": ["Bearing","Seal","Sensor","Motor coupling"][i%4],
                           "part_category": ["MECHANICAL","MECHANICAL","INSTRUMENTATION","MECHANICAL"][i%4],
                           "unit_cost": float([45, 18, 32, 75][i%4]), "active": True} for i in range(1, 21)])

    shifts = []
    for d in range(days):
        day = start + timedelta(days=d)
        for s, (name, begin, end) in enumerate([("DAY",6,14),("EVENING",14,22),("NIGHT",22,6)], 1):
            shifts.append({"shift_id": f"SHF-{day:%Y%m%d}-{s}", "shift_name": name,
                           "start_at": (day+timedelta(hours=begin)).isoformat(),
                           "end_at": (day+timedelta(days=(1 if end <= begin else 0), hours=end)).isoformat()})
    shifts = pd.DataFrame(shifts)

    # Deterministic failure machines and times, with a pre-failure signal window.
    failure_machines = rng.choice(machines["machine_id"].to_numpy(), size=min(n_failures, n_machines), replace=False)
    failure_specs = []
    for ix, mid in enumerate(failure_machines):
        day = int(rng.integers(12, max(13, days-2)))
        failure_time = start + timedelta(days=day, hours=int(rng.integers(1, 23)))
        failure_specs.append({"failure_id": _id("FAIL", ix+1, 6), "machine_id": mid,
                              "failure_at": failure_time, "failure_mode": ["BEARING_WEAR","OVERHEAT","VIBRATION"][ix%3],
                              "severity": ["MEDIUM","HIGH","CRITICAL"][ix%3]})
    fail_by_machine = {x["machine_id"]: x for x in failure_specs}

    # Generate readings with stable sensor mapping and timestamped records.
    sensor_ids = sensors["sensor_id"].to_numpy()
    sensor_rows = sensors.set_index("sensor_id").to_dict("index")
    machine_ids = machines["machine_id"].to_numpy()
    timestamps = rng.integers(0, days*24*60, size=n_readings)
    chosen_sensors = rng.integers(0, len(sensor_ids), size=n_readings)
    telemetry = []
    ground_truth = []
    # Keep normal records, then inject deliberate edge cases into final rows.
    for i in range(n_readings):
        sid = sensor_ids[chosen_sensors[i]]
        sr = sensor_rows[sid]
        mid = sr["machine_id"]
        minute = int(timestamps[i])
        ts = start + timedelta(minutes=minute)
        state = rng.choice(STATES, p=[0.72,0.12,0.10,0.06])
        typ = sr["sensor_type"]
        nominal = float(sr["nominal_value"])
        sigma = {"TEMP":4.0,"VIB":1.2,"PRESS":1.0,"CURRENT":4.0,"RPM":120.0}[typ]

        lo = float(sr["min_value"])
        hi = float(sr["max_value"])

        value = float(np.clip(rng.normal(nominal, sigma), lo, hi))
        fs = fail_by_machine.get(mid)
        if fs and timedelta(0) <= fs["failure_at"] - ts <= timedelta(days=3):
            # Drift increases toward the labelled failure; make a portion visibly pre-failure.
            proximity = 1.0 - (fs["failure_at"] - ts).total_seconds()/(3*86400)
            if typ == "TEMP": value += 18.0 * proximity
            elif typ == "VIB": value += 7.0 * proximity
            elif typ == "CURRENT": value += 12.0 * proximity
        # Operating-state adjustment.
        if state in ("SHUTDOWN","MAINTENANCE"):
            value = nominal * 0.02 + float(rng.normal(0, sigma*0.05))
        value = float(np.clip(value, lo, hi))
        value = round(value, 3)
        telemetry.append({"telemetry_id": f"TEL-{sid}-{ts:%Y%m%dT%H%M%S}-{i+1:08d}",
                          "sensor_id": sid, "machine_id": mid, "timestamp": ts.isoformat(),
                          "operating_state": state, "value": value, "unit": sr["unit"],
                          "is_zero_imputed": False, "source": "synthetic_generator"})
    telemetry = pd.DataFrame(telemetry)

    # Failures and linked maintenance records are generated from failure specs.
    failures, work_orders, bridge = [], [], []
    for ix, fs in enumerate(failure_specs, 1):
        ft = fs["failure_at"]
        failures.append({"failure_id": fs["failure_id"], "machine_id": fs["machine_id"],
                         "failure_at": ft.isoformat(), "failure_mode": fs["failure_mode"],
                         "severity": fs["severity"], "downtime_minutes": int(rng.integers(30, 480)),
                         "ground_truth_label": 1})
        wo_start = ft + timedelta(minutes=int(rng.integers(5, 90)))
        wo_end = wo_start + timedelta(hours=int(rng.integers(1, 12)))
        wo_id = f"WO-2026-{ix:06d}"
        work_orders.append({"work_order_id": wo_id, "machine_id": fs["machine_id"],
                            "technician_id": techs.iloc[(ix-1)%len(techs)]["technician_id"],
                            "failure_id": fs["failure_id"], "opened_at": wo_start.isoformat(),
                            "started_at": wo_start.isoformat(), "ended_at": wo_end.isoformat(),
                            "status": "COMPLETED", "downtime_minutes": failures[-1]["downtime_minutes"]})
        bridge.append({"work_order_id": wo_id, "part_id": parts.iloc[(ix-1)%len(parts)]["part_id"],
                       "quantity": 1, "replacement_at": wo_end.isoformat()})

    # Explicit, labelled anomaly rows. Keep these isolated and identifiable.
    if len(telemetry):
        idx = len(telemetry)-1
        row = telemetry.iloc[idx].copy()
        row["sensor_id"] = "SNS-UNKNOWN-999"
        row["telemetry_id"] = f"TEL-ANOM-UNKNOWN-{idx+1:08d}"
        telemetry.iloc[idx] = row
        ground_truth.append({"case_id":"ANOM-001","record_type":"telemetry","record_id":row["telemetry_id"],
                             "issue_type":"unknown_sensor","expected_label":"INVALID_FOREIGN_KEY",
                             "description":"Telemetry references a sensor absent from the sensor master."})
        idx2 = max(0, len(telemetry)-2)
        row2 = telemetry.iloc[idx2].copy()
        row2["value"] = 999999.0
        row2["telemetry_id"] = f"TEL-ANOM-RANGE-{idx2+1:08d}"
        telemetry.iloc[idx2] = row2
        ground_truth.append({"case_id":"ANOM-002","record_type":"telemetry","record_id":row2["telemetry_id"],
                             "issue_type":"impossible_range","expected_label":"OUT_OF_RANGE",
                             "description":"Telemetry value deliberately exceeds sensor's configured maximum."})
        idx3 = max(0, len(telemetry)-3)
        row3 = telemetry.iloc[idx3].copy()
        row3["is_zero_imputed"] = True
        row3["value"] = 0.0
        row3["telemetry_id"] = f"TEL-ANOM-ZEROGAP-{idx3+1:08d}"
        telemetry.iloc[idx3] = row3
        ground_truth.append({"case_id":"ANOM-003","record_type":"telemetry","record_id":row3["telemetry_id"],
                             "issue_type":"zero_hidden_time_gap","expected_label":"IMPUTED_GAP",
                             "description":"Zero-imputed reading flags a hidden telemetry gap."})
    # Deliberately invalid maintenance end-before-start case is isolated and labelled.
    if work_orders:
        wo = dict(work_orders[0])
        wo["work_order_id"] = "WO-ANOM-2026-000001"
        wo["ended_at"] = (datetime.fromisoformat(wo["started_at"]) - timedelta(minutes=1)).isoformat()
        work_orders.append(wo)
        ground_truth.append({"case_id":"ANOM-004","record_type":"maintenance_work_order",
                             "record_id":wo["work_order_id"],"issue_type":"maintenance_end_before_start",
                             "expected_label":"INVALID_DATE_ORDER",
                             "description":"Maintenance end timestamp intentionally precedes start timestamp."})

    tables = {
        "plants": plants, "production_lines": lines, "machines": machines, "sensors": sensors,
        "operating_shifts": shifts, "technicians": techs, "parts": parts,
        "telemetry_events": telemetry, "failure_events": pd.DataFrame(failures),
        "maintenance_work_orders": pd.DataFrame(work_orders), "work_order_parts": pd.DataFrame(bridge),
        "ground_truth": pd.DataFrame(ground_truth)
    }
    # Derive risk from telemetry only; ground truth and failure table are not inputs.
    from .risk import assess_risk
    tables["risk_assessments"] = assess_risk(tables["telemetry_events"], tables["sensors"], tables["machines"])

    for name, df in tables.items():
        df.to_csv(out / f"{name}.csv", index=False)
        df.to_json(out / f"{name}.json", orient="records", indent=2, date_format="iso")
    write_sqlite(tables, out / "equipment_risk.sqlite")
    write_dictionary(out / "data_dictionary.md")
    manifest = {"generator":"equipment_risk.generator", "seed":int(seed), "scale":scale,
                "days":int(days), "telemetry_readings":int(n_readings), "synthetic_only":True,
                "generated_at_utc":datetime.now(timezone.utc).isoformat(),
                "tables":{k:{"rows":int(len(v)),"columns":list(v.columns)} for k,v in tables.items()}}
    (out/"run_metadata.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out/"source_manifest.json").write_text(json.dumps({
        "data_provenance":"All records are generated locally by this project; no external dataset used.",
        "external_sources":[], "license_note":"Synthetic records; project source is provided for candidate review."
    }, indent=2), encoding="utf-8")
    return tables

def write_sqlite(tables, path):
    conn = sqlite3.connect(path)

    try:
        for name, df in tables.items():
            df.to_sql(
                name,
                conn,
                if_exists="replace",
                index=False
            )

        relationship_rows = [
            {
                "parent_table": "plants",
                "parent_key": "plant_id",
                "child_table": "production_lines",
                "child_key": "plant_id"
            },
            {
                "parent_table": "lines",
                "parent_key": "line_id",
                "child_table": "machines",
                "child_key": "line_id"
            },
            {
                "parent_table": "machines",
                "parent_key": "machine_id",
                "child_table": "sensors",
                "child_key": "machine_id"
            },
            {
                "parent_table": "sensors",
                "parent_key": "sensor_id",
                "child_table": "telemetry_events",
                "child_key": "sensor_id"
            }
        ]

        pd.DataFrame(relationship_rows).to_sql(
            "relationship_dictionary",
            conn,
            if_exists="replace",
            index=False
        )

        conn.commit()

    finally:
        conn.close()

def write_dictionary(path):
    path.write_text("""# Data Dictionary\n\n| Entity/table | Key | Main fields | Validation |\n|---|---|---|---|\n| plants | plant_id (PK) | name, region, created_at, lifecycle_state | unique ID; ACTIVE/INACTIVE |\n| production_lines | line_id (PK) | plant_id (FK), name, lifecycle_state, effective dates | plant must exist; effective_to >= effective_from |\n| machines | machine_id (PK) | line_id (FK), machine_type, commissioned_at, lifecycle_state | line must exist; lifecycle enum |\n| sensors | sensor_id (PK) | machine_id (FK), type, unit, min/max/nominal values | machine exists; min <= nominal <= max |\n| telemetry_events | telemetry_id (PK) | sensor_id, machine_id, timestamp, state, value, unit, zero-imputation flag | sensor/machine references; enum; unit/range; duplicate timestamp checks |\n| operating_shifts | shift_id (PK) | shift_name, start_at, end_at | end after start; DAY/EVENING/NIGHT |\n| maintenance_work_orders | work_order_id (PK) | machine_id, technician_id, failure_id, opened/started/ended, status | parent references; dates ordered; lifecycle enum |\n| failure_events | failure_id (PK) | machine_id, failure_at, failure_mode, severity, downtime | machine exists; downtime >= 0 |\n| parts | part_id (PK) | name, category, unit_cost, active | unique ID; cost >= 0 |\n| technicians | technician_id (PK) | name, skill_group, active | unique ID; skill group enum |\n| work_order_parts | (work_order_id, part_id) bridge | quantity, replacement_at | both FKs exist; quantity > 0 |\n| ground_truth | case_id (PK) | record type/id, issue_type, expected_label | kept separate from risk input features |\n| risk_assessments | machine_id (PK) | risk_score, decision, factors, evaluated_at | score 0–100; LOW/MEDIUM/HIGH |\n\n## Relationships and cardinality\n- Plant 1:N ProductionLine; ProductionLine 1:N Machine; Machine 1:N Sensor; Sensor 1:N TelemetryEvent.\n- Machine 1:N FailureEvent and Machine 1:N MaintenanceWorkOrder.\n- Technician 1:N MaintenanceWorkOrder (optional for unassigned orders; generated records are assigned).\n- MaintenanceWorkOrder N:M Part through `work_order_parts`.\n- FailureEvent 1:N MaintenanceWorkOrder is allowed by the model; `failure_id` may be empty for preventive maintenance.\n- OperatingShift is a time dimension; a telemetry event's operating state is stored directly. Shift interval joins can be derived by timestamp.\n\n## Notes\nIDs are immutable and zero-padded where applicable. Synthetic anomaly records are labelled in `ground_truth.csv`; ground truth is not used by risk scoring. All dates are ISO-8601 UTC strings. `risk_assessments` is a transparent rule-based baseline, not a production-grade predictive maintenance model.\n""", encoding="utf-8")
