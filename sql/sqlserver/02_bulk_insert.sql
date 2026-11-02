-- Edit the folder path (find & replace C:\etl-warehouse-dataset\data\) then run.
-- Files are UTF-8 with LF line endings and one header row.
BULK INSERT src.PHSTATE      FROM 'C:\etl-warehouse-dataset\data\PHSTATE.csv'      WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.PHHQ         FROM 'C:\etl-warehouse-dataset\data\PHHQ.csv'         WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.PHPARTY_A    FROM 'C:\etl-warehouse-dataset\data\PHPARTY_A.csv'    WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.PHITEM       FROM 'C:\etl-warehouse-dataset\data\PHITEM.csv'       WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.PHPOSTING    FROM 'C:\etl-warehouse-dataset\data\PHPOSTING.csv'    WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.PHPOSTINGDET FROM 'C:\etl-warehouse-dataset\data\PHPOSTINGDET.csv' WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK);
BULK INSERT src.EMPLOYEE     FROM 'C:\etl-warehouse-dataset\data\EMPLOYEE.csv'     WITH (FIRSTROW = 2, FIELDTERMINATOR = ',', ROWTERMINATOR = '0x0a', CODEPAGE = '65001', TABLOCK, KEEPNULLS);
