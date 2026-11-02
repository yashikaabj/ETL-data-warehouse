#!/usr/bin/env python3
"""
Generate the ERP-style SOURCE dataset for the ETL / data-warehouse project.

Tables mirror the T-SQL practice scripts: PHSTATE, PHHQ, PHPARTY_A, PHITEM,
PHPOSTING, PHPOSTINGDET, EMPLOYEE (same column names and order).
The only addition is PHPOSTING.POSTING_DATE (needed for date dimensions and
incremental loads; the original DDL has no date column).

Output
  data/*.csv                full initial load (2025-01-01 .. 2026-09-30)
  data/batch_2/*.csv        next incremental load (October 2026)
  answer_key/*.csv          every injected data-quality issue / change event

Run:  python3 generate_dataset.py          (deterministic, SEED below)
"""
import csv
import math
import os
import random
from collections import defaultdict
from datetime import date, timedelta
from itertools import accumulate

SEED = 42
random.seed(SEED)

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
B2 = os.path.join(DATA, "batch_2")
KEY = os.path.join(ROOT, "answer_key")
for d in (DATA, B2, KEY):
    os.makedirs(d, exist_ok=True)

ORIGIN = date(2025, 1, 1)
MAIN_END = date(2026, 9, 30)
B2_START, B2_END = date(2026, 10, 1), date(2026, 10, 31)
N_CUSTOMERS = 3000

DQ = []        # data-quality manifest rows
CHANGES = []   # batch_2 change-event rows


def dq(table, key_col, key_val, issue, note=""):
    DQ.append(("main", table, key_col, key_val, issue, note))


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def m2(x):
    return f"{x:.2f}"


# ----------------------------------------------------------------- reference
STATES = [
    (1, "Andhra Pradesh"), (2, "Arunachal Pradesh"), (3, "Assam"), (4, "Bihar"),
    (5, "Chhattisgarh"), (6, "Goa"), (7, "Gujarat"), (8, "Haryana"),
    (9, "Himachal Pradesh"), (10, "Jharkhand"), (11, "Karnataka"),
    (12, "Uttarakhand"), (13, "Madhya Pradesh"), (14, "Maharashtra"),
    (15, "Odisha"), (16, "Punjab"), (17, "Rajasthan"), (18, "Tamil Nadu"),
    (19, "Telangana"), (20, "Uttar Pradesh"),
    (21, "MANIPUR"), (22, "KERALA"),            # upper-case, as in the practice script
    (23, "West Bengal"), (24, "Delhi"), (25, "Jammu and Kashmir"),
    (26, "Meghalaya"), (27, "Mizoram"), (28, "Nagaland"), (29, "Sikkim"),
    (30, "Tripura"), (31, "Chandigarh"), (32, "Puducherry"), (33, "Ladakh"),
]
DUP_STATE = (34, "UTTARAKHAND ")  # injected: trailing-space duplicate of id 12

HQ_BASE = [
    (101, "Visakhapatnam HQ", 1), (102, "Itanagar HQ", 2), (103, "Guwahati HQ", 3),
    (104, "Patna HQ", 4), (105, "Raipur HQ", 5), (106, "Panaji HQ", 6),
    (107, "Ahmedabad HQ", 7), (108, "Gurugram HQ", 8), (109, "Shimla HQ", 9),
    (110, "Ranchi HQ", 10), (111, "Bengaluru HQ", 11), (112, "Dehradun HQ", 12),
    (113, "Bhopal HQ", 13), (114, "Mumbai HQ", 14), (115, "Bhubaneswar HQ", 15),
    (116, "Chandigarh HQ", 16), (117, "Jaipur HQ", 17), (118, "Chennai HQ", 18),
    (119, "Hyderabad HQ", 19), (120, "Lucknow HQ", 20),
    (121, "HARIDWAR HQ", 12), (122, "AMRITSAR", 16), (123, "RUDRAPUR", 12),
]
HQ_EXTRA_NAMES = [
    ("Kochi HQ", 22), ("Thiruvananthapuram HQ", 22), ("Imphal HQ", 21),
    ("Kolkata HQ", 23), ("Siliguri HQ", 23), ("New Delhi HQ", 24),
    ("Srinagar HQ", 25), ("Jammu HQ", 25), ("Shillong HQ", 26),
    ("Aizawl HQ", 27), ("Kohima HQ", 28), ("Gangtok HQ", 29), ("Agartala HQ", 30),
    ("Pune HQ", 14), ("Nagpur HQ", 14), ("Nashik HQ", 14), ("Surat HQ", 7),
    ("Vadodara HQ", 7), ("Coimbatore HQ", 18), ("Madurai HQ", 18),
    ("Mysuru HQ", 11), ("Kanpur HQ", 20), ("Varanasi HQ", 20), ("Noida HQ", 20),
    ("Indore HQ", 13), ("Jodhpur HQ", 17), ("Ludhiana HQ", 16),
    ("Vijayawada HQ", 1), ("Cuttack HQ", 15), ("Haldwani HQ", 12),
    ("Faridabad HQ", 8), ("Kullu HQ", 9), ("Jamshedpur HQ", 10), ("Gaya HQ", 4),
    ("Dibrugarh HQ", 3), ("Bilaspur HQ", 5), ("Margao HQ", 6), ("Warangal HQ", 19),
]
HQS = list(HQ_BASE)
for i, (n, s) in enumerate(HQ_EXTRA_NAMES):
    HQS.append((124 + i, n, s))
