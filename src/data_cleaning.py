"""Documented, non-destructive cleaning steps.

Principles: nothing is silently dropped. Every step appends a log entry
(step, rule, rows affected, rationale). Anomalous rows are CLASSIFIED and kept
(negative quantities are meaningful cancellations), except rows that cannot be
interpreted at all (unparseable date/quantity/price), which go to a rejected-rows report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _log(step: str, rule: str, rows: int, rationale: str) -> dict:
    return {"step": step, "rule": rule, "rows_affected": int(rows), "rationale": rationale}


def coerce_types(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Convert text/object columns to proper types. Unparseable values become NA and are counted."""
    out = df.copy()
    log = []
    before = {c: out[c].notna() for c in ["InvoiceDate", "Quantity", "UnitPrice", "CustomerID"]}
    out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    out["UnitPrice"] = pd.to_numeric(out["UnitPrice"], errors="coerce")
    out["CustomerID"] = pd.to_numeric(out["CustomerID"], errors="coerce")
    for col in ["InvoiceDate", "Quantity", "UnitPrice", "CustomerID"]:
        failed = int((before[col] & out[col].isna()).sum())
        log.append(_log("coerce_types", f"{col}: parse to native type; unparseable -> NA", failed,
                        "Type conversion only; failures are counted, never hidden."))
    # Quantity should be whole; CustomerID is an integer code stored as float in Excel
    frac = out["Quantity"].notna() & (out["Quantity"] % 1 != 0)
    log.append(_log("coerce_types", "Quantity: non-integer values", int(frac.sum()),
                    "Reported only; values are not altered."))
    out["Quantity"] = out["Quantity"].round().astype("Int64")
    out["CustomerID"] = out["CustomerID"].round().astype("Int64")
    out["UnitPrice"] = out["UnitPrice"].astype(float)
    return out, log


