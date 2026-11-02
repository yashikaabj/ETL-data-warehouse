#!/usr/bin/env python3
"""Sanity-check the generated dataset: PK uniqueness, FK integrity, and that every
injected data-quality issue in answer_key/dq_manifest.csv is actually detectable."""
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data")
B2 = os.path.join(D, "batch_2")
TABLES = ["PHSTATE", "PHHQ", "PHPARTY_A", "PHITEM", "PHPOSTING", "PHPOSTINGDET", "EMPLOYEE"]

con = sqlite3.connect(":memory:")
for t in TABLES:
    pd.read_csv(os.path.join(D, f"{t}.csv"), keep_default_na=False, na_values=[""],
                dtype={"STATE_NAME": str, "CUST_NAME": str, "HEAD_QTR": str}).to_sql(t, con, index=False)
for t in ["PHHQ", "PHITEM", "PHPARTY_A", "PHPOSTING", "PHPOSTINGDET"]:
    pd.read_csv(os.path.join(B2, f"{t}.csv"), keep_default_na=False, na_values=[""],
                dtype={"CUST_NAME": str, "HEAD_QTR": str}).to_sql(f"B2_{t}", con, index=False)
man = pd.read_csv(os.path.join(ROOT, "answer_key", "dq_manifest.csv"))
expected = man.groupby("issue_code").size().to_dict()


def q(sql):
    return con.execute(sql).fetchall()


ok = True


def check(label, got, want):
    global ok
    flag = "OK " if got == want else "FAIL"
    if got != want:
        ok = False
    print(f"[{flag}] {label}: got {got}, expected {want}")


print("== row counts ==")
for t in TABLES:
    print(f"  {t:14s} {q(f'SELECT COUNT(*) FROM {t}')[0][0]:>8}")

print("== primary keys unique ==")
for t, cols in [("PHSTATE", "ID"), ("PHHQ", "HQ_ID"), ("PHPARTY_A", "CUST_ID"), ("PHITEM", "ITEM_ID"),
                ("PHPOSTING", "POSTING_ID"), ("PHPOSTINGDET", "POSTINGDET_ID"), ("EMPLOYEE", "EMP_ID")]:
    check(t, q(f"SELECT COUNT(*) - COUNT(DISTINCT {cols}) FROM {t}")[0][0], 0)
check("PHPOSTING.BILL_NO unique", q("SELECT COUNT(*)-COUNT(DISTINCT BILL_NO) FROM PHPOSTING")[0][0], 0)

print("== injected issues are detectable ==")
check("ORPHAN_CUSTOMER", q("SELECT COUNT(*) FROM PHPOSTING WHERE CUST_ID NOT IN (SELECT CUST_ID FROM PHPARTY_A)")[0][0],
      expected["ORPHAN_CUSTOMER"])
check("ORPHAN_ITEM", q("SELECT COUNT(*) FROM PHPOSTINGDET WHERE ITEM_ID NOT IN (SELECT ITEM_ID FROM PHITEM)")[0][0],
      expected["ORPHAN_ITEM"])
check("ORPHAN det->posting", q("SELECT COUNT(*) FROM PHPOSTINGDET WHERE POSTING_ID NOT IN (SELECT POSTING_ID FROM PHPOSTING)")[0][0], 0)
check("HQ_UNASSIGNED", q("SELECT COUNT(*) FROM PHPARTY_A WHERE HQ_ID=0")[0][0], expected["HQ_UNASSIGNED"])
check("HQ_ORPHAN", q("SELECT COUNT(*) FROM PHPARTY_A WHERE HQ_ID<>0 AND HQ_ID NOT IN (SELECT HQ_ID FROM PHHQ)")[0][0],
      expected["HQ_ORPHAN"])
check("HQ_NO_STATE", q("SELECT COUNT(*) FROM PHHQ WHERE STATE_ID NOT IN (SELECT ID FROM PHSTATE)")[0][0],
      expected["HQ_NO_STATE"])
check("NAME_WHITESPACE_OR_CASE",
      q("SELECT COUNT(*) FROM PHPARTY_A WHERE CUST_NAME <> UPPER(TRIM(CUST_NAME)) OR CUST_NAME LIKE '%  %'")[0][0],
      expected["NAME_WHITESPACE_OR_CASE"])
check("DUPLICATE_STATE",
      q("SELECT COUNT(*) FROM (SELECT UPPER(TRIM(STATE_NAME)) n FROM PHSTATE GROUP BY n HAVING COUNT(*)>1)")[0][0],
      expected["DUPLICATE_STATE"])
check("ZERO_QTY", q("SELECT COUNT(*) FROM PHPOSTINGDET WHERE QTY=0")[0][0], expected["ZERO_QTY"])
check("AMOUNT_MISMATCH", q("SELECT COUNT(*) FROM PHPOSTINGDET WHERE ABS(AMOUNT-ROUND(QTY*RATE,2))>0.005")[0][0],
      expected["AMOUNT_MISMATCH"])
