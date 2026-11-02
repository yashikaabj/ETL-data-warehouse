# Performance: indexing and partitioning the fact table

## What was measured

`dw.fact_sales_line` has only 129K rows, too small to show what indexes or partitions do. `benchmark/run_benchmark.py`
copies it into schema `bench` scaled **20x (2.58M rows)** and **40x (5.16M rows)**: every copy shifts the sales dates by
a different offset and gets unique ids. Rows are stored in date order, like a fact table loaded chronologically.
The same five read queries and one bulk write run against four stages:

| Stage | What changed |
|---|---|
| 1 baseline | primary key only |
| 2 B-tree | + single-column indexes on date, customer, product, invoice |
| 3 covering | covering indexes (`INCLUDE`) replace the date/customer/product indexes, so queries can use index-only scans |
| 4 partitioned | monthly range partitions (48) + the same covering indexes |

Queries: **Q1** category revenue for one month, **Q2** one customer's daily sales, **Q3** top 10 products in a quarter,
**Q4** invoice lookup by `posting_id`, **Q5** monthly revenue for all of 2025 (a large scan, on purpose),
**W1** bulk insert of 129K rows (rolled back; measures what indexes cost on write).

Each number is the median of 5 warm runs from `EXPLAIN (ANALYZE, BUFFERS)`, on PostgreSQL 16 with default settings
(`shared_buffers` 128 MB, `work_mem` 4 MB) on a single-core sandbox. Full plans are saved in `benchmark/results/plans/`.

## Results at 2.58M rows (ms; speedup vs. baseline in brackets)

| Query | 1 baseline | 2 B-tree | 3 covering | 4 partitioned |
|---|---:|---:|---:|---:|
| Q1 Category revenue, one month | 271.3 | 38.6 (7.0x) | 33.3 (8.2x) | 46.2 (5.9x) |
| Q2 One customer's daily sales | 230.8 | 3.77 (61x) | 1.73 (134x) | 3.02 (76x) |
| Q3 Top 10 products, one quarter | 331.6 | 134.6 (2.5x) | 123.3 (2.7x) | 165.0 (2.0x) |
| Q4 Invoice lookup | 198.3 | 0.01 (>1,000x) | 0.01 (>1,000x) | 0.23 (851x) |
| Q5 Monthly revenue, all 2025 | 347.9 | 169.3 (2.1x) | 139.1 (2.5x) | 185.7 (1.9x) |
| W1 Bulk insert 129K rows | 475.5 | 1,316 (0.4x) | 1,107 (0.4x) | 1,231 (0.4x) |

Pages (8 KB) read per query, baseline → B-tree → covering: Q1 38,475 → 1,121 → 322; Q2 38,499 → 1,626 → 29;
Q5 38,439 → 5,708 → 1,611. Index size grows from 58 MB to 305 MB, about the size of the table (315 MB).

A second run and the 40x run (5.16M rows) show the same pattern: indexes give Q2 67x → 152x and Q4 >1,000x,
Q1 about 6-8x, Q3 about 3x, and partitioning never beats the covering indexes
(`benchmark/results_40x/results.md`). Two 20x runs agreed within about 10%.

## What the plans show

- **Invoice lookup (Q4).** Without an index, Postgres runs a parallel sequential scan over the whole table
  (38K pages, about 200 ms). With `ix_fact_posting` it reads 4 pages in about 0.006 ms.
- **Customer history (Q2).** Seq scan (231 ms) becomes a bitmap heap scan with the B-tree index (3.8 ms), then an
  **index-only scan** with `(customer_key, date_key) INCLUDE (amount)` (1.7 ms, 29 pages, `Heap Fetches: 0`):
  the answer comes from the index alone.
- **Covering indexes on large scans (Q1, Q3, Q5).** Time barely moves (these queries are dominated by aggregating
  50K-600K rows, and the data is cached), but the pages read drop 3-7x. That matters once the table no longer fits in
  memory, which this benchmark does not test.
- **Partitioning.** Pruning works: Q1 touched 1 of 48 partitions and Q5 touched 12. But the planner still had to
  scan those partitions, so queries were not faster than the covering indexes, and they paid extra: planning time rose from
  about 0.02 ms to 0.8-1.3 ms and the invoice lookup probes the index of every partition (0.01 ms became 0.23 ms).
- **Write cost.** Bulk-loading 129K rows is about 2.5x slower with the indexes (475 → 1,107-1,316 ms). For a
  warehouse that loads once a night, that is a good trade.

## Decisions

1. **Applied to the warehouse:** `dw.fact_sales_line` now has the two covering indexes plus the `posting_id` index
   (`sql/warehouse/00_ddl.sql`). An existing database is upgraded automatically on its next ETL run.
2. **Not partitioned.** At 129K rows (or even 5M) partitioning buys no query speed here. It starts to pay for
   retention (dropping a whole old month with `DROP TABLE` instead of a huge `DELETE`), per-partition maintenance, and tables
   with hundreds of millions of rows. Partitioning would also require changing the ETL's idempotency key from
   `ON CONFLICT (postingdet_id)` to `(postingdet_id, date_key)`, because a unique key on a partitioned table must include the
   partition column.
3. **Not tested here:** cold-cache behaviour, tables larger than RAM, concurrent users.

## Limits of this benchmark

- The data is a scale-up of the synthetic dataset (same customer/product mix, dates shifted), so real-world skew may differ.
- Numbers come from a single-core sandbox. On a multi-core laptop the baseline's parallel scans are faster, so the speedups on
  Q1, Q3 and Q5 will be smaller, while Q2 and Q4 stay large. Run the benchmark to get numbers for your own machine.

## Reproduce

```powershell
python etl/run_etl.py --reset                     # dw.fact_sales_line must exist
python benchmark/run_benchmark.py                 # 20x, about 2-5 minutes, about 1.5 GB peak disk
python benchmark/run_benchmark.py --multiplier 40 # 5.2M rows, about 3 GB peak disk
python benchmark/run_benchmark.py --keep          # keep schema bench for further experiments
```

Results land in `benchmark/results/` (`results.md`, `results.csv`, `results.json`, `plans/`).
The script only touches schema `bench`; drop it with `DROP SCHEMA bench CASCADE;` if you used `--keep`.
