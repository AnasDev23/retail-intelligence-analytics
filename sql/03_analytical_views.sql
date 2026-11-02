/* =====================================================================================
   03 - Analytical views. KPI definitions match src/kpi_calculations.py:
     SalesValue  = LineRevenue of LineType='SALE'         AND ProductKind='PRODUCT'
     CancelValue = LineRevenue of LineType='CANCELLATION' AND ProductKind='PRODUCT' (negative)
     Net Revenue = SalesValue + CancelValue.    No cost / profit / margin exists in the source.
   ===================================================================================== */
USE RetailIntelligenceDB;
GO
CREATE OR ALTER VIEW dbo.vw_FactSales AS
SELECT f.InvoiceLineID, f.Invoice, f.LineType, f.StockCode, p.Description, p.ProductKind, f.CustomerID,
       c.Country, f.CountryKey, f.DateKey, f.InvoiceDate, d.FullDate, d.[Year], d.[Quarter], d.[Month], d.YearMonth,
       d.DayName, d.DayOfWeekNum, f.Quantity, f.UnitPrice, f.LineRevenue, f.IsDuplicateWithinSheet,
       CASE WHEN f.LineType = 'SALE' AND p.ProductKind = 'PRODUCT' THEN f.LineRevenue ELSE CAST(0 AS DECIMAL(19,4)) END AS SalesValue,
       CASE WHEN f.LineType = 'CANCELLATION' AND p.ProductKind = 'PRODUCT' THEN f.LineRevenue ELSE CAST(0 AS DECIMAL(19,4)) END AS CancelValue,
       CASE WHEN f.LineType = 'SALE' AND p.ProductKind = 'PRODUCT' THEN f.Quantity ELSE 0 END AS SaleUnits,
       CASE WHEN f.LineType = 'CANCELLATION' AND p.ProductKind = 'PRODUCT' THEN -f.Quantity ELSE 0 END AS CancelUnits,
       CASE WHEN f.LineType = 'SALE' AND p.ProductKind = 'PRODUCT' THEN 1 ELSE 0 END AS IsProductSaleLine
FROM dbo.FactInvoiceLines f
JOIN dbo.DimProducts  p ON p.StockCode = f.StockCode
JOIN dbo.DimCountries c ON c.CountryKey = f.CountryKey
JOIN dbo.DimDate      d ON d.DateKey = f.DateKey;
GO
CREATE OR ALTER VIEW dbo.vw_MonthlyRevenue AS
SELECT YearMonth, MIN([Year]) AS [Year], MIN([Month]) AS [Month],
       SUM(SalesValue) AS GrossSales, SUM(CancelValue) AS CancelledValue, SUM(SalesValue) + SUM(CancelValue) AS NetRevenue,
       COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN Invoice END) AS SalesInvoices
FROM dbo.vw_FactSales GROUP BY YearMonth;
GO
CREATE OR ALTER VIEW dbo.vw_ProductPerformance AS
SELECT StockCode, MAX(Description) AS Description,
       SUM(SaleUnits) AS UnitsSold, SUM(SalesValue) AS GrossSales, SUM(CancelUnits) AS UnitsCancelled,
       SUM(CancelValue) AS CancelledValue, SUM(SalesValue) + SUM(CancelValue) AS NetRevenue
FROM dbo.vw_FactSales WHERE ProductKind = 'PRODUCT' GROUP BY StockCode;
GO
CREATE OR ALTER VIEW dbo.vw_CountryPerformance AS
SELECT Country, SUM(SalesValue) AS GrossSales, SUM(CancelValue) AS CancelledValue,
       SUM(SalesValue) + SUM(CancelValue) AS NetRevenue,
       COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN Invoice END) AS SalesInvoices,
       COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN CustomerID END) AS Customers
FROM dbo.vw_FactSales GROUP BY Country;
GO
/* Invoice grain (product SALE lines only) - used for basket and invoice-value analysis */
CREATE OR ALTER VIEW dbo.vw_InvoiceSummary AS
SELECT Invoice, MIN(InvoiceDate) AS InvoiceDate, MAX(CustomerID) AS CustomerID, MAX(Country) AS Country,
       COUNT(*) AS LineCount, SUM(SaleUnits) AS Units, SUM(SalesValue) AS InvoiceValue
FROM dbo.vw_FactSales WHERE IsProductSaleLine = 1 GROUP BY Invoice;
GO
/* RFM on identified customers. Scores via NTILE(5) (5 = best). Ties are broken by CustomerID, so a few
   customers on tie boundaries can score differently from the Python rank-based implementation. */
CREATE OR ALTER VIEW dbo.vw_CustomerRFM AS
WITH base AS (
    SELECT CustomerID, MAX(InvoiceDate) AS LastPurchase, COUNT(*) AS Frequency, SUM(InvoiceValue) AS Monetary
    FROM dbo.vw_InvoiceSummary WHERE CustomerID IS NOT NULL GROUP BY CustomerID),
snap AS (SELECT DATEADD(DAY, 1, CAST(MAX(InvoiceDate) AS DATE)) AS SnapshotDate FROM dbo.vw_InvoiceSummary),
scored AS (
    SELECT b.*, DATEDIFF(DAY, b.LastPurchase, s.SnapshotDate) AS Recency,
           NTILE(5) OVER (ORDER BY b.LastPurchase, b.CustomerID) AS R,
           NTILE(5) OVER (ORDER BY b.Frequency,    b.CustomerID) AS F,
           NTILE(5) OVER (ORDER BY b.Monetary,     b.CustomerID) AS M
    FROM base b CROSS JOIN snap s)
SELECT CustomerID, LastPurchase, Recency, Frequency, Monetary, R, F, M,
       CASE WHEN R >= 4 AND F >= 4 THEN 'Champions'
            WHEN R >= 3 AND F >= 3 THEN 'Loyal Customers'
            WHEN R <= 2 AND F >= 4 THEN 'At Risk (high frequency)'
            WHEN R >= 4 AND F <= 2 THEN 'New / Recent'
            WHEN R <= 2 AND F <= 2 THEN 'Hibernating'
            ELSE 'Needs Attention' END AS Segment
FROM scored;
GO