hdr_bad = q("""SELECT COUNT(*) FROM PHPOSTING p JOIN
               (SELECT POSTING_ID, SUM(AMOUNT) s FROM PHPOSTINGDET GROUP BY POSTING_ID) d USING(POSTING_ID)
               WHERE ABS(p.BILL_AMOUNT - d.s) > 0.01""")[0][0]
amt_posts = man[man.issue_code == "AMOUNT_MISMATCH"].key_value.astype(int).tolist()
n_amt_posts = q("SELECT COUNT(DISTINCT POSTING_ID) FROM PHPOSTINGDET WHERE POSTINGDET_ID IN (%s)"
                % ",".join(map(str, amt_posts)))[0][0]
check("HEADER_TOTAL_MISMATCH (+ postings with a bad line)", hdr_bad, expected["HEADER_TOTAL_MISMATCH"] + n_amt_posts)
print("  natural same name+HQ customer pairs (incl. 12 injected):",
      q("SELECT COUNT(*) FROM (SELECT 1 FROM PHPARTY_A WHERE HQ_ID<>0 GROUP BY UPPER(TRIM(CUST_NAME)), HQ_ID HAVING COUNT(*)>1)")[0][0])

print("== customer running total reconciles with posting headers ==")
bad = q("""SELECT COUNT(*) FROM PHPARTY_A c LEFT JOIN
           (SELECT CUST_ID, SUM(BILL_AMOUNT) s FROM PHPOSTING GROUP BY CUST_ID) p USING(CUST_ID)
           WHERE ABS(c.BILL_AMOUNT - COALESCE(p.s,0)) > 0.01""")[0][0]
print(f"  customers off vs. headers (only those with a tampered header): {bad}")

print("== batch_2 ==")
for t, col in [("PHHQ", "HQ_ID"), ("PHITEM", "ITEM_ID"), ("PHPARTY_A", "CUST_ID"),
               ("PHPOSTING", "POSTING_ID"), ("PHPOSTINGDET", "POSTINGDET_ID")]:
    check(f"B2_{t} keys unique", q(f"SELECT COUNT(*) - COUNT(DISTINCT {col}) FROM B2_{t}")[0][0], 0)
check("batch_2 HQs: ids that already existed keep the same state unless renamed",
      q("""SELECT COUNT(*) FROM B2_PHHQ b JOIN PHHQ m USING(HQ_ID) WHERE b.STATE_ID <> m.STATE_ID""")[0][0], 0)
check("new posting ids don't collide (excluding 15 resends)",
      q("SELECT COUNT(*) FROM B2_PHPOSTING b JOIN PHPOSTING m USING(POSTING_ID)")[0][0], 15)
check("resent rows identical",
      q("""SELECT COUNT(*) FROM B2_PHPOSTING b JOIN PHPOSTING m USING(POSTING_ID)
           WHERE b.BILL_AMOUNT=m.BILL_AMOUNT AND b.CUST_ID=m.CUST_ID AND b.POSTING_DATE=m.POSTING_DATE""")[0][0], 15)
check("late-arriving postings (Sep dates, new ids)",
      q("SELECT COUNT(*) FROM B2_PHPOSTING WHERE POSTING_DATE < '2026-10-01' AND POSTING_ID > (SELECT MAX(POSTING_ID) FROM PHPOSTING)")[0][0], 25)
check("batch_2 det lines all have a posting",
      q("SELECT COUNT(*) FROM B2_PHPOSTINGDET WHERE POSTING_ID NOT IN (SELECT POSTING_ID FROM B2_PHPOSTING)")[0][0], 0)
check("batch_2 det lines all have a known item",
      q("SELECT COUNT(*) FROM B2_PHPOSTINGDET WHERE ITEM_ID NOT IN (SELECT ITEM_ID FROM B2_PHITEM)")[0][0], 0)
check("batch_2 postings all have a known customer",
      q("SELECT COUNT(*) FROM B2_PHPOSTING WHERE CUST_ID NOT IN (SELECT CUST_ID FROM B2_PHPARTY_A)")[0][0], 0)
check("batch_2 header = sum of lines (clean batch)",
      q("""SELECT COUNT(*) FROM B2_PHPOSTING p JOIN
           (SELECT POSTING_ID, SUM(AMOUNT) s FROM B2_PHPOSTINGDET GROUP BY POSTING_ID) d USING(POSTING_ID)
           WHERE ABS(p.BILL_AMOUNT-d.s)>0.01""")[0][0], 0)
check("customers whose HQ changed",
      q("SELECT COUNT(*) FROM PHPARTY_A m JOIN B2_PHPARTY_A b USING(CUST_ID) WHERE m.HQ_ID<>b.HQ_ID")[0][0], 40)
check("new customers", q("SELECT COUNT(*) FROM B2_PHPARTY_A WHERE CUST_ID NOT IN (SELECT CUST_ID FROM PHPARTY_A)")[0][0], 60)

print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)
