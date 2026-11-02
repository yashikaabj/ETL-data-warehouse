-- Stage 4: the same table range-partitioned by month on date_key, with the same covering indexes.
-- Note: a primary/unique key on a partitioned table must include the partition column.
CREATE TABLE bench.fact_part (
    sales_line_key   BIGINT GENERATED ALWAYS AS IDENTITY,
    postingdet_id    BIGINT        NOT NULL,
    posting_id       BIGINT        NOT NULL,
    bill_no          INT,
    doc_type         TEXT          NOT NULL,
    date_key         INT           NOT NULL,
    customer_key     INT           NOT NULL,
    product_key      INT           NOT NULL,
    qty              NUMERIC(12,2) NOT NULL,
    rate             NUMERIC(14,2) NOT NULL,
    amount           NUMERIC(14,2) NOT NULL,
    amount_corrected BOOLEAN       NOT NULL DEFAULT FALSE,
    dq_flags         TEXT,
    run_id           INT           NOT NULL DEFAULT 1,
    loaded_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
) PARTITION BY RANGE (date_key);

DO $$
DECLARE d DATE := DATE '2024-01-01';
BEGIN
    WHILE d < DATE '2028-01-01' LOOP
        EXECUTE format('CREATE TABLE bench.fact_part_%s PARTITION OF bench.fact_part FOR VALUES FROM (%s) TO (%s)',
                       to_char(d, 'YYYYMM'),
                       to_char(d, 'YYYYMMDD')::INT,
                       to_char((d + INTERVAL '1 month')::DATE, 'YYYYMMDD')::INT);
        d := (d + INTERVAL '1 month')::DATE;
    END LOOP;
END $$;

INSERT INTO bench.fact_part
    (postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount)
SELECT postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount
FROM bench.fact_src
ORDER BY date_key, k, postingdet_id;

ALTER TABLE bench.fact_part ADD PRIMARY KEY (sales_line_key, date_key);
CREATE INDEX ix_part_posting    ON bench.fact_part (posting_id);
CREATE INDEX ix_part_date_cover ON bench.fact_part (date_key)               INCLUDE (product_key, amount);
CREATE INDEX ix_part_cust_cover ON bench.fact_part (customer_key, date_key) INCLUDE (amount);