HQ_JUNK = [(22, "PUNJAB", 0), (23, "UTTAKHAND", 0)]  # leftovers from the practice script
REAL_HQ_IDS = [h[0] for h in HQS]

# ---------------------------------------------------------------------- items
TYPES = [  # (type, low, high, brands) -- first 20 also exist as plain generic items
    ("MOUSE", 350, 1800, ["LOGITECH", "HP", "DELL", "ZEBRONICS"]),
    ("KEYBOARD", 600, 3500, ["LOGITECH", "HP", "DELL", "ZEBRONICS"]),
    ("LAPTOP", 32000, 125000, ["HP", "DELL", "LENOVO", "ASUS"]),
    ("MONITOR", 7000, 32000, ["SAMSUNG", "LG", "DELL", "HP"]),
    ("PRINTER", 6000, 38000, ["HP", "CANON", "EPSON", "BROTHER"]),
    ("SCANNER", 5000, 25000, ["CANON", "EPSON", "HP", "BROTHER"]),
    ("UPS", 2800, 14000, ["APC", "LUMINOUS", "MICROTEK", "ZEBRONICS"]),
    ("ROUTER", 1200, 9000, ["TP-LINK", "D-LINK", "NETGEAR", "ASUS"]),
    ("NETWORK SWITCH", 1500, 22000, ["TP-LINK", "D-LINK", "NETGEAR", "CISCO"]),
    ("HARD DISK", 3500, 9000, ["SEAGATE", "WD", "TOSHIBA", "SAMSUNG"]),
    ("SSD", 2200, 14000, ["SAMSUNG", "WD", "CRUCIAL", "KINGSTON"]),
    ("RAM", 1800, 9500, ["CRUCIAL", "KINGSTON", "CORSAIR", "SAMSUNG"]),
    ("PEN DRIVE", 400, 2200, ["SANDISK", "HP", "KINGSTON", "SAMSUNG"]),
    ("PROJECTOR", 22000, 80000, ["EPSON", "BENQ", "ACER", "VIEWSONIC"]),
    ("WEBCAM", 1200, 6500, ["LOGITECH", "HP", "DELL", "ZEBRONICS"]),
    ("HEADPHONE", 800, 9000, ["BOAT", "JBL", "SONY", "LOGITECH"]),
    ("SPEAKER", 900, 12000, ["JBL", "BOAT", "SONY", "LOGITECH"]),
    ("TABLET", 9000, 65000, ["SAMSUNG", "LENOVO", "APPLE", "XIAOMI"]),
    ("MOBILE PHONE", 8000, 95000, ["SAMSUNG", "XIAOMI", "ONEPLUS", "APPLE"]),
    ("DESKTOP PC", 28000, 90000, ["HP", "DELL", "LENOVO", "ASUS"]),
    ("CCTV CAMERA", 1800, 7500, ["HIKVISION", "CP PLUS", "DAHUA", "GODREJ"]),
    ("POWER BANK", 800, 3500, ["MI", "ANKER", "BOAT", "PTRON"]),
    ("LAPTOP BAG", 700, 3000, ["WILDCRAFT", "HP", "DELL", "LENOVO"]),
    ("HDMI CABLE", 200, 900, ["BELKIN", "PORTRONICS", "ZEBRONICS", "AMAZONBASICS"]),
    ("MEMORY CARD", 350, 2200, ["SANDISK", "SAMSUNG", "KINGSTON", "LEXAR"]),
    ("GRAPHICS CARD", 14000, 85000, ["NVIDIA", "ASUS", "MSI", "GIGABYTE"]),
    ("MOTHERBOARD", 6500, 28000, ["ASUS", "MSI", "GIGABYTE", "ASROCK"]),
    ("PROCESSOR", 8000, 52000, ["INTEL", "AMD", "INTEL", "AMD"]),
    ("SMPS", 1800, 7500, ["CORSAIR", "COOLER MASTER", "ANTEC", "ZEBRONICS"]),
    ("CABINET", 1800, 8500, ["COOLER MASTER", "ANTEC", "ZEBRONICS", "CORSAIR"]),
]
GENERIC_ORDER = ["MOUSE", "KEYBOARD", "LAPTOP", "MONITOR", "PRINTER", "SCANNER", "UPS",
                 "ROUTER", "NETWORK SWITCH", "HARD DISK", "SSD", "RAM", "PEN DRIVE",
                 "PROJECTOR", "WEBCAM", "HEADPHONE", "SPEAKER", "TABLET",
                 "MOBILE PHONE", "DESKTOP PC"]
