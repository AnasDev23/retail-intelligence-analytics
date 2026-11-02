"""UNIT-TEST FIXTURES ONLY: tiny hand-written rows used to check code logic.

These rows are NOT part of the project dataset, are never loaded by the app or pipeline
scripts, and no analytical result is ever derived from them.
"""
import pandas as pd

from src import data_cleaning


def raw_sample() -> pd.DataFrame:
    rows = [
        # Invoice, StockCode, Description, Qty, Date, Price, Cust, Country, Sheet, Row
        ("500001", "85123a", " MUG ", 10, "2010-01-04 10:00:00", 2.0, 1001, "United Kingdom", "S1", 2),
        ("500001", "85124", "BOWL", 5, "2010-01-04 10:00:00", 4.0, 1001, "United Kingdom", "S1", 3),
        ("500002", "85123A", "MUG", 4, "2010-02-10 09:00:00", 2.0, 1002, "France", "S1", 4),
        ("C500003", "85123A", "MUG", -2, "2010-02-11 09:00:00", 2.0, 1002, "France", "S1", 5),
        ("500004", "POST", "POSTAGE", 1, "2010-03-01 12:00:00", 15.0, 1001, "United Kingdom", "S1", 6),
        ("500005", "85124", None, 3, "2010-03-05 12:00:00", 0.0, None, "United Kingdom", "S1", 7),
        ("500006", "85124", "BOWL", -3, "2010-03-06 12:00:00", 4.0, None, "United Kingdom", "S1", 8),
        ("500002", "85123A", "MUG", 4, "2010-02-10 09:00:00", 2.0, 1002, "France", "S1", 9),  # in-sheet repeat
        # second sheet repeats the first row exactly (overlap) plus one new row
        ("500001", "85123A", "MUG", 10, "2010-01-04 10:00:00", 2.0, 1001, "United Kingdom", "S2", 2),
        ("500007", "85124", "BOWL", 6, "2011-01-10 08:00:00", 4.0, 1003, "Germany", "S2", 3),
    ]
    cols = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "UnitPrice", "CustomerID",
            "Country", "SourceSheet", "SourceRow"]
    df = pd.DataFrame(rows, columns=cols)
    df["Invoice"] = df["Invoice"].astype(object)
    return df


def clean_sample() -> pd.DataFrame:
    return data_cleaning.run_cleaning_pipeline(raw_sample())["fact"]
