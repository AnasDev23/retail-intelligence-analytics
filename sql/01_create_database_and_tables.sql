/* =====================================================================================
   01 - Create database and tables            Target: SQL Server 2017+ (Express is fine)
   Dataset : UCI "Online Retail II" (Daqing Chen, CC BY 4.0) - real transactions, GBP.

   MODEL (star schema derived ONLY from fields that exist in the source):
     FactInvoiceLines  GRAIN = one invoice line (one product on one invoice) as recorded in
                       the source workbook, after removal of exact cross-sheet overlap rows.
     DimProducts   (StockCode)      DimCustomers (CustomerID)
     DimCountries  (CountryKey)     DimDate      (DateKey = yyyymmdd)
   Relationships: Fact.StockCode->DimProducts, Fact.CustomerID->DimCustomers (NULLABLE: many
   lines have no Customer ID in the source), Fact.CountryKey->DimCountries, Fact.DateKey->DimDate.
   The source has NO category, cost, profit, discount or delivery fields: none are invented.

   Loading flow:  CSV -> dbo.stg_InvoiceLines (typed copy of source) -> dims + fact (script 02).
   ===================================================================================== */
IF DB_ID(N'RetailIntelligenceDB') IS NULL
    CREATE DATABASE RetailIntelligenceDB;
GO
USE RetailIntelligenceDB;
GO
DROP TABLE IF EXISTS dbo.FactInvoiceLines;
DROP TABLE IF EXISTS dbo.DimProducts;
DROP TABLE IF EXISTS dbo.DimCustomers;
DROP TABLE IF EXISTS dbo.DimCountries;
DROP TABLE IF EXISTS dbo.DimDate;
DROP TABLE IF EXISTS dbo.RejectedRows;
DROP TABLE IF EXISTS dbo.stg_InvoiceLines;
GO
/* Staging: mirrors data/processed/stg_invoice_lines.csv (both workbook sheets, source values) */
CREATE TABLE dbo.stg_InvoiceLines (
    Invoice      NVARCHAR(30)   NULL,
    StockCode    NVARCHAR(50)   NULL,
    Description  NVARCHAR(500)  NULL,
    Quantity     INT            NULL,
    InvoiceDate  DATETIME2(0)   NULL,
    UnitPrice    DECIMAL(18,4)  NULL,
    CustomerID   INT            NULL,
    Country      NVARCHAR(100)  NULL,
    SourceSheet  NVARCHAR(100)  NOT NULL,
    SourceRow    INT            NOT NULL
);
CREATE TABLE dbo.RejectedRows (
    SourceSheet NVARCHAR(100) NOT NULL, SourceRow INT NOT NULL, RejectReason NVARCHAR(200) NOT NULL,
    CONSTRAINT PK_RejectedRows PRIMARY KEY (SourceSheet, SourceRow)
);
CREATE TABLE dbo.DimCountries (
    CountryKey INT IDENTITY(1,1) CONSTRAINT PK_DimCountries PRIMARY KEY,
    Country    NVARCHAR(100) NOT NULL CONSTRAINT UQ_DimCountries_Country UNIQUE
);
CREATE TABLE dbo.DimProducts (
    StockCode           NVARCHAR(30)  NOT NULL CONSTRAINT PK_DimProducts PRIMARY KEY,
    Description         NVARCHAR(500) NULL,      -- most frequent description for the code
    ProductKind         VARCHAR(12)   NOT NULL CONSTRAINT CK_DimProducts_Kind CHECK (ProductKind IN ('PRODUCT','NON_PRODUCT')),
    DescriptionVariants INT           NOT NULL
);
CREATE TABLE dbo.DimCustomers (
    CustomerID INT NOT NULL CONSTRAINT PK_DimCustomers PRIMARY KEY,   -- pseudonymous ID from source
    FirstSeen  DATETIME2(0) NOT NULL,
    LastSeen   DATETIME2(0) NOT NULL
);
CREATE TABLE dbo.DimDate (
    DateKey INT NOT NULL CONSTRAINT PK_DimDate PRIMARY KEY,
    FullDate DATE NOT NULL, [Year] INT NOT NULL, [Quarter] INT NOT NULL, [Month] INT NOT NULL,
    MonthName NVARCHAR(20) NOT NULL, YearMonth CHAR(7) NOT NULL,
    DayOfWeekNum INT NOT NULL, DayName NVARCHAR(20) NOT NULL
);
CREATE TABLE dbo.FactInvoiceLines (
    InvoiceLineID INT IDENTITY(1,1) CONSTRAINT PK_FactInvoiceLines PRIMARY KEY,
    Invoice       NVARCHAR(30)  NOT NULL,
    LineType      VARCHAR(20)   NOT NULL,
    StockCode     NVARCHAR(30)  NOT NULL CONSTRAINT FK_Fact_Product  FOREIGN KEY REFERENCES dbo.DimProducts(StockCode),
    CustomerID    INT           NULL     CONSTRAINT FK_Fact_Customer FOREIGN KEY REFERENCES dbo.DimCustomers(CustomerID),
    CountryKey    INT           NOT NULL CONSTRAINT FK_Fact_Country  FOREIGN KEY REFERENCES dbo.DimCountries(CountryKey),
    DateKey       INT           NOT NULL CONSTRAINT FK_Fact_Date     FOREIGN KEY REFERENCES dbo.DimDate(DateKey),
    InvoiceDate   DATETIME2(0)  NOT NULL,
    Quantity      INT           NOT NULL,
    UnitPrice     DECIMAL(18,4) NOT NULL,
    LineRevenue   AS (CAST(Quantity AS DECIMAL(19,4)) * UnitPrice) PERSISTED,   -- derived: Quantity x UnitPrice
    IsDuplicateWithinSheet BIT  NOT NULL,
    SourceSheet   NVARCHAR(100) NOT NULL,
    SourceRow     INT           NOT NULL,
    CONSTRAINT CK_Fact_LineType CHECK (LineType IN ('SALE','CANCELLATION','ADJUSTMENT','STOCK_ADJUSTMENT','ZERO_PRICE','OTHER_ANOMALY')),
    CONSTRAINT UQ_Fact_Source UNIQUE (SourceSheet, SourceRow)
);
CREATE INDEX IX_Fact_DateKey   ON dbo.FactInvoiceLines (DateKey) INCLUDE (LineType, Quantity, UnitPrice);
CREATE INDEX IX_Fact_Customer  ON dbo.FactInvoiceLines (CustomerID) INCLUDE (Invoice, InvoiceDate, LineType);
CREATE INDEX IX_Fact_Product   ON dbo.FactInvoiceLines (StockCode) INCLUDE (LineType, Quantity, UnitPrice);
CREATE INDEX IX_Fact_Country   ON dbo.FactInvoiceLines (CountryKey);
CREATE INDEX IX_Fact_Invoice   ON dbo.FactInvoiceLines (Invoice);
GO
PRINT 'Tables created.';