TYPE_BY_NAME = {t[0]: t for t in TYPES}


def build_items():
    items, n = [], 0

    def add(name, base):
        nonlocal n
        n += 1
        items.append({"id": 400 + n, "name": name, "code": f"ITM{n:03d}", "base": base})

    for t in GENERIC_ORDER:
        _, lo, hi, _ = TYPE_BY_NAME[t]
        add(t, round(random.uniform(lo, hi) / 10) * 10)
    for t, lo, hi, brands in TYPES:
        for b in brands:
            model = random.choice("ABCDEFGHKMPRSTX") + str(random.randint(100, 990))
            add(f"{t} {b} {model}", round(random.uniform(lo, hi) / 10) * 10)
    return items


ITEMS = build_items()

# ------------------------------------------------------------------ people/names
FIRST = ("AARAV ADITYA AKASH AMAN ANANYA ANISHA ANJALI ANKIT ARJUN AYUSH DEEPAK DEV DIVYA "
         "GAURAV HARSH HIMANSHU ISHAN JATIN KAVYA KARAN LAKSHAY MANISH MEERA NEHA NIKHIL "
         "NISHA PALLAVI PARTH POOJA PRIYA RAHUL RAJAT RIYA ROHAN ROHIT SANYA SAURABH SHREYA "
         "SHIVAM SIMRAN SNEHA SURAJ TANYA TARUN UTKARSH VAIBHAV VIKAS VIVEK YOGESH ZOYA "
         "ABHAY ALOK BHUMIKA CHETAN DISHA ESHA FARHAN GARIMA HARLEEN INDER JASPREET").split()
LAST = ("SHARMA VERMA GUPTA SINGH KUMAR JOSHI BISHT RAWAT NEGI PANDEY MISHRA TIWARI YADAV "
        "CHAUHAN THAKUR AGARWAL JAIN MEHTA PATEL SHAH REDDY NAIR IYER RAO DAS BOSE GHOSH SEN "
        "KAPOOR MALHOTRA BHATIA ARORA SETHI KHANNA SAXENA SRIVASTAVA DUBEY TRIPATHI PATHAK "
        "BANSAL GOEL MITTAL KULKARNI DESHMUKH PAWAR SHINDE NAYAK MENON PILLAI CHOPRA").split()


def full_name():
    return f"{random.choice(FIRST)} {random.choice(LAST)}"


# -------------------------------------------------------------------- EMPLOYEE
def gen_employees(n=60):
    rows, used = [], set()
    for i in range(1, n + 1):
        while True:
            nm = full_name()
            if nm not in used:
                used.add(nm)
                break
        if i == 1:
            mgr = ""
        elif i <= 5:
            mgr = 1
        elif i <= 20:
            mgr = random.randint(2, 5)
        elif i <= 45:
            mgr = random.randint(6, 20)
        else:
            mgr = random.randint(21, 45)
        rows.append((i, nm, mgr))
    return rows


