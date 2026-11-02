/* =====================================================================================
   02 - Load CSV into staging, transform into the model, validate.
   PREREQUISITE: run `python scripts/prepare_data.py` first (creates data/processed/.csv).

  STEP A  Copy data\processed\stg_invoice_lines.csv to a folder the SQL Server SERVICE
           ACCOUNT can read (e.g. C:\RetailData). BULK INSERT reads from the SERVER's view of the
           file system; files under your user profile are often NOT readable by the service.
   STEP B  Edit @DataFolder below.
   ALTERNATIVE (no file permissions needed): SSMS > right-click RetailIntelligenceDB >
           Tasks > Import Flat File..., choose stg_invoice_lines.csv, target table
           dbo.stg_InvoiceLines (existing table), map columns by name, then run from STEP 2 below.
   =====================================================================================  */

USE RetailIntelligenceDB;
GO
SET NOCOUNT ON;
TRUNCATE TABLE dbo.stg_InvoiceLines;

DECLARE @DataFolder NVARCHAR(400) = N'D:\Anas\Retail_Intelligence_Portfolio\data\processed';          -- <<< EDIT (no trailing backslash)
DECLARE @sql NVARCHAR(MAX) = N'BULK INSERT dbo.stg_InvoiceLines FROM ''' + @DataFolder + N'\stg_invoice_lines.csv''
  WITH (FORMAT = ''CSV'', FIRSTROW = 2, FIELDQUOTE = ''"'', FIELDTERMINATOR = '','', ROWTERMINATOR = ''0x0a'',
        CODEPAGE = ''65001'', KEEPNULLS, TABLOCK);';
EXEC sys.sp_executesql @sql;
SELECT COUNT(*) AS StagingRows FROM dbo.stg_InvoiceLines;   -- compare: reports/pipeline_summary.json -> staging_rows
GO
/* -------- STEP 2: transform (idempotent: clears model tables first) ------------------------- */
DELETE FROM dbo.FactInvoiceLines; DELETE FROM dbo.DimProducts; DELETE FROM dbo.DimCustomers;
DELETE FROM dbo.DimCountries;     DELETE FROM dbo.DimDate;     DELETE FROM dbo.RejectedRows;
DBCC CHECKIDENT ('dbo.DimCountries', RESEED, 0) WITH NO_INFOMSGS;
DBCC CHECKIDENT ('dbo.FactInvoiceLines', RESEED, 0) WITH NO_INFOMSGS;

-- 2.1 Normalise text (TRIM; StockCode UPPER; empty description -> NULL). Mirrors src/data_cleaning.normalize_text
DROP TABLE IF EXISTS #norm;
SELECT LTRIM(RTRIM(Invoice)) AS Invoice, UPPER(LTRIM(RTRIM(StockCode))) AS StockCode,
       NULLIF(LTRIM(RTRIM(Description)), N'') AS Description, Quantity, InvoiceDate, UnitPrice, CustomerID,
       ISNULL(LTRIM(RTRIM(Country)), N'(missing)') AS Country, SourceSheet, SourceRow
INTO #norm FROM dbo.stg_InvoiceLines;

-- 2.2 Rejected rows: cannot be interpreted (reported, not silently dropped)
INSERT INTO dbo.RejectedRows (SourceSheet, SourceRow, RejectReason)
SELECT SourceSheet, SourceRow,
       CONCAT_WS(';', CASE WHEN Invoice IS NULL THEN 'missing_invoice' END,
                      CASE WHEN StockCode IS NULL THEN 'missing_stockcode' END,
                      CASE WHEN InvoiceDate IS NULL THEN 'invalid_or_missing_date' END,
                      CASE WHEN Quantity IS NULL THEN 'invalid_or_missing_quantity' END,
                      CASE WHEN UnitPrice IS NULL THEN 'invalid_or_missing_price' END)
FROM #norm
WHERE Invoice IS NULL OR StockCode IS NULL OR InvoiceDate IS NULL OR Quantity IS NULL OR UnitPrice IS NULL;

