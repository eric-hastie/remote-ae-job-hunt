#!/usr/bin/env python3
"""Turn data/speedrun_raw.tsv into a decided list, one verdict per row.

Every row that came out of the harvester is written to data/speedrun_triage.csv
with the reason it did or did not qualify. Nothing is dropped silently: a row
this script rejects is still in the file, carrying the test it failed, because
"the market is quiet" and "my filter is broken" look identical in a count.

The gate, in order:
  1. remote           jobLocationType is TELECOMMUTE
  2. us               applicant location requirement or job country includes US
  3. ic               closing individual-contributor title (scripts/bar.BAD)
  4. ceiling          does not demand more than ~8 years (scripts/bar.yoe_ok)
  5. live             job id present in the company's OWN ATS feed

Only a row passing all five is a winner. Step 5 reuses verify_links.classify,
so this obeys the same rule the rest of the repo does: a posting counts as live
only when its ID is in the board API, never because a page fetched with a 200.

    python3 scripts/triage_speedrun.py
    python3 scripts/triage_speedrun.py --no-verify   # skip step 5 (offline)
"""
import argparse, csv, importlib.util, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

from bar import BAD, base, seg, yoe_ok  # noqa: E402

RAW = os.path.join(REPO, "data", "speedrun_raw.tsv")
TRIAGE = os.path.join(REPO, "data", "speedrun_triage.csv")
LATEST = os.path.join(REPO, "data", "latest.csv")
UNIVERSE = os.path.join(REPO, "data", "claude_universe.csv")

OUT_COLS = ["Company", "Title", "Segment", "Posted", "Verdict", "Reason",
            "MinYOE", "CompMin", "CompMax", "Countries", "Requirement",
            "ApplyURL", "ATS", "BoardURL", "KnownCompany"]


def load_verify():
    """verify_links.py has no import guard issue - it is safe to import."""
    spec = importlib.util.spec_from_file_location(
        "verify_links", os.path.join(REPO, "scripts", "verify_links.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def is_us(row):
    req = (row.get("States") or "")
    countries = (row.get("Countries") or "").split("|")
    if re.search(r"United States|USA|\bUS\b", req, re.I):
        return True
    return "US" in countries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(RAW, newline=""), delimiter="\t"))
    sys.stderr.write(f"read {len(rows)} rows from {os.path.basename(RAW)}\n")

    published_urls = set()
    published_cos = set()
    for r in csv.DictReader(open(LATEST, newline="", encoding="utf-8")):
        published_urls.add((r.get("Job Posting URL") or "").strip())
        published_cos.add(base(r["Company"]))
    universe_cos = {base(r["Company"])
                    for r in csv.DictReader(open(UNIVERSE, newline="", encoding="utf-8"))}

    vl = None if args.no_verify else load_verify()
    out, counts = [], {}

    def bump(k):
        counts[k] = counts.get(k, 0) + 1

    for r in rows:
        title, body = r["Title"], r.get("Requirements", "")
        verdict, reason = "", ""

        if r.get("WorkplaceType") != "Remote":
            verdict, reason = "reject", "not flagged remote"
        elif not is_us(r):
            verdict, reason = "reject", "not open to US applicants"
        elif BAD.search(title):
            verdict, reason = "reject", "not an IC closing title"
        elif not yoe_ok(r.get("MinYOE")):
            verdict, reason = "reject", f"demands {r.get('MinYOE')}+ years"

        board_url = ""
        if not verdict:
            if args.no_verify:
                verdict, reason = "unchecked", "verification skipped"
            elif not r.get("ApplyURL", "").strip():
                verdict, reason = "hold", "no apply URL"
            else:
                status, org, kind, jid = vl.classify(r["ApplyURL"])
                board_url = f"{kind}:{org}"
                if status == "LIVE":
                    verdict, reason = "win", "id present in ATS feed"
                elif status in ("DEAD_ID", "HTTP_DEAD"):
                    verdict, reason = "reject", f"posting gone ({status})"
                else:
                    verdict, reason = "hold", status

        known = ("published" if base(r["Company"]) in published_cos
                 else "in universe" if base(r["Company"]) in universe_cos
                 else "net-new")
        if verdict == "win" and r["ApplyURL"] in published_urls:
            verdict, reason = "dup", "already on latest.csv"

        bump(verdict)
        out.append({
            "Company": r["Company"], "Title": title,
            "Segment": seg(title, body), "Posted": r.get("Posted", ""),
            "Verdict": verdict, "Reason": reason, "MinYOE": r.get("MinYOE", ""),
            "CompMin": r.get("CompMin", ""), "CompMax": r.get("CompMax", ""),
            "Countries": r.get("Countries", ""), "Requirement": r.get("States", ""),
            "ApplyURL": r["ApplyURL"], "ATS": r.get("ATS", ""),
            "BoardURL": board_url, "KnownCompany": known,
        })

    with open(TRIAGE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUT_COLS)
        w.writeheader()
        w.writerows(sorted(out, key=lambda x: (x["Verdict"], x["Company"], x["Title"])))

    # Count at both ends. In must equal out.
    assert len(out) == len(rows), f"lost rows: {len(rows)} in, {len(out)} out"
    sys.stderr.write(f"verdicts: {counts}\n")
    sys.stderr.write(f"wrote {len(out)} rows -> {TRIAGE}\n")


if __name__ == "__main__":
    main()
