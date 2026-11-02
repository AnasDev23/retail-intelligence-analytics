"""Retail Intelligence & Business Analytics Platform - Streamlit dashboard.

Data: UCI Online Retail II (Daqing Chen, CC BY 4.0). Run:  streamlit run app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from src import config, customer_segmentation as seg, data_loader
from src import kpi_calculations as kpi

st.set_page_config(page_title="Retail Intelligence Platform", page_icon="📊", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.4rem;max-width:1400px}
div[data-testid="stMetric"]{background:#F3F6FB;border:1px solid #E1E8F2;border-radius:10px;padding:12px 14px}
h1,h2,h3{letter-spacing:-0.01em}
</style>""", unsafe_allow_html=True)
CHART_H = 340
PALETTE = px.colors.qualitative.Safe


def money(x) -> str:
    return "n/a" if x is None or pd.isna(x) else f"£{x:,.0f}"


def pct(x, scale=1.0) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x * scale:.1f}%"


def style(fig, h=CHART_H):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), template="plotly_white", legend_title_text="")
    return fig


@st.cache_data(show_spinner="Loading processed data ...")
def get_data() -> pd.DataFrame:
    return data_loader.load_processed_fact()


@st.cache_data
def get_report(name: str) -> pd.DataFrame:
    return data_loader.load_report(name)


try:
    data = get_data()
except data_loader.DataNotFoundError as exc:
    st.title("Retail Intelligence & Business Analytics Platform")
    st.error(str(exc))
    st.info("Steps: 1) `python scripts/download_data.py`  2) `python scripts/prepare_data.py`  3) restart this app. "
            f"Source: {config.LANDING_URL}")
    st.stop()
except Exception as exc:  # unexpected file/format problem
    st.error(f"Could not load the processed data: {exc}")
    st.stop()

# ---------------- Sidebar filters ----------------
st.sidebar.header("Filters")
dmin, dmax = data["InvoiceDate"].min().date(), data["InvoiceDate"].max().date()
dates = st.sidebar.date_input("Invoice date range", (dmin, dmax), min_value=dmin, max_value=dmax)
start, end = (dates if isinstance(dates, (tuple, list)) and len(dates) == 2 else (dmin, dmax))
all_countries = sorted(data["Country"].astype(str).unique())
countries = st.sidebar.multiselect("Country (empty = all)", all_countries)
inc_dups = st.sidebar.checkbox("Include flagged exact-duplicate lines", value=True,
                               help="Identical lines repeated within a sheet. Retained by default; may be genuine.")
st.sidebar.caption("Revenue = product lines (5-digit stock codes). Postage/fees/manual codes are excluded from product KPIs "
                   "but shown in Operations & Data Quality.")
df = kpi.apply_filters(data, start, end, countries or None, inc_dups)

st.title("Retail Intelligence & Business Analytics Platform")
st.caption(f"Real data: {config.DATASET_TITLE} (UCI, {config.DATASET_AUTHOR}, CC BY 4.0) · UK online gift-ware retailer · "
           f"{config.CURRENCY} · {dmin} to {dmax}")
if df.empty:
    st.warning("No data matches the current filters. Widen the date range or clear the country filter.")
    st.stop()

k = kpi.compute_kpis(df)
tabs = st.tabs(["Executive Overview", "Product Intelligence", "Customer Intelligence", "Country Analytics",
                "Operations & Data Quality"])

