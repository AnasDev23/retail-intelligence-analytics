/* =====================================================================================
   06 - Optional reusable reporting procedures.
   ===================================================================================== */
USE RetailIntelligenceDB;
GO
CREATE OR ALTER PROCEDURE dbo.usp_MonthlyRevenue
    @StartDate DATE = NULL, @EndDate DATE = NULL, @Country NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT YearMonth, SUM(SalesValue) AS GrossSales, SUM(CancelValue) AS CancelledValue,
           SUM(SalesValue) + SUM(CancelValue) AS NetRevenue,
           COUNT(DISTINCT CASE WHEN IsProductSaleLine = 1 THEN Invoice END) AS SalesInvoices
    FROM dbo.vw_FactSales
    WHERE (@StartDate IS NULL OR FullDate >= @StartDate) AND (@EndDate IS NULL OR FullDate <= @EndDate)
      AND (@Country IS NULL OR Country = @Country)
    GROUP BY YearMonth ORDER BY YearMonth;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_TopProducts
    @TopN INT = 10, @Country NVARCHAR(100) = NULL, @StartDate DATE = NULL, @EndDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP (@TopN) StockCode, MAX(Description) AS Description, SUM(SaleUnits) AS UnitsSold, SUM(SalesValue) AS GrossSales,
           SUM(SalesValue) + SUM(CancelValue) AS NetRevenue
    FROM dbo.vw_FactSales
    WHERE ProductKind = 'PRODUCT' AND (@Country IS NULL OR Country = @Country)
      AND (@StartDate IS NULL OR FullDate >= @StartDate) AND (@EndDate IS NULL OR FullDate <= @EndDate)
    GROUP BY StockCode ORDER BY NetRevenue DESC;
END;
GO
CREATE OR ALTER PROCEDURE dbo.usp_CustomerProfile @CustomerID INT
AS
BEGIN
    SET NOCOUNT ON;
    SELECT r.CustomerID, r.LastPurchase, r.Recency, r.Frequency, r.Monetary, r.R, r.F, r.M, r.Segment
    FROM dbo.vw_CustomerRFM r WHERE r.CustomerID = @CustomerID;
    SELECT TOP (10) InvoiceDate, Invoice, Units, InvoiceValue FROM dbo.vw_InvoiceSummary
    WHERE CustomerID = @CustomerID ORDER BY InvoiceDate DESC;
END;
GO
-- Usage:  EXEC dbo.usp_MonthlyRevenue @Country = N'United Kingdom';   EXEC dbo.usp_TopProducts @TopN = 5;
