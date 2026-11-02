# Dataset Selection Record (researched 2026-10-20)

| Criterion | UCI Online Retail II (SELECTED) | Olist Brazilian E-Commerce (Kaggle) | UCI Online Retail (first version) |
|---|---|---|---|
| Publisher | UCI ML Repository; creator Daqing Chen (verified on UCI page) | Olist (via Kaggle) | UCI ML Repository |
| License | CC BY 4.0, stated on the UCI page (verified) | **Not verified**: Kaggle page content could not be retrieved during research; I did not assume one | Not re-verified in this research |
| Access | Direct HTTPS download, no login (verified link) | Kaggle download requires login | UCI |
| Size | 1,067,371 instances, one workbook of 43.5 MB (UCI page) | ~100k orders, 9 CSV tables (secondary descriptions) | Smaller, one period |
| Schema | Flat transaction lines (8 fields) | Relational, richer (payments, reviews, delivery) | Flat |
| Cancellations | Explicit C-invoices + negative quantities (real cleaning challenges) | Order status field | Same convention |

**Decision:** Online Retail II. It is the only candidate whose license and no-login download I could verify from the official source, it has over one million real lines, two years of dates, and genuine data-quality problems (cancellations, missing customer IDs, non-product codes, overlapping sheets, repeated lines).
**Trade-off acknowledged:** it is a flat file, so the star schema is derived (products, customers, countries, dates) from existing fields only; Olist would offer a richer native relational model if its license is confirmed and you accept Kaggle login.
