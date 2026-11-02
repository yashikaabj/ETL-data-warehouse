# Benchmark results

Scale-up: **2,580,500 rows** (129,025 x 20). Median of 5 warm runs.

Environment: PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1); shared_buffers=128MB, work_mem=4MB, max_parallel_workers_per_gather=2 (defaults). Absolute times depend on your hardware; compare stages with each other.

## Execution time (ms) and speedup vs. baseline

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 Category revenue, one month | 271.3 | 38.6 (7.0x) | 33.3 (8.2x) | 46.2 (5.9x) |
| Q2 One customer's daily sales | 230.8 | 3.77 (61.3x) | 1.73 (134x) | 3.02 (76.4x) |
| Q3 Top 10 products, one quarter | 331.6 | 134.6 (2.5x) | 123.3 (2.7x) | 165.0 (2.0x) |
| Q4 Invoice lookup by posting_id | 198.3 | 0.01 (>1,000x) | 0.01 (>1,000x) | 0.23 (851x) |
| Q5 Monthly revenue, all of 2025 (big scan) | 347.9 | 169.3 (2.1x) | 139.1 (2.5x) | 185.7 (1.9x) |
| W1 Bulk insert 129,025 rows | 475.5 | 1,316.0 (0.4x) | 1,107.0 (0.4x) | 1,230.5 (0.4x) |

Speedup above 1x is faster than baseline; below 1x is slower (for W1, slower is the price of indexes).

## Buffers touched (8 KB pages; fewer = less I/O)

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 | 38,475 | 1,121 | 322 | 1,056 |
| Q2 | 38,499 | 1,626 | 29 | 189 |
| Q3 | 38,475 | 3,104 | 915 | 2,918 |
| Q4 | 38,425 | 4 | 4 | 93 |
| Q5 | 38,439 | 5,708 | 1,611 | 5,332 |

## Planning time (ms)

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 | 0.19 | 0.23 | 0.17 | 0.29 |
| Q2 | 0.11 | 0.06 | 0.04 | 1.29 |
| Q3 | 0.20 | 0.24 | 0.21 | 0.32 |
| Q4 | 0.08 | 0.01 | 0.01 | 0.76 |
| Q5 | 0.10 | 0.12 | 0.16 | 0.55 |

## Access path chosen by the planner

| Query | Stage | Path |
|---|---|---|
| Q1 | 1_baseline | Seq Scan |
| Q1 | 2_btree | Index Scan |
| Q1 | 3_covering | Index Only Scan (heap fetches 0) |
| Q1 | 4_partitioned | Seq Scan on 1 partition(s) |
| Q2 | 1_baseline | Seq Scan |
| Q2 | 2_btree | Bitmap Heap Scan |
| Q2 | 3_covering | Index Only Scan (heap fetches 0) |
| Q2 | 4_partitioned | Index Only Scan on 48 partition(s) (heap fetches 0) |
| Q3 | 1_baseline | Seq Scan |
| Q3 | 2_btree | Index Scan |
| Q3 | 3_covering | Index Only Scan (heap fetches 0) |
| Q3 | 4_partitioned | Seq Scan on 3 partition(s) |
| Q4 | 1_baseline | Seq Scan |
| Q4 | 2_btree | Index Scan |
| Q4 | 3_covering | Index Scan |
| Q4 | 4_partitioned | Bitmap Heap Scan + Index Scan + Seq Scan on 48 partition(s) |
| Q5 | 1_baseline | Seq Scan |
| Q5 | 2_btree | Index Scan |
| Q5 | 3_covering | Index Only Scan (heap fetches 0) |
| Q5 | 4_partitioned | Seq Scan on 12 partition(s) |

## Storage (MB)

| Stage | Table | Indexes |
|---|---:|---:|
| 1_baseline | 315 | 58 |
| 2_btree | 315 | 157 |
| 3_covering | 315 | 305 |
| 4_partitioned | 317 | 310 |
