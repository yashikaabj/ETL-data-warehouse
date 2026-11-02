# Source dataset guide

A synthetic ERP-style dataset built from the tables in a set of T-SQL practice scripts
(`PHSTATE`, `PHHQ`, `PHPARTY_A`, `PHITEM`, `PHPOSTING`, `PHPOSTINGDET`, `EMPLOYEE`), same
table names, same column names and order. It is the **source system** for the pipeline:

```
CSV / source tables  ->  staging  ->  transform + validate  ->  warehouse (star schema)  ->  reports
```

Everything is synthetic and reproducible (`python3 generate_dataset.py`, seed 42).

## What's in the folder

```
data/                 initial load: 2025-01-01 .. 2026-09-30
data/batch_2/         next incremental load: October 2026
answer_key/           every seeded data issue + every batch-2 change (look only after writing your own checks)
sql/postgres/         source schema + COPY load (tested on PostgreSQL 16)
sql/sqlserver/        source schema + BULK INSERT (T-SQL, not tested here)
sql/warehouse/        staging + star schema + ETL steps + sample reports
etl/run_etl.py        ETL runner (stg -> dw, audit logging, watermark, rollback)
benchmark/            index/partitioning benchmark (run_benchmark.py) and saved results
docs/                 warehouse design, performance write-up, ER diagram, how to run
docker-compose.yml    Postgres 16 that auto-creates and loads the source schema
tools/verify_dataset.py   self-check against the answer key
generate_dataset.py   regenerates everything
```

The warehouse and ETL layer is documented in [warehouse_design.md](warehouse_design.md).

## Tables

| Table | Initial load | Batch 2 | Meaning |
|---|---:|---:|---|
| PHSTATE | 34 | – (unchanged) | states |
| PHHQ | 63 | 65 (full snapshot) | headquarters, each belongs to a state |
| PHPARTY_A | 3,012 | 3,072 (full snapshot) | customers, each belongs to an HQ; `BILL_AMOUNT` is the running total of their postings |
| PHITEM | 140 | 146 (full snapshot) | products (20 generic + 120 branded) |
| PHPOSTING | 34,658 | 1,972 (new + re-sent rows) | invoice headers |
| PHPOSTINGDET | 122,431 | 6,913 (new + re-sent rows) | invoice lines, `AMOUNT = QTY * RATE` |
| EMPLOYEE | 60 | – | manager hierarchy, 5 levels (not linked to sales; use it for a hierarchy dimension or recursive-CTE practice) |

Relationships: `PHSTATE <- PHHQ <- PHPARTY_A <- PHPOSTING <- PHPOSTINGDET -> PHITEM`

Initial-load totals: about ₹3.29 billion of sales over 21 months, 2025 growing roughly 1.2% a month,
fewer postings on weekends, a few customers responsible for most of the volume.

## Differences from the original practice scripts

- **`PHPOSTING.POSTING_DATE` (DATE) was added.** The original table has no date, so a date
  dimension and incremental loads would be impossible.
- `FLOAT` columns are `NUMERIC(14,2)` in the Postgres DDL so sums reconcile exactly
  (the SQL Server DDL keeps `FLOAT`).
- `PHPOSTINGDET.POSTINGDET_ID` is a plain `INT`, not `IDENTITY`, so ids load as given.
- State names follow the final state of the original script (`MANIPUR` and `KERALA` upper-case, the others title-case).
- Item names starting with a product type (`MOUSE LOGITECH M221`) let you derive a category in the transform step.

## Seeded data-quality issues (initial load)

| Issue | Where | Count |
|---|---|---:|
| Customer HQ_ID = 0 (unassigned) | PHPARTY_A | 45 |
| Customer HQ_ID not in PHHQ | PHPARTY_A | 15 |
| Name with stray spaces / wrong case | PHPARTY_A | 60 |
| Duplicate customer (same name + HQ, different id) | PHPARTY_A | 12 |
| Duplicate state (`'UTTARAKHAND '` vs id 12) | PHSTATE | 1 |
| HQ with STATE_ID = 0 (`PUNJAB`, `UTTAKHAND`) | PHHQ | 2 |
| Posting for a customer that doesn't exist | PHPOSTING | 90 |
| Header total ≠ sum of its lines | PHPOSTING | 135 |
| Line `AMOUNT` ≠ `QTY * RATE` | PHPOSTINGDET | 420 |
| Line with `QTY = 0` | PHPOSTINGDET | 263 |
| Line with an item not in PHITEM (id 999) | PHPOSTINGDET | 140 |

Customers also collide on name and HQ by chance (about 45 pairs), so `CUST_ID` is the real
key; only the 12 planted rows are listed in the answer key. A posting with a bad line also
shows up in a header-vs-lines check, which gives 549 mismatching headers in total.

## Batch 2 (October 2026): what to expect

| Event | Count | Pipeline behaviour it tests |
|---|---:|---|
| Customer HQ changed | 40 | SCD Type 2 on the customer dimension |
| New customers | 60 | inserts |
| New items / renamed items | 6 / 3 | dimension upserts |
| New / renamed HQ | 2 / 1 | dimension upserts |
| Late-arriving postings (September date, new id) | 25 | a date-based watermark misses them, an id-based one catches them |
| Re-sent postings already loaded | 15 | loads must be idempotent (`ON CONFLICT` / `MERGE`) |

`PHPARTY_A.BILL_AMOUNT` is a running total that changes for most active customers every month.
Don't track it as an SCD2 attribute; compute it from the facts.

## Quick start

**Postgres (Docker):**

```bash
docker compose up -d
psql -h localhost -p 5433 -U etl -d warehouse        # password: etl
# later, to practise incremental loads:
docker compose exec -T db psql -U etl -d warehouse < sql/postgres/batch2/load_batch2.sql
```

Source tables are in schema `src`, batch 2 in `src_batch2`.

**SQL Server:** run `sql/sqlserver/01_schema.sql` in a practice database (it creates schema
`src`, so nothing clashes with `dbo` tables), edit the path in `02_bulk_insert.sql`, then run it.

**Self-check:** `python3 tools/verify_dataset.py` (needs pandas).

## Suggested warehouse model

- Facts: `fact_sales_line` (grain: one invoice line) and optionally `fact_sales_invoice`
- Dimensions: `dim_customer` (SCD2, with HQ and state denormalised), `dim_product`
  (with derived category), `dim_date`, `dim_doc_type`
- Handle the issues above in staging: reject or quarantine bad rows into an `audit` table,
  map unknown HQ / customer / item to an "Unknown" member, and log counts per run.
