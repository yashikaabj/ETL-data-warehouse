# Benchmark results

Scale-up: **5,161,000 rows** (129,025 x 40). Median of 5 warm runs.

Environment: PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1); shared_buffers=128MB, work_mem=4MB, max_parallel_workers_per_gather=2 (defaults). Absolute times depend on your hardware; compare stages with each other.

## Execution time (ms) and speedup vs. baseline

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 Category revenue, one month | 517.8 | 64.1 (8.1x) | 91.5 (5.7x) | 79.9 (6.5x) |
| Q2 One customer's daily sales | 469.4 | 6.97 (67.4x) | 3.08 (152x) | 5.18 (90.6x) |
| Q3 Top 10 products, one quarter | 578.6 | 217.6 (2.7x) | 201.0 (2.9x) | 240.4 (2.4x) |
| Q4 Invoice lookup by posting_id | 382.7 | 0.01 (>1,000x) | 0.01 (>1,000x) | 0.23 (>1,000x) |
| Q5 Monthly revenue, all of 2025 (big scan) | 780.7 | 588.4 (1.3x) | 419.0 (1.9x) | 731.3 (1.1x) |
| W1 Bulk insert 129,025 rows | 557.1 | 1,380.4 (0.4x) | 1,424.2 (0.4x) | 1,453.2 (0.4x) |

Speedup above 1x is faster than baseline; below 1x is slower (for W1, slower is the price of indexes).

## Buffers touched (8 KB pages; fewer = less I/O)

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 | 76,889 | 1,747 | 550 | 1,673 |
| Q2 | 76,919 | 3,231 | 54 | 242 |
| Q3 | 76,889 | 5,194 | 1,500 | 4,868 |
| Q4 | 76,845 | 4 | 4 | 97 |
| Q5 | 76,859 | 20,766 | 5,860 | 19,487 |

## Planning time (ms)

| Query | 1_baseline | 2_btree | 3_covering | 4_partitioned |
|---|---:|---:|---:|---:|
| Q1 | 0.18 | 0.22 | 0.24 | 0.27 |
| Q2 | 0.11 | 0.06 | 0.05 | 1.13 |
| Q3 | 0.19 | 0.24 | 0.22 | 0.43 |
| Q4 | 0.07 | 0.02 | 0.02 | 0.83 |
| Q5 | 0.10 | 0.11 | 0.12 | 0.58 |

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
| Q4 | 4_partitioned | Bitmap Heap Scan + Index Scan on 48 partition(s) |
| Q5 | 1_baseline | Seq Scan |
| Q5 | 2_btree | Index Scan |
| Q5 | 3_covering | Index Only Scan (heap fetches 0) |
| Q5 | 4_partitioned | Seq Scan on 12 partition(s) |

## Storage (MB)

| Stage | Table | Indexes |
|---|---:|---:|
| 1_baseline | 630 | 116 |
| 2_btree | 630 | 305 |
| 3_covering | 630 | 588 |
| 4_partitioned | 632 | 618 |