# ---------------- A. Executive overview ----------------
with tabs[0]:
    c = st.columns(5)
    c[0].metric("Net revenue", money(k["net_revenue"]))
    c[1].metric("Gross sales", money(k["gross_sales"]))
    c[2].metric("Sales invoices", f"{k['sales_invoices']:,}")
    c[3].metric("Avg invoice value", money(k["avg_invoice_value"]))
    c[4].metric("Cancellation rate (value)", pct(k["cancellation_rate_value"], 100))
    st.caption("Profit and margin are NOT shown: the source dataset has no cost data.")
    mt = kpi.monthly_trend(df)
    parts = kpi.partial_months(df)
    l, r = st.columns(2)
    with l:
        fig = px.line(mt, x="YearMonth", y=["GrossSales", "NetRevenue"], markers=True, title="Monthly sales trend (£)",
                      color_discrete_sequence=PALETTE)
        st.plotly_chart(style(fig), use_container_width=True)
    with r:
        yoy = kpi.yoy_comparison(mt).dropna(subset=["YoYPct"])
        if yoy.empty:
            st.info("Year-over-year needs the same month in two different years; widen the date range.")
        else:
            yoy["Period"] = yoy["Year"].astype(str) + "-" + yoy["Month"].astype(str).str.zfill(2)
            fig = px.bar(yoy, x="Period", y="YoYPct", title="Year-over-year change in net revenue (%)",
                         color=np.where(yoy["YoYPct"] >= 0, "Growth", "Decline"),
                         color_discrete_map={"Growth": "#2E8B57", "Decline": "#C0392B"})
            st.plotly_chart(style(fig), use_container_width=True)
    if parts:
        st.caption(f"Partial months in range: {', '.join(parts)} (not a full calendar month).")
    l, r = st.columns(2)
    with l:
        mt2 = mt.copy()
        mt2["MoM %"] = mt2["MonthOverMonthPct"]
        fig = px.bar(mt2, x="YearMonth", y="MoM %", title="Month-over-month change in net revenue (%)",
                     color_discrete_sequence=["#1F6FEB"])
        st.plotly_chart(style(fig), use_container_width=True)
    with r:
        dow = df[(df["LineType"] == "SALE") & (df["ProductKind"] == "PRODUCT")].copy()
        dow["Weekday"] = dow["InvoiceDate"].dt.day_name()
        order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        g = dow.groupby("Weekday")["LineRevenue"].sum().reindex(order).dropna().reset_index()
        fig = px.bar(g, x="Weekday", y="LineRevenue", title="Gross sales by weekday (£)", color_discrete_sequence=["#1F6FEB"])
        st.plotly_chart(style(fig), use_container_width=True)
    st.subheader("Insights (calculated from the current selection)")
    for m in kpi.generate_insights(df):
        st.markdown(f"- {m}")

# ---------------- B. Products ----------------
with tabs[1]:
    st.caption("The source has no product category, cost, or discount fields, so category/margin/discount analysis is not available.")
    pp = kpi.product_performance(df)
    if pp.empty:
        st.info("No product sales in the current selection.")
    else:
        n = st.slider("Products to show", 5, 30, 10)
        l, r = st.columns(2)
        with l:
            top = pp.head(n).assign(Label=lambda d: d["StockCode"] + " " + d["Description"].fillna("").str[:28])
            fig = px.bar(top.iloc[::-1], x="NetRevenue", y="Label", orientation="h", title=f"Top {n} products by net revenue (£)",
                         color_discrete_sequence=["#1F6FEB"])
            st.plotly_chart(style(fig, 80 + 22 * n), use_container_width=True)
        with r:
            tu = pp.sort_values("UnitsSold", ascending=False).head(n).assign(
                Label=lambda d: d["StockCode"] + " " + d["Description"].fillna("").str[:28])
            fig = px.bar(tu.iloc[::-1], x="UnitsSold", y="Label", orientation="h", title=f"Top {n} products by units sold",
                         color_discrete_sequence=["#2E8B57"])
            st.plotly_chart(style(fig, 80 + 22 * n), use_container_width=True)
        sc = pp[pp["GrossSales"] > 0].head(300)
        fig = px.scatter(sc, x="UnitsSold", y="GrossSales", size="GrossSales", hover_data=["StockCode", "Description", "AvgSellingPrice"],
                         log_x=True, log_y=True, title="Units sold vs gross sales (top 300 products, log scale)",
                         color_discrete_sequence=["#1F6FEB"])
        st.plotly_chart(style(fig), use_container_width=True)
        st.subheader("Highest cancellation rates (products with ≥ £1,000 gross sales)")
        hc = pp[pp["GrossSales"] >= 1000].assign(CancellationRatePct=lambda d: d["CancelledValue"].abs() / d["GrossSales"] * 100)
        st.dataframe(hc.sort_values("CancellationRatePct", ascending=False).head(15)[
            ["StockCode", "Description", "GrossSales", "CancelledValue", "CancellationRatePct"]], use_container_width=True, hide_index=True)
        st.subheader("Price bands (gross sales)")
        s = df[(df["LineType"] == "SALE") & (df["ProductKind"] == "PRODUCT")]
        bands = pd.cut(s["UnitPrice"], [0, 1, 3, 5, 10, np.inf], labels=["<1", "1–2.99", "3–4.99", "5–9.99", "10+"], right=False)
        pb = s.groupby(bands, observed=True)["LineRevenue"].sum().reset_index()
        st.plotly_chart(style(px.bar(pb, x="UnitPrice", y="LineRevenue", labels={"UnitPrice": "Unit price band (£)"},
                                     color_discrete_sequence=["#1F6FEB"])), use_container_width=True)

