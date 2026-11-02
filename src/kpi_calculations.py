"""KPI definitions (the single source of truth shared with the SQL views).

Definitions (all in GBP, product lines only: ProductKind = 'PRODUCT'):
  Gross Sales        = SUM(Quantity * UnitPrice) over LineType = 'SALE'
  Cancelled Value    = SUM(Quantity * UnitPrice) over LineType = 'CANCELLATION' (negative number)
  Net Revenue        = Gross Sales + Cancelled Value
  Sales Invoices     = COUNT(DISTINCT Invoice) over SALE lines
  Avg Invoice Value  = Gross Sales / Sales Invoices
  Cancellation Rate  = ABS(Cancelled Value) / Gross Sales   (value-based; cancellations cannot be
                       matched to their original invoice because the source has no reference field)
NOT available in the source (so NOT computed): cost, profit, margin, discount, delivery time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide(numerator, denominator):
    """Division returning NaN instead of raising/inf when the denominator is 0 or missing."""
    if denominator is None or pd.isna(denominator) or denominator == 0 or pd.isna(numerator):
        return np.nan
    return numerator / denominator


def _sales(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["LineType"] == "SALE") & (df["ProductKind"] == "PRODUCT")]


def _cancels(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df["LineType"] == "CANCELLATION") & (df["ProductKind"] == "PRODUCT")]


def apply_filters(df: pd.DataFrame, start=None, end=None, countries=None,
                  include_duplicates: bool = True) -> pd.DataFrame:
    """Filter by date range (inclusive), countries and optionally drop flagged duplicate lines."""
    out = df
    if start is not None:
        out = out[out["InvoiceDate"] >= pd.Timestamp(start)]
    if end is not None:
        out = out[out["InvoiceDate"] < pd.Timestamp(end) + pd.Timedelta(days=1)]
    if countries:
        out = out[out["Country"].isin(countries)]
    if not include_duplicates:
        out = out[~out["IsDuplicateWithinSheet"]]
    return out


def compute_kpis(df: pd.DataFrame) -> dict:
    """Headline KPIs for the (already filtered) frame. Safe on empty input."""
    s, c = _sales(df), _cancels(df)
    gross = float(s["LineRevenue"].sum()) if len(s) else 0.0
    cancelled = float(c["LineRevenue"].sum()) if len(c) else 0.0
    sale_inv = int(s["Invoice"].nunique()) if len(s) else 0
    canc_inv = int(c["Invoice"].nunique()) if len(c) else 0
    return {
        "gross_sales": gross,
        "cancelled_value": cancelled,
        "net_revenue": gross + cancelled,
        "sales_invoices": sale_inv,
        "cancelled_invoices": canc_inv,
        "avg_invoice_value": safe_divide(gross, sale_inv),
        "units_sold": int(s["Quantity"].sum()) if len(s) else 0,
        "units_cancelled": int(abs(c["Quantity"].sum())) if len(c) else 0,
        "identified_customers": int(s["CustomerID"].nunique()) if len(s) else 0,
        "cancellation_rate_value": safe_divide(abs(cancelled), gross),
        "cancellation_rate_invoices": safe_divide(canc_inv, sale_inv),
        "unidentified_customer_line_share": safe_divide(int(s["CustomerID"].isna().sum()), len(s)) if len(s) else np.nan,
    }


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Month-level gross, cancelled, net revenue and invoice counts."""
    cols = ["YearMonth", "GrossSales", "CancelledValue", "NetRevenue", "SalesInvoices", "MonthOverMonthPct"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    work = df.copy()
    if "YearMonth" not in work.columns:
        work["YearMonth"] = work["InvoiceDate"].dt.to_period("M").astype(str)
    s = _sales(work).groupby("YearMonth").agg(GrossSales=("LineRevenue", "sum"), SalesInvoices=("Invoice", "nunique"))
    c = _cancels(work).groupby("YearMonth").agg(CancelledValue=("LineRevenue", "sum"))
    out = s.join(c, how="outer").fillna({"GrossSales": 0.0, "CancelledValue": 0.0, "SalesInvoices": 0})
    out["SalesInvoices"] = out["SalesInvoices"].astype(int)
    out["NetRevenue"] = out["GrossSales"] + out["CancelledValue"]
    out = out.sort_index()
    out["MonthOverMonthPct"] = out["NetRevenue"].pct_change().replace([np.inf, -np.inf], np.nan) * 100
    return out.reset_index()[cols]


def partial_months(df: pd.DataFrame) -> list[str]:
    """Months at the edges of the data that do not cover the full calendar month."""
    if df.empty:
        return []
    first, last = df["InvoiceDate"].min(), df["InvoiceDate"].max()
    parts = []
    if first.day > 1:
        parts.append(first.strftime("%Y-%m"))
    if last.normalize() < (last + pd.offsets.MonthEnd(0)).normalize():
        parts.append(last.strftime("%Y-%m"))
    return sorted(set(parts))


def yoy_comparison(monthly: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year change in Net Revenue for the same calendar month."""
    if monthly.empty:
        return pd.DataFrame(columns=["Year", "Month", "NetRevenue", "PriorYearNetRevenue", "YoYPct"])
    m = monthly[["YearMonth", "NetRevenue"]].copy()
    period = pd.PeriodIndex(m["YearMonth"], freq="M")
    m["Year"], m["Month"] = period.year, period.month
    prior = m[["Year", "Month", "NetRevenue"]].rename(columns={"NetRevenue": "PriorYearNetRevenue"})
    prior["Year"] = prior["Year"] + 1
    out = m.merge(prior, on=["Year", "Month"], how="left")
    out["YoYPct"] = (out["NetRevenue"] / out["PriorYearNetRevenue"].replace(0, np.nan) - 1) * 100
    return out[["Year", "Month", "NetRevenue", "PriorYearNetRevenue", "YoYPct"]]


def product_performance(df: pd.DataFrame) -> pd.DataFrame:
    """Per-product units, revenue and cancellations (most frequent description per StockCode)."""
    cols = ["StockCode", "Description", "UnitsSold", "GrossSales", "UnitsCancelled", "CancelledValue",
            "NetRevenue", "AvgSellingPrice", "RevenueSharePct"]
    s, c = _sales(df), _cancels(df)
    if s.empty and c.empty:
        return pd.DataFrame(columns=cols)
    sg = s.groupby("StockCode").agg(UnitsSold=("Quantity", "sum"), GrossSales=("LineRevenue", "sum"))
    cg = c.groupby("StockCode").agg(UnitsCancelled=("Quantity", lambda q: abs(q.sum())),
                                    CancelledValue=("LineRevenue", "sum"))
    out = sg.join(cg, how="outer").fillna(0.0)
    out["NetRevenue"] = out["GrossSales"] + out["CancelledValue"]
    out["AvgSellingPrice"] = out["GrossSales"] / out["UnitsSold"].replace(0, np.nan)
    total = out["NetRevenue"].sum()
    out["RevenueSharePct"] = out["NetRevenue"] / total * 100 if total else np.nan
    cnt = (df.dropna(subset=["Description"]).groupby(["StockCode", "Description"]).size().reset_index(name="n")
           .sort_values(["StockCode", "n", "Description"], ascending=[True, False, True]).drop_duplicates("StockCode"))
    out = out.reset_index().merge(cnt[["StockCode", "Description"]], on="StockCode", how="left")
    return out[cols].sort_values("NetRevenue", ascending=False).reset_index(drop=True)


def country_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-country revenue, invoices, customers, AOV and cancellation rate."""
    cols = ["Country", "GrossSales", "CancelledValue", "NetRevenue", "SalesInvoices", "Customers",
            "AvgInvoiceValue", "CancellationRatePct", "NetRevenueSharePct"]
    s, c = _sales(df), _cancels(df)
    if s.empty and c.empty:
        return pd.DataFrame(columns=cols)
    sg = s.groupby("Country", observed=True).agg(GrossSales=("LineRevenue", "sum"), SalesInvoices=("Invoice", "nunique"),
                                                 Customers=("CustomerID", "nunique"))
    cg = c.groupby("Country", observed=True).agg(CancelledValue=("LineRevenue", "sum"))
    out = sg.join(cg, how="outer").fillna(0.0)
    out["NetRevenue"] = out["GrossSales"] + out["CancelledValue"]
    out["AvgInvoiceValue"] = out["GrossSales"] / out["SalesInvoices"].replace(0, np.nan)
    out["CancellationRatePct"] = out["CancelledValue"].abs() / out["GrossSales"].replace(0, np.nan) * 100
    total = out["NetRevenue"].sum()
    out["NetRevenueSharePct"] = out["NetRevenue"] / total * 100 if total else np.nan
    return out.reset_index()[cols].sort_values("NetRevenue", ascending=False).reset_index(drop=True)


def line_type_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Row counts, invoices and value by LineType (operations / data-quality view)."""
    if df.empty:
        return pd.DataFrame(columns=["LineType", "Lines", "Invoices", "Value"])
    g = df.groupby("LineType", observed=True).agg(Lines=("Invoice", "size"), Invoices=("Invoice", "nunique"),
                                                  Value=("LineRevenue", "sum")).reset_index()
    return g.sort_values("Lines", ascending=False).reset_index(drop=True)


def generate_insights(df: pd.DataFrame) -> list[str]:
    """Plain-language findings computed from the CURRENT filtered data (nothing pre-written)."""
    if df.empty:
        return ["No data for the current filter selection."]
    k = compute_kpis(df)
    msgs = []
    if k["net_revenue"] == 0 and k["gross_sales"] == 0:
        return ["No product sales in the current filter selection."]
    cs = country_summary(df)
    if not cs.empty and pd.notna(cs.loc[0, "NetRevenueSharePct"]):
        msgs.append(f"{cs.loc[0, 'Country']} contributes {cs.loc[0, 'NetRevenueSharePct']:.1f}% of net revenue "
                    f"across {len(cs)} countr{'y' if len(cs) == 1 else 'ies'} in view.")
    mt = monthly_trend(df)
    if not mt.empty:
        peak = mt.loc[mt["NetRevenue"].idxmax()]
        msgs.append(f"Peak month: {peak['YearMonth']} with net revenue of £{peak['NetRevenue']:,.0f}.")
    pp = product_performance(df)
    if not pp.empty and pp["NetRevenue"].sum() > 0:
        top10 = pp.head(10)["NetRevenue"].sum() / pp["NetRevenue"].sum() * 100
        msgs.append(f"The top 10 products account for {top10:.1f}% of net revenue (concentration).")
    if pd.notna(k["cancellation_rate_value"]):
        msgs.append(f"Cancelled value equals {k['cancellation_rate_value'] * 100:.1f}% of gross sales "
                    f"({k['cancelled_invoices']:,} cancellation invoices).")
    if pd.notna(k["unidentified_customer_line_share"]):
        msgs.append(f"{k['unidentified_customer_line_share'] * 100:.1f}% of sale lines have no Customer ID, "
                    f"so customer-level analysis covers only identified customers.")
    parts = partial_months(df)
    if parts:
        msgs.append(f"Note: {', '.join(parts)} is a partial month in the data; compare it with care.")
    return msgs
