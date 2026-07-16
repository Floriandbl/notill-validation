#!/usr/bin/env python3
"""
export_responses.py — flatten the LOCAL SQLite responses into a tidy CSV for R.

Model-agnostic: whatever answer keys exist in the `answers` JSON become columns
(currently q_field and the conditional q_when), plus the technical context that
is now recorded with every answer (ip + selected meta fields).

Usage:
    python export_responses.py            # -> responses_export.csv
    python export_responses.py out.csv

Columns:
    field_id, province, year, respondent, created_at, ip,
    <one per answer key: q_field, q_when, ...>,
    meta_timezone, meta_tz_offset_min, meta_client_time, meta_platform,
    meta_language, meta_screen, meta_user_agent,
    truth_a, truth_b        (only if pairs_metadata.csv still carries synthetic truth)

For PRODUCTION data pulled from Supabase, export the `responses` table to CSV from
the dashboard instead — it has the same answers/meta/ip fields.
"""
import csv
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "data", "study.db")
META_CSV = os.path.join(ROOT, "pairs_metadata.csv")

META_FIELDS = ["timezone", "tz_offset_min", "client_time", "platform",
               "language", "screen", "user_agent"]


def load_truth():
    """Synthetic truth, if the placeholder metadata is still around."""
    truth = {}
    if os.path.exists(META_CSV):
        with open(META_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("truth_a"):
                    truth[row["pair_id"]] = (row.get("truth_a", ""), row.get("truth_b", ""))
    return truth


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "responses_export.csv")
    if not os.path.exists(DB_PATH):
        sys.exit(f"No database at {DB_PATH}. Collect some answers first.")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cols_present = {r[1] for r in con.execute("PRAGMA table_info(responses)")}
    sel = ["r.pair_id", "p.province", "p.year", "r.respondent", "r.created_at", "r.answers"]
    sel.append("r.ip" if "ip" in cols_present else "NULL AS ip")
    sel.append("r.meta" if "meta" in cols_present else "NULL AS meta")
    rows = con.execute(f"""
        SELECT {', '.join(sel)}
        FROM responses r JOIN pairs p ON p.pair_id = r.pair_id
        ORDER BY r.created_at
    """).fetchall()
    con.close()

    parsed, keys = [], []
    for r in rows:
        ans = json.loads(r["answers"] or "{}")
        meta = json.loads(r["meta"] or "{}") if r["meta"] else {}
        for k in ans:
            if k not in keys:
                keys.append(k)
        parsed.append((r, ans, meta))

    truth = load_truth()
    has_truth = bool(truth)
    header = (["field_id", "province", "year", "respondent", "created_at", "ip"]
              + keys + [f"meta_{m}" for m in META_FIELDS])
    if has_truth:
        header += ["truth_a", "truth_b"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r, ans, meta in parsed:
            line = [r["pair_id"], r["province"], r["year"], r["respondent"],
                    r["created_at"], r["ip"]]
            line += [ans.get(k, "") for k in keys]
            line += [meta.get(m, "") for m in META_FIELDS]
            if has_truth:
                ta, tb = truth.get(r["pair_id"], ("", ""))
                line += [ta, tb]
            w.writerow(line)

    print(f"Exported {len(parsed)} responses -> {out_path}")
    print(f"  answer columns: {', '.join(keys) if keys else '(none)'}")
    print(f"  respondents   : {len({r['respondent'] for r, _, _ in parsed})}")
    if has_truth:
        print("  synthetic truth columns included (placeholder dataset only)")


if __name__ == "__main__":
    main()
