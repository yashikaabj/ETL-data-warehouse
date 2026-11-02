-- @@ reject_non_positive_qty
INSERT INTO audit.rejected_rows (run_id, source_table, key_value, reason, row_data)
SELECT {{run_id}}, 'PHPOSTINGDET', postingdet_id::TEXT, 'NON_POSITIVE_QTY',
       jsonb_build_object('posting_id', posting_id, 'item_id', item_id, 'qty', qty, 'rate', rate, 'amount', amount)
FROM stg.phpostingdet WHERE qty <= 0;

-- Customer key = the SCD2 version valid on the posting date (falls back to the earliest version, then Unknown).
-- @@ tmp_fact
CREATE TEMP TABLE tmp_fact ON COMMIT DROP AS
SELECT d.postingdet_id, d.posting_id, p.bill_no, p.doc_type,
       to_char(p.posting_date, 'YYYYMMDD')::INT AS date_key,
       COALESCE(c.customer_key, 0)              AS customer_key,
       COALESCE(pr.product_key, 0)              AS product_key,
       d.qty, d.rate,
       ROUND(d.qty * d.rate, 2)                 AS amount,
       ABS(d.amount - ROUND(d.qty * d.rate, 2)) > 0.005 AS amount_corrected,
       NULLIF(concat_ws(',',
           CASE WHEN pr.product_key IS NULL THEN 'ORPHAN_ITEM' END,
           CASE WHEN c.customer_key IS NULL THEN 'ORPHAN_CUSTOMER' END,
           CASE WHEN ABS(d.amount - ROUND(d.qty * d.rate, 2)) > 0.005 THEN 'AMOUNT_RECALCULATED' END), '') AS dq_flags
FROM stg.phpostingdet d
JOIN stg.phposting p ON p.posting_id = d.posting_id
LEFT JOIN dw.dim_product pr ON pr.item_id = d.item_id
LEFT JOIN LATERAL (
    SELECT x.customer_key FROM dw.dim_customer x
    WHERE x.cust_id = p.cust_id
    ORDER BY (p.posting_date BETWEEN x.valid_from AND x.valid_to) DESC, x.valid_from
    LIMIT 1) c ON TRUE
WHERE d.qty > 0;

-- Idempotent upsert: re-sent identical rows touch nothing.
-- @@ upsert_fact_sales_line
INSERT INTO dw.fact_sales_line AS f
    (postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key,
     qty, rate, amount, amount_corrected, dq_flags, run_id)
SELECT postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key,
       qty, rate, amount, amount_corrected, dq_flags, {{run_id}}
FROM tmp_fact
ON CONFLICT (postingdet_id) DO UPDATE SET
    posting_id = EXCLUDED.posting_id, bill_no = EXCLUDED.bill_no, doc_type = EXCLUDED.doc_type,
    date_key = EXCLUDED.date_key, customer_key = EXCLUDED.customer_key, product_key = EXCLUDED.product_key,
    qty = EXCLUDED.qty, rate = EXCLUDED.rate, amount = EXCLUDED.amount,
    amount_corrected = EXCLUDED.amount_corrected, dq_flags = EXCLUDED.dq_flags,
    run_id = EXCLUDED.run_id, loaded_at = now()
WHERE (f.posting_id, f.bill_no, f.doc_type, f.date_key, f.customer_key, f.product_key,
       f.qty, f.rate, f.amount, f.amount_corrected, f.dq_flags)
      IS DISTINCT FROM
      (EXCLUDED.posting_id, EXCLUDED.bill_no, EXCLUDED.doc_type, EXCLUDED.date_key, EXCLUDED.customer_key,
       EXCLUDED.product_key, EXCLUDED.qty, EXCLUDED.rate, EXCLUDED.amount, EXCLUDED.amount_corrected,
       EXCLUDED.dq_flags);
