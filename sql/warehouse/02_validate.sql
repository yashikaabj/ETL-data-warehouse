-- Data-quality checks on the staged batch. Results go to audit.dq_check_result.
-- @@ dq_checks
INSERT INTO audit.dq_check_result (run_id, check_name, severity, failed_rows, handling)
SELECT {{run_id}}, v.check_name, v.severity, v.failed_rows, v.handling
FROM (
    SELECT 'ORPHAN_CUSTOMER_ON_POSTING' AS check_name, 'WARN' AS severity,
           (SELECT COUNT(*) FROM stg.phposting p
             WHERE NOT EXISTS (SELECT 1 FROM stg.phparty_a c WHERE c.cust_id = p.cust_id)) AS failed_rows,
           'loaded against Unknown customer (key 0); fact.dq_flags = ORPHAN_CUSTOMER' AS handling
    UNION ALL
    SELECT 'ORPHAN_ITEM_ON_LINE', 'WARN',
           (SELECT COUNT(*) FROM stg.phpostingdet d
             WHERE NOT EXISTS (SELECT 1 FROM stg.phitem i WHERE i.item_id = d.item_id)),
           'loaded against Unknown product (key 0); fact.dq_flags = ORPHAN_ITEM'
    UNION ALL
    SELECT 'CUSTOMER_HQ_UNASSIGNED', 'INFO',
           (SELECT COUNT(*) FROM stg.phparty_a WHERE hq_id = 0),
           'customer points at Unknown geography (key 0)'
    UNION ALL
    SELECT 'CUSTOMER_HQ_NOT_FOUND', 'WARN',
           (SELECT COUNT(*) FROM stg.phparty_a c
             WHERE c.hq_id <> 0 AND NOT EXISTS (SELECT 1 FROM stg.phhq h WHERE h.hq_id = c.hq_id)),
           'customer points at Unknown geography (key 0)'
    UNION ALL
    SELECT 'CUSTOMER_NAME_NEEDS_CLEANING', 'INFO',
           (SELECT COUNT(*) FROM stg.phparty_a
             WHERE cust_name <> upper(regexp_replace(btrim(cust_name), '\s+', ' ', 'g'))),
           'trimmed, whitespace collapsed, upper-cased in dim_customer'
    UNION ALL
    SELECT 'POSSIBLE_DUPLICATE_CUSTOMERS (groups)', 'INFO',
           (SELECT COUNT(*) FROM (
                SELECT 1 FROM stg.phparty_a WHERE hq_id <> 0
                GROUP BY upper(regexp_replace(btrim(cust_name), '\s+', ' ', 'g')), hq_id
                HAVING COUNT(*) > 1) x),
           'kept as separate customers (cust_id is the key); review manually'
    UNION ALL
    SELECT 'DUPLICATE_STATE_NAME (groups)', 'WARN',
           (SELECT COUNT(*) FROM (
                SELECT 1 FROM stg.phstate GROUP BY lower(btrim(state_name)) HAVING COUNT(*) > 1) x),
           'raw ids collapsed onto the canonical (lowest) id via dw.ref_state_alias'
    UNION ALL
    SELECT 'HQ_WITHOUT_VALID_STATE', 'ERROR',
           (SELECT COUNT(*) FROM stg.phhq h
             WHERE h.state_id = 0
                OR (NOT EXISTS (SELECT 1 FROM stg.phstate s WHERE s.id = h.state_id)
                    AND NOT EXISTS (SELECT 1 FROM dw.ref_state_alias a WHERE a.raw_state_id = h.state_id))),
           'rejected to audit.rejected_rows; not loaded into dim_geography'
    UNION ALL
    SELECT 'NON_POSITIVE_QTY', 'ERROR',
           (SELECT COUNT(*) FROM stg.phpostingdet WHERE qty <= 0),
           'rejected to audit.rejected_rows; not loaded into the fact'
    UNION ALL
    SELECT 'LINE_AMOUNT_MISMATCH', 'WARN',
           (SELECT COUNT(*) FROM stg.phpostingdet WHERE ABS(amount - ROUND(qty * rate, 2)) > 0.005),
           'amount recalculated as qty*rate; fact.amount_corrected = true'
    UNION ALL
    SELECT 'HEADER_TOTAL_MISMATCH_IN_SOURCE', 'WARN',
           (SELECT COUNT(*) FROM stg.phposting p
              JOIN (SELECT posting_id, SUM(amount) AS s FROM stg.phpostingdet GROUP BY posting_id) d USING (posting_id)
             WHERE ABS(p.bill_amount - d.s) > 0.01),
           'header total is not loaded (facts are at line grain); see RECON_HEADER_VS_WAREHOUSE'
) v;