-- 2.3 Remove exact cross-sheet overlap (later sheet rows identical, incl. occurrence number, to earlier sheet rows)
DROP TABLE IF EXISTS #usable;
SELECT n.*, ROW_NUMBER() OVER (PARTITION BY n.Invoice, n.StockCode, ISNULL(n.Description, N'<NA>'), n.Quantity,
            n.InvoiceDate, n.UnitPrice, ISNULL(n.CustomerID, -1), n.Country, n.SourceSheet ORDER BY n.SourceRow) AS Occ
INTO #usable
FROM #norm n
WHERE n.Invoice IS NOT NULL AND n.StockCode IS NOT NULL AND n.InvoiceDate IS NOT NULL
  AND n.Quantity IS NOT NULL AND n.UnitPrice IS NOT NULL;

DROP TABLE IF EXISTS #sheetorder;
SELECT SourceSheet, ROW_NUMBER() OVER (ORDER BY MIN(InvoiceDate)) AS SheetRank
INTO #sheetorder FROM #usable GROUP BY SourceSheet;

DROP TABLE IF EXISTS #deduped;
SELECT u.* INTO #deduped
FROM #usable u
JOIN #sheetorder so ON so.SourceSheet = u.SourceSheet
WHERE NOT EXISTS (
    SELECT 1 FROM #usable e
    JOIN #sheetorder eo ON eo.SourceSheet = e.SourceSheet AND eo.SheetRank = so.SheetRank - 1
    WHERE e.Invoice = u.Invoice AND e.StockCode = u.StockCode
      AND ISNULL(e.Description, N'<NA>') = ISNULL(u.Description, N'<NA>')
      AND e.Quantity = u.Quantity AND e.InvoiceDate = u.InvoiceDate AND e.UnitPrice = u.UnitPrice
      AND ISNULL(e.CustomerID, -1) = ISNULL(u.CustomerID, -1) AND e.Country = u.Country AND e.Occ = u.Occ);

-- 2.4 Classify lines (mirrors src/data_cleaning.classify_lines; first matching rule wins) + duplicate flag
DROP TABLE IF EXISTS #final;
SELECT d.*,
       CASE WHEN UPPER(d.Invoice) LIKE 'C%' THEN 'CANCELLATION'
            WHEN UPPER(d.Invoice) LIKE 'A%' THEN 'ADJUSTMENT'
            WHEN d.UnitPrice < 0            THEN 'OTHER_ANOMALY'
            WHEN d.Quantity <= 0            THEN 'STOCK_ADJUSTMENT'
            WHEN d.UnitPrice = 0            THEN 'ZERO_PRICE'
            ELSE 'SALE' END AS LineType,
       CASE WHEN ROW_NUMBER() OVER (PARTITION BY d.Invoice, d.StockCode, ISNULL(d.Description, N'<NA>'), d.Quantity,
                 d.InvoiceDate, d.UnitPrice, ISNULL(d.CustomerID, -1), d.Country, d.SourceSheet ORDER BY d.SourceRow) > 1
            THEN 1 ELSE 0 END AS IsDup
INTO #final FROM #deduped d;

-- 2.5 Dimensions
INSERT INTO dbo.DimCountries (Country) SELECT DISTINCT Country FROM #final ORDER BY Country;

