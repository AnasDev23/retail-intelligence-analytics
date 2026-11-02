# Portfolio Walkthrough (5-minute demo script)
1. **Problem** - a UK online gift-ware wholesaler/retailer wants to understand revenue, customers, products, countries and cancellations. Real, public data (UCI, CC BY 4.0).
2. **Provenance & ethics** - official source, license attribution, pseudonymous customer IDs, no re-identification.
3. **Data challenges** - show `reports/quality_before.csv` and `cleaning_log.csv`: cancellations kept as events, overlapping sheets, missing customers, non-product codes.
4. **SQL** - staging -> star schema -> views -> 24 queries (CTEs, windows, LAG/LEAD, NTILE, cohorts). Show Q02/Q03/Q14/Q17.
5. **Python** - modular pipeline and tests; KPI definitions shared by SQL and Python; reconciliation checks.
6. **Dashboard** - walk the five tabs; change filters; show insights recomputing.
7. **Honesty slide** - no cost data -> no margin; no categories; cancellations not linked; what you would do next.
Only describe results you have personally run and checked. Do not claim work experience this project is not.