def normalize_text(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Trim whitespace; upper-case StockCode (SQL Server's default collation is case-insensitive)."""
    out = df.copy()
    log = []
    for col in ["Invoice", "StockCode", "Description", "Country"]:
        original = out[col].astype("string")
        cleaned = original.str.strip()
        if col == "StockCode":
            cleaned = cleaned.str.upper()
        if col == "Description":
            cleaned = cleaned.mask(cleaned == "")
        changed = int(((original != cleaned) & original.notna()).sum())
        out[col] = cleaned
        rule = {"StockCode": "TRIM + UPPER", "Description": "TRIM; empty -> NA"}.get(col, "TRIM")
        log.append(_log("normalize_text", f"{col}: {rule}", changed,
                        "Prevents the same code/name being split by whitespace or case."))
    return out, log


def split_rejected(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """Move rows with missing Invoice/StockCode/date/quantity/price to a rejected-rows frame."""
    reasons = pd.DataFrame({
        "missing_invoice": df["Invoice"].isna(),
        "missing_stockcode": df["StockCode"].isna(),
        "invalid_or_missing_date": df["InvoiceDate"].isna(),
        "invalid_or_missing_quantity": df["Quantity"].isna(),
        "invalid_or_missing_price": df["UnitPrice"].isna(),
    })
    bad = reasons.any(axis=1)
    rejected = df[bad].copy()
    if len(rejected):
        rejected["RejectReason"] = reasons[bad].apply(lambda r: ";".join(r.index[r]), axis=1)
    else:
        rejected["RejectReason"] = pd.Series(dtype="string")
    log = [_log("split_rejected", "Rows missing invoice/stockcode/date/quantity/price -> rejected_rows.csv",
                int(bad.sum()), "Cannot compute revenue or place the line in time; kept in a report, not deleted.")]
    return df[~bad].copy(), rejected, log


def remove_cross_sheet_overlap(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Drop later-sheet rows that exactly repeat earlier-sheet rows (multiset match on all 8 fields).

    The two workbook sheets cover overlapping periods; exact repeats would double-count revenue.
    Matching uses an occurrence counter so legitimate repeated lines are only removed when the
    earlier sheet contains the same number of identical lines.
    """
    sheets = df.groupby("SourceSheet")["InvoiceDate"].min().sort_values().index.tolist()
    if len(sheets) < 2:
        return df, [_log("remove_cross_sheet_overlap", "Only one sheet present; nothing to compare", 0, "n/a")]
    keys = config.KEY_COLUMNS

    def keyed(frame: pd.DataFrame) -> pd.DataFrame:
        k = frame[keys].copy()
        k["Description"] = k["Description"].astype("string").fillna("<NA>")
        k["CustomerID"] = k["CustomerID"].astype("Int64").fillna(-1)
        k["InvoiceDate"] = k["InvoiceDate"].fillna(pd.Timestamp(0))
        k["_occ"] = k.groupby(keys + [], sort=False).cumcount()
        return k

    drop_idx: list = []
    for earlier, later in zip(sheets[:-1], sheets[1:]):
        e = df[df["SourceSheet"] == earlier]
        l = df[df["SourceSheet"] == later]
        ke, kl = keyed(e), keyed(l)
        merged = kl.reset_index().merge(ke.drop_duplicates(), on=keys + ["_occ"], how="left", indicator=True)
        drop_idx.extend(merged.loc[merged["_merge"] == "both", "index"].tolist())
    out = df.drop(index=drop_idx)
    return out, [_log("remove_cross_sheet_overlap",
                      "Later-sheet rows identical (all 8 fields + occurrence #) to earlier-sheet rows removed",
                      len(drop_idx), "Sheets overlap in time; removing exact repeats prevents double-counted revenue.")]


def flag_within_sheet_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Flag (do NOT remove) exact repeated lines inside one sheet.

    A repeated line may be a genuine second scan of the same item, so the decision is left
    to the analyst; the dashboard has a toggle.
    """
    out = df.copy()
    out["IsDuplicateWithinSheet"] = out.duplicated(subset=config.KEY_COLUMNS + ["SourceSheet"], keep="first")
    return out, [_log("flag_duplicates", "Exact repeated line within the same sheet -> IsDuplicateWithinSheet=True",
                      int(out["IsDuplicateWithinSheet"].sum()),
                      "Flagged and retained; may be genuine repeated scans. Excluding is optional.")]


def classify_lines(df: pd.DataFrame) -> pd.DataFrame:
    """Add LineType and ProductKind. Rule order matters (first match wins)."""
    out = df.copy()
    inv = out["Invoice"].astype("string").str.upper()
    qty = out["Quantity"].astype(float)
    price = out["UnitPrice"].astype(float)
    conditions = [
        inv.str.startswith("C").fillna(False).to_numpy(dtype=bool),
        inv.str.startswith("A").fillna(False).to_numpy(dtype=bool),
        (price < 0).to_numpy(dtype=bool),
        (qty <= 0).to_numpy(dtype=bool),
        (price == 0).to_numpy(dtype=bool),
    ]
    choices = ["CANCELLATION", "ADJUSTMENT", "OTHER_ANOMALY", "STOCK_ADJUSTMENT", "ZERO_PRICE"]
    out["LineType"] = np.select(conditions, choices, default="SALE")
    is_product = out["StockCode"].astype("string").str.match(config.PRODUCT_CODE_PATTERN).fillna(False)
    out["ProductKind"] = np.where(is_product.to_numpy(dtype=bool), "PRODUCT", "NON_PRODUCT")
    out["LineRevenue"] = (out["Quantity"].astype(float) * out["UnitPrice"]).round(4)
    return out


def run_cleaning_pipeline(raw: pd.DataFrame) -> dict:
    """Full raw -> clean pipeline. Returns dict(fact, rejected, staging, log)."""
    log: list[dict] = [_log("input", "Raw rows read from source", len(raw), "Starting point (all sheets).")]
    typed, l1 = coerce_types(raw)
    log += l1
    staging = typed.copy()  # typed, un-normalised, still contains both sheets (loaded to SQL staging)
    normed, l2 = normalize_text(typed)
    log += l2
    usable, rejected, l3 = split_rejected(normed)
    log += l3
    deduped, l4 = remove_cross_sheet_overlap(usable)
    log += l4
    flagged, l5 = flag_within_sheet_duplicates(deduped)
    log += l5
    fact = classify_lines(flagged)
    for lt, n in fact["LineType"].value_counts().items():
        log.append(_log("classify_lines", f"LineType={lt}", int(n), "Classification only - rows retained."))
    log.append(_log("output", "Rows in cleaned fact table", len(fact), "Rows available for analysis."))
    return {"fact": fact.reset_index(drop=True), "rejected": rejected, "staging": staging,
            "log": pd.DataFrame(log)}


def build_dimensions(fact: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Derive dimension tables strictly from fields present in the data."""
    counts = (fact.dropna(subset=["Description"]).groupby(["StockCode", "Description"]).size()
              .reset_index(name="n").sort_values(["StockCode", "n", "Description"], ascending=[True, False, True]))
    desc = counts.drop_duplicates("StockCode")[["StockCode", "Description"]]
    variants = counts.groupby("StockCode").size().rename("DescriptionVariants").reset_index()
    kind = fact.drop_duplicates("StockCode")[["StockCode", "ProductKind"]]
    products = kind.merge(desc, on="StockCode", how="left").merge(variants, on="StockCode", how="left")
    products["DescriptionVariants"] = products["DescriptionVariants"].fillna(0).astype(int)
    cust = fact.dropna(subset=["CustomerID"]).groupby("CustomerID").agg(
        FirstSeen=("InvoiceDate", "min"), LastSeen=("InvoiceDate", "max"),
        CountriesSeen=("Country", "nunique")).reset_index()
    countries = fact[["Country"]].drop_duplicates().sort_values("Country").reset_index(drop=True)
    return {"products": products.sort_values("StockCode").reset_index(drop=True),
            "customers": cust, "countries": countries}