;WITH cnt AS (
    SELECT StockCode, Description, COUNT(*) AS n FROM #final WHERE Description IS NOT NULL GROUP BY StockCode, Description),
best AS (SELECT StockCode, Description, ROW_NUMBER() OVER (PARTITION BY StockCode ORDER BY n DESC, Description) AS rn FROM cnt),
variants AS (SELECT StockCode, COUNT(*) AS v FROM cnt GROUP BY StockCode)
INSERT INTO dbo.DimProducts (StockCode, Description, ProductKind, DescriptionVariants)
SELECT s.StockCode, b.Description,
       CASE WHEN s.StockCode COLLATE Latin1_General_BIN LIKE '[0-9][0-9][0-9][0-9][0-9]'
              OR s.StockCode COLLATE Latin1_General_BIN LIKE '[0-9][0-9][0-9][0-9][0-9][A-Z]'
              OR s.StockCode COLLATE Latin1_General_BIN LIKE '[0-9][0-9][0-9][0-9][0-9][A-Z][A-Z]'
            THEN 'PRODUCT' ELSE 'NON_PRODUCT' END,
       ISNULL(v.v, 0)
FROM (SELECT DISTINCT StockCode FROM #final) s
LEFT JOIN best b ON b.StockCode = s.StockCode AND b.rn = 1
LEFT JOIN variants v ON v.StockCode = s.StockCode;

INSERT INTO dbo.DimCustomers (CustomerID, FirstSeen, LastSeen)
SELECT CustomerID, MIN(InvoiceDate), MAX(InvoiceDate) FROM #final WHERE CustomerID IS NOT NULL GROUP BY CustomerID;

DECLARE @minD DATE = (SELECT MIN(CAST(InvoiceDate AS DATE)) FROM #final);
DECLARE @maxD DATE = (SELECT MAX(CAST(InvoiceDate AS DATE)) FROM #final);
;WITH dates AS (SELECT @minD AS d UNION ALL SELECT DATEADD(DAY, 1, d) FROM dates WHERE d < @maxD)
INSERT INTO dbo.DimDate (DateKey, FullDate, [Year], [Quarter], [Month], MonthName, YearMonth, DayOfWeekNum, DayName)
SELECT YEAR(d) * 10000 + MONTH(d) * 100 + DAY(d), d, YEAR(d), DATEPART(QUARTER, d), MONTH(d), DATENAME(MONTH, d),
       CONVERT(CHAR(7), d, 120), DATEPART(WEEKDAY, d), DATENAME(WEEKDAY, d)
FROM dates OPTION (MAXRECURSION 0);

-- 2.6 Fact
INSERT INTO dbo.FactInvoiceLines (Invoice, LineType, StockCode, CustomerID, CountryKey, DateKey, InvoiceDate,
                                  Quantity, UnitPrice, IsDuplicateWithinSheet, SourceSheet, SourceRow)
SELECT f.Invoice, f.LineType, f.StockCode, f.CustomerID, c.CountryKey,
       YEAR(f.InvoiceDate) * 10000 + MONTH(f.InvoiceDate) * 100 + DAY(f.InvoiceDate),
       f.InvoiceDate, f.Quantity, f.UnitPrice, f.IsDup, f.SourceSheet, f.SourceRow
FROM #final f JOIN dbo.DimCountries c ON c.Country = f.Country
ORDER BY f.SourceSheet, f.SourceRow;
GO
/* -------- STEP 3: post-import validation (compare with data/processed/reports/pipeline_summary.json) ----- */
SELECT 'staging_rows' AS metric, COUNT(*) AS value FROM dbo.stg_InvoiceLines
UNION ALL SELECT 'rejected_rows', COUNT(*) FROM dbo.RejectedRows
UNION ALL SELECT 'fact_rows', COUNT(*) FROM dbo.FactInvoiceLines;            -- expect = fact_rows in JSON

SELECT LineType, COUNT(*) AS Lines FROM dbo.FactInvoiceLines GROUP BY LineType ORDER BY Lines DESC;  -- = line_type_counts

SELECT SUM(CASE WHEN f.LineType = 'SALE' THEN f.LineRevenue END)         AS GrossSalesProduct,         -- = gross_sales_product
       SUM(CASE WHEN f.LineType = 'CANCELLATION' THEN f.LineRevenue END) AS CancelledValueProduct,     -- = cancelled_value_product
       SUM(CASE WHEN f.LineType IN ('SALE','CANCELLATION') THEN f.LineRevenue END) AS NetRevenueProduct -- = net_revenue_product
FROM dbo.FactInvoiceLines f JOIN dbo.DimProducts p ON p.StockCode = f.StockCode WHERE p.ProductKind = 'PRODUCT';

SELECT MIN(InvoiceDate) AS MinDate, MAX(InvoiceDate) AS MaxDate FROM dbo.FactInvoiceLines;          -- = min_date/max_date
-- Orphan checks (must all be 0 - the FKs enforce this, shown for documentation)
SELECT (SELECT COUNT(*) FROM dbo.FactInvoiceLines f LEFT JOIN dbo.DimProducts p ON p.StockCode = f.StockCode WHERE p.StockCode IS NULL) AS OrphanProducts,
       (SELECT COUNT(*) FROM dbo.FactInvoiceLines f LEFT JOIN dbo.DimDate d ON d.DateKey = f.DateKey WHERE d.DateKey IS NULL) AS OrphanDates;
GO
