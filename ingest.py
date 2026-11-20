"""Step 1 - Ingest: local Kaggle CSV -> PostgreSQL schema raw_data (table named after the file)."""
import sys

import pandas as pd
from sqlalchemy import text

import config


def read_csv() -> pd.DataFrame:
    if not config.CSV_PATH.exists():
        sys.exit(
            f"[ingest] CSV not found: {config.CSV_PATH}\n"
            f"         Download {config.CSV_FILE} from Kaggle and put it in the data/ folder."
        )
    df = pd.read_csv(config.CSV_PATH)
    print(f"[ingest] read {len(df):,} rows x {df.shape[1]} columns from {config.CSV_PATH.name}")
    return df


def load_to_postgres(df: pd.DataFrame) -> None:
    engine = config.get_engine()
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {config.RAW_SCHEMA}"))
    # Full refresh so re-runs are idempotent; raw data is stored as-is.
    df.to_sql(
        config.RAW_TABLE,
        engine,
        schema=config.RAW_SCHEMA,
        if_exists="replace",
        index=False,
        chunksize=10_000,
    )
    print(f"[ingest] loaded {len(df):,} rows -> {config.RAW_SCHEMA}.{config.RAW_TABLE}")


def main() -> None:
    load_to_postgres(read_csv())


if __name__ == "__main__":
    main()
