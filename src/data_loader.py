"""Reading raw source files and the processed analytical tables."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import config


class DataNotFoundError(FileNotFoundError):
    """Raised with a user-friendly message when data files are missing."""


def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename source headers to the project's canonical names.

    Raises ValueError if a required column is missing (a blocking error).
    """
    mapping = {}
    for col in df.columns:
        key = re.sub(r"[\s_]+", "", str(col).lower())
        if key in config.COLUMN_ALIASES:
            mapping[col] = config.COLUMN_ALIASES[key]
    out = df.rename(columns=mapping)
    missing = [c for c in config.REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"Required column(s) missing from source data: {missing}. Found: {list(df.columns)}")
    return out


def read_raw_workbook(path: Path) -> pd.DataFrame:
    """Read every sheet of the official workbook and stack them.

    Adds SourceSheet and SourceRow (1-based Excel row number) for provenance.
    Reading ~1M rows from .xlsx is slow (several minutes) - this is expected.
    """
    path = Path(path)
    if not path.exists():
        raise DataNotFoundError(f"Raw workbook not found: {path}")
    sheets = pd.read_excel(path, sheet_name=None, dtype=object, engine="openpyxl")
    frames = []
    for name, sheet in sheets.items():
        sheet = standardize_columns(sheet).copy()
        sheet["SourceSheet"] = str(name)
        sheet["SourceRow"] = range(2, len(sheet) + 2)  # header is row 1
        frames.append(sheet[config.REQUIRED_COLUMNS + ["SourceSheet", "SourceRow"]])
    if not frames:
        raise ValueError("Workbook contains no sheets.")
    return pd.concat(frames, ignore_index=True)


def read_raw_csvs(paths: list[Path]) -> pd.DataFrame:
    """Alternative to the workbook: one CSV per sheet (e.g. exported manually)."""
    frames = []
    for p in paths:
        p = Path(p)
        sheet = standardize_columns(pd.read_csv(p, dtype=object, keep_default_na=True)).copy()
        sheet["SourceSheet"] = p.stem
        sheet["SourceRow"] = range(2, len(sheet) + 2)
        frames.append(sheet[config.REQUIRED_COLUMNS + ["SourceSheet", "SourceRow"]])
    if not frames:
        raise DataNotFoundError("No raw CSV files supplied.")
    return pd.concat(frames, ignore_index=True)


def find_raw_input(raw_dir: Path = config.RAW_DIR) -> pd.DataFrame:
    """Load the raw data from data/raw (workbook preferred, else *.csv)."""
    xlsx = raw_dir / config.XLSX_NAME
    if xlsx.exists():
        return read_raw_workbook(xlsx)
    csvs = sorted(raw_dir.glob("*.csv"))
    if csvs:
        return read_raw_csvs(csvs)
    raise DataNotFoundError(
        f"No raw data found in {raw_dir}. Run `python scripts/download_data.py` "
        f"or follow the manual download steps in README.md."
    )


_PROCESSED_DTYPES = {
    "Invoice": "string", "LineType": "category", "ProductKind": "category",
    "StockCode": "string", "Description": "string", "Country": "category",
    "SourceSheet": "category",
}


def load_processed_fact(processed_dir: Path = config.PROCESSED_DIR) -> pd.DataFrame:
    """Load the cleaned fact table produced by scripts/prepare_data.py."""
    path = Path(processed_dir) / "fact_invoice_lines.csv"
    if not path.exists():
        raise DataNotFoundError(
            "Processed data not found. Run `python scripts/download_data.py` and then "
            "`python scripts/prepare_data.py` (or run setup_windows.bat)."
        )
    df = pd.read_csv(path, dtype=_PROCESSED_DTYPES, parse_dates=["InvoiceDate"])
    df["CustomerID"] = pd.to_numeric(df["CustomerID"], errors="coerce").astype("Int64")
    df["IsDuplicateWithinSheet"] = df["IsDuplicateWithinSheet"].astype(bool)
    df["YearMonth"] = df["InvoiceDate"].dt.to_period("M").astype(str)
    return df


def load_report(name: str, report_dir: Path = config.REPORT_DIR) -> pd.DataFrame:
    """Load a CSV report (quality checks, cleaning log, ...). Empty frame if absent."""
    path = Path(report_dir) / name
    return pd.read_csv(path) if path.exists() else pd.DataFrame()
