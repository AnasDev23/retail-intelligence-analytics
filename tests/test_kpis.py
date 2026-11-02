import math
import pandas as pd
from src import kpi_calculations as k
from tests.helpers import clean_sample


def test_safe_divide():
    assert math.isnan(k.safe_divide(1, 0))
    assert k.safe_divide(6, 3) == 2


def test_net_revenue_handles_cancellations():
    kp = k.compute_kpis(clean_sample())
    assert kp["cancelled_value"] == -4.0
    assert kp["net_revenue"] == kp["gross_sales"] + kp["cancelled_value"]


def test_exact_values():
    # SALE product lines: 500001 MUG 20, 500001 BOWL 20, 500002 MUG 8 (+8 repeat), 500007 BOWL 24
    kp = k.compute_kpis(clean_sample())
    assert kp["gross_sales"] == 80.0
    assert kp["sales_invoices"] == 3  # 500001, 500002, 500007 (POST excluded as non-product)
    assert kp["avg_invoice_value"] == 80.0 / 3
    assert kp["cancellation_rate_value"] == 4.0 / 80.0
    assert kp["units_sold"] == 10 + 5 + 4 + 4 + 6


def test_duplicate_toggle():
    df = clean_sample()
    kp = k.compute_kpis(k.apply_filters(df, include_duplicates=False))
    assert kp["gross_sales"] == 72.0


def test_country_filter_and_dates():
    df = clean_sample()
    fr = k.apply_filters(df, countries=["France"])
    assert set(fr["Country"]) == {"France"}
    sub = k.apply_filters(df, start="2011-01-01", end="2011-12-31")
    assert set(sub["Invoice"]) == {"500007"}


def test_empty_dataframe_safe():
    df = clean_sample().iloc[0:0]
    kp = k.compute_kpis(df)
    assert kp["net_revenue"] == 0 and math.isnan(kp["avg_invoice_value"])
    assert k.monthly_trend(df).empty and k.product_performance(df).empty and k.country_summary(df).empty
    assert k.generate_insights(df) == ["No data for the current filter selection."]


def test_monthly_and_yoy():
    df = clean_sample()
    m = k.monthly_trend(df)
    assert m["NetRevenue"].sum() == k.compute_kpis(df)["net_revenue"]
    y = k.yoy_comparison(m)
    assert {"YoYPct", "PriorYearNetRevenue"} <= set(y.columns)
    jan11 = y[(y["Year"] == 2011) & (y["Month"] == 1)].iloc[0]
    assert jan11["PriorYearNetRevenue"] == 40.0 and jan11["NetRevenue"] == 24.0  # Jan-2010 net 40, Jan-2011 net 24
    assert abs(jan11["YoYPct"] - (-40.0)) < 1e-9
    assert y[y["Year"] == 2010]["YoYPct"].isna().all()
