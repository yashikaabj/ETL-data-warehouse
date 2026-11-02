#!/usr/bin/env python3
"""
Measure what indexing and partitioning buy on the fact table.

  python benchmark/run_benchmark.py                    # default: 20x scale-up (~2.6M rows)
  python benchmark/run_benchmark.py --multiplier 40    # ~5.2M rows (needs ~3 GB free disk, takes longer)
  python benchmark/run_benchmark.py --keep             # keep the bench.* tables for further experiments

Run the ETL first (dw.fact_sales_line must exist). Everything is built in schema `bench`; the dw schema is untouched.
Connection: PG* environment variables, same defaults as etl/run_etl.py.

Four stages, same data and the same queries each time:
  1_baseline     primary key only
  2_btree        + single-column B-tree indexes (date, customer, product, invoice)
  3_covering     covering indexes (INCLUDE) -> index-only scans
  4_partitioned  monthly range partitions + the same covering indexes
"""
import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "benchmark"
sys.path.insert(0, str(ROOT / "etl"))
from run_etl import connect  # noqa: E402  (reuse the same connection defaults)

STAGES = [
    ("1_baseline", "primary key only", ["02_baseline.sql"], "bench.fact_baseline"),
    ("2_btree", "+ B-tree indexes", ["03_btree_indexes.sql"], "bench.fact_baseline"),
    ("3_covering", "covering indexes", ["04_covering_indexes.sql"], "bench.fact_baseline"),
    ("4_partitioned", "monthly partitions + covering", ["05_partitioned.sql"], "bench.fact_part"),
]

QUERIES = [
    ("Q1", "Category revenue, one month",
     "SELECT p.category, SUM(f.amount) AS sales FROM {t} f JOIN dw.dim_product p USING (product_key) "
     "WHERE f.date_key BETWEEN 20260301 AND 20260331 GROUP BY p.category ORDER BY sales DESC"),
    ("Q2", "One customer's daily sales",
     "SELECT date_key, SUM(amount) AS sales FROM {t} WHERE customer_key = {cust} GROUP BY date_key ORDER BY date_key"),
    ("Q3", "Top 10 products, one quarter",
     "SELECT p.item_name, SUM(f.amount) AS sales FROM {t} f JOIN dw.dim_product p USING (product_key) "
     "WHERE f.date_key BETWEEN 20260101 AND 20260331 GROUP BY p.item_name ORDER BY sales DESC LIMIT 10"),
    ("Q4", "Invoice lookup by posting_id",
     "SELECT * FROM {t} WHERE posting_id = {posting}"),
    ("Q5", "Monthly revenue, all of 2025 (big scan)",
     "SELECT date_key / 100 AS ym, SUM(amount) AS sales FROM {t} "
     "WHERE date_key BETWEEN 20250101 AND 20251231 GROUP BY 1 ORDER BY 1"),
]
WRITE_SQL = ("INSERT INTO {t} (postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount) "
             "SELECT postingdet_id, posting_id, bill_no, doc_type, date_key, customer_key, product_key, qty, rate, amount "
             "FROM bench.fact_src WHERE k = 0")


def fmt_ms(v):
    return f"{v:,.2f}" if v < 10 else f"{v:,.1f}"


def fmt_speedup(x):
    if x >= 1000:
        return ">1,000x"
    return f"{x:,.0f}x" if x >= 100 else f"{x:,.1f}x"


def run_file(cur, name, mult):
    sql = (BENCH / "sql" / name).read_text(encoding="utf-8").replace("{{mult}}", str(mult))
    cur.execute(sql)


def walk(plan, out):
    out.append(plan)
    for child in plan.get("Plans", []):
        walk(child, out)


def access_path(root):
    nodes = []
    walk(root, nodes)
    scans = [n for n in nodes if "Scan" in n["Node Type"] and n.get("Relation Name", "").startswith("fact_")]
    kinds = sorted({n["Node Type"] for n in scans})
    rels = {n["Relation Name"] for n in scans}
    parts = {r for r in rels if r.startswith("fact_part_")}
    text = " + ".join(kinds) if kinds else "?"
    if parts:
        text += f" on {len(parts)} partition(s)"
    fetches = sum(n.get("Heap Fetches", 0) for n in scans if n["Node Type"] == "Index Only Scan")
    if any(n["Node Type"] == "Index Only Scan" for n in scans):
        text += f" (heap fetches {fetches})"
    return text