# --------------------------------------------------------------------- customers
def gen_customers():
    hq_w = {h: random.lognormvariate(0, 0.7) for h in REAL_HQ_IDS}
    ids = list(hq_w)
    cum = list(accumulate(hq_w[h] for h in ids))
    cust = {}
    for cid in range(1, N_CUSTOMERS + 1):
        cust[cid] = {"name": full_name(),
                     "hq": random.choices(ids, cum_weights=cum)[0],
                     "csbc": "CUSTOMER", "bill": 0.0}
    return cust


CUST = gen_customers()
# activity weights: a few customers buy a lot (Pareto), duplicates (added later) get 0
CUST_W = {cid: min(random.paretovariate(1.4), 60.0) for cid in CUST}

# ------------------------------------------------------------------- postings
DOC_TYPES, DOC_W = ["SALE", "INVOICE", "BILL"], [80, 12, 8]
NL_W = [10, 22, 24, 18, 11, 7, 5, 3]  # lines per posting 1..8


def draw_qty(base):
    if base < 3000:
        return random.choices(range(1, 21), [20, 18, 15, 12, 10, 8, 6, 5, 4, 3, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1])[0]
    if base < 20000:
        return random.choices(range(1, 11), [30, 22, 15, 10, 8, 5, 4, 3, 2, 1])[0]
    return random.choices(range(1, 5), [60, 25, 10, 5])[0]


def month_idx(d):
    return (d.year - ORIGIN.year) * 12 + d.month - ORIGIN.month


def make_item_weights(items):
    return list(accumulate(random.lognormvariate(0, 0.9) / (it["base"] ** 0.25) for it in items))


def make_one(d, pid, did, cust_ids, cust_cum, items, item_cum, zero_qty_rate, zero_log):
    mi = month_idx(d)
    cust = random.choices(cust_ids, cum_weights=cust_cum)[0]
    doc = random.choices(DOC_TYPES, DOC_W)[0]
    nl = random.choices(range(1, 9), NL_W)[0]
    picks = []
    while len(picks) < nl:
        k = random.choices(range(len(items)), cum_weights=item_cum)[0]
        if k not in picks:
            picks.append(k)
    dets, total = [], 0.0
    for k in picks:
        it = items[k]
        qty = draw_qty(it["base"])
        rate = round(it["base"] * (1 + 0.004 * mi) * random.uniform(0.95, 1.07), 2)
        if zero_qty_rate and random.random() < zero_qty_rate:
            qty = 0
            zero_log.append(did)
        amt = round(qty * rate, 2)
        total += amt
        dets.append([it["id"], qty, rate, amt, pid, did])
        did += 1
    return [pid, doc, round(total, 2), cust, 1000 + pid, d.isoformat()], dets, did


def gen_postings(d0, d1, pid0, did0, cust_ids, cust_cum, items, item_cum, zero_qty_rate=0.0):
    postings, dets, zero_log = [], [], []
    pid, did, d = pid0, did0, d0
    while d <= d1:
        growth = 1 + 0.012 * month_idx(d)
        lam = 55 * growth * {5: 0.8, 6: 0.35}.get(d.weekday(), 1.0)
        n = max(0, int(round(random.gauss(lam, math.sqrt(lam)))))
        for _ in range(n):
            p, dd, did = make_one(d, pid, did, cust_ids, cust_cum, items, item_cum, zero_qty_rate, zero_log)
            postings.append(p)
            dets.extend(dd)
            pid += 1
        d += timedelta(days=1)
    return postings, dets, zero_log


cust_ids = list(CUST)
cust_cum = list(accumulate(CUST_W[c] for c in cust_ids))
item_cum = make_item_weights(ITEMS)

POSTINGS, DETS, ZERO_LOG = gen_postings(ORIGIN, MAIN_END, 1, 1, cust_ids, cust_cum, ITEMS, item_cum,
                                        zero_qty_rate=0.002)
for did in ZERO_LOG:
    dq("PHPOSTINGDET", "POSTINGDET_ID", did, "ZERO_QTY", "QTY=0 and AMOUNT=0")

# ----------------------------------------------------- injections (main load)
rng_p = list(range(len(POSTINGS)))
rng_d = list(range(len(DETS)))
random.shuffle(rng_p)
random.shuffle(rng_d)

