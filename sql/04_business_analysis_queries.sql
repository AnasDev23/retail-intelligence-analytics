/* =====================================================================================
   04 - Business analysis queries (24). Run them one at a time (select + F5).
   All money is GBP. Revenue = product lines only (see 03). Cancellations are matched by VALUE,
   not by original invoice (source has no reference). No profit/discount/delivery questions
   are answered because the source contains no such fields.
   ===================================================================================== */
USE RetailIntelligenceDB;
GO
-- Q01  What are the headline KPIs for the whole period?
SELECT SUM(SalesValue) AS GrossSales, SUM(CancelValue) AS CancelledValue, SUM(SalesValue) + SUM(CancelValue) AS NetRevenue,
       COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN Invoice END) AS SalesInvoices,
       SUM(SalesValue) / NULLIF(COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN Invoice END), 0) AS AvgInvoiceValue,
       SUM(SaleUnits) AS UnitsSold, COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN CustomerID END) AS IdentifiedCustomers,
       100.0 * ABS(SUM(CancelValue)) / NULLIF(SUM(SalesValue), 0) AS CancellationRatePct
FROM dbo.vw_FactSales;

-- Q02  How does net revenue change month over month? (LAG)
SELECT YearMonth, NetRevenue, LAG(NetRevenue) OVER (ORDER BY YearMonth) AS PrevMonthNet,
       100.0 * (NetRevenue - LAG(NetRevenue) OVER (ORDER BY YearMonth)) / NULLIF(LAG(NetRevenue) OVER (ORDER BY YearMonth), 0) AS MoM_Pct
FROM dbo.vw_MonthlyRevenue ORDER BY YearMonth;
-- NOTE: first and last months of the data may be partial (check MIN/MAX InvoiceDate).

-- Q03  How does each month compare with the same month a year earlier? (LAG partitioned by month)
SELECT [Year], [Month], NetRevenue,
       LAG(NetRevenue) OVER (PARTITION BY [Month] ORDER BY [Year]) AS SameMonthPriorYear,
       100.0 * (NetRevenue - LAG(NetRevenue) OVER (PARTITION BY [Month] ORDER BY [Year]))
             / NULLIF(LAG(NetRevenue) OVER (PARTITION BY [Month] ORDER BY [Year]), 0) AS YoY_Pct
FROM dbo.vw_MonthlyRevenue ORDER BY [Year], [Month];

-- Q04  What is the cumulative (running) net revenue over time?
SELECT YearMonth, NetRevenue, SUM(NetRevenue) OVER (ORDER BY YearMonth ROWS UNBOUNDED PRECEDING) AS RunningNetRevenue
FROM dbo.vw_MonthlyRevenue ORDER BY YearMonth;

-- Q05  How much does each quarter contribute to total net revenue?
WITH q AS (SELECT [Year], [Quarter], SUM(SalesValue) + SUM(CancelValue) AS Net FROM dbo.vw_FactSales GROUP BY [Year], [Quarter])
SELECT [Year], [Quarter], Net, 100.0 * Net / NULLIF(SUM(Net) OVER (), 0) AS PctOfTotal FROM q ORDER BY [Year], [Quarter];

-- Q06  Which 10 products drive the most net revenue, and what share do they hold? (DENSE_RANK)
SELECT TOP (10) DENSE_RANK() OVER (ORDER BY NetRevenue DESC) AS RevenueRank, StockCode, Description, UnitsSold, NetRevenue,
       100.0 * NetRevenue / NULLIF(SUM(NetRevenue) OVER (), 0) AS PctOfNetRevenue
FROM dbo.vw_ProductPerformance ORDER BY NetRevenue DESC;

-- Q07  Which 10 products sell the most units? (ROW_NUMBER)
SELECT TOP (10) ROW_NUMBER() OVER (ORDER BY UnitsSold DESC, StockCode) AS UnitRank, StockCode, Description, UnitsSold, GrossSales
FROM dbo.vw_ProductPerformance ORDER BY UnitsSold DESC, StockCode;

-- Q08  How concentrated is revenue? How many products account for 80% of positive net revenue? (Pareto)
WITH p AS (SELECT StockCode, NetRevenue FROM dbo.vw_ProductPerformance WHERE NetRevenue > 0),
c AS (SELECT StockCode, NetRevenue, ROW_NUMBER() OVER (ORDER BY NetRevenue DESC) AS rn,
             SUM(NetRevenue) OVER (ORDER BY NetRevenue DESC ROWS UNBOUNDED PRECEDING) AS Cum,
             SUM(NetRevenue) OVER () AS Total FROM p)
SELECT MAX(rn) AS ProductsFor80Pct, (SELECT COUNT(*) FROM p) AS ProductsWithRevenue,
       100.0 * MAX(rn) / NULLIF((SELECT COUNT(*) FROM p), 0) AS PctOfProducts
FROM c WHERE Cum - NetRevenue < 0.8 * Total;

