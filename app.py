#!/usr/bin/env python3
"""
app.py - LOCAL backend + dev server for the image-pair comparison study.

Standard library only (http.server + sqlite3). This lets you run and test the
ENTIRE flow on your machine - name login, 50-pair batches, max-2 labelers,
partial saving - with no Supabase account. For public diffusion you switch the
frontend to the Supabase backend (see supabase/schema.sql and README); the API
contract below is mirrored exactly by the Supabase RPC functions.

Run:
    python app.py                 # http://localhost:8000  (auto-opens browser)
    python app.py --reload-pairs  # re-import pairs_metadata.csv into the DB
    python app.py --reset         # wipe responses + re-import pairs (fresh study)

API (also implemented by Supabase RPC for production):
    GET  /api/config              -> public study config (from static/config.js? no: from server)
    POST /api/claim   {name}      -> { pairs: [...up to batch_size...], remaining }
    POST /api/submit  {name, pair_id, answers}
                                  -> { ok } | { ok:false, reason }
    GET  /api/stats               -> coverage counts
"""
import argparse
import csv
import datetime
import json
import mimetypes
import os
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(ROOT, "images")
STATIC_DIR = os.path.join(ROOT, "static")
DATA_DIR = os.path.join(ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "study.db")
META_CSV = os.path.join(ROOT, "pairs_metadata.csv")

BATCH_SIZE = 50
MAX_LABELERS = 2
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_lock = threading.Lock()


