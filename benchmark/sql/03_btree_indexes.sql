-- Stage 2: the usual "add an index on every column we filter or join on".
CREATE INDEX ix_fact_date     ON bench.fact_baseline (date_key);
CREATE INDEX ix_fact_customer ON bench.fact_baseline (customer_key);
CREATE INDEX ix_fact_product  ON bench.fact_baseline (product_key);
CREATE INDEX ix_fact_posting  ON bench.fact_baseline (posting_id);
