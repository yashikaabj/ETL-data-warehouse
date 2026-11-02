-- Warehouse DDL (idempotent). Schemas: stg = staging, dw = star schema, audit = ETL bookkeeping.
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS audit;

-- ============================== audit ==============================
CREATE TABLE IF NOT EXISTS audit.etl_run (
    run_id          SERIAL      PRIMARY KEY,
    source_schema   TEXT        NOT NULL,
    effective_date  DATE        NOT NULL,          -- date new SCD2 versions become valid
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    error           TEXT
);
CREATE TABLE IF NOT EXISTS audit.etl_step_log (
    step_id        SERIAL      PRIMARY KEY,
    run_id         INT         NOT NULL REFERENCES audit.etl_run (run_id),
    step           TEXT        NOT NULL,
    rows_affected  BIGINT,
    duration_ms    INT,
    logged_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit.rejected_rows (
    id            BIGSERIAL   PRIMARY KEY,
    run_id        INT         NOT NULL REFERENCES audit.etl_run (run_id),
    source_table  TEXT        NOT NULL,
    key_value     TEXT        NOT NULL,
    reason        TEXT        NOT NULL,
    row_data      JSONB,
    rejected_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit.dq_check_result (
    id           BIGSERIAL   PRIMARY KEY,
    run_id       INT         NOT NULL REFERENCES audit.etl_run (run_id),
    check_name   TEXT        NOT NULL,
    severity     TEXT        NOT NULL CHECK (severity IN ('INFO', 'WARN', 'ERROR')),
    failed_rows  BIGINT      NOT NULL,
    handling     TEXT        NOT NULL,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS audit.watermark (
    table_name  TEXT        PRIMARY KEY,
    last_value  BIGINT      NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ,
    run_id      INT
);
INSERT INTO audit.watermark (table_name, last_value) VALUES ('phposting.posting_id', 0) ON CONFLICT DO NOTHING;

-- ============================== staging (current batch only; truncated each run) ==============================
CREATE TABLE IF NOT EXISTS stg.phstate (
    id INT, state_name VARCHAR(255),
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS stg.phhq (
    hq_id INT, head_qtr VARCHAR(255), state_id INT,
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS stg.phparty_a (
    cust_id INT, cust_name VARCHAR(255), hq_id INT, csbc VARCHAR(255), bill_amount NUMERIC(14,2),
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS stg.phitem (
    item_id INT, item_name VARCHAR(255), item_code VARCHAR(255),
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS stg.phposting (
    posting_id INT, doc_type VARCHAR(255), bill_amount NUMERIC(14,2), cust_id INT, bill_no INT, posting_date DATE,
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS stg.phpostingdet (
    item_id INT, qty NUMERIC(12,2), rate NUMERIC(14,2), amount NUMERIC(14,2), posting_id INT, postingdet_id INT,
    run_id INT, loaded_at TIMESTAMPTZ DEFAULT now());
CREATE INDEX IF NOT EXISTS stg_phposting_id    ON stg.phposting (posting_id);
CREATE INDEX IF NOT EXISTS stg_phpostingdet_pid ON stg.phpostingdet (posting_id);
CREATE INDEX IF NOT EXISTS stg_phparty_a_id    ON stg.phparty_a (cust_id);

-- ============================== reference data ==============================
CREATE TABLE IF NOT EXISTS dw.ref_state (
    state_id    INT  PRIMARY KEY,
    state_name  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.ref_state_alias (          -- maps every raw state id to its canonical id
    raw_state_id  INT PRIMARY KEY,
    state_id      INT NOT NULL REFERENCES dw.ref_state (state_id)
);
INSERT INTO dw.ref_state (state_id, state_name) VALUES (0, 'Unknown') ON CONFLICT DO NOTHING;
INSERT INTO dw.ref_state_alias (raw_state_id, state_id) VALUES (0, 0) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.ref_category (             -- keyword -> product category (longest match wins)
    keyword TEXT PRIMARY KEY
);
INSERT INTO dw.ref_category (keyword) VALUES
 ('MOUSE'), ('KEYBOARD'), ('LAPTOP'), ('LAPTOP BAG'), ('DESKTOP PC'), ('MONITOR'), ('PRINTER'), ('SCANNER'),
 ('UPS'), ('ROUTER'), ('NETWORK SWITCH'), ('HARD DISK'), ('SSD'), ('RAM'), ('PEN DRIVE'), ('PROJECTOR'),
 ('WEBCAM'), ('HEADPHONE'), ('SPEAKER'), ('TABLET'), ('MOBILE PHONE'), ('CCTV CAMERA'), ('POWER BANK'),
 ('HDMI CABLE'), ('MEMORY CARD'), ('GRAPHICS CARD'), ('MOTHERBOARD'), ('PROCESSOR'), ('SMPS'), ('CABINET')
ON CONFLICT DO NOTHING;

-- ============================== dimensions ==============================
CREATE TABLE IF NOT EXISTS dw.dim_date (
    date_key        INT     PRIMARY KEY,               -- yyyymmdd
    full_date       DATE    NOT NULL UNIQUE,
    year            INT     NOT NULL,
    quarter         INT     NOT NULL,
    month           INT     NOT NULL,
    month_name      TEXT    NOT NULL,
    day             INT     NOT NULL,
    day_of_week     INT     NOT NULL,                  -- 1 = Monday .. 7 = Sunday
    day_name        TEXT    NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    fiscal_year     TEXT    NOT NULL,                  -- Indian FY, April-March, e.g. FY2025-26
    fiscal_quarter  INT     NOT NULL
);
INSERT INTO dw.dim_date
SELECT to_char(d, 'YYYYMMDD')::INT, d::DATE,
       EXTRACT(YEAR FROM d)::INT, EXTRACT(QUARTER FROM d)::INT, EXTRACT(MONTH FROM d)::INT,
       trim(to_char(d, 'Month')), EXTRACT(DAY FROM d)::INT, EXTRACT(ISODOW FROM d)::INT, trim(to_char(d, 'Day')),
       EXTRACT(ISODOW FROM d) IN (6, 7),
       'FY' || fy || '-' || right((fy + 1)::TEXT, 2),
       ((EXTRACT(MONTH FROM d)::INT + 8) % 12) / 3 + 1
FROM generate_series('2024-01-01'::DATE, '2027-12-31'::DATE, '1 day') AS g(d),
     LATERAL (SELECT CASE WHEN EXTRACT(MONTH FROM d) >= 4 THEN EXTRACT(YEAR FROM d)::INT
                          ELSE EXTRACT(YEAR FROM d)::INT - 1 END AS fy) f
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_geography (            -- Type 1: HQ + state, overwritten when the source changes
    hq_key      SERIAL      PRIMARY KEY,
    hq_id       INT         NOT NULL UNIQUE,
    hq_name     TEXT        NOT NULL,
    state_id    INT         NOT NULL,
    state_name  TEXT        NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO dw.dim_geography (hq_key, hq_id, hq_name, state_id, state_name)
VALUES (0, 0, 'Unknown', 0, 'Unknown') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_product (              -- Type 1
    product_key  SERIAL      PRIMARY KEY,
    item_id      INT         NOT NULL UNIQUE,
    item_code    TEXT        NOT NULL,
    item_name    TEXT        NOT NULL,
    category     TEXT        NOT NULL,
    brand        TEXT        NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO dw.dim_product (product_key, item_id, item_code, item_name, category, brand)
VALUES (0, 0, 'N/A', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS dw.dim_customer (             -- Type 2: tracks name, csbc, HQ
    customer_key  SERIAL  PRIMARY KEY,
    cust_id       INT     NOT NULL,                      -- natural key
    cust_name     TEXT    NOT NULL,
    csbc          TEXT    NOT NULL,
    hq_key        INT     NOT NULL REFERENCES dw.dim_geography (hq_key),
    valid_from    DATE    NOT NULL,
    valid_to      DATE    NOT NULL DEFAULT '9999-12-31',
    is_current    BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (cust_id, valid_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS dim_customer_one_current ON dw.dim_customer (cust_id) WHERE is_current;
INSERT INTO dw.dim_customer (customer_key, cust_id, cust_name, csbc, hq_key, valid_from, valid_to, is_current)
VALUES (0, 0, 'UNKNOWN', 'UNKNOWN', 0, '1900-01-01', '9999-12-31', TRUE) ON CONFLICT DO NOTHING;

-- ============================== fact ==============================
CREATE TABLE IF NOT EXISTS dw.fact_sales_line (          -- grain: one invoice line
    sales_line_key    BIGSERIAL     PRIMARY KEY,
    postingdet_id     INT           NOT NULL UNIQUE,     -- source line id: makes loads idempotent
    posting_id        INT           NOT NULL,
    bill_no           INT,
    doc_type          TEXT          NOT NULL,
    date_key          INT           NOT NULL REFERENCES dw.dim_date (date_key),
    customer_key      INT           NOT NULL REFERENCES dw.dim_customer (customer_key),
    product_key       INT           NOT NULL REFERENCES dw.dim_product (product_key),
    qty               NUMERIC(12,2) NOT NULL,
    rate              NUMERIC(14,2) NOT NULL,
    amount            NUMERIC(14,2) NOT NULL,
    amount_corrected  BOOLEAN       NOT NULL DEFAULT FALSE,
    dq_flags          TEXT,
    run_id            INT           NOT NULL REFERENCES audit.etl_run (run_id),
    loaded_at         TIMESTAMPTZ   NOT NULL DEFAULT now()
);
-- Index set chosen by the benchmark in benchmark/ (see docs/performance.md): two covering indexes serve the
-- report queries with index-only scans; posting_id serves invoice lookups. (The older single-column indexes are
-- dropped; need "all sales of one product, any date"? add an index on product_key.)
DROP INDEX IF EXISTS dw.fact_sales_line_date;
DROP INDEX IF EXISTS dw.fact_sales_line_customer;
DROP INDEX IF EXISTS dw.fact_sales_line_product;
CREATE INDEX IF NOT EXISTS fact_sales_line_date_cover ON dw.fact_sales_line (date_key) INCLUDE (product_key, amount);
CREATE INDEX IF NOT EXISTS fact_sales_line_cust_cover ON dw.fact_sales_line (customer_key, date_key) INCLUDE (amount);
CREATE INDEX IF NOT EXISTS fact_sales_line_posting    ON dw.fact_sales_line (posting_id);
