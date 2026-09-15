#!/usr/bin/env python3
"""Drop every row matching a URL (when multiple rows share the same posting URL).

  python3 scripts/drop_multi.py --url <url> --expect <n>

Refuses unless exactly <n> rows match. Same write-and-verify logic as edit_row.py.
"""
import argparse, csv, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(REPO, "data", "latest.csv")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--expect", type=int, required=True, help="exact number of rows expected to drop")
    ap.add_argument("--file", default=LATEST)
    args = ap.parse_args()

    with open(args.file, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames
        rows = list(rd)
    if not rows:
        sys.exit("REFUSED: file parsed to 0 rows.")

    hits = [r for r in rows if (r.get("Job Posting URL") or "").strip() == args.url.strip()]
    if len(hits) != args.expect:
        sys.exit(f"REFUSED: expected {args.expect} matches, found {len(hits)}. Nothing written.")

    out = [r for r in rows if (r.get("Job Posting URL") or "").strip() != args.url.strip()]
    expected = len(rows) - args.expect

    tmp = args.file + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    with open(tmp, newline="", encoding="utf-8") as f:
        back = len(list(csv.DictReader(f)))
    if back != expected:
        os.remove(tmp)
        sys.exit(f"REFUSED: wrote {back} rows, expected {expected}. Original untouched.")
    os.replace(tmp, args.file)

    companies = list({r.get("Company", "") for r in hits})
    print(f"{len(rows)} rows in, {back} rows out. Dropped {args.expect} rows for {companies} URL={args.url}")

if __name__ == "__main__":
    sys.exit(main())
