"""Step 2 - Transform: raw_data -> Cleaning, Feature Engineering, Joining, Aggregation -> production.

clean(), add_features() and build_tables() are pure functions (DataFrame in, DataFrame out),
so they can be tested without a database.
"""
import numpy as np
import pandas as pd
from sqlalchemy import text

import config

# ------------------------------------------------------------------ constants
RENAME = {
    "race:AfricanAmerican": "race_african_american",
    "race:Asian": "race_asian",
    "race:Caucasian": "race_caucasian",
    "race:Hispanic": "race_hispanic",
    "race:Other": "race_other",
    "hbA1c_level": "hba1c_level",
}
RACE_COLUMNS = {
    "race_african_american": "African American",
    "race_asian": "Asian",
    "race_caucasian": "Caucasian",
    "race_hispanic": "Hispanic",
    "race_other": "Other",
}
NUMERIC_COLUMNS = [
    "year", "age", *RACE_COLUMNS, "hypertension", "heart_disease",
    "bmi", "hba1c_level", "blood_glucose_level", "diabetes",
]
BINARY_COLUMNS = [*RACE_COLUMNS, "hypertension", "heart_disease", "diabetes"]
TEXT_COLUMNS = {  # column -> label used to fill missing values
    "gender": "Unknown",
    "location": "Unknown",
    "smoking_history": "No Info",
    "clinical_notes": "",
}
# Physiologically possible ranges (inclusive); rows outside are dropped.
VALID_RANGES = {
    "age": (0, 120),
    "bmi": (10, 100),
    "hba1c_level": (3, 20),
    "blood_glucose_level": (20, 1000),
}

AGE_BINS = [0, 18, 30, 40, 50, 60, 70, np.inf]
AGE_LABELS = ["0-17", "18-29", "30-39", "40-49", "50-59", "60-69", "70-80"]
# WHO adult BMI classes
BMI_BINS = [0, 18.5, 25, 30, 35, 40, np.inf]
BMI_LABELS = ["Underweight", "Normal", "Overweight", "Obese I", "Obese II", "Obese III (40+)"]
# ADA HbA1c criteria
HBA1C_BINS = [0, 5.7, 6.5, np.inf]
HBA1C_LABELS = ["Normal (<5.7)", "Prediabetes (5.7-6.4)", "Diabetes (6.5+)"]
GLUCOSE_BINS = [0, 100, 126, 201, np.inf]
GLUCOSE_LABELS = ["Normal (<100)", "Prediabetes (100-125)", "High (126-200)", "Very high (>200)"]
COMORBIDITY_LABELS = ["None", "Hypertension only", "Heart disease only", "Both"]

# Lookup table joined onto patients (the dataset is a single file, so this is the join).
SMOKING_MAP = pd.DataFrame(
    [
        ("never", "Never", 1),
        ("former", "Past", 2),
        ("not current", "Past", 3),
        ("ever", "Past", 4),
        ("current", "Current", 5),
        ("No Info", "Unknown", 6),
    ],
    columns=["smoking_history", "smoking_group", "smoking_sort_order"],
)

NOT_A_STATE = "United States"  # national-level label in `location`, not a place on the map
SMALL_SAMPLE_THRESHOLD = 1000
SCATTER_PER_CLASS = 2500
HIGH_RISK_MARKERS = 4


# ------------------------------------------------------------------ cleaning
def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=RENAME)

    for col, fill in TEXT_COLUMNS.items():
        df[col] = df[col].astype("string").str.strip().replace("", pd.NA).fillna(fill)

    # Coerce types: malformed values become NaN, then fill with the column median.
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].fillna(df[col].median())

    # Drop impossible values.
    valid = pd.Series(True, index=df.index)
    for col, (low, high) in VALID_RANGES.items():
        valid &= df[col].between(low, high)
    for col in BINARY_COLUMNS:
        valid &= df[col].isin([0, 1])
    df = df[valid]

    df = df.drop_duplicates().reset_index(drop=True)

    for col in ["year", "blood_glucose_level", *BINARY_COLUMNS]:
        df[col] = df[col].astype(int)
    for col in TEXT_COLUMNS:
        df[col] = df[col].astype(str)
    return df