-- Q09  Which products with meaningful sales have the highest cancellation rate? (HAVING)
SELECT TOP (15) StockCode, Description, GrossSales, ABS(CancelledValue) AS CancelledAbs,
       100.0 * ABS(CancelledValue) / NULLIF(GrossSales, 0) AS CancellationRatePct
FROM dbo.vw_ProductPerformance
GROUP BY StockCode, Description, GrossSales, CancelledValue
HAVING GrossSales >= 1000
ORDER BY CancellationRatePct DESC;

-- Q10  Which price bands generate the revenue? (CASE)
SELECT CASE WHEN UnitPrice < 1 THEN '1) < 1' WHEN UnitPrice < 3 THEN '2) 1-2.99' WHEN UnitPrice < 5 THEN '3) 3-4.99'
            WHEN UnitPrice < 10 THEN '4) 5-9.99' ELSE '5) 10+' END AS PriceBand,
       SUM(SaleUnits) AS Units, SUM(SalesValue) AS GrossSales, 100.0 * SUM(SalesValue) / NULLIF(SUM(SUM(SalesValue)) OVER (), 0) AS PctOfSales
FROM dbo.vw_FactSales WHERE IsProductSaleLine = 1
GROUP BY CASE WHEN UnitPrice < 1 THEN '1) < 1' WHEN UnitPrice < 3 THEN '2) 1-2.99' WHEN UnitPrice < 5 THEN '3) 3-4.99'
              WHEN UnitPrice < 10 THEN '4) 5-9.99' ELSE '5) 10+' END
ORDER BY PriceBand;

-- Q11  Which countries generate the most net revenue and what is their share? (DENSE_RANK)
SELECT DENSE_RANK() OVER (ORDER BY NetRevenue DESC) AS CountryRank, Country, NetRevenue, SalesInvoices, Customers,
       GrossSales / NULLIF(SalesInvoices, 0) AS AvgInvoiceValue, 100.0 * NetRevenue / NULLIF(SUM(NetRevenue) OVER (), 0) AS PctOfNet
FROM dbo.vw_CountryPerformance ORDER BY NetRevenue DESC;

-- Q12  Which countries cancel more than the company average? (HAVING with scalar subquery)
SELECT Country, GrossSales, ABS(CancelledValue) AS CancelledAbs, 100.0 * ABS(CancelledValue) / NULLIF(GrossSales, 0) AS CancelRatePct
FROM dbo.vw_CountryPerformance
GROUP BY Country, GrossSales, CancelledValue
HAVING GrossSales > 0 AND ABS(CancelledValue) / NULLIF(GrossSales, 0) >
       (SELECT ABS(SUM(CancelValue)) / NULLIF(SUM(SalesValue), 0) FROM dbo.vw_FactSales)
ORDER BY CancelRatePct DESC;

-- Q13  Who are the top 20 identified customers by gross sales? (INNER JOIN to DimCustomers)
SELECT TOP (20) c.CustomerID, c.FirstSeen, c.LastSeen, SUM(s.SalesValue) AS GrossSales, COUNT(DISTINCT CASE WHEN s.IsProductSaleLine = 1 THEN s.Invoice END) AS Invoices
FROM dbo.DimCustomers c JOIN dbo.vw_FactSales s ON s.CustomerID = c.CustomerID
GROUP BY c.CustomerID, c.FirstSeen, c.LastSeen ORDER BY GrossSales DESC;

-- Q14  How much revenue comes from the top 10% of customers? (NTILE)
WITH cust AS (SELECT CustomerID, SUM(InvoiceValue) AS Value FROM dbo.vw_InvoiceSummary WHERE CustomerID IS NOT NULL GROUP BY CustomerID),
t AS (SELECT Value, NTILE(10) OVER (ORDER BY Value DESC) AS Decile FROM cust)
SELECT Decile, COUNT(*) AS Customers, SUM(Value) AS Revenue, 100.0 * SUM(Value) / NULLIF(SUM(SUM(Value)) OVER (), 0) AS PctOfCustomerRevenue
FROM t GROUP BY Decile ORDER BY Decile;

-- Q15  What share of identified customers buy more than once?
WITH f AS (SELECT CustomerID, COUNT(*) AS Invoices FROM dbo.vw_InvoiceSummary WHERE CustomerID IS NOT NULL GROUP BY CustomerID)
SELECT COUNT(*) AS Customers, SUM(CASE WHEN Invoices >= 2 THEN 1 ELSE 0 END) AS RepeatCustomers,
       100.0 * SUM(CASE WHEN Invoices >= 2 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0) AS RepeatRatePct FROM f;

-- Q16  How do RFM segments compare in size and revenue?
SELECT Segment, COUNT(*) AS Customers, SUM(Monetary) AS Revenue, AVG(CAST(Recency AS FLOAT)) AS AvgRecencyDays,
       AVG(CAST(Frequency AS FLOAT)) AS AvgFrequency, 100.0 * SUM(Monetary) / NULLIF(SUM(SUM(Monetary)) OVER (), 0) AS PctOfRevenue
FROM dbo.vw_CustomerRFM GROUP BY Segment ORDER BY Revenue DESC;

