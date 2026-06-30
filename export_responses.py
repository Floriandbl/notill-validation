#!/usr/bin/env python3
"""
export_responses.py - flatten the LOCAL SQLite responses into a tidy CSV.

Joins responses with their pair (province/year) and, when available, the
synthetic ground truth from pairs_metadata.csv, so r/analyze_responses.R can
read a plain CSV (no database packages required).

Usage:
    python export_responses.py            # -> responses_export.csv
    python export_responses.py out.csv

Columns: pair_id, province, year, respondent, created_at,
         <one column per answer key, e.g. q_a, q_b>,
         truth_a, truth_b   (only if pairs_metadata.csv is present)
"""
import csv
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "study.db")
META_CSV = os.path.join(ROOT, "pairs_metadata.csv")


def load_truth():
    truth = {}
    if os.path.exists(META_CSV):
        with open(META_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                truth[row["pair_id"]] = (row.get("truth_a", ""), row.get("truth_b", ""))
    return truth


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "responses_export.csv")
    if not os.path.exists(DB_PATH):
        sys.exit(f"No database at {DB_PATH}. Start app.py and collect some answers first.")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT r.pair_id, p.province, p.year, r.respondent, r.created_at, r.answers
        FROM responses r JOIN pairs p ON p.pair_id = r.pair_id
        ORDER BY r.created_at
    """).fetchall()
    con.close()

    truth = load_truth()
    # discover all answer keys across rows for stable columns
    parsed = []
    keys = []
    for r in rows:
        ans = json.loads(r["answers"])
        for k in ans:
            if k not in keys:
                keys.append(k)
        parsed.append((r, ans))

    has_truth = bool(truth)
    header = ["pair_id", "province", "year", "respondent", "created_at"] + keys
    if has_truth:
        header += ["truth_a", "truth_b"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r, ans in parsed:
            line = [r["pair_id"], r["province"], r["year"], r["respondent"], r["created_at"]]
            line += [ans.get(k, "") for k in keys]
            if has_truth:
                ta, tb = truth.get(r["pair_id"], ("", ""))
                line += [ta, tb]
            w.writerow(line)

    print(f"Exported {len(parsed)} responses -> {out_path}")
    if has_truth:
        print("Included synthetic truth columns (truth_a, truth_b) for self-checking.")


if __name__ == "__main__":
    main()