# --------------------------------------------------------- feature engineering
def _cut(series: pd.Series, bins, labels) -> pd.Series:
    return pd.cut(series, bins=bins, labels=labels, right=False).astype(str)


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.insert(0, "patient_id", np.arange(1, len(df) + 1))

    # One-hot race columns -> one readable column (exactly one is 1 per row).
    df["race"] = df[list(RACE_COLUMNS)].idxmax(axis=1).map(RACE_COLUMNS)

    df["age_group"] = _cut(df["age"], AGE_BINS, AGE_LABELS)
    df["bmi_category"] = _cut(df["bmi"], BMI_BINS, BMI_LABELS)
    df["hba1c_band"] = _cut(df["hba1c_level"], HBA1C_BINS, HBA1C_LABELS)
    df["glucose_band"] = _cut(df["blood_glucose_level"], GLUCOSE_BINS, GLUCOSE_LABELS)

    # Join: smoking history -> smoking group via the lookup table.
    df = df.merge(SMOKING_MAP[["smoking_history", "smoking_group"]], on="smoking_history", how="left")
    df["smoking_group"] = df["smoking_group"].fillna("Unknown")

    df["comorbidity_group"] = np.select(
        [
            (df["hypertension"] == 1) & (df["heart_disease"] == 1),
            df["hypertension"] == 1,
            df["heart_disease"] == 1,
        ],
        ["Both", "Hypertension only", "Heart disease only"],
        default="None",
    )

    markers = [
        df["age"] >= 45,
        df["bmi"] >= 30,
        df["hypertension"] == 1,
        df["heart_disease"] == 1,
        df["hba1c_level"] >= 5.7,
        df["blood_glucose_level"] >= 126,
    ]
    df["risk_marker_count"] = sum(m.astype(int) for m in markers)

    df["is_us_state"] = df["location"] != NOT_A_STATE
    df["diabetes_status"] = np.where(df["diabetes"] == 1, "Diabetic", "Non-diabetic")
    df["note_length"] = df["clinical_notes"].str.len()
    return df


# ----------------------------------------------------------------- aggregation
def rate_table(df: pd.DataFrame, by, order: list | None = None) -> pd.DataFrame:
    """Patients, diabetics and diabetes rate per group, with lab/body averages."""
    by = [by] if isinstance(by, str) else list(by)
    out = (
        df.groupby(by, observed=True)
        .agg(
            patients=("patient_id", "count"),
            diabetics=("diabetes", "sum"),
            avg_age=("age", "mean"),
            avg_bmi=("bmi", "mean"),
            avg_hba1c=("hba1c_level", "mean"),
            avg_glucose=("blood_glucose_level", "mean"),
        )
        .reset_index()
    )
    out["diabetes_rate_pct"] = out["diabetics"] / out["patients"] * 100
    out["share_of_patients_pct"] = out["patients"] / len(df) * 100
    out["share_of_diabetics_pct"] = out["diabetics"] / df["diabetes"].sum() * 100
    if order is not None:
        out["sort_order"] = out[by[0]].map({v: i + 1 for i, v in enumerate(order)})
        out = out.sort_values(["sort_order", *by[1:]]).reset_index(drop=True)
    return out.round(2)


def comorbidity_table(df: pd.DataFrame) -> pd.DataFrame:
    """Long table (filter by `factor` in Data Studio): sub-tables stacked with concat."""
    yes_no = {1: "Yes", 0: "No"}
    parts = []
    for factor, col in [("Hypertension", "hypertension"), ("Heart disease", "heart_disease")]:
        part = rate_table(df.assign(level=df[col].map(yes_no)), "level", ["No", "Yes"])
        parts.append(part.assign(factor=factor))
    part = rate_table(df.rename(columns={"comorbidity_group": "level"}), "level", COMORBIDITY_LABELS)
    parts.append(part.assign(factor="Comorbidity group"))
    out = pd.concat(parts, ignore_index=True)
    return out[["factor", "level", *[c for c in out.columns if c not in ("factor", "level")]]]


def lab_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """HbA1c band x glucose band, all 12 cells (empty cells get 0 patients)."""
    grid = pd.MultiIndex.from_product([HBA1C_LABELS, GLUCOSE_LABELS], names=["hba1c_band", "glucose_band"])
    counts = (
        df.groupby(["hba1c_band", "glucose_band"])
        .agg(patients=("patient_id", "count"), diabetics=("diabetes", "sum"))
        .reindex(grid, fill_value=0)
        .reset_index()
    )
    counts["diabetes_rate_pct"] = (
        counts["diabetics"] / counts["patients"].replace(0, np.nan) * 100
    ).round(2).fillna(0)
    counts["hba1c_sort_order"] = counts["hba1c_band"].map({v: i + 1 for i, v in enumerate(HBA1C_LABELS)})
    counts["glucose_sort_order"] = counts["glucose_band"].map({v: i + 1 for i, v in enumerate(GLUCOSE_LABELS)})
    return counts