-- Q17  Cohort view: of customers first seen in each month, how many bought again in later months?
WITH first_m AS (SELECT CustomerID, CONVERT(CHAR(7), MIN(InvoiceDate), 120) AS CohortMonth FROM dbo.vw_InvoiceSummary WHERE CustomerID IS NOT NULL GROUP BY CustomerID),
act AS (SELECT DISTINCT i.CustomerID, CONVERT(CHAR(7), i.InvoiceDate, 120) AS ActiveMonth FROM dbo.vw_InvoiceSummary i WHERE i.CustomerID IS NOT NULL)
SELECT f.CohortMonth,
       DATEDIFF(MONTH, CAST(f.CohortMonth + '-01' AS DATE), CAST(a.ActiveMonth + '-01' AS DATE)) AS MonthsSinceFirst,
       COUNT(DISTINCT a.CustomerID) AS ActiveCustomers
FROM first_m f JOIN act a ON a.CustomerID = f.CustomerID
GROUP BY f.CohortMonth, DATEDIFF(MONTH, CAST(f.CohortMonth + '-01' AS DATE), CAST(a.ActiveMonth + '-01' AS DATE))
ORDER BY f.CohortMonth, MonthsSinceFirst;

-- Q18  How many days pass between a repeat customer's consecutive orders? (LAG / LEAD)
WITH o AS (SELECT CustomerID, InvoiceDate, LAG(InvoiceDate) OVER (PARTITION BY CustomerID ORDER BY InvoiceDate) AS PrevOrder,
                  LEAD(InvoiceDate) OVER (PARTITION BY CustomerID ORDER BY InvoiceDate) AS NextOrder
           FROM dbo.vw_InvoiceSummary WHERE CustomerID IS NOT NULL)
SELECT AVG(CAST(DATEDIFF(DAY, PrevOrder, InvoiceDate) AS FLOAT)) AS AvgDaysBetweenOrders,
       COUNT(PrevOrder) AS OrderPairs, COUNT(NextOrder) AS OrdersFollowedByAnother FROM o;

-- Q19  Which weekday and hour of day see the most sales?
SELECT DayName, DayOfWeekNum, DATEPART(HOUR, InvoiceDate) AS HourOfDay, SUM(SalesValue) AS GrossSales
FROM dbo.vw_FactSales WHERE IsProductSaleLine = 1
GROUP BY DayName, DayOfWeekNum, DATEPART(HOUR, InvoiceDate) ORDER BY DayOfWeekNum, HourOfDay;

-- Q20  How do cancellations trend by month?
SELECT YearMonth, GrossSales, ABS(CancelledValue) AS CancelledAbs, 100.0 * ABS(CancelledValue) / NULLIF(GrossSales, 0) AS CancelRatePct
FROM dbo.vw_MonthlyRevenue ORDER BY YearMonth;

-- Q21  Which line types exist and how much do they matter? (data-structure overview)
SELECT LineType, COUNT(*) AS Line_Count, COUNT(DISTINCT Invoice) AS Invoices, SUM(LineRevenue) AS Value
FROM dbo.FactInvoiceLines GROUP BY LineType ORDER BY Line_Count DESC;

-- Q22  Which registered customers have NO product sales (LEFT JOIN anti-pattern)? e.g. only cancellations/non-products
SELECT c.CustomerID, c.FirstSeen, c.LastSeen
FROM dbo.DimCustomers c
LEFT JOIN (SELECT DISTINCT CustomerID FROM dbo.vw_FactSales WHERE IsProductSaleLine = 1) s ON s.CustomerID = c.CustomerID
WHERE s.CustomerID IS NULL;

-- Q23  What does a typical basket look like (lines and units per invoice)?
SELECT COUNT(*) AS Invoices, AVG(CAST(LineCount AS FLOAT)) AS AvgLines, AVG(CAST(Units AS FLOAT)) AS AvgUnits, AVG(InvoiceValue) AS AvgValue,
       MAX(InvoiceValue) AS LargestInvoice FROM dbo.vw_InvoiceSummary;

-- Q24  How are invoices distributed by value band, and how much revenue does each band hold? (CASE + share)
SELECT CASE WHEN InvoiceValue < 50 THEN '1) < 50' WHEN InvoiceValue < 200 THEN '2) 50-199' WHEN InvoiceValue < 1000 THEN '3) 200-999'
            ELSE '4) 1000+' END AS InvoiceBand, COUNT(*) AS Invoices, SUM(InvoiceValue) AS Revenue,
       100.0 * SUM(InvoiceValue) / NULLIF(SUM(SUM(InvoiceValue)) OVER (), 0) AS PctOfRevenue
FROM dbo.vw_InvoiceSummary
GROUP BY CASE WHEN InvoiceValue < 50 THEN '1) < 50' WHEN InvoiceValue < 200 THEN '2) 50-199' WHEN InvoiceValue < 1000 THEN '3) 200-999' ELSE '4) 1000+' END
ORDER BY InvoiceBand;
GO
