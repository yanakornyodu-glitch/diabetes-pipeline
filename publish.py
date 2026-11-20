"""Step 3 - Publish: production tables -> Google Sheets (one worksheet per table) for Data Studio."""
import sys

import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe
from sqlalchemy import inspect

import config

# Patient-level table stays in Postgres only (100k rows + free-text clinical notes).
NOT_PUBLISHED = {"patients_clean"}
SHEETS_CELL_LIMIT = 10_000_000


def read_production_tables() -> dict[str, pd.DataFrame]:
    engine = config.get_engine()
    names = sorted(set(inspect(engine).get_table_names(schema=config.PROD_SCHEMA)) - NOT_PUBLISHED)
    tables = {n: pd.read_sql_table(n, engine, schema=config.PROD_SCHEMA) for n in names}
    print(f"[publish] tables to publish: {names}")
    return tables


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Sheets handles neither NaN nor numpy bools well -> plain values."""
    df = df.copy()
    for col in df.select_dtypes(include="bool").columns:
        df[col] = df[col].map({True: "TRUE", False: "FALSE"})
    return df.astype(object).where(df.notna(), "")


def open_spreadsheet() -> gspread.Spreadsheet:
    if not config.SPREADSHEET_ID:
        sys.exit("[publish] SPREADSHEET_ID is empty in .env")
    if not config.GOOGLE_CREDENTIALS_FILE.exists():
        sys.exit(f"[publish] credentials file not found: {config.GOOGLE_CREDENTIALS_FILE}")
    # BackOffHTTPClient retries automatically on APIError 429 (quota exceeded).
    client = gspread.service_account(
        filename=str(config.GOOGLE_CREDENTIALS_FILE), http_client=gspread.BackOffHTTPClient
    )
    return client.open_by_key(config.SPREADSHEET_ID)


def main() -> None:
    tables = read_production_tables()
    total_cells = sum((len(df) + 1) * df.shape[1] for df in tables.values())
    print(f"[publish] total cells {total_cells:,} / {SHEETS_CELL_LIMIT:,}")
    if total_cells > SHEETS_CELL_LIMIT:
        sys.exit("[publish] over the Google Sheets cell limit - aggregate further before publishing")

    sh = open_spreadsheet()
    existing = {ws.title: ws for ws in sh.worksheets()}
    for name, df in tables.items():
        rows, cols = len(df) + 1, max(df.shape[1], 1)
        ws = existing.get(name)
        if ws is None:
            ws = sh.add_worksheet(title=name, rows=rows, cols=cols)
        else:
            ws.resize(rows=rows, cols=cols)  # exact size, so every cell is overwritten below
        set_with_dataframe(ws, prepare(df), include_index=False, resize=False)
        print(f"[publish] uploaded {len(df):,} rows -> worksheet '{name}'")

    print(f"[publish] done: {sh.url}")


if __name__ == "__main__":
    main()
