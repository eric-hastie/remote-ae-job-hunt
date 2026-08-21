#!/usr/bin/env python3
"""Merge a triaged speedrun pull into the published list, the dedup memory and the ring.

Three writes, each with its own rule:

  data/latest.csv         append winning roles that are not already there,
                          keyed by posting URL.
  data/claude_universe.csv record ONLY companies whose postings this pull
                          actually judged. UPDATE a company's existing row,
                          never append a second one.
  data/scan_queue.csv     seed the board's company sitemap as ring fuel,
                          marked Source=a16z-speedrun, left UNCHECKED.

Why the universe and the ring get different sets, which is the one non-obvious
thing here: the board is NOT a complete mirror of each company's own careers
page. It describes 1,509 employers, and most of them show no Account Executive
posting - but that set includes Amazon, Walmart, CVS and TikTok, which plainly
do hire Account Executives, and 1Password, which the board itself labels as
hiring sales while listing none of those roles. So "the board lists no AE role"
is NOT evidence that a company has no AE role, and recording those companies as
checked would poison the dedup memory and make future runs skip them forever.
Companies enter the universe only on evidence from a posting we actually read;
the rest go into the ring so the normal ATS pipeline visits them properly.

    python3 scripts/merge_speedrun.py --dry-run
    python3 scripts/merge_speedrun.py
    python3 scripts/merge_speedrun.py --no-seed     # skip the ring seed
"""
import argparse, csv, datetime, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from bar import base  # noqa: E402

TRIAGE = os.path.join(REPO, "data", "speedrun_triage.csv")
RAW = os.path.join(REPO, "data", "speedrun_raw.tsv")
LATEST = os.path.join(REPO, "data", "latest.csv")
UNIVERSE = os.path.join(REPO, "data", "claude_universe.csv")
QUEUE = os.path.join(REPO, "data", "scan_queue.csv")
COMPANIES = os.path.join(REPO, "data", "speedrun_companies.csv")

SOURCE = "a16z-speedrun"
TODAY = datetime.date.today().isoformat()

# Only claim OTE when the posting says OTE. Boards publish BASE far more often,
# and for an AE base is roughly half of OTE, so a mislabelled figure is worse
# than no figure. Everything else is recorded with the label withheld.
OTE_LABEL = re.compile(
    r"\b(OTE|on[- ]target earnings|total target (?:cash|earnings|compensation))\b", re.I)


def money(lo, hi):
    try:
        lo, hi = int(float(lo)), int(float(hi))
    except (TypeError, ValueError):
        return ""
    return f"${lo:,}" if lo == hi else f"${lo:,}-${hi:,}"


