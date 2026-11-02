-- @@ recon_checks
INSERT INTO audit.dq_check_result (run_id, check_name, severity, failed_rows, handling)
SELECT {{run_id}}, v.check_name, v.severity, v.failed_rows, v.handling
FROM (
    SELECT 'RECON_STAGED_LINES_NOT_IN_FACT' AS check_name, 'ERROR' AS severity,
           (SELECT COUNT(*) FROM stg.phpostingdet d
             WHERE d.qty > 0 AND NOT EXISTS (SELECT 1 FROM dw.fact_sales_line f WHERE f.postingdet_id = d.postingdet_id)) AS failed_rows,
           'must be 0: every valid staged line is in the fact' AS handling
    UNION ALL
    SELECT 'RECON_HEADER_VS_WAREHOUSE', 'WARN',
           (SELECT COUNT(*) FROM stg.phposting p
              LEFT JOIN (SELECT posting_id, SUM(amount) AS s FROM dw.fact_sales_line
                          WHERE posting_id IN (SELECT posting_id FROM stg.phposting) GROUP BY posting_id) t USING (posting_id)
             WHERE ABS(p.bill_amount - COALESCE(t.s, 0)) > 0.01),
           'source header total still disagrees after line corrections: the source header itself is wrong'
    UNION ALL
    SELECT 'UNCATEGORIZED_PRODUCTS', 'INFO',
           (SELECT COUNT(*) FROM dw.dim_product WHERE category = 'UNCATEGORIZED'),
           'add a keyword to dw.ref_category'
) v;

-- @@ advance_watermark
UPDATE audit.watermark
SET last_value = GREATEST(last_value, (SELECT COALESCE(MAX(posting_id), 0) FROM stg.phposting)),
    updated_at = now(), run_id = {{run_id}}
WHERE table_name = 'phposting.posting_id';