def explain_json(cur, sql):
    cur.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql)
    doc = cur.fetchone()[0]
    if isinstance(doc, str):
        doc = json.loads(doc)
    return doc[0]


def measure(cur, sql, runs):
    explain_json(cur, sql)  # warm-up (not counted)
    ex, pl, last = [], [], None
    for _ in range(runs):
        last = explain_json(cur, sql)
        ex.append(last["Execution Time"])
        pl.append(last["Planning Time"])
    root = last["Plan"]
    buffers = root.get("Shared Hit Blocks", 0) + root.get("Shared Read Blocks", 0)
    return statistics.median(ex), min(ex), max(ex), statistics.median(pl), buffers, access_path(root)


def sizes(cur, table):
    if table.endswith("fact_part"):
        cur.execute("SELECT SUM(pg_table_size(relid)), SUM(pg_indexes_size(relid)) "
                    "FROM pg_partition_tree(%s::regclass) WHERE isleaf", (table,))
    else:
        cur.execute("SELECT pg_table_size(%s::regclass), pg_indexes_size(%s::regclass)", (table, table))
    t, i = cur.fetchone()
    return int(t) / 1e6, int(i) / 1e6


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--multiplier", type=int, default=20, help="scale-up factor (rows = 129K x multiplier)")
    ap.add_argument("--runs", type=int, default=5, help="timed runs per query (median reported)")
    ap.add_argument("--keep", action="store_true", help="do not drop schema bench at the end")
    ap.add_argument("--out", default=str(BENCH / "results"))
    args = ap.parse_args()
    out = Path(args.out)
    (out / "plans").mkdir(parents=True, exist_ok=True)

    conn = connect()
    conn.autocommit = True  # VACUUM cannot run inside a transaction
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM dw.fact_sales_line")
    except Exception:
        sys.exit("dw.fact_sales_line not found. Run the ETL first: python etl/run_etl.py --reset")
    base_rows = cur.fetchone()[0]
    if base_rows == 0:
        sys.exit("dw.fact_sales_line is empty. Run the ETL first.")

    print(f"Building scaled source: {base_rows:,} x {args.multiplier} rows ...")
    t0 = time.time()
    cur.execute("SET work_mem = '256MB'; SET maintenance_work_mem = '512MB'")  # build only
    run_file(cur, "01_scaled_source.sql", args.multiplier)
    cur.execute("SELECT COUNT(*) FROM bench.fact_src")
    total_rows = cur.fetchone()[0]
    print(f"  {total_rows:,} rows in {time.time() - t0:.0f}s")

    # Fixed, repeatable parameters: a busy customer and an existing invoice.
    cur.execute("SELECT customer_key FROM bench.fact_src GROUP BY 1 ORDER BY COUNT(*) DESC, 1 OFFSET 50 LIMIT 1")
    cust = cur.fetchone()[0]
    cur.execute("SELECT posting_id FROM bench.fact_src ORDER BY date_key, k, postingdet_id OFFSET %s LIMIT 1",
                (total_rows // 2,))
    posting = cur.fetchone()[0]
    print(f"  parameters: customer_key={cust}, posting_id={posting}")

    results, size_rows = [], []
    for stage, label, files, table in STAGES:
        print(f"\n== {stage}: {label}")
        t0 = time.time()
        cur.execute("SET work_mem = '256MB'; SET maintenance_work_mem = '512MB'")
        for f in files:
            run_file(cur, f, args.multiplier)
        cur.execute(f"VACUUM (ANALYZE) {table}")
        cur.execute("RESET work_mem; RESET maintenance_work_mem")  # measure with default settings
        tbl_mb, idx_mb = sizes(cur, table)
        size_rows.append((stage, tbl_mb, idx_mb))
        print(f"   built in {time.time() - t0:.0f}s   table {tbl_mb:,.0f} MB   indexes {idx_mb:,.0f} MB")

        params = {"t": table, "cust": cust, "posting": posting}
        for qid, qname, tmpl in QUERIES:
            sql = tmpl.format(**params)
            med, lo, hi, plan_ms, buffers, path = measure(cur, sql, args.runs)
            results.append(dict(stage=stage, query=qid, name=qname, median_ms=med, min_ms=lo, max_ms=hi,
                                planning_ms=plan_ms, buffers=buffers, access_path=path))
            cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql)
            (out / "plans" / f"{stage}_{qid}.txt").write_text(
                f"-- {qid}: {qname}\n-- {sql}\n\n" + "\n".join(r[0] for r in cur.fetchall()) + "\n", encoding="utf-8")
            print(f"   {qid} {med:9.2f} ms   {buffers:>9,} buffers   {path}")

        # Write cost: bulk-insert one copy of the data (129K rows), then roll back.
        times = []
        for _ in range(3):
            cur.execute("BEGIN")
            cur.execute("EXPLAIN (ANALYZE) " + WRITE_SQL.format(t=table))
            line = [r[0] for r in cur.fetchall() if r[0].startswith("Execution Time")][0]
            times.append(float(line.split(":")[1].replace("ms", "").strip()))
            cur.execute("ROLLBACK")
        results.append(dict(stage=stage, query="W1", name=f"Bulk insert {base_rows:,} rows",
                            median_ms=statistics.median(times), min_ms=min(times), max_ms=max(times),
                            planning_ms=0.0, buffers=0, access_path="insert + index maintenance"))
        print(f"   W1 {statistics.median(times):9.2f} ms   bulk insert of {base_rows:,} rows (rolled back)")

    # ------------------------------------------------------------ write reports
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()), lineterminator="\n")
        w.writeheader()
        for r in results:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})

    names = [s[0] for s in STAGES]
    by = {(r["stage"], r["query"]): r for r in results}
    qids = [q[0] for q in QUERIES] + ["W1"]
    qname = {r["query"]: r["name"] for r in results}
    cur.execute("SELECT split_part(version(), ' on ', 1), current_setting('shared_buffers'), "
                "current_setting('max_parallel_workers_per_gather'), current_setting('work_mem')")
    ver, sb, mpw, wm = cur.fetchone()
    md = [f"# Benchmark results\n",
          f"Scale-up: **{total_rows:,} rows** ({base_rows:,} x {args.multiplier}). Median of {args.runs} warm runs.\n",
          f"Environment: {ver}; shared_buffers={sb}, work_mem={wm}, max_parallel_workers_per_gather={mpw} "
          f"(defaults). Absolute times depend on the hardware; compare stages with each other.\n",
          "## Execution time (ms) and speedup vs. baseline\n",
          "| Query | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for q in qids:
        base = by[(names[0], q)]["median_ms"]
        cells = []
        for s in names:
            v = by[(s, q)]["median_ms"]
            cells.append(fmt_ms(v) if s == names[0] else f"{fmt_ms(v)} ({fmt_speedup(base / v)})")
        md.append(f"| {q} {qname[q]} | " + " | ".join(cells) + " |")
    md += ["\nSpeedup above 1x is faster than baseline; below 1x is slower (for W1, slower is the price of indexes).\n",
           "## Buffers touched (8 KB pages; fewer = less I/O)\n",
           "| Query | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for q in qids[:-1]:
        md.append(f"| {q} | " + " | ".join(f"{by[(s, q)]['buffers']:,}" for s in names) + " |")
    md += ["\n## Planning time (ms)\n",
           "| Query | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for q in qids[:-1]:
        md.append(f"| {q} | " + " | ".join(f"{by[(s, q)]['planning_ms']:.2f}" for s in names) + " |")
    md += ["\n## Access path chosen by the planner\n",
           "| Query | Stage | Path |", "|---|---|---|"]
    for q in qids[:-1]:
        for s in names:
            md.append(f"| {q} | {s} | {by[(s, q)]['access_path']} |")
    md += ["\n## Storage (MB)\n", "| Stage | Table | Indexes |", "|---|---:|---:|"]
    for s, t, i in size_rows:
        md.append(f"| {s} | {t:,.0f} | {i:,.0f} |")
    (out / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (out / "results.json").write_text(json.dumps(
        {"rows": total_rows, "multiplier": args.multiplier, "environment": [ver, sb, wm, mpw],
         "results": results, "sizes_mb": size_rows}, indent=1), encoding="utf-8")
    print(f"\nWrote {out / 'results.md'}, results.csv, results.json and plans/")

    if not args.keep:
        cur.execute("DROP SCHEMA bench CASCADE")
        print("Dropped schema bench (use --keep to retain it).")
    conn.close()


if __name__ == "__main__":
    main()
