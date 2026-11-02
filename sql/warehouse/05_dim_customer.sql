-- SCD Type 2 on (cust_name, csbc, hq). {{eff}} = date new versions become valid.
-- @@ tmp_customer_clean
CREATE TEMP TABLE tmp_customer_clean ON COMMIT DROP AS
SELECT c.cust_id,
       upper(regexp_replace(btrim(c.cust_name), '\s+', ' ', 'g')) AS cust_name,
       btrim(c.csbc) AS csbc,
       COALESCE(g.hq_key, 0) AS hq_key
FROM stg.phparty_a c
LEFT JOIN dw.dim_geography g ON g.hq_id = c.hq_id;

-- @@ close_changed_versions
UPDATE dw.dim_customer d
SET valid_to = {{eff}}::DATE - 1, is_current = FALSE
FROM tmp_customer_clean s
WHERE d.cust_id = s.cust_id AND d.is_current
  AND (d.cust_name, d.csbc, d.hq_key) IS DISTINCT FROM (s.cust_name, s.csbc, s.hq_key);

-- A brand-new customer gets valid_from = 1900-01-01 so late-arriving older facts still resolve to it;
-- a changed customer's new version starts on the effective date.
-- @@ insert_new_versions
INSERT INTO dw.dim_customer (cust_id, cust_name, csbc, hq_key, valid_from, valid_to, is_current)
SELECT s.cust_id, s.cust_name, s.csbc, s.hq_key,
       CASE WHEN EXISTS (SELECT 1 FROM dw.dim_customer x WHERE x.cust_id = s.cust_id)
            THEN {{eff}}::DATE ELSE DATE '1900-01-01' END,
       DATE '9999-12-31', TRUE
FROM tmp_customer_clean s
WHERE NOT EXISTS (SELECT 1 FROM dw.dim_customer d WHERE d.cust_id = s.cust_id AND d.is_current);
