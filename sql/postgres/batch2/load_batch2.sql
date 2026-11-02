-- Run manually AFTER the first ETL run, to practise incremental loads:
--   docker compose exec -T db psql -U etl -d warehouse < sql/postgres/batch2/load_batch2.sql
-- Batch 2 lands in its own schema (no unique indexes: it contains re-sent rows on purpose).
CREATE SCHEMA IF NOT EXISTS src_batch2;
CREATE TABLE src_batch2.phhq         (LIKE src.phhq         INCLUDING DEFAULTS);
CREATE TABLE src_batch2.phitem       (LIKE src.phitem       INCLUDING DEFAULTS);
CREATE TABLE src_batch2.phparty_a    (LIKE src.phparty_a    INCLUDING DEFAULTS);
CREATE TABLE src_batch2.phposting    (LIKE src.phposting    INCLUDING DEFAULTS);
CREATE TABLE src_batch2.phpostingdet (LIKE src.phpostingdet INCLUDING DEFAULTS);

COPY src_batch2.phhq         FROM '/data/batch_2/PHHQ.csv'         WITH (FORMAT csv, HEADER true);
COPY src_batch2.phitem       FROM '/data/batch_2/PHITEM.csv'       WITH (FORMAT csv, HEADER true);
COPY src_batch2.phparty_a    FROM '/data/batch_2/PHPARTY_A.csv'    WITH (FORMAT csv, HEADER true);
COPY src_batch2.phposting    FROM '/data/batch_2/PHPOSTING.csv'    WITH (FORMAT csv, HEADER true);
COPY src_batch2.phpostingdet FROM '/data/batch_2/PHPOSTINGDET.csv' WITH (FORMAT csv, HEADER true);