# ---------------- C. Customers ----------------
with tabs[2]:
    rfm = seg.build_rfm(df)
    if rfm.empty:
        st.info("No identified-customer sales in the current selection.")
    else:
        rp = seg.repeat_purchase_summary(rfm)
        c = st.columns(4)
        c[0].metric("Identified customers", f"{rp['customers']:,}")
        c[1].metric("Repeat customers (2+ invoices)", f"{rp['repeat_customers']:,}")
        c[2].metric("Repeat rate", pct(rp["repeat_rate"], 100))
        c[3].metric("Top 10% customers' revenue share", pct(seg.revenue_concentration(rfm), 100))
        l, r = st.columns(2)
        with l:
            ss = seg.segment_summary(rfm)
            st.plotly_chart(style(px.bar(ss, x="Segment", y="Revenue", color="Segment", title="Revenue by RFM segment (£)",
                                         color_discrete_sequence=PALETTE)), use_container_width=True)
        with r:
            st.plotly_chart(style(px.histogram(rfm, x="Monetary", nbins=60, log_y=True,
                                               title="Customer spending distribution (£, log count)",
                                               color_discrete_sequence=["#1F6FEB"])), use_container_width=True)
        st.dataframe(ss, use_container_width=True, hide_index=True)
        st.subheader("Top 20 customers by gross sales")
        st.dataframe(rfm.sort_values("Monetary", ascending=False).head(20), use_container_width=True, hide_index=True)
        with st.expander("RFM method, customer value and what is NOT estimated"):
            st.markdown(
                "- **Recency** = days from snapshot (day after last invoice in view) to last sale invoice; **Frequency** = distinct sale invoices; "
                "**Monetary** = gross sales £ of the customer.\n- Scores 1–5 are rank-based quintiles (5 = best). Segment rules: Champions R≥4 & F≥4; "
                "Loyal R≥3 & F≥3; At Risk R≤2 & F≥4; New/Recent R≥4 & F≤2; Hibernating R≤2 & F≤2; otherwise Needs Attention.\n"
                "- **Customer value shown is OBSERVED revenue.** No predictive lifetime value is produced: the data has no costs/margins, spans only "
                "two years, and many customers are wholesalers, so a forecast would rest on invented assumptions.\n"
                "- Only lines with a Customer ID are included; see the share of unidentified lines in Operations & Data Quality.")

