-- @@ ref_state requires=phstate
WITH n AS (
    SELECT id, replace(initcap(lower(regexp_replace(btrim(state_name), '\s+', ' ', 'g'))), ' And ', ' and ') AS nm
    FROM stg.phstate),
canon AS (SELECT nm, MIN(id) AS state_id FROM n GROUP BY nm)
INSERT INTO dw.ref_state AS r (state_id, state_name)
SELECT state_id, nm FROM canon
ON CONFLICT (state_id) DO UPDATE SET state_name = EXCLUDED.state_name
WHERE r.state_name IS DISTINCT FROM EXCLUDED.state_name;

-- @@ ref_state_alias requires=phstate
WITH n AS (
    SELECT id, replace(initcap(lower(regexp_replace(btrim(state_name), '\s+', ' ', 'g'))), ' And ', ' and ') AS nm
    FROM stg.phstate),
canon AS (SELECT nm, MIN(id) AS state_id FROM n GROUP BY nm)
INSERT INTO dw.ref_state_alias (raw_state_id, state_id)
SELECT n.id, canon.state_id FROM n JOIN canon USING (nm)
ON CONFLICT (raw_state_id) DO UPDATE SET state_id = EXCLUDED.state_id;

-- @@ reject_hq_without_state
INSERT INTO audit.rejected_rows (run_id, source_table, key_value, reason, row_data)
SELECT {{run_id}}, 'PHHQ', h.hq_id::TEXT, 'HQ_WITHOUT_VALID_STATE',
       jsonb_build_object('hq_id', h.hq_id, 'head_qtr', h.head_qtr, 'state_id', h.state_id)
FROM stg.phhq h
WHERE h.state_id = 0
   OR NOT EXISTS (SELECT 1 FROM dw.ref_state_alias a WHERE a.raw_state_id = h.state_id);

-- @@ upsert_dim_geography
INSERT INTO dw.dim_geography AS g (hq_id, hq_name, state_id, state_name)
SELECT h.hq_id,
       regexp_replace(initcap(lower(regexp_replace(btrim(h.head_qtr), '\s+', ' ', 'g'))), ' Hq$', ' HQ'),
       s.state_id, s.state_name
FROM stg.phhq h
JOIN dw.ref_state_alias a ON a.raw_state_id = h.state_id AND h.state_id <> 0
JOIN dw.ref_state s       ON s.state_id = a.state_id
ON CONFLICT (hq_id) DO UPDATE
   SET hq_name = EXCLUDED.hq_name, state_id = EXCLUDED.state_id,
       state_name = EXCLUDED.state_name, updated_at = now()
WHERE (g.hq_name, g.state_id, g.state_name) IS DISTINCT FROM (EXCLUDED.hq_name, EXCLUDED.state_id, EXCLUDED.state_name);
