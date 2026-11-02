# Analysis Report - Online Retail II
> Fill every number from your own run of the SQL/dashboard. Do not copy numbers from anywhere else. Data: UCI Online Retail II (D. Chen), CC BY 4.0. Real transactions of a UK online retailer; findings describe that company only.

## 1. Executive summary
*(3-5 sentences: period covered, net revenue, trend direction, one key risk, one key opportunity - each with the query/dashboard tab it came from.)*

## 2. Key findings
| # | Finding | Value | Source (SQL Qnn / tab) |
|---|---------|-------|------------------------|

## 3. Revenue drivers
*(top products, countries, seasonality, invoice-value bands)*

## 4. Risks (profitability cannot be assessed - no cost data)
*(revenue concentration, UK dependence, cancellation rate, share of unidentified customers)*

## 5. Customer opportunities
*(repeat rate, RFM segments, at-risk high-frequency customers)*

## 6. Operational / data issues
*(cancellations, stock adjustments, zero-price lines, duplicates; cite quality_before.csv)*

## 7. Recommendations
*(each tied to a finding; state it is a hypothesis to test, not a proven result)*

## 8. KPI definitions
Gross Sales, Cancelled Value, Net Revenue, Sales Invoices, Avg Invoice Value, Cancellation Rate - see `src/kpi_calculations.py` header.

## 9. Limitations
Single UK retailer, 2009-12-01..2011-12-09; GBP, no inflation adjustment; no cost/margin/category/discount/delivery data; cancellations not linked to original invoices; missing Customer IDs; product-code classification is a heuristic; partial first/last months.
