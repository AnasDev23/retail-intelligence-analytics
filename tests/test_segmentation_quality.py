import pandas as pd
from src import customer_segmentation as cs, data_quality as dq
from tests.helpers import clean_sample, raw_sample


def test_rfm_columns_and_scores_in_range():
    rfm = cs.build_rfm(clean_sample())
    assert len(rfm) == 3
    assert rfm[["R", "F", "M"]].min().min() >= 1 and rfm[["R", "F", "M"]].max().max() <= 5
    assert rfm["Segment"].notna().all()


def test_rfm_recency_direction():
    rfm = cs.build_rfm(clean_sample()).set_index("CustomerID")
    assert rfm.loc[1003, "Recency"] < rfm.loc[1001, "Recency"]
    assert rfm.loc[1003, "R"] >= rfm.loc[1001, "R"]


def test_assign_segment_rules():
    assert cs.assign_segment(5, 5) == "Champions"
    assert cs.assign_segment(1, 1) == "Hibernating"
    assert cs.assign_segment(5, 1) == "New / Recent"
    assert cs.assign_segment(1, 5) == "At Risk (high frequency)"


def test_rfm_empty():
    assert cs.build_rfm(clean_sample().iloc[0:0]).empty
    assert cs.repeat_purchase_summary(cs.build_rfm(clean_sample().iloc[0:0]))["customers"] == 0


def test_repeat_summary():
    r = cs.repeat_purchase_summary(cs.build_rfm(clean_sample()))
    assert r["customers"] == 3 and r["repeat_customers"] == 0


def test_quality_checks_find_expected_issues():
    from src import data_cleaning
    typed, _ = data_cleaning.coerce_types(raw_sample())
    checks = dq.run_quality_checks(typed).set_index("check")
    assert checks.loc["zero_price", "issue_count"] == 1
    assert checks.loc["missing_customer_id", "issue_count"] == 2
    assert checks.loc["negative_quantity_cancellation_invoice", "issue_count"] == 1
    assert checks.loc["negative_quantity_other_invoice", "issue_count"] == 1
    assert checks.loc["missing_description", "issue_count"] == 1


def test_blocking_error_raises():
    bad = pd.DataFrame([{"check": "x", "severity": "ERROR", "issue_count": 3, "pct_of_rows": 1, "note": "n"}])
    try:
        dq.assert_no_blocking_errors(bad)
    except dq.DataQualityError:
        return
    raise AssertionError("expected DataQualityError")


def test_missing_required_column_is_error():
    checks = dq.run_quality_checks(pd.DataFrame({"Invoice": ["1"]}))
    assert checks.iloc[0]["severity"] == "ERROR"


def test_reconciliation_passes_and_detects_tampering():
    fact = clean_sample()
    assert dq.reconcile_revenue(fact)["passed"].all()
    bad = fact.copy()
    bad.loc[0, "LineRevenue"] += 5
    assert not dq.reconcile_revenue(bad)["passed"].all()


def test_empty_reconciliation():
    assert dq.reconcile_revenue(clean_sample().iloc[0:0]).empty
