"""Pipeline settings, read from .env (or environment variables)."""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Source file downloaded manually from Kaggle; the raw table is named after it.
CSV_FILE = os.getenv("CSV_FILE", "diabetes_dataset_with_notes.csv")
CSV_PATH = DATA_DIR / CSV_FILE
RAW_TABLE = Path(CSV_FILE).stem

RAW_SCHEMA = "raw_data"
PROD_SCHEMA = "production"

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "pipeline")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "pipeline")
POSTGRES_DB = os.getenv("POSTGRES_DB", "diabetes")

GOOGLE_CREDENTIALS_FILE = BASE_DIR / os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "").strip()


def get_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
    )
    return create_engine(url)
