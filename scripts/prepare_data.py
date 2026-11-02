"""Raw -> processed pipeline. Never modifies files in data/raw.

Outputs (data/processed):
  stg_invoice_lines.csv       typed rows from BOTH sheets, loaded into SQL Server staging
  fact_invoice_lines.csv      cleaned + classified fact table (used by the dashboard)
  dim_products.csv, dim_customers.csv, dim_countries.csv
  reports/quality_before.csv, quality_after.csv, profile_before.csv, profile_after.csv,
  reports/cleaning_log.csv, reconciliation.csv, rejected_rows.csv, pipeline_summary.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config, data_cleaning, data_loader, data_quality  # noqa: E402


def run(raw: pd.DataFrame | None = None, out_dir: Path = config.PROCESSED_DIR) -> dict:
    out_dir = Path(out_dir)
    rep = out_dir / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    if raw is None:
        print("Reading raw data (the .xlsx read can take several minutes) ...")
        raw = data_loader.find_raw_input()
    warnings = []
    if len(raw) != config.EXPECTED_TOTAL_ROWS:
        warnings.append(f"Row count {len(raw):,} differs from the {config.EXPECTED_TOTAL_ROWS:,} stated by UCI.")
    result = data_cleaning.run_cleaning_pipeline(raw)
    fact, staging = result["fact"], result["staging"]

    before = data_quality.run_quality_checks(staging, raw_row_count=len(raw))
    data_quality.assert_no_blocking_errors(before)  # stops here on ERROR
    after = data_quality.run_quality_checks(fact)
    recon = data_quality.reconcile_revenue(fact)

    data_quality.profile_dataframe(staging).to_csv(rep / "profile_before.csv", index=False)
    data_quality.profile_dataframe(fact).to_csv(rep / "profile_after.csv", index=False)
    before.to_csv(rep / "quality_before.csv", index=False)
    after.to_csv(rep / "quality_after.csv", index=False)
    result["log"].to_csv(rep / "cleaning_log.csv", index=False)
    recon.to_csv(rep / "reconciliation.csv", index=False)
    result["rejected"].to_csv(rep / "rejected_rows.csv", index=False)

    stg = staging.copy()
    stg["InvoiceDate"] = stg["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    stg.to_csv(out_dir / "stg_invoice_lines.csv", index=False, lineterminator="\n", encoding="utf-8")
    fact_out = fact.copy()
    fact_out["InvoiceDate"] = fact_out["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    fact_out.to_csv(out_dir / "fact_invoice_lines.csv", index=False, lineterminator="\n", encoding="utf-8")
    dims = data_cleaning.build_dimensions(fact)
    for name, d in dims.items():
        d.to_csv(out_dir / f"dim_{name}.csv", index=False, lineterminator="\n", encoding="utf-8")

    prod = fact[fact["ProductKind"] == "PRODUCT"]
    summary = {
        "raw_rows": int(len(raw)), "staging_rows": int(len(staging)), "rejected_rows": int(len(result["rejected"])),
        "fact_rows": int(len(fact)),
        "line_type_counts": {k: int(v) for k, v in fact["LineType"].value_counts().items()},
        "gross_sales_product": round(float(prod.loc[prod.LineType == "SALE", "LineRevenue"].sum()), 2),
        "cancelled_value_product": round(float(prod.loc[prod.LineType == "CANCELLATION", "LineRevenue"].sum()), 2),
        "min_date": str(fact["InvoiceDate"].min()), "max_date": str(fact["InvoiceDate"].max()),
        "reconciliation_all_passed": bool(recon["passed"].all()), "warnings": warnings,
    }
    summary["net_revenue_product"] = round(summary["gross_sales_product"] + summary["cancelled_value_product"], 2)
    (rep / "pipeline_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    s = run()
    print(json.dumps(s, indent=2))
    print("Done. Launch the dashboard with run_dashboard.bat")
