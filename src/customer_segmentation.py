"""Rule-based RFM segmentation on identified customers (no machine learning).

Recency   = days from the snapshot date to the customer's last SALE invoice (lower = better)
Frequency = number of distinct SALE invoices
Monetary  = total gross sales value of the customer's SALE lines (GBP)
Scores run 1 (worst) .. 5 (best) using rank-based quintiles; with fewer than 5 customers the
number of score bins is reduced to the number of customers.

This is OBSERVED customer value. The source has no cost/margin data and covers only two years,
so no predictive lifetime-value model is produced (see README, Limitations).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RFM_COLUMNS = ["CustomerID", "Recency", "Frequency", "Monetary", "LastPurchase",
               "R", "F", "M", "RFMScore", "Segment"]


def _score(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    n = len(values)
    bins = min(5, n)
    ranks = values.rank(method="first", ascending=higher_is_better)
    scored = pd.qcut(ranks, q=bins, labels=False) + 1
    if bins < 5:  # stretch so the best group is still 5
        scored = np.ceil(scored * 5 / bins).astype(int)
    return scored.astype(int)


def assign_segment(r: int, f: int) -> str:
    """Segment labels from R and F scores (rules documented in README)."""
    if r >= 4 and f >= 4:
        return "Champions"
    if r >= 3 and f >= 3:
        return "Loyal Customers"
    if r <= 2 and f >= 4:
        return "At Risk (high frequency)"
    if r >= 4 and f <= 2:
        return "New / Recent"
    if r <= 2 and f <= 2:
        return "Hibernating"
    return "Needs Attention"


def build_rfm(df: pd.DataFrame, snapshot_date=None) -> pd.DataFrame:
    """Return one row per identified customer with RFM metrics, scores and segment."""
    if df.empty:
        return pd.DataFrame(columns=RFM_COLUMNS)
    s = df[(df["LineType"] == "SALE") & (df["ProductKind"] == "PRODUCT") & df["CustomerID"].notna()]
    if s.empty:
        return pd.DataFrame(columns=RFM_COLUMNS)
    snapshot = pd.Timestamp(snapshot_date) if snapshot_date is not None else s["InvoiceDate"].max().normalize() + pd.Timedelta(days=1)
    per_invoice = s.groupby(["CustomerID", "Invoice"]).agg(InvoiceDate=("InvoiceDate", "max"),
                                                           Value=("LineRevenue", "sum")).reset_index()
    rfm = per_invoice.groupby("CustomerID").agg(LastPurchase=("InvoiceDate", "max"),
                                                Frequency=("Invoice", "nunique"),
                                                Monetary=("Value", "sum")).reset_index()
    rfm["Recency"] = (snapshot - rfm["LastPurchase"]).dt.days
    rfm["R"] = _score(rfm["Recency"], higher_is_better=False)
    rfm["F"] = _score(rfm["Frequency"], higher_is_better=True)
    rfm["M"] = _score(rfm["Monetary"], higher_is_better=True)
    rfm["RFMScore"] = rfm["R"].astype(str) + rfm["F"].astype(str) + rfm["M"].astype(str)
    rfm["Segment"] = [assign_segment(r, f) for r, f in zip(rfm["R"], rfm["F"])]
    return rfm[RFM_COLUMNS]


def segment_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    """Customers, revenue and averages per RFM segment."""
    if rfm.empty:
        return pd.DataFrame(columns=["Segment", "Customers", "Revenue", "AvgRecencyDays", "AvgFrequency", "RevenueSharePct"])
    g = rfm.groupby("Segment").agg(Customers=("CustomerID", "count"), Revenue=("Monetary", "sum"),
                                   AvgRecencyDays=("Recency", "mean"), AvgFrequency=("Frequency", "mean")).reset_index()
    total = g["Revenue"].sum()
    g["RevenueSharePct"] = g["Revenue"] / total * 100 if total else np.nan
    return g.sort_values("Revenue", ascending=False).reset_index(drop=True)


def repeat_purchase_summary(rfm: pd.DataFrame) -> dict:
    """Share of identified customers with 2+ sale invoices."""
    if rfm.empty:
        return {"customers": 0, "repeat_customers": 0, "repeat_rate": np.nan}
    repeat = int((rfm["Frequency"] >= 2).sum())
    return {"customers": int(len(rfm)), "repeat_customers": repeat, "repeat_rate": repeat / len(rfm)}


def revenue_concentration(rfm: pd.DataFrame, top_share: float = 0.10) -> float:
    """Share of total customer revenue contributed by the top `top_share` of customers."""
    if rfm.empty or rfm["Monetary"].sum() == 0:
        return float("nan")
    k = max(1, int(np.ceil(len(rfm) * top_share)))
    return float(rfm["Monetary"].nlargest(k).sum() / rfm["Monetary"].sum())
