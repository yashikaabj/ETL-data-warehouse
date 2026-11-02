-- Source ("ERP") tables, mirroring the T-SQL practice scripts.
-- Types: FLOAT -> NUMERIC(14,2) here so sums reconcile exactly; see README.
CREATE SCHEMA IF NOT EXISTS src;

CREATE TABLE src.phstate (
    id          INT          NOT NULL DEFAULT 0,
    state_name  VARCHAR(255) NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX phstate_id ON src.phstate (id);
CREATE INDEX phstate_name ON src.phstate (state_name);

CREATE TABLE src.phhq (
    hq_id      INT          NOT NULL DEFAULT 0,
    head_qtr   VARCHAR(255) NOT NULL DEFAULT '',
    state_id   INT          NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX phhq_id ON src.phhq (hq_id);
CREATE INDEX phhq_headqtr_state ON src.phhq (head_qtr, state_id);

CREATE TABLE src.phparty_a (
    cust_id      INT           NOT NULL DEFAULT 0,
    cust_name    VARCHAR(255)  NOT NULL DEFAULT '',
    hq_id        INT           NOT NULL DEFAULT 0,
    csbc         VARCHAR(255)  NOT NULL DEFAULT '',
    bill_amount  NUMERIC(14,2) NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX phparty_a_uid ON src.phparty_a (cust_id);

CREATE TABLE src.phitem (
    item_id    INT          NOT NULL DEFAULT 0,
    item_name  VARCHAR(255) NOT NULL DEFAULT '',
    item_code  VARCHAR(255) NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX phitem_id_code ON src.phitem (item_id, item_code);
CREATE INDEX phitem_name ON src.phitem (item_name);

CREATE TABLE src.phposting (
    posting_id    INT           NOT NULL DEFAULT 0,
    doc_type      VARCHAR(255)  NOT NULL DEFAULT '',
    bill_amount   NUMERIC(14,2) NOT NULL DEFAULT 0,
    cust_id       INT           NOT NULL DEFAULT 0,
    bill_no       INT,
    posting_date  DATE          NOT NULL      -- added: not in the original DDL
);
CREATE UNIQUE INDEX phposting_id ON src.phposting (posting_id);

CREATE TABLE src.phpostingdet (
    item_id        INT           NOT NULL DEFAULT 0,
    qty            NUMERIC(12,2) NOT NULL DEFAULT 0,
    rate           NUMERIC(14,2) NOT NULL DEFAULT 0,
    amount         NUMERIC(14,2) NOT NULL DEFAULT 0,
    posting_id     INT           NOT NULL DEFAULT 0,
    postingdet_id  INT           NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX phpostingdet_posting_det ON src.phpostingdet (posting_id, postingdet_id);

CREATE TABLE src.employee (
    emp_id    INT,
    emp_name  VARCHAR(255),
    mngr_id   INT                              -- NULL for the root of the hierarchy
);
