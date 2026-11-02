-- Stage 3: covering indexes. The INCLUDE columns let Postgres answer the report queries from the index alone
-- (index-only scans, no table lookups). They replace the single-column date/customer/product indexes.
DROP INDEX bench.ix_fact_date;
DROP INDEX bench.ix_fact_customer;
DROP INDEX bench.ix_fact_product;
CREATE INDEX ix_fact_date_cover ON bench.fact_baseline (date_key)               INCLUDE (product_key, amount);
CREATE INDEX ix_fact_cust_cover ON bench.fact_baseline (customer_key, date_key) INCLUDE (amount);