def lab_scatter_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Balanced sample (2,500 per class) for the scatter chart - not real prevalence."""
    cols = ["patient_id", "diabetes_status", "hba1c_level", "blood_glucose_level", "bmi", "age"]
    return (
        df.groupby("diabetes", group_keys=False)[cols]
        .apply(lambda g: g.sample(n=min(SCATTER_PER_CLASS, len(g)), random_state=42))
        .sort_values("patient_id")
        .reset_index(drop=True)
    )


def smoking_table(df: pd.DataFrame) -> pd.DataFrame:
    out = rate_table(df, "smoking_history")
    out = out.merge(SMOKING_MAP, on="smoking_history", how="left")
    out = out.rename(columns={"smoking_sort_order": "sort_order"}).sort_values("sort_order")
    return out.reset_index(drop=True)


def state_table(df: pd.DataFrame) -> pd.DataFrame:
    out = rate_table(df[df["is_us_state"]], "location").rename(columns={"location": "state"})
    out = out.sort_values("diabetes_rate_pct", ascending=False).reset_index(drop=True)
    out["rank_by_rate"] = np.arange(1, len(out) + 1)
    out["small_sample"] = out["patients"] < SMALL_SAMPLE_THRESHOLD
    return out


def kpi_summary(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    diabetics = int(df["diabetes"].sum())
    high_risk = df["risk_marker_count"] >= HIGH_RISK_MARKERS
    row = {
        "total_patients": n,
        "diabetics": diabetics,
        "non_diabetics": n - diabetics,
        "diabetes_rate_pct": diabetics / n * 100,
        "avg_age": df["age"].mean(),
        "avg_bmi": df["bmi"].mean(),
        "avg_hba1c": df["hba1c_level"].mean(),
        "avg_glucose": df["blood_glucose_level"].mean(),
        "hypertension_pct": df["hypertension"].mean() * 100,
        "heart_disease_pct": df["heart_disease"].mean() * 100,
        "locations_covered": df.loc[df["is_us_state"], "location"].nunique(),
        "high_risk_patients_pct": high_risk.mean() * 100,
        "high_risk_share_of_diabetics_pct": high_risk[df["diabetes"] == 1].mean() * 100,
    }
    return pd.DataFrame([row]).round(2)


def build_tables(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "patients_clean": df,
        "kpi_summary": kpi_summary(df),
        "diabetes_by_age_group": rate_table(df, "age_group", AGE_LABELS),
        "diabetes_by_bmi_category": rate_table(df, "bmi_category", BMI_LABELS),
        "diabetes_by_comorbidity": comorbidity_table(df),
        "diabetes_by_hba1c_band": rate_table(df, "hba1c_band", HBA1C_LABELS),
        "diabetes_by_glucose_band": rate_table(df, "glucose_band", GLUCOSE_LABELS),
        "diabetes_by_lab_matrix": lab_matrix(df),
        "lab_scatter_sample": lab_scatter_sample(df),
        "diabetes_by_smoking": smoking_table(df),
        "diabetes_by_state": state_table(df),
        "diabetes_by_demographic": rate_table(df, ["age_group", "gender", "race"], AGE_LABELS),
        "diabetes_by_risk_markers": rate_table(df, "risk_marker_count", list(range(7))),
    }


# ------------------------------------------------------------------- database
def read_raw() -> pd.DataFrame:
    df = pd.read_sql_table(config.RAW_TABLE, config.get_engine(), schema=config.RAW_SCHEMA)
    print(f"[transform] read {len(df):,} rows from {config.RAW_SCHEMA}.{config.RAW_TABLE}")
    return df


def write_production(tables: dict[str, pd.DataFrame]) -> None:
    engine = config.get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.PROD_SCHEMA}"))
    for name, frame in tables.items():
        frame.to_sql(name, engine, schema=config.PROD_SCHEMA, if_exists="replace",
                     index=False, chunksize=10_000)
        print(f"[transform] wrote {len(frame):,} rows -> {config.PROD_SCHEMA}.{name}")


def main() -> None:
    raw = read_raw()
    cleaned = clean(raw)
    print(f"[transform] cleaned: {len(raw) - len(cleaned):,} rows removed (duplicates / invalid)")
    write_production(build_tables(add_features(cleaned)))


if __name__ == "__main__":
    main()