# 1) orphan customer on postings (excluded from customer totals)
for idx in rng_p[:90]:
    POSTINGS[idx][3] = 99999
    dq("PHPOSTING", "POSTING_ID", POSTINGS[idx][0], "ORPHAN_CUSTOMER", "CUST_ID=99999 not in PHPARTY_A")
orphan_posting_idx = set(rng_p[:90])

# 2) customer running totals = sum of true header totals of postings that still point at them
for p in POSTINGS:
    if p[3] in CUST:
        CUST[p[3]]["bill"] += p[2]
for c in CUST.values():
    c["bill"] = round(c["bill"], 2)

# 3) detail-line AMOUNT mismatches (header keeps the correct total)
zero_set = set(ZERO_LOG)
det_candidates = [i for i in rng_d if DETS[i][5] not in zero_set]
mismatch_idx = det_candidates[:420]
mismatch_posting_ids = set()
for i in mismatch_idx:
    DETS[i][3] = round(DETS[i][3] * random.choice([0.5, 0.9, 1.1, 1.5]) + 1, 2)
    mismatch_posting_ids.add(DETS[i][4])
    dq("PHPOSTINGDET", "POSTINGDET_ID", DETS[i][5], "AMOUNT_MISMATCH", "AMOUNT <> QTY*RATE")

# 4) orphan item ids on detail lines
for i in det_candidates[420:560]:
    old = DETS[i][0]
    DETS[i][0] = 999
    dq("PHPOSTINGDET", "POSTINGDET_ID", DETS[i][5], "ORPHAN_ITEM", f"ITEM_ID=999 not in PHITEM (was {old})")

# 5) header total <> sum of its detail amounts (postings not otherwise touched)
hdr_pool = [i for i in rng_p[90:] if POSTINGS[i][0] not in mismatch_posting_ids]
for idx in hdr_pool[:135]:
    POSTINGS[idx][2] = round(POSTINGS[idx][2] + random.choice([-1, 1]) * random.randint(50, 5000), 2)
    dq("PHPOSTING", "POSTING_ID", POSTINGS[idx][0], "HEADER_TOTAL_MISMATCH", "BILL_AMOUNT <> SUM(detail AMOUNT)")

# 6) customer-table issues
cids = list(CUST)
random.shuffle(cids)
for cid in cids[:45]:
    CUST[cid]["hq"] = 0
    dq("PHPARTY_A", "CUST_ID", cid, "HQ_UNASSIGNED", "HQ_ID=0 (default); map to an 'Unknown' member")
for cid in cids[45:60]:
    CUST[cid]["hq"] = random.choice([998, 999])
    dq("PHPARTY_A", "CUST_ID", cid, "HQ_ORPHAN", "HQ_ID not in PHHQ")
for cid in cids[60:120]:
    nm = CUST[cid]["name"]
    CUST[cid]["name"] = random.choice([" " + nm, nm + " ", nm.title(), nm.replace(" ", "  ")])
    dq("PHPARTY_A", "CUST_ID", cid, "NAME_WHITESPACE_OR_CASE", repr(CUST[cid]["name"]))
NEXT_CID = N_CUSTOMERS + 1
for src in cids[120:132]:
    CUST[NEXT_CID] = {"name": CUST[src]["name"], "hq": CUST[src]["hq"], "csbc": "CUSTOMER", "bill": 0.0}
    CUST_W[NEXT_CID] = 0.0
    dq("PHPARTY_A", "CUST_ID", NEXT_CID, "DUPLICATE_CUSTOMER", f"same name+HQ as CUST_ID {src}")
    NEXT_CID += 1

dq("PHSTATE", "ID", DUP_STATE[0], "DUPLICATE_STATE", "'UTTARAKHAND ' (trailing space) duplicates ID 12")
for h in HQ_JUNK:
    dq("PHHQ", "HQ_ID", h[0], "HQ_NO_STATE", f"{h[1]!r} has STATE_ID=0")

# ------------------------------------------------------------------- write main
STATE_ROWS = STATES + [DUP_STATE]
HQ_ROWS = HQ_JUNK + HQS
HQ_ROWS.sort(key=lambda r: r[0])
write_csv(f"{DATA}/PHSTATE.csv", ["ID", "STATE_NAME"], STATE_ROWS)
write_csv(f"{DATA}/PHHQ.csv", ["HQ_ID", "HEAD_QTR", "STATE_ID"], HQ_ROWS)
write_csv(f"{DATA}/PHITEM.csv", ["ITEM_ID", "ITEM_NAME", "ITEM_CODE"],
          [(i["id"], i["name"], i["code"]) for i in ITEMS])


