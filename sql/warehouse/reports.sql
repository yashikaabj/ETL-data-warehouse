-- Sample queries on the star schema. Run after the ETL: psql -d warehouse -f sql/warehouse/reports.sql

-- 1. Monthly sales (Indian fiscal year shown)
SELECT d.fiscal_year, d.year, d.month, d.month_name,
       COUNT(DISTINCT f.posting_id) AS invoices, SUM(f.amount) AS sales
FROM dw.fact_sales_line f JOIN dw.dim_date d USING (date_key)
GROUP BY d.fiscal_year, d.year, d.month, d.month_name
ORDER BY d.year, d.month;

-- 2. Top 5 states by sales (state as of the posting date, thanks to SCD2)
SELECT g.state_name, SUM(f.amount) AS sales, COUNT(DISTINCT c.cust_id) AS customers
FROM dw.fact_sales_line f
JOIN dw.dim_customer c  USING (customer_key)
JOIN dw.dim_geography g ON g.hq_key = c.hq_key
GROUP BY g.state_name ORDER BY sales DESC LIMIT 5;

-- 3. Category and brand performance
SELECT p.category, p.brand, SUM(f.qty) AS units, SUM(f.amount) AS sales
FROM dw.fact_sales_line f JOIN dw.dim_product p USING (product_key)
GROUP BY p.category, p.brand ORDER BY sales DESC LIMIT 10;

-- 4. Customers who changed HQ (the SCD2 history)
SELECT c.cust_id, c.cust_name, g.hq_name, g.state_name, c.valid_from, c.valid_to, c.is_current
FROM dw.dim_customer c JOIN dw.dim_geography g USING (hq_key)
WHERE c.cust_id IN (SELECT cust_id FROM dw.dim_customer GROUP BY cust_id HAVING COUNT(*) > 1)
ORDER BY c.cust_id, c.valid_from LIMIT 10;

-- 5. How much revenue carries a data-quality flag?
SELECT COALESCE(dq_flags, 'CLEAN') AS flags, COUNT(*) AS lines, SUM(amount) AS sales
FROM dw.fact_sales_line GROUP BY 1 ORDER BY lines DESC;

-- 6. Last ETL runs
SELECT r.run_id, r.source_schema, r.status, r.started_at::timestamp(0), SUM(s.rows_affected) FILTER (WHERE s.step LIKE '06%upsert%') AS fact_rows
FROM audit.etl_run r LEFT JOIN audit.etl_step_log s USING (run_id)
GROUP BY r.run_id ORDER BY r.run_id DESC LIMIT 5;
