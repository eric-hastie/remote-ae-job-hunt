#!/usr/bin/env python3
"""Edit one row of data/latest.csv without ever routing the file through context.

Job 1 has to do two things to the list: repair a posting URL, and drop a row
whose posting is dead. Until now ROUTINE.md named no mechanism for either, while
every other data step named a script. So each run improvised, and the natural
improvisation for an agent is to read the file and write it back, which is how
2026-08-25 and 2026-08-26 lost 358 and 366 rows: the copy came back short and a
truncated CSV is still a valid CSV.

This reads from disk, edits the matched row, writes every other row back
unchanged, and refuses if the row count moved by anything other than the amount
the operation asks for.

  python3 scripts/edit_row.py set-url --url <old> --to <new>
  python3 scripts/edit_row.py set     --url <old> --field Status --to "Needs check"
  python3 scripts/edit_row.py drop    --url <old>

--url matches on the exact Job Posting URL, which is the one column that is
unique per row and is copy-pasted rather than retyped. Matching must hit exactly
one row or nothing is written.
"""
import argparse
import csv
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = os.path.join(REPO, "data", "latest.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("op", choices=["set-url", "set", "drop"])
    ap.add_argument("--url", required=True, help="exact current Job Posting URL")
    ap.add_argument("--to", help="new value")
    ap.add_argument("--field", help="column to set, for the bare 'set' op")
    ap.add_argument("--file", default=LATEST)
    args = ap.parse_args()

    if args.op in ("set-url", "set") and args.to is None:
        sys.exit("REFUSED: --to is required for this operation.")
    if args.op == "set" and not args.field:
        sys.exit("REFUSED: --set needs --field.")

    with open(args.file, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames
        rows = list(rd)
    if not rows:
        sys.exit("REFUSED: the file parsed to 0 rows. An empty scope is not a pass.")
    if args.op == "set" and args.field not in cols:
        sys.exit(f"REFUSED: no column named {args.field!r}. Columns: {cols}")

    hits = [r for r in rows if (r.get("Job Posting URL") or "").strip() == args.url.strip()]
    if len(hits) != 1:
        sys.exit(f"REFUSED: --url matched {len(hits)} rows, expected exactly 1. "
                 f"Nothing was written.")
    row = hits[0]

    if args.op == "drop":
        out = [r for r in rows if r is not row]
        expected = len(rows) - 1
        what = f"dropped {row.get('Company','')} | {row.get('Title','')}"
    else:
        field = "Job Posting URL" if args.op == "set-url" else args.field
        old = row.get(field, "")
        row[field] = args.to
        out = rows
        expected = len(rows)
        what = (f"{row.get('Company','')} | {row.get('Title','')}: "
                f"{field} {old!r} -> {args.to!r}")

    if len(out) != expected:
        sys.exit("REFUSED: row count does not match the operation. Nothing written.")

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

    print(f"{len(rows)} rows in, {back} rows out. {what}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
