from pathlib import Path
import json
import pandas as pd


# These are the intentional anomalies created by the generator.
# Each anomaly is expected to trigger a specific validation check.
EXPECTED_ANOMALIES = {
    "invalid_foreign_key": 1,
    "unknown_sensor": 1,
    "unit_mismatch": 0,
    "out_of_range": 1,
    "zero_imputed": 1,
    "maintenance_end_before_start": 1,
}


def validate_dataset(input_dir):
    p = Path(input_dir)

    def read(name):
        f = p / f"{name}.csv"
        return pd.read_csv(f) if f.exists() else pd.DataFrame()

    names = [
        "plants",
        "production_lines",
        "machines",
        "sensors",
        "telemetry_events",
        "operating_shifts",
        "maintenance_work_orders",
        "failure_events",
        "parts",
        "technicians",
        "work_order_parts",
    ]

    tables = {name: read(name) for name in names}

    observed = {
        "invalid_foreign_key": 0,
        "unknown_sensor": 0,
        "unit_mismatch": 0,
        "out_of_range": 0,
        "zero_imputed": 0,
        "maintenance_end_before_start": 0,
    }

    issues = []

    # ---------------------------------------------------------
    # Primary key validation
    # ---------------------------------------------------------

    def check_pk(table, key):
        df = tables[table]

        if key in df.columns:
            duplicates = int(df[key].duplicated().sum())

            if duplicates:
                issues.append(
                    f"{table}: {duplicates} duplicate primary key(s) in {key}"
                )

    primary_keys = [
        ("plants", "plant_id"),
        ("production_lines", "line_id"),
        ("machines", "machine_id"),
        ("sensors", "sensor_id"),
        ("telemetry_events", "telemetry_id"),
        ("operating_shifts", "shift_id"),
        ("maintenance_work_orders", "work_order_id"),
        ("failure_events", "failure_id"),
        ("parts", "part_id"),
        ("technicians", "technician_id"),
    ]

    for table, key in primary_keys:
        check_pk(table, key)

    # ---------------------------------------------------------
    # Foreign key validation
    # ---------------------------------------------------------

    def check_fk(child, field, parent, parent_key):
        child_df = tables[child]
        parent_df = tables[parent]

        if field not in child_df.columns:
            return

        if parent_key not in parent_df.columns:
            return

        valid_values = set(
            parent_df[parent_key]
                .dropna()
                .astype(str)
        )

        values = child_df[field].dropna().astype(str)

        invalid = values[
            ~values.isin(valid_values)
        ]

        if len(invalid):
            observed["invalid_foreign_key"] += len(invalid)

            issues.append(
                f"{child}.{field}: "
                f"{len(invalid)} invalid foreign-key value(s)"
            )

    foreign_keys = [
        ("production_lines", "plant_id", "plants", "plant_id"),
        ("machines", "line_id", "production_lines", "line_id"),
        ("sensors", "machine_id", "machines", "machine_id"),
        ("telemetry_events", "sensor_id", "sensors", "sensor_id"),
        ("telemetry_events", "machine_id", "machines", "machine_id"),
        ("failure_events", "machine_id", "machines", "machine_id"),
        (
            "maintenance_work_orders",
            "machine_id",
            "machines",
            "machine_id",
        ),
        (
            "maintenance_work_orders",
            "technician_id",
            "technicians",
            "technician_id",
        ),
        (
            "work_order_parts",
            "work_order_id",
            "maintenance_work_orders",
            "work_order_id",
        ),
        ("work_order_parts", "part_id", "parts", "part_id"),
    ]

    for args in foreign_keys:
        check_fk(*args)

    # ---------------------------------------------------------
    # Telemetry validation
    # ---------------------------------------------------------

    telemetry = tables["telemetry_events"]
    sensors = tables["sensors"]

    if not telemetry.empty and not sensors.empty:

        sensor_columns = [
            "sensor_id",
            "unit",
            "min_value",
            "max_value",
        ]

        available_columns = [
            col for col in sensor_columns
            if col in sensors.columns
        ]

        if "sensor_id" in available_columns:

            merged = telemetry.merge(
                sensors[available_columns],
                on="sensor_id",
                how="left",
                suffixes=("_event", "_sensor"),
            )

            # Unknown sensors
            if "min_value" in merged.columns:
                unknown = merged["min_value"].isna()
            else:
                unknown = merged["sensor_id"].isna()

            unknown_count = int(unknown.sum())

            if unknown_count:
                observed["unknown_sensor"] += unknown_count

                issues.append(
                    f"telemetry_events: "
                    f"{unknown_count} unknown sensor(s)"
                )

            # Unit mismatch
            if (
                "unit_event" in merged.columns
                and "unit_sensor" in merged.columns
            ):
                known = merged[
                    merged["unit_sensor"].notna()
                ]

                mismatch = (
                    known["unit_event"]
                    != known["unit_sensor"]
                )

                mismatch_count = int(mismatch.sum())

                if mismatch_count:
                    observed["unit_mismatch"] += mismatch_count

                    issues.append(
                        f"telemetry_events: "
                        f"{mismatch_count} unit mismatch(es)"
                    )

            # Out-of-range readings
            if (
                "min_value" in merged.columns
                and "max_value" in merged.columns
                and "value" in merged.columns
            ):
                known = merged[
                    merged["min_value"].notna()
                    & merged["max_value"].notna()
                ]

                values = pd.to_numeric(
                    known["value"],
                    errors="coerce",
                )

                out_of_range = (
                    (values < known["min_value"])
                    | (values > known["max_value"])
                )

                out_count = int(out_of_range.sum())

                if out_count:
                    observed["out_of_range"] += out_count

                    issues.append(
                        f"telemetry_events: "
                        f"{out_count} out-of-range reading(s)"
                    )

            # Zero-imputed gap flags
            if "is_zero_imputed" in merged.columns:

                zero_imputed = (
                    merged["is_zero_imputed"]
                    .astype(str)
                    .str.lower()
                    .eq("true")
                )

                zero_count = int(zero_imputed.sum())

                if zero_count:
                    observed["zero_imputed"] += zero_count

                    issues.append(
                        f"telemetry_events: "
                        f"{zero_count} zero-imputed gap flag(s)"
                    )

    # ---------------------------------------------------------
    # Maintenance work order validation
    # ---------------------------------------------------------

    work_orders = tables["maintenance_work_orders"]

    required_dates = {
        "started_at",
        "ended_at",
    }

    if (
        not work_orders.empty
        and required_dates.issubset(work_orders.columns)
    ):

        start = pd.to_datetime(
            work_orders["started_at"],
            utc=True,
            errors="coerce",
        )

        end = pd.to_datetime(
            work_orders["ended_at"],
            utc=True,
            errors="coerce",
        )

        bad = end < start
        bad_count = int(bad.sum())

        if bad_count:
            observed[
                "maintenance_end_before_start"
            ] += bad_count

            issues.append(
                f"maintenance_work_orders: "
                f"{bad_count} end-before-start record(s)"
            )

    # ---------------------------------------------------------
    # Expected vs unexpected anomalies
    # ---------------------------------------------------------

    expected_anomalies = []
    unexpected_anomalies = []

    for anomaly_type, expected_count in EXPECTED_ANOMALIES.items():

        actual_count = observed[anomaly_type]

        if actual_count == expected_count:

            if expected_count > 0:
                expected_anomalies.append({
                    "type": anomaly_type,
                    "count": actual_count,
                    "status": "EXPECTED",
                })

        else:

            unexpected_anomalies.append({
                "type": anomaly_type,
                "expected_count": expected_count,
                "actual_count": actual_count,
                "status": "UNEXPECTED",
            })

    # Issues that are expected are still visible in "issues".
    # Dataset is valid when no unexpected anomaly count is found.
    valid = len(unexpected_anomalies) == 0

    summary = {
        "valid": valid,
        "issue_count": len(issues),
        "issues": issues,
        "expected_anomalies": expected_anomalies,
        "unexpected_anomalies": unexpected_anomalies,
        "tables_checked": names,
        "row_counts": {
            name: int(len(df))
            for name, df in tables.items()
        },
    }

    (p / "validation_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    return summary