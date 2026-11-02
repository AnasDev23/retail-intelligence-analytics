/* =====================================================================================
   05 - Data quality & reconciliation. Result columns: CheckName, Severity, IssueCount, Note.
   Severity: ERROR (stop/fix) | WARNING (review) | INFO (descriptive).
   ===================================================================================== */
USE RetailIntelligenceDB;
GO
SELECT * FROM (
    SELECT 'rejected_rows' AS CheckName, 'WARNING' AS Severity, COUNT(*) AS IssueCount, 'Rows with unparseable/missing key fields (dbo.RejectedRows)' AS Note FROM dbo.RejectedRows
    UNION ALL SELECT 'staging_lines_not_in_fact (overlap + rejected)', 'INFO',
        (SELECT COUNT(*) FROM dbo.stg_InvoiceLines) - (SELECT COUNT(*) FROM dbo.FactInvoiceLines), 'Cross-sheet exact duplicates removed plus rejected rows'
    UNION ALL SELECT 'missing_customer_id', 'INFO', COUNT(*), 'Fact lines without Customer ID (kept)' FROM dbo.FactInvoiceLines WHERE CustomerID IS NULL
    UNION ALL SELECT 'missing_description', 'WARNING', COUNT(*), 'Products whose description is missing' FROM dbo.DimProducts WHERE Description IS NULL
    UNION ALL SELECT 'zero_price_lines', 'WARNING', COUNT(*), 'UnitPrice = 0' FROM dbo.FactInvoiceLines WHERE UnitPrice = 0
    UNION ALL SELECT 'negative_price_lines', 'WARNING', COUNT(*), 'UnitPrice < 0' FROM dbo.FactInvoiceLines WHERE UnitPrice < 0
    UNION ALL SELECT 'cancellation_lines_with_positive_quantity', 'ERROR', COUNT(*), 'C-invoices should have Quantity < 0' FROM dbo.FactInvoiceLines WHERE LineType = 'CANCELLATION' AND Quantity > 0
    UNION ALL SELECT 'sale_lines_with_nonpositive_quantity', 'ERROR', COUNT(*), 'SALE must have Quantity > 0' FROM dbo.FactInvoiceLines WHERE LineType = 'SALE' AND Quantity <= 0
    UNION ALL SELECT 'stock_adjustment_lines', 'WARNING', COUNT(*), 'Negative quantity without C prefix' FROM dbo.FactInvoiceLines WHERE LineType = 'STOCK_ADJUSTMENT'
    UNION ALL SELECT 'flagged_exact_duplicate_lines', 'WARNING', COUNT(*), 'Repeated identical lines within a sheet (retained, flagged)' FROM dbo.FactInvoiceLines WHERE IsDuplicateWithinSheet = 1
    UNION ALL SELECT 'invoices_with_multiple_customers', 'WARNING', COUNT(*), 'Invoices with >1 distinct Customer ID'
        FROM (SELECT Invoice FROM dbo.FactInvoiceLines WHERE CustomerID IS NOT NULL GROUP BY Invoice HAVING COUNT(DISTINCT CustomerID) > 1) x
    UNION ALL SELECT 'invoices_with_multiple_countries', 'WARNING', COUNT(*), 'Invoices with >1 country'
        FROM (SELECT Invoice FROM dbo.FactInvoiceLines GROUP BY Invoice HAVING COUNT(DISTINCT CountryKey) > 1) x
    UNION ALL SELECT 'products_with_multiple_descriptions', 'INFO', COUNT(*), 'StockCodes with several description spellings' FROM dbo.DimProducts WHERE DescriptionVariants > 1
    UNION ALL SELECT 'non_product_stockcodes', 'INFO', COUNT(*), 'Codes like postage/fees (excluded from product KPIs)' FROM dbo.DimProducts WHERE ProductKind = 'NON_PRODUCT'
    UNION ALL SELECT 'dates_outside_documented_range', 'WARNING', COUNT(*), 'Outside 2009-12-01..2011-12-09 (UCI documentation)' FROM dbo.FactInvoiceLines WHERE InvoiceDate < '2009-12-01' OR InvoiceDate >= '2011-12-10'
) q ORDER BY CASE Severity WHEN 'ERROR' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END, CheckName;

-- Reconciliation: each row must show Passed = 1
SELECT 'sum by LineType = sum of all lines' AS Reconciliation,
       (SELECT SUM(LineRevenue) FROM dbo.FactInvoiceLines) AS Expected,
       (SELECT SUM(v) FROM (SELECT SUM(LineRevenue) AS v FROM dbo.FactInvoiceLines GROUP BY LineType) t) AS Actual,
       CASE WHEN ABS((SELECT SUM(LineRevenue) FROM dbo.FactInvoiceLines) - (SELECT SUM(v) FROM (SELECT SUM(LineRevenue) AS v FROM dbo.FactInvoiceLines GROUP BY LineType) t)) <= 0.01 THEN 1 ELSE 0 END AS Passed
UNION ALL
SELECT 'view net revenue = fact SALE+CANCELLATION (products)',
       (SELECT SUM(f.LineRevenue) FROM dbo.FactInvoiceLines f JOIN dbo.DimProducts p ON p.StockCode = f.StockCode WHERE p.ProductKind = 'PRODUCT' AND f.LineType IN ('SALE','CANCELLATION')),
       (SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue),
       CASE WHEN ABS((SELECT SUM(f.LineRevenue) FROM dbo.FactInvoiceLines f JOIN dbo.DimProducts p ON p.StockCode = f.StockCode WHERE p.ProductKind = 'PRODUCT' AND f.LineType IN ('SALE','CANCELLATION')) - (SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue)) <= 0.01 THEN 1 ELSE 0 END
UNION ALL
SELECT 'country view net = monthly view net', (SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue), (SELECT SUM(NetRevenue) FROM dbo.vw_CountryPerformance),
       CASE WHEN ABS((SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue) - (SELECT SUM(NetRevenue) FROM dbo.vw_CountryPerformance)) <= 0.01 THEN 1 ELSE 0 END
UNION ALL
SELECT 'product view net = monthly view net', (SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue), (SELECT SUM(NetRevenue) FROM dbo.vw_ProductPerformance),
       CASE WHEN ABS((SELECT SUM(NetRevenue) FROM dbo.vw_MonthlyRevenue) - (SELECT SUM(NetRevenue) FROM dbo.vw_ProductPerformance)) <= 0.01 THEN 1 ELSE 0 END;
GO