# ----------------------------------------------------------------------------
# Database
# ----------------------------------------------------------------------------
def connect():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = connect()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS pairs (
            pair_id   TEXT PRIMARY KEY,
            province  TEXT,
            year      INTEGER,
            image_a   TEXT NOT NULL,
            image_b   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS responses (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_id    TEXT NOT NULL REFERENCES pairs(pair_id),
            respondent TEXT NOT NULL,
            answers    TEXT NOT NULL,           -- JSON {q1:..., q2:...}
            created_at TEXT NOT NULL,
            UNIQUE(pair_id, respondent)         -- one answer per person per pair
        );
        CREATE INDEX IF NOT EXISTS idx_resp_pair ON responses(pair_id);
        CREATE INDEX IF NOT EXISTS idx_resp_name ON responses(respondent);
    """)
    con.commit()
    con.close()


def reload_pairs():
    """Import pairs_metadata.csv into the pairs table (idempotent upsert)."""
    if not os.path.exists(META_CSV):
        print(f"WARNING: {META_CSV} not found. Run: python generate_pairs.py")
        return 0
    con = connect()
    n = 0
    with open(META_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # local mode serves images from /images/<relpath>
            con.execute(
                """INSERT INTO pairs(pair_id, province, year, image_a, image_b)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(pair_id) DO UPDATE SET
                     province=excluded.province, year=excluded.year,
                     image_a=excluded.image_a, image_b=excluded.image_b""",
                (row["pair_id"], row.get("province"), row.get("year"),
                 "/images/" + row["image_a"], "/images/" + row["image_b"]))
            n += 1
    con.commit()
    con.close()
    return n


# ----------------------------------------------------------------------------
# Core API logic (mirrors Supabase RPC)
# ----------------------------------------------------------------------------
def claim_batch(name, size=BATCH_SIZE):
    """Return up to `size` pairs for this respondent:
       - exclude pairs already at MAX_LABELERS
       - exclude pairs this respondent already answered
       - prefer pairs that already have 1 label (to drive them to 2)
    """
    name = name.strip()
    with _lock:
        con = connect()
        rows = con.execute(
            """
            SELECT p.pair_id, p.province, p.year, p.image_a, p.image_b,
                   (SELECT COUNT(*) FROM responses r WHERE r.pair_id = p.pair_id) AS lc
            FROM pairs p
            WHERE (SELECT COUNT(*) FROM responses r WHERE r.pair_id = p.pair_id) < ?
              AND p.pair_id NOT IN (
                    SELECT pair_id FROM responses WHERE respondent = ?)
            ORDER BY lc DESC, p.pair_id
            LIMIT ?
            """, (MAX_LABELERS, name, size)).fetchall()
        remaining = con.execute(
            """SELECT COUNT(*) FROM pairs p
               WHERE (SELECT COUNT(*) FROM responses r WHERE r.pair_id=p.pair_id) < ?
                 AND p.pair_id NOT IN (SELECT pair_id FROM responses WHERE respondent=?)
            """, (MAX_LABELERS, name)).fetchone()[0]
        con.close()
    pairs = [{"pair_id": r["pair_id"], "province": r["province"], "year": r["year"],
              "image_a": r["image_a"], "image_b": r["image_b"]} for r in rows]
    return {"pairs": pairs, "remaining": remaining}


def submit_response(name, pair_id, answers):
    """Atomically record one answer, enforcing the max-2 rule at write time."""
    name = name.strip()
    with _lock:
        con = connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            exists = con.execute("SELECT 1 FROM pairs WHERE pair_id=?", (pair_id,)).fetchone()
            if not exists:
                con.rollback(); con.close()
                return {"ok": False, "reason": "unknown_pair"}
            count = con.execute(
                "SELECT COUNT(*) FROM responses WHERE pair_id=?", (pair_id,)).fetchone()[0]
            already = con.execute(
                "SELECT 1 FROM responses WHERE pair_id=? AND respondent=?",
                (pair_id, name)).fetchone()
            if already:
                # idempotent update of this person's own answer
                con.execute(
                    "UPDATE responses SET answers=?, created_at=? WHERE pair_id=? AND respondent=?",
                    (json.dumps(answers), datetime.datetime.now().isoformat(timespec="seconds"),
                     pair_id, name))
                con.commit(); con.close()
                return {"ok": True, "updated": True}
            if count >= MAX_LABELERS:
                con.rollback(); con.close()
                return {"ok": False, "reason": "pair_full"}
            con.execute(
                "INSERT INTO responses(pair_id, respondent, answers, created_at) VALUES(?,?,?,?)",
                (pair_id, name, json.dumps(answers),
                 datetime.datetime.now().isoformat(timespec="seconds")))
            con.commit(); con.close()
            return {"ok": True}
        except sqlite3.Error as e:
            con.rollback(); con.close()
            return {"ok": False, "reason": f"db_error: {e}"}


def stats():
    con = connect()
    total = con.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]
    by_count = con.execute(
        """SELECT lc, COUNT(*) AS n FROM (
               SELECT (SELECT COUNT(*) FROM responses r WHERE r.pair_id=p.pair_id) AS lc
               FROM pairs p) GROUP BY lc ORDER BY lc""").fetchall()
    responses = con.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
    labelers = con.execute("SELECT COUNT(DISTINCT respondent) FROM responses").fetchone()[0]
    con.close()
    dist = {str(r["lc"]): r["n"] for r in by_count}
    complete = sum(n for lc, n in dist.items() if int(lc) >= MAX_LABELERS)
    return {"total_pairs": total, "responses": responses, "labelers": labelers,
            "label_count_distribution": dist, "complete_pairs": complete,
            "max_labelers": MAX_LABELERS, "batch_size": BATCH_SIZE}


# ----------------------------------------------------------------------------
# HTTP handler
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "PairStudy/1.0"

    def log_message(self, *a):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path):
        if not os.path.isfile(path):
            self._json({"error": "not found"}, 404); return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _safe(self, base, name):
        name = unquote(name).lstrip("/\\")
        full = os.path.normpath(os.path.join(base, name))
        if os.path.commonpath([os.path.abspath(full), base]) != base:
            return None
        return full

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._file(os.path.join(ROOT, "index.html")); return
        if path == "/api/stats":
            self._json(stats()); return
        if path.startswith("/images/"):
            full = self._safe(IMAGES_DIR, path[len("/images/"):])
            self._file(full) if full else self._json({"error": "bad path"}, 400); return
        if path.startswith("/static/"):
            full = self._safe(STATIC_DIR, path[len("/static/"):])
            self._file(full) if full else self._json({"error": "bad path"}, 400); return
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._body()
        if data is None:
            self._json({"error": "invalid json"}, 400); return

        if path == "/api/claim":
            name = str(data.get("name", "")).strip()
            if not name:
                self._json({"error": "name required"}, 400); return
            self._json(claim_batch(name, int(data.get("size", BATCH_SIZE)))); return

        if path == "/api/submit":
            name = str(data.get("name", "")).strip()
            pair_id = str(data.get("pair_id", "")).strip()
            answers = data.get("answers")
            if not name or not pair_id or not isinstance(answers, dict):
                self._json({"ok": False, "reason": "bad_request"}, 400); return
            self._json(submit_response(name, pair_id, answers)); return

        self._json({"error": "not found"}, 404)


def find_free_port(preferred):
    import socket
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def main():
    ap = argparse.ArgumentParser(description="Local backend for the pair-comparison study.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--reload-pairs", action="store_true", help="re-import pairs_metadata.csv")
    ap.add_argument("--reset", action="store_true", help="wipe responses and re-import pairs")
    args = ap.parse_args()

    init_db()
    if args.reset:
        con = connect(); con.execute("DELETE FROM responses"); con.execute("DELETE FROM pairs")
        con.commit(); con.close()
        print("Reset: responses + pairs cleared.")
    # import pairs if table is empty, or if explicitly asked
    con = connect(); npairs = con.execute("SELECT COUNT(*) FROM pairs").fetchone()[0]; con.close()
    if npairs == 0 or args.reload_pairs or args.reset:
        n = reload_pairs()
        print(f"Imported {n} pairs into the database.")

    port = find_free_port(args.port)
    url = f"http://{args.host}:{port}/"
    httpd = ThreadingHTTPServer((args.host, port), Handler)
    s = stats()
    print("=" * 62)
    print("  Image-pair comparison study  (LOCAL backend / SQLite)")
    print(f"  Pairs in DB   : {s['total_pairs']}   responses: {s['responses']}")
    print(f"  Database      : {DB_PATH}")
    print(f"  URL           : {url}")
    print("  Ctrl+C to stop.")
    print("=" * 62)
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Responses are in data/study.db (export with r/analyze_responses.R).")
        httpd.shutdown()


if __name__ == "__main__":
    main()
