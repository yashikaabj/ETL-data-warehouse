#!/usr/bin/env python3
"""
Run one ETL batch: src schema -> stg -> dw (star schema), with audit logging.

  python etl/run_etl.py --reset                                   # drop + rebuild warehouse, load initial data
  python etl/run_etl.py --source-schema src_batch2 --effective-date 2026-10-01
  python etl/run_etl.py --source-schema src_batch2 --effective-date 2026-10-01 --ignore-watermark

Connection: standard PG* environment variables (defaults match docker-compose.yml).
"""
import argparse
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql" / "warehouse"
PIPELINE = [
    "01_stage.sql",
    "02_validate.sql",
    "03_dim_geography.sql",
    "04_dim_product.sql",
    "05_dim_customer.sql",
    "06_fact_sales_line.sql",
    "07_reconcile_and_watermark.sql",
]
ALLOWED_SOURCES = {"src", "src_batch2"}
HEADER = re.compile(r"^-- @@ (\S+)(.*)$", re.M)


def connect():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5433"),
        dbname=os.getenv("PGDATABASE", "warehouse"),
        user=os.getenv("PGUSER", "etl"),
        password=os.getenv("PGPASSWORD", "etl"),
    )


def parse_statements(path):
    """Split a step file into (name, requires, sql) using '-- @@ name [requires=table]' markers."""
    text = path.read_text(encoding="utf-8")
    marks = list(HEADER.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        req = re.search(r"requires=(\w+)", m.group(2))
        out.append((m.group(1), req.group(1) if req else None, text[m.end():end].strip()))
    return out


def table_exists(cur, schema, table):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"{schema}.{table}",))
    return cur.fetchone()[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-schema", default="src", choices=sorted(ALLOWED_SOURCES))
    ap.add_argument("--effective-date", help="YYYY-MM-DD when new SCD2 versions become valid "
                                             "(defaults to 1900-01-01 for the initial load, required otherwise)")
    ap.add_argument("--ignore-watermark", action="store_true",
                    help="re-extract everything from the source (tests idempotent loads)")
    ap.add_argument("--reset", action="store_true", help="DROP stg/dw/audit schemas first (full rebuild)")
    args = ap.parse_args()

    if args.effective_date:
        eff = date.fromisoformat(args.effective_date)
    elif args.source_schema == "src":
        eff = date(1900, 1, 1)
    else:
        sys.exit("--effective-date is required for incremental batches (e.g. 2026-10-01)")

    conn = connect()
    cur = conn.cursor()

    if args.reset:
        cur.execute("DROP SCHEMA IF EXISTS stg CASCADE; DROP SCHEMA IF EXISTS dw CASCADE; DROP SCHEMA IF EXISTS audit CASCADE;")
        conn.commit()
        print("Reset: dropped stg, dw, audit")

    # DDL is idempotent; run it every time so a fresh database just works.
    cur.execute((SQL_DIR / "00_ddl.sql").read_text(encoding="utf-8"))
    cur.execute("INSERT INTO audit.etl_run (source_schema, effective_date) VALUES (%s, %s) RETURNING run_id",
                (args.source_schema, eff))
    run_id = cur.fetchone()[0]
    conn.commit()  # the run row survives even if the work below is rolled back
    print(f"Run {run_id}: source={args.source_schema} effective_date={eff} "
          f"watermark={'ignored' if args.ignore_watermark else 'on'}")

    try:
        cur.execute("SELECT last_value FROM audit.watermark WHERE table_name = 'phposting.posting_id'")
        wm = 0 if args.ignore_watermark else cur.fetchone()[0]
        repl = {"{{run_id}}": str(run_id), "{{src}}": args.source_schema, "{{eff}}": f"'{eff.isoformat()}'", "{{wm}}": str(wm)}

        for fname in PIPELINE:
            for name, requires, sql in parse_statements(SQL_DIR / fname):
                step = f"{fname[:-4]}:{name}"
                if requires and not table_exists(cur, args.source_schema, requires):
                    print(f"  - {step:<52} skipped ({args.source_schema}.{requires} not in this batch)")
                    continue
                for k, v in repl.items():
                    sql = sql.replace(k, v)
                t0 = time.time()
                cur.execute(sql)
                ms = int((time.time() - t0) * 1000)
                n = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else None
                cur.execute("INSERT INTO audit.etl_step_log (run_id, step, rows_affected, duration_ms) VALUES (%s,%s,%s,%s)",
                            (run_id, step, n, ms))
                print(f"  - {step:<52} {'' if n is None else f'{n:>8} rows':>13} {ms:>6} ms")

        cur.execute("UPDATE audit.etl_run SET status='SUCCESS', finished_at=now() WHERE run_id=%s", (run_id,))
        conn.commit()
    except Exception as exc:  # roll back all warehouse changes; keep the failed run row for diagnosis
        conn.rollback()
        cur.execute("UPDATE audit.etl_run SET status='FAILED', finished_at=now(), error=%s WHERE run_id=%s",
                    (str(exc)[:2000], run_id))
        conn.commit()
        print(f"\nRun {run_id} FAILED and was rolled back:\n{exc}", file=sys.stderr)
        sys.exit(1)

    print("\nData-quality results")
    cur.execute("""SELECT severity, check_name, failed_rows, handling FROM audit.dq_check_result
                   WHERE run_id = %s ORDER BY CASE severity WHEN 'ERROR' THEN 1 WHEN 'WARN' THEN 2 ELSE 3 END, id""",
                (run_id,))
    for sev, name, n, handling in cur.fetchall():
        print(f"  [{sev:<5}] {name:<40} {n:>8}  {handling}")

    print("\nWarehouse row counts")
    for t in ["dim_date", "dim_geography", "dim_product", "dim_customer", "fact_sales_line"]:
        cur.execute(f"SELECT COUNT(*) FROM dw.{t}")
        print(f"  dw.{t:<18} {cur.fetchone()[0]:>9,}")
    cur.execute("SELECT COUNT(*) FROM audit.rejected_rows WHERE run_id = %s", (run_id,))
    print(f"  rejected this run  {cur.fetchone()[0]:>9,}")
    conn.close()


if __name__ == "__main__":
    main()