def cust_rows():
    return [(cid, c["name"], c["hq"], c["csbc"], m2(c["bill"])) for cid, c in sorted(CUST.items())]


write_csv(f"{DATA}/PHPARTY_A.csv", ["CUST_ID", "CUST_NAME", "HQ_ID", "CSBC", "BILL_AMOUNT"], cust_rows())
write_csv(f"{DATA}/PHPOSTING.csv",
          ["POSTING_ID", "DOC_TYPE", "BILL_AMOUNT", "CUST_ID", "BILL_NO", "POSTING_DATE"],
          [(p[0], p[1], m2(p[2]), p[3], p[4], p[5]) for p in POSTINGS])
write_csv(f"{DATA}/PHPOSTINGDET.csv",
          ["ITEM_ID", "QTY", "RATE", "AMOUNT", "POSTING_ID", "POSTINGDET_ID"],
          [(d[0], d[1], m2(d[2]), m2(d[3]), d[4], d[5]) for d in DETS])
EMP = gen_employees()
write_csv(f"{DATA}/EMPLOYEE.csv", ["EMP_ID", "EMP_NAME", "MNGR_ID"], EMP)

# ======================================================================= BATCH 2
snapshot_main = {cid: dict(c) for cid, c in CUST.items()}

# items: 6 new, 3 renamed
renames = {407: "UPS 600VA", 413: "USB PEN DRIVE", 415: "HD WEBCAM"}
for iid, nm in renames.items():
    it = next(i for i in ITEMS if i["id"] == iid)
    CHANGES.append(("PHITEM", "ITEM_ID", iid, "ITEM_RENAMED", f"{it['name']} -> {nm}"))
    it["name"] = nm
new_items = [("SMART WATCH", 4500), ("NVME SSD 1TB", 6500), ("WIFI 6 ROUTER", 7200),
             ("GAMING MOUSE", 2100), ("MECHANICAL KEYBOARD", 3800), ("USB-C DOCK", 5200)]
nid = max(i["id"] for i in ITEMS)
for nm, base in new_items:
    nid += 1
    ITEMS.append({"id": nid, "name": nm, "code": f"ITM{nid - 400:03d}", "base": base})
    CHANGES.append(("PHITEM", "ITEM_ID", nid, "NEW_ITEM", nm))
item_cum2 = make_item_weights(ITEMS)

# HQs: 2 new, 1 renamed
HQ2 = [list(h) for h in HQ_ROWS]
for h in HQ2:
    if h[0] == 122:
        CHANGES.append(("PHHQ", "HQ_ID", 122, "HQ_RENAMED", "AMRITSAR -> Amritsar HQ"))
        h[1] = "Amritsar HQ"
for hid, nm, sid in [(200, "Prayagraj HQ", 20), (201, "Hubballi HQ", 11)]:
    HQ2.append([hid, nm, sid])
    REAL_HQ_IDS.append(hid)
    CHANGES.append(("PHHQ", "HQ_ID", hid, "NEW_HQ", nm))

# customers: 40 HQ moves (SCD2), 60 new
clean = [cid for cid in CUST if CUST[cid]["hq"] in REAL_HQ_IDS and CUST_W.get(cid, 0) > 0
         and CUST[cid]["name"] == CUST[cid]["name"].strip()]
movers = random.sample(clean, 40)
for cid in movers:
    old = CUST[cid]["hq"]
    new = random.choice([h for h in REAL_HQ_IDS if h != old])
    CUST[cid]["hq"] = new
    CHANGES.append(("PHPARTY_A", "CUST_ID", cid, "HQ_CHANGED_SCD2", f"HQ_ID {old} -> {new}"))
for _ in range(60):
    CUST[NEXT_CID] = {"name": full_name(), "hq": random.choice(REAL_HQ_IDS), "csbc": "CUSTOMER", "bill": 0.0}
    CUST_W[NEXT_CID] = min(random.paretovariate(1.4), 60.0)
    CHANGES.append(("PHPARTY_A", "CUST_ID", NEXT_CID, "NEW_CUSTOMER", CUST[NEXT_CID]["name"]))
    NEXT_CID += 1

