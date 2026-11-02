-- Placeholders filled by etl/run_etl.py: {{run_id}} {{src}} {{wm}}
-- Statement header:  -- @@ <name> [requires=<table that must exist in the source schema>]

-- @@ truncate_stg
TRUNCATE stg.phstate, stg.phhq, stg.phparty_a, stg.phitem, stg.phposting, stg.phpostingdet;

-- @@ stage_phstate requires=phstate
INSERT INTO stg.phstate (id, state_name, run_id)
SELECT id, state_name, {{run_id}} FROM {{src}}.phstate;

-- @@ stage_phhq requires=phhq
INSERT INTO stg.phhq (hq_id, head_qtr, state_id, run_id)
SELECT hq_id, head_qtr, state_id, {{run_id}} FROM {{src}}.phhq;

-- @@ stage_phparty_a requires=phparty_a
INSERT INTO stg.phparty_a (cust_id, cust_name, hq_id, csbc, bill_amount, run_id)
SELECT cust_id, cust_name, hq_id, csbc, bill_amount, {{run_id}} FROM {{src}}.phparty_a;

-- @@ stage_phitem requires=phitem
INSERT INTO stg.phitem (item_id, item_name, item_code, run_id)
SELECT item_id, item_name, item_code, {{run_id}} FROM {{src}}.phitem;

-- Incremental extract: only postings above the high-water mark (late-arriving rows have NEW ids, so they are caught).
-- @@ stage_phposting requires=phposting
INSERT INTO stg.phposting (posting_id, doc_type, bill_amount, cust_id, bill_no, posting_date, run_id)
SELECT posting_id, doc_type, bill_amount, cust_id, bill_no, posting_date, {{run_id}}
FROM {{src}}.phposting
WHERE posting_id > {{wm}};

-- @@ stage_phpostingdet requires=phpostingdet
INSERT INTO stg.phpostingdet (item_id, qty, rate, amount, posting_id, postingdet_id, run_id)
SELECT d.item_id, d.qty, d.rate, d.amount, d.posting_id, d.postingdet_id, {{run_id}}
FROM {{src}}.phpostingdet d
WHERE EXISTS (SELECT 1 FROM stg.phposting p WHERE p.posting_id = d.posting_id);
