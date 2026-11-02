"""Central configuration: paths, source metadata and shared business rules.

All paths are derived from the project root with pathlib (no hard-coded drives/users).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORT_DIR = PROCESSED_DIR / "reports"
DOCS_DIR = ROOT / "docs"

# ---- Official source (verified against the UCI dataset page) -------------------------
DATASET_TITLE = "Online Retail II"
DATASET_AUTHOR = "Daqing Chen"
DATASET_DOI = "https://doi.org/10.24432/C5CG6D"
LANDING_URL = "https://archive.ics.uci.edu/dataset/502/online+retail+ii"
DOWNLOAD_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
LICENSE_NAME = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/legalcode"
XLSX_NAME = "online_retail_II.xlsx"
# Figures stated on the UCI page; the pipeline WARNS (never silently ignores) on mismatch.
EXPECTED_TOTAL_ROWS = 1_067_371
EXPECTED_DATE_RANGE = ("2009-12-01", "2011-12-09")
CURRENCY = "GBP"

# ---- Schema ---------------------------------------------------------------------------
# The UCI web page names columns InvoiceNo/UnitPrice/CustomerID; the workbook headers
# may differ (e.g. Invoice/Price/"Customer ID"). Aliases make the loader tolerant of both.
COLUMN_ALIASES = {
    "invoice": "Invoice",
    "invoiceno": "Invoice",
    "stockcode": "StockCode",
    "description": "Description",
    "quantity": "Quantity",
    "invoicedate": "InvoiceDate",
    "price": "UnitPrice",
    "unitprice": "UnitPrice",
    "customerid": "CustomerID",
    "country": "Country",
}
REQUIRED_COLUMNS = [
    "Invoice", "StockCode", "Description", "Quantity",
    "InvoiceDate", "UnitPrice", "CustomerID", "Country",
]
KEY_COLUMNS = REQUIRED_COLUMNS  # a "line" is identified by all eight source fields

# ---- Business rules (project assumptions; documented in README) ------------------------
LINE_TYPES = ["SALE", "CANCELLATION", "ADJUSTMENT", "STOCK_ADJUSTMENT", "ZERO_PRICE", "OTHER_ANOMALY"]
# Source documentation: invoice codes starting with 'C' are cancellations.
# 'A' prefix = bad-debt adjustment (observed convention; treated as a non-sale line).
PRODUCT_CODE_PATTERN = re.compile(r"^\d{5}[A-Z]{0,2}$")  # 5 digits + up to 2 letters

BLOCKING_UNPARSEABLE_SHARE = 0.01  # >1% unparseable date/quantity/price stops the pipeline