cust_ids2 = list(CUST)
cust_cum2 = list(accumulate(CUST_W[c] for c in cust_ids2))
P2, D2, _ = gen_postings(B2_START, B2_END, POSTINGS[-1][0] + 1, DETS[-1][5] + 1,
                         cust_ids2, cust_cum2, ITEMS, item_cum2)

# 25 late-arriving postings: Sept dates but new IDs (a date watermark would miss them)
pid2, did2 = P2[-1][0] + 1, D2[-1][5] + 1
late_p, late_d = [], []
for _ in range(25):
    d = date(2026, 9, random.randint(15, 30))
    p, dd, did2 = make_one(d, pid2, did2, cust_ids2, cust_cum2, ITEMS, item_cum2, 0, [])
    late_p.append(p)
    late_d.extend(dd)
    CHANGES.append(("PHPOSTING", "POSTING_ID", pid2, "LATE_ARRIVING", f"POSTING_DATE={p[5]} but new ID"))
    pid2 += 1

# 15 re-sent postings (identical to rows already loaded) -> tests idempotent loads
resent_p = POSTINGS[-15:]
resent_ids = {p[0] for p in resent_p}
resent_d = [d for d in DETS if d[4] in resent_ids]
for p in resent_p:
    CHANGES.append(("PHPOSTING", "POSTING_ID", p[0], "RESENT_DUPLICATE", "identical to main load"))

# customer running totals for the snapshot
for p in P2 + late_p:
    CUST[p[3]]["bill"] += p[2]
for c in CUST.values():
    c["bill"] = round(c["bill"], 2)

write_csv(f"{B2}/PHHQ.csv", ["HQ_ID", "HEAD_QTR", "STATE_ID"], sorted(HQ2))
write_csv(f"{B2}/PHITEM.csv", ["ITEM_ID", "ITEM_NAME", "ITEM_CODE"],
          [(i["id"], i["name"], i["code"]) for i in ITEMS])
write_csv(f"{B2}/PHPARTY_A.csv", ["CUST_ID", "CUST_NAME", "HQ_ID", "CSBC", "BILL_AMOUNT"], cust_rows())
all_p = resent_p + P2 + late_p
all_d = resent_d + D2 + late_d
write_csv(f"{B2}/PHPOSTING.csv",
          ["POSTING_ID", "DOC_TYPE", "BILL_AMOUNT", "CUST_ID", "BILL_NO", "POSTING_DATE"],
          [(p[0], p[1], m2(p[2]), p[3], p[4], p[5]) for p in all_p])
write_csv(f"{B2}/PHPOSTINGDET.csv",
          ["ITEM_ID", "QTY", "RATE", "AMOUNT", "POSTING_ID", "POSTINGDET_ID"],
          [(d[0], d[1], m2(d[2]), m2(d[3]), d[4], d[5]) for d in all_d])

# ----------------------------------------------------------------- answer key
write_csv(f"{KEY}/dq_manifest.csv", ["load", "table", "key_column", "key_value", "issue_code", "note"], DQ)
write_csv(f"{KEY}/batch2_changes.csv", ["table", "key_column", "key_value", "event", "note"], CHANGES)

# -------------------------------------------------------------------- summary
counts = defaultdict(int)
for r in DQ:
    counts[(r[1], r[4])] += 1
ev = defaultdict(int)
for r in CHANGES:
    ev[r[3]] += 1
rows_main = {"PHSTATE": len(STATE_ROWS), "PHHQ": len(HQ_ROWS), "PHPARTY_A": len(snapshot_main),
             "PHITEM": len(ITEMS) - len(new_items), "PHPOSTING": len(POSTINGS),
             "PHPOSTINGDET": len(DETS), "EMPLOYEE": len(EMP)}
rows_b2 = {"PHHQ": len(HQ2), "PHITEM": len(ITEMS), "PHPARTY_A": len(CUST),
           "PHPOSTING": len(all_p), "PHPOSTINGDET": len(all_d)}
print("MAIN", rows_main)
print("BATCH2", rows_b2)
print("DQ", dict(counts))
print("EVENTS", dict(ev))
print("date range main", POSTINGS[0][5], POSTINGS[-1][5], "batch2 new", P2[0][5], P2[-1][5])
print("total sales main", round(sum(p[2] for p in POSTINGS), 2))