# ---------------- D. Countries ----------------
with tabs[3]:
    cs = kpi.country_summary(df)
    if cs.empty:
        st.info("No country-level sales in the current selection.")
    else:
        topn = st.slider("Countries to show", 5, 25, 12)
        l, r = st.columns(2)
        with l:
            st.plotly_chart(style(px.bar(cs.head(topn), x="Country", y="NetRevenue", title="Net revenue by country (£)",
                                         color_discrete_sequence=["#1F6FEB"])), use_container_width=True)
        with r:
            ex = cs[cs["Country"] != "United Kingdom"].head(topn)
            st.plotly_chart(style(px.bar(ex, x="Country", y="NetRevenue", title="Net revenue excluding United Kingdom (£)",
                                         color_discrete_sequence=["#2E8B57"])), use_container_width=True)
        # Plotly requires bubble sizes to be non-negative. Some countries can have
        # negative net revenue due to cancellations/adjustments, so use the absolute
        # revenue magnitude for bubble size while preserving the original NetRevenue.
        scatter_data = cs[cs["SalesInvoices"] > 0].copy()
        scatter_data["BubbleSize"] = (
            pd.to_numeric(scatter_data["NetRevenue"], errors="coerce")
            .abs()
            .replace([np.inf, -np.inf], np.nan)
            .fillna(0)
        )
        st.plotly_chart(
            style(
                px.scatter(
                    scatter_data,
                    x="SalesInvoices",
                    y="AvgInvoiceValue",
                    size="BubbleSize",
                    hover_name="Country",
                    hover_data={"NetRevenue": True, "BubbleSize": False},
                    log_x=True,
                    title="Invoice volume vs average invoice value",
                    color_discrete_sequence=["#1F6FEB"],
                    size_max=45,
                )
            ),
            use_container_width=True,
        )
        st.dataframe(cs, use_container_width=True, hide_index=True)
        st.caption("The source provides only the customer's country (no regions/cities); delivery and shipping times are not available.")

# ---------------- E. Operations & data quality ----------------
with tabs[4]:
    lt = kpi.line_type_summary(df)
    st.subheader("Line types in current selection")
    st.dataframe(lt, use_container_width=True, hide_index=True)
    c = st.columns(4)
    c[0].metric("Cancellation invoices", f"{k['cancelled_invoices']:,}")
    c[1].metric("Cancellation rate (invoices)", pct(k["cancellation_rate_invoices"], 100))
    c[2].metric("Cancellation rate (value)", pct(k["cancellation_rate_value"], 100))
    c[3].metric("Sale lines w/o Customer ID", pct(k["unidentified_customer_line_share"], 100))
    mt = kpi.monthly_trend(df).assign(CancelledAbs=lambda d: d["CancelledValue"].abs())
    st.plotly_chart(style(px.bar(mt, x="YearMonth", y="CancelledAbs", title="Cancelled value by month (£)",
                                 color_discrete_sequence=["#C0392B"])), use_container_width=True)
    st.info("Cancellations are measured by value/count; the source has no field linking a cancellation to its original invoice, "
            "so a true 'return rate per order' is not available.")
    st.subheader("Data-quality report (full dataset, before cleaning)")
    qb, qa = get_report("quality_before.csv"), get_report("quality_after.csv")
    if qb.empty:
        st.warning("Quality reports not found. Run scripts/prepare_data.py.")
    else:
        st.dataframe(qb, use_container_width=True, hide_index=True)
        with st.expander("After cleaning"):
            st.dataframe(qa, use_container_width=True, hide_index=True)
    st.subheader("Cleaning log (every transformation, with affected row counts)")
    st.dataframe(get_report("cleaning_log.csv"), use_container_width=True, hide_index=True)
    st.subheader("Revenue reconciliation (current selection)")
    from src import data_quality as dq
    st.dataframe(dq.reconcile_revenue(df), use_container_width=True, hide_index=True)
    st.subheader("Download filtered data")
    st.download_button("Download filtered lines (CSV)", df.drop(columns=["YearMonth"], errors="ignore").to_csv(index=False).encode("utf-8"),
                       file_name="filtered_invoice_lines.csv", mime="text/csv")
