"""Profiling, quality checks (ERROR vs WARNING vs INFO) and revenue reconciliation.

ERROR   = blocks processing (pipeline raises DataQualityError)
WARNING = reported, processing continues, analyst should review
INFO    = descriptive fact about the data (e.g. cancellations are negative quantities by design)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


class DataQualityError(RuntimeError):
    """Raised when a blocking (ERROR) data-quality check fails."""


def profile_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Column-level profile: dtype, non-null, missing count/pct, distinct values."""
    if df.empty and len(df.columns) == 0:
        return pd.DataFrame(columns=["column", "dtype", "non_null", "missing", "missing_pct", "distinct"])
    rows = []
    n = len(df)
    for col in df.columns:
        miss = int(df[col].isna().sum())
        rows.append({"column": col, "dtype": str(df[col].dtype), "non_null": n - miss, "missing": miss,
                     "missing_pct": round(miss / n * 100, 3) if n else 0.0, "distinct": int(df[col].nunique(dropna=True))})
    return pd.DataFrame(rows)


def _row(check: str, severity: str, count: int, total: int, note: str) -> dict:
    return {"check": check, "severity": severity, "issue_count": int(count),
            "pct_of_rows": round(count / total * 100, 4) if total else 0.0, "note": note}


def run_quality_checks(df: pd.DataFrame, raw_row_count: int | None = None) -> pd.DataFrame:
    """Checks on a TYPED frame (after coerce_types, before classification is required).

    Works on the pre-clean frame (unparseable values are NA) and on the clean fact.
    Blocking checks are decided in `assert_no_blocking_errors`.
    """
    n = len(df)
    missing_cols = [c for c in config.REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        return pd.DataFrame([_row("required_columns_present", "ERROR", len(missing_cols), len(missing_cols),
                                  f"Missing columns: {missing_cols}")])
    if n == 0:
        return pd.DataFrame([_row("dataset_not_empty", "ERROR", 1, 1, "Dataset has zero rows.")])
    inv = df["Invoice"].astype("string").str.upper()
    qty = pd.to_numeric(df["Quantity"], errors="coerce")
    price = pd.to_numeric(df["UnitPrice"], errors="coerce")
    date = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    is_c = inv.str.startswith("C").fillna(False)
    is_a = inv.str.startswith("A").fillna(False)
    lo, hi = pd.Timestamp(config.EXPECTED_DATE_RANGE[0]), pd.Timestamp(config.EXPECTED_DATE_RANGE[1]) + pd.Timedelta(days=1)
    rows = [
        _row("invalid_or_missing_date", "ERROR" if date.isna().mean() > config.BLOCKING_UNPARSEABLE_SHARE else "WARNING",
             date.isna().sum(), n, "InvoiceDate could not be parsed (blocking above 1% of rows)."),
        _row("invalid_or_missing_quantity", "ERROR" if qty.isna().mean() > config.BLOCKING_UNPARSEABLE_SHARE else "WARNING",
             qty.isna().sum(), n, "Quantity missing/non-numeric."),
        _row("invalid_or_missing_price", "ERROR" if price.isna().mean() > config.BLOCKING_UNPARSEABLE_SHARE else "WARNING",
             price.isna().sum(), n, "UnitPrice missing/non-numeric."),
        _row("date_outside_documented_range", "WARNING", ((date < lo) | (date >= hi)).sum(), n,
             f"Dates outside {config.EXPECTED_DATE_RANGE[0]}..{config.EXPECTED_DATE_RANGE[1]} documented by UCI."),
        _row("missing_invoice", "WARNING", df["Invoice"].isna().sum(), n, "Invoice missing."),
        _row("missing_stockcode", "WARNING", df["StockCode"].isna().sum(), n, "StockCode missing."),
        _row("missing_description", "WARNING", df["Description"].isna().sum(), n, "Product description missing."),
        _row("missing_customer_id", "INFO", df["CustomerID"].isna().sum(), n,
             "Lines without Customer ID are kept; excluded only from customer-level analysis."),
        _row("negative_quantity_cancellation_invoice", "INFO", ((qty < 0) & is_c).sum(), n,
             "Negative quantity on a 'C' invoice = cancellation (meaningful business event, retained)."),
        _row("negative_quantity_other_invoice", "WARNING", ((qty < 0) & ~is_c & ~is_a).sum(), n,
             "Negative quantity without cancellation prefix (e.g. stock write-offs); classified STOCK_ADJUSTMENT."),
        _row("zero_quantity", "WARNING", (qty == 0).sum(), n, "Quantity equals 0."),
        _row("zero_price", "WARNING", (price == 0).sum(), n, "UnitPrice equals 0 (free items / adjustments)."),
        _row("negative_price", "WARNING", (price < 0).sum(), n, "UnitPrice negative (e.g. bad-debt adjustments)."),
        _row("adjustment_invoice_prefix_A", "INFO", is_a.sum(), n, "Invoices starting with 'A' (bad-debt adjustments)."),
        _row("unexpected_invoice_format", "WARNING",
             (~inv.str.match(r"^[CA]?\d{6}$").fillna(False) & df["Invoice"].notna()).sum(), n,
             "Invoice not matching optional C/A prefix + 6 digits."),
    ]
    if "StockCode" in df:
        np_mask = ~df["StockCode"].astype("string").str.upper().str.match(config.PRODUCT_CODE_PATTERN).fillna(False)
        rows.append(_row("non_product_stockcode", "INFO", (np_mask & df["StockCode"].notna()).sum(), n,
                         "StockCode not 5 digits(+letters), e.g. postage/fees/manual; excluded from product KPIs."))
    keys = [c for c in config.KEY_COLUMNS]
    dup_cols = keys + (["SourceSheet"] if "SourceSheet" in df.columns else [])
    rows.append(_row("exact_duplicate_lines", "WARNING", df.duplicated(subset=dup_cols).sum(), n,
                     "Fully identical lines (within sheet). Flagged; may be legitimate repeats."))
    g = df.dropna(subset=["Invoice"]).groupby("Invoice")
    rows.append(_row("invoice_with_multiple_customers", "WARNING", int((g["CustomerID"].nunique() > 1).sum()),
                     max(df["Invoice"].nunique(), 1), "Invoices (count of invoices) with >1 distinct Customer ID."))
    rows.append(_row("invoice_with_multiple_countries", "WARNING", int((g["Country"].nunique() > 1).sum()),
                     max(df["Invoice"].nunique(), 1), "Invoices with >1 distinct Country."))
    sc = df.dropna(subset=["StockCode", "Description"]).groupby("StockCode")["Description"].nunique()
    rows.append(_row("stockcode_with_multiple_descriptions", "INFO", int((sc > 1).sum()), max(len(sc), 1),
                     "StockCodes (count) with several description spellings; most frequent is used."))
    cc = df.dropna(subset=["CustomerID"]).groupby("CustomerID")["Country"].nunique()
    rows.append(_row("customer_with_multiple_countries", "INFO", int((cc > 1).sum()), max(len(cc), 1),
                     "Customers (count) appearing under >1 country."))
    pos_p = price[price > 0]
    if len(pos_p) > 10:
        q1, q3 = pos_p.quantile([0.25, 0.75])
        rows.append(_row("price_outliers_3xIQR", "INFO", int((pos_p > q3 + 3 * (q3 - q1)).sum()), n,
                         "Positive prices above Q3 + 3*IQR (potential outliers; retained)."))
    pos_q = qty[qty > 0]
    if len(pos_q) > 10:
        q1, q3 = pos_q.quantile([0.25, 0.75])
        rows.append(_row("quantity_outliers_3xIQR", "INFO", int((pos_q > q3 + 3 * (q3 - q1)).sum()), n,
                         "Positive quantities above Q3 + 3*IQR (wholesale orders are common; retained)."))
    out = pd.DataFrame(rows)
    if raw_row_count is not None:
        out.attrs["raw_row_count"] = raw_row_count
    return out


def assert_no_blocking_errors(checks: pd.DataFrame) -> None:
    """Raise DataQualityError if any ERROR-severity check has issues."""
    bad = checks[(checks["severity"] == "ERROR") & (checks["issue_count"] > 0)]
    if len(bad):
        raise DataQualityError("Blocking data-quality errors: " + "; ".join(
            f"{r.check} ({r.issue_count}): {r.note}" for r in bad.itertuples()))


def reconcile_revenue(fact: pd.DataFrame) -> pd.DataFrame:
    """Internal consistency checks on the cleaned fact table (tolerance 0.01 GBP)."""
    if fact.empty:
        return pd.DataFrame(columns=["check", "expected", "actual", "difference", "passed"])
    tol = 0.01
    total = float(fact["LineRevenue"].sum())
    by_type = float(fact.groupby("LineType", observed=True)["LineRevenue"].sum().sum())
    by_invoice = float(fact.groupby("Invoice")["LineRevenue"].sum().sum())
    recomputed = float((fact["Quantity"].astype(float) * fact["UnitPrice"]).sum())
    prod = fact[fact["ProductKind"] == "PRODUCT"]
    gross = float(prod.loc[prod["LineType"] == "SALE", "LineRevenue"].sum())
    canc = float(prod.loc[prod["LineType"] == "CANCELLATION", "LineRevenue"].sum())
    net = float(prod.loc[prod["LineType"].isin(["SALE", "CANCELLATION"]), "LineRevenue"].sum())
    checks = [
        ("sum by LineType = sum of all lines", total, by_type),
        ("sum by Invoice = sum of all lines", total, by_invoice),
        ("LineRevenue = Quantity x UnitPrice (recomputed)", recomputed, total),
        ("Gross + Cancelled = Net (product lines)", gross + canc, net),
    ]
    rows = [{"check": c, "expected": round(e, 4), "actual": round(a, 4), "difference": round(a - e, 4),
             "passed": bool(abs(a - e) <= tol)} for c, e, a in checks]
    rows.append({"check": "every row has exactly one valid LineType", "expected": len(fact),
                 "actual": int(fact["LineType"].isin(config.LINE_TYPES).sum()),
                 "difference": int(fact["LineType"].isin(config.LINE_TYPES).sum()) - len(fact),
                 "passed": bool(fact["LineType"].isin(config.LINE_TYPES).all())})
    return pd.DataFrame(rows)
