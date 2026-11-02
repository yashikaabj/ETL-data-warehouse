-- Scale the real warehouse fact table up {{mult}}x so indexing/partitioning effects become measurable.
-- Each copy k shifts every sale by k*37 days (wrapping inside 2024-01-01 .. 2027-12-31, the dim_date range)
-- and gets unique invoice/line ids. Rows are stored in date order, like a fact table loaded chronologically.
CREATE SCHEMA IF NOT EXISTS bench;
DROP TABLE IF EXISTS bench.fact_baseline CASCADE;
DROP TABLE IF EXISTS bench.fact_part CASCADE;
DROP TABLE IF EXISTS bench.fact_src CASCADE;

CREATE UNLOGGED TABLE bench.fact_src AS
SELECT s.k,
       s.k::BIGINT * 10000000 + f.posting_id    AS posting_id,
       s.k::BIGINT * 10000000 + f.postingdet_id AS postingdet_id,
       f.bill_no, f.doc_type,
       to_char(DATE '2024-01-01'
               + ((to_date(f.date_key::TEXT, 'YYYYMMDD') - DATE '2024-01-01' + s.k * 37) % 1461),
               'YYYYMMDD')::INT                 AS date_key,
       f.customer_key, f.product_key, f.qty, f.rate, f.amount
FROM dw.fact_sales_line f
CROSS JOIN generate_series(0, {{mult}} - 1) AS s(k)
ORDER BY date_key, k, postingdet_id;

ANALYZE bench.fact_src;
