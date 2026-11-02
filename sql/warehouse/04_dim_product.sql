-- @@ tmp_product
CREATE TEMP TABLE tmp_product ON COMMIT DROP AS
SELECT i.item_id, btrim(i.item_code) AS item_code, btrim(i.item_name) AS item_name,
       COALESCE(c.keyword, 'UNCATEGORIZED') AS category,
       CASE WHEN c.keyword IS NOT NULL AND upper(btrim(i.item_name)) LIKE c.keyword || ' %'
            THEN COALESCE(NULLIF(regexp_replace(substr(btrim(i.item_name), length(c.keyword) + 2), '\s*\S+$', ''), ''), 'UNBRANDED')
            ELSE 'UNBRANDED' END AS brand
FROM stg.phitem i
LEFT JOIN LATERAL (
    SELECT r.keyword FROM dw.ref_category r
    WHERE upper(i.item_name) LIKE '%' || r.keyword || '%'
    ORDER BY length(r.keyword) DESC LIMIT 1) c ON TRUE;

-- @@ upsert_dim_product
INSERT INTO dw.dim_product AS p (item_id, item_code, item_name, category, brand)
SELECT item_id, item_code, item_name, category, brand FROM tmp_product
ON CONFLICT (item_id) DO UPDATE
   SET item_code = EXCLUDED.item_code, item_name = EXCLUDED.item_name,
       category = EXCLUDED.category, brand = EXCLUDED.brand, updated_at = now()
WHERE (p.item_code, p.item_name, p.category, p.brand)
      IS DISTINCT FROM (EXCLUDED.item_code, EXCLUDED.item_name, EXCLUDED.category, EXCLUDED.brand);
