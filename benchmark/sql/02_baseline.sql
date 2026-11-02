-- Stage 1: baseline. Same columns as dw.fact_sales_line, primary key only, no secondary indexes.
CREATE TABLE bench.fact_baseline (
    sales_line_key   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
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
);
INSERT INTO bench.fact_baseline
    (postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount)
SELECT postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount
FROM bench.fact_src
ORDER BY date_key, k, postingdet_id;
