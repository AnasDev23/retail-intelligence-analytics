import pandas as pd
from src import data_cleaning
from tests.helpers import raw_sample, clean_sample


def test_cross_sheet_overlap_removed_and_logged():
    res = data_cleaning.run_cleaning_pipeline(raw_sample())
    log = res["log"]
    removed = log[log["step"] == "remove_cross_sheet_overlap"]["rows_affected"].iloc[0]
    assert removed == 1
    assert len(res["fact"]) == len(raw_sample()) - 1


def test_stockcode_normalized_to_upper():
    fact = clean_sample()
    assert "85123a" not in set(fact["StockCode"])


def test_line_types():
    fact = clean_sample()
    lt = dict(zip(fact["Invoice"] + "|" + fact["StockCode"] + "|" + fact["Quantity"].astype(str), fact["LineType"]))
    assert lt["C500003|85123A|-2"] == "CANCELLATION"
    assert lt["500006|85124|-3"] == "STOCK_ADJUSTMENT"
    assert lt["500005|85124|3"] == "ZERO_PRICE"
    assert lt["500001|85123A|10"] == "SALE"


def test_non_product_kind_and_line_revenue():
    fact = clean_sample()
    post = fact[fact["StockCode"] == "POST"].iloc[0]
    assert post["ProductKind"] == "NON_PRODUCT"
    mug = fact[(fact["Invoice"] == "500001") & (fact["StockCode"] == "85123A")].iloc[0]
    assert mug["LineRevenue"] == 20.0


def test_within_sheet_duplicate_flagged_not_removed():
    fact = clean_sample()
    assert int(fact["IsDuplicateWithinSheet"].sum()) == 1
    assert ((fact["Invoice"] == "500002") & (fact["StockCode"] == "85123A")).sum() == 2


def test_unparseable_values_go_to_rejected_not_deleted():
    raw = raw_sample()
    raw.loc[0, "InvoiceDate"] = "not a date"
    res = data_cleaning.run_cleaning_pipeline(raw)
    assert len(res["rejected"]) == 1
    assert "invalid_or_missing_date" in res["rejected"]["RejectReason"].iloc[0]


def test_negative_quantity_not_dropped():
    fact = clean_sample()
    assert (fact["Quantity"] < 0).sum() == 2


def test_missing_values_preserved_not_imputed():
    fact = clean_sample()
    assert fact["CustomerID"].isna().sum() == 2
    assert fact["Description"].isna().sum() == 1


def test_empty_dataset_pipeline_inputs():
    from src import data_quality
    empty = raw_sample().iloc[0:0]
    checks = data_quality.run_quality_checks(empty)
    assert (checks["severity"] == "ERROR").any()