def posting_url(apply_url):
    """The human posting page, copied from the apply link - never retyped.

    Ashby apply links end in /application; latest.csv stores the posting page.
    """
    return re.sub(r"/application/?$", "", apply_url)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-seed", action="store_true")
    args = ap.parse_args()

    triage = list(csv.DictReader(open(TRIAGE, newline="")))
    bodies = {(r["Company"], r["Title"]): r.get("Requirements", "")
              for r in csv.DictReader(open(RAW, newline=""), delimiter="\t")}

    # ---- latest.csv -------------------------------------------------------
    with open(LATEST, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        latest_cols = rd.fieldnames
        latest = list(rd)
    have = {(r.get("Job Posting URL") or "").strip() for r in latest}
    # Company+title is the second dedup key, and it is the one that actually
    # holds. A URL check alone cannot see that latest.csv already carries this
    # role under a SIBLING posting: boards list one job once per city, so the
    # same Mixpanel role exists nine times with nine ids. Matching on URL only,
    # every rerun published another copy of a role already on the list.
    have_role = {(r["Company"], r["Title"]) for r in latest}

    # One published row per company+title. Boards routinely post the same job
    # once per city with a different ATS id - Mixpanel had 19 postings for 3
    # titles in the first pull. Those are one role each to a reader, so keep the
    # most recently posted and count the rest as collapsed, not as findings.
    best = {}
    for t in triage:
        if t["Verdict"] != "win":
            continue
        k = (t["Company"], t["Title"])
        # Newest wins, and the APPLY URL breaks a tie. Without that tie-break the
        # winner among several identical same-day postings depended on the order
        # the harvester's threads happened to finish, so a rerun could publish a
        # different one of Mixpanel's nine copies and look like a new finding.
        rank = (t["Posted"], t["ApplyURL"])
        if k not in best or rank > (best[k]["Posted"], best[k]["ApplyURL"]):
            best[k] = t
    collapsed = sum(1 for t in triage if t["Verdict"] == "win") - len(best)

    new_rows, skipped_dup = [], 0
    for t in best.values():
        url = posting_url(t["ApplyURL"])
        if url in have or (t["Company"], t["Title"]) in have_role:
            skipped_dup += 1
            continue
        have.add(url)
        have_role.add((t["Company"], t["Title"]))
        body = bodies.get((t["Company"], t["Title"]), "")
        rng = money(t["CompMin"], t["CompMax"])
        if rng:
            ote = f"{rng} OTE" if OTE_LABEL.search(body) else f"{rng} (base or OTE not stated)"
        else:
            ote = ""
        new_rows.append({
            "Company": t["Company"],
            "Funding ($M)": "",
            "OTE": ote,
            "Title": t["Title"],
            "Segment": t["Segment"],
            "HQ": "",
            "Remote": "Y",
            "RepVue": "",            # scripts/enrich_repvue.py fills this
            "Industry": "",          # the board carries none; a labelled blank
            "Job Posting URL": url,
            "Date Added": TODAY,
            "Posted": t["Posted"],
            "Location": "Remote",
            "Status": "Verified",
        })

    # ---- claude_universe.csv ---------------------------------------------
    with open(UNIVERSE, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        uni_cols = rd.fieldnames
        uni = list(rd)
    uni_by_key = {}
    for r in uni:
        uni_by_key.setdefault(base(r["Company"]), r)

    # One verdict per company, best-first: a win beats a reject.
    judged = {}
    for t in triage:
        k = base(t["Company"])
        cur = judged.get(k)
        if cur is None or (t["Verdict"] == "win" and cur["Verdict"] != "win"):
            judged[k] = t

    uni_updated, uni_added = 0, 0
    for k, t in judged.items():
        open_flag = "Y" if t["Verdict"] in ("win", "dup") else "N"
        note = (f"{t['Title']} ({t['Segment']})" if open_flag == "Y"
                else f"speedrun board: {t['Reason']}")
        row = uni_by_key.get(k)
        if row is None:
            row = {c: "" for c in uni_cols}
            row["Company"] = t["Company"]
            row["Source"] = SOURCE
            uni.append(row)
            uni_by_key[k] = row
            uni_added += 1
        else:
            uni_updated += 1
        row["Last Checked"] = TODAY
        row["Currently Open"] = open_flag
        row["Notes"] = note

    # ---- scan_queue.csv (the ring) ---------------------------------------
    seeded = 0
    queue_rows, queue_cols = [], ["Company", "Slug", "Score", "Source"]
    if not args.no_seed:
        with open(QUEUE, newline="") as f:
            rd = csv.DictReader(f)
            existing = list(rd)
        existing_keys = {base(r["Company"]) for r in existing}
        # Already-evaluated companies do not need a ring slot; the ring is for
        # companies the pipeline has never opened an ATS board for.
        evaluated = set(uni_by_key)
        seeds = []
        for r in csv.DictReader(open(COMPANIES, newline="")):
            k = base(r["Company"])
            if k in existing_keys or k in evaluated:
                continue
            existing_keys.add(k)
            seeds.append({"Company": r["Company"], "Slug": r["Slug"],
                          "Score": "", "Source": SOURCE,
                          "_rp": r.get("RemotePosture", ""),
                          "_sales": 1 if "sales" in (r.get("Functions") or "") else 0,
                          "_open": int(r.get("OpenRoles") or 0)})
        # Order, not filter. NOTHING is excluded. The board states, per company,
        # a remote posture (remote-first / hybrid-friendly / onsite-leaning) and
        # the functions it hires for. Those are the board's own labels, so a
        # remote-first company that hires sales goes first and an onsite-leaning
        # company that has never listed a sales role goes last. A company at the
        # back is still in the ring and will still be checked against its own
        # ATS - this only decides who gets looked at on day one versus day ten.
        RANK = {"remote-first": 0, "hybrid-friendly": 1, "onsite-leaning": 2, "": 3}
        seeds.sort(key=lambda r: (-r["_sales"], RANK.get(r["_rp"], 3),
                                  -r["_open"], r["Company"].lower()))
        for r in seeds:
            del r["_rp"], r["_sales"], r["_open"]
        seeded = len(seeds)
        # Seeds go to the FRONT. Every RepVue row below them is a re-check by
        # design (the ring has zero net-new RepVue companies left at >= 76), and
        # a never-before-seen company outyields a re-check. The RepVue block
        # keeps its exact score order; only the block order changes.
        for r in existing:
            r.setdefault("Source", "repvue")
            if not r.get("Source"):
                r["Source"] = "repvue"
        queue_rows = seeds + existing

    # ---- report + write ---------------------------------------------------
    print(f"latest.csv       + {len(new_rows)} roles  ({skipped_dup} already present, "
          f"{collapsed} same-title postings collapsed)")
    print(f"claude_universe  ~ {uni_updated} updated, + {uni_added} added  "
          f"({len(judged)} companies judged from a posting we read)")
    print(f"scan_queue       + {seeded} seeded at the front of the ring"
          if not args.no_seed else "scan_queue       untouched (--no-seed)")
    if args.dry_run:
        print("(--dry-run: nothing written)")
        return

    with open(LATEST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=latest_cols)
        w.writeheader()
        w.writerows(latest + new_rows)
    with open(UNIVERSE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=uni_cols)
        w.writeheader()
        w.writerows(uni)
    if not args.no_seed:
        with open(QUEUE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=queue_cols)
            w.writeheader()
            w.writerows(queue_rows)
    print("written.")


if __name__ == "__main__":
    main()
