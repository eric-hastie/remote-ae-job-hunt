#!/usr/bin/env python3
"""Backfill the OTE column in data/latest.csv from each ATS's own JSON API.

Why this exists: rows were losing their comp range even when the posting
published one. The scan agents read posting PAGES with WebFetch, but Ashby,
HireBridge and friends render the description client-side, so the fetch returns
only the page shell and the agent records "no comp stated". The board APIs
carry the number as a structured field, so read it from there instead.

Covers Ashby (compensationTierSummary), Greenhouse (pay range in job content)
and Lever (salaryRange). Non-API hosts are reported as NEEDS_BROWSER - those
have to be read in a real browser.

IMPORTANT - base vs OTE: this column is named OTE but ATS feeds publish BASE
far more often. For an AE, base is typically ~half of OTE, so a recorded
"$60,000-$70,000" may be base against a ~$130K OTE. Values written by this
script are suffixed " base" when the source says base, so the two are never
silently conflated.

Usage:
    python3 scripts/backfill_comp.py            # dry run, prints what it would fill
    python3 scripts/backfill_comp.py --write    # apply to data/latest.csv
"""
import csv, json, re, sys, urllib.request, urllib.error
from urllib.parse import urlparse

CSV = 'data/latest.csv'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; ae-market-map/1.0)'}
_cache = {}


def get(url):
    if url in _cache:
        return _cache[url]
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            _cache[url] = json.loads(r.read().decode('utf-8', 'replace'))
    except Exception:
        _cache[url] = None
    return _cache[url]


def money(s):
    """Normalise a comp string to '$X-$Y', or '' if it has no real figure."""
    if not s:
        return ''
    s = re.sub(r'<[^>]+>', ' ', str(s))
    nums = re.findall(r'\$\s?([\d,]+(?:\.\d+)?)\s*([kK])?', s)
    vals = []
    for raw, k in nums:
        try:
            v = float(raw.replace(',', ''))
        except ValueError:
            continue
        if k:
            v *= 1000
        if v >= 30000:            # drop equity %, bonuses, stray small numbers
            vals.append(int(v))
    if not vals:
        return ''
    lo, hi = min(vals), max(vals)
    return f'${lo:,}' if lo == hi else f'${lo:,}-${hi:,}'


def is_base(text):
    t = str(text).lower()
    return 'base' in t and 'ote' not in t and 'on target' not in t


def ashby(url):
    m = re.search(r'ashbyhq\.com/([^/]+)/([0-9a-f-]{36})', url, re.I)
    if not m:
        return None
    board = get(f'https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}?includeCompensation=true')
    if not board:
        return None
    for j in board.get('jobs', []):
        if j.get('id') == m.group(2) or m.group(2) in json.dumps(j):
            c = j.get('compensation') or {}
            s = c.get('compensationTierSummary') or c.get('summaryComponents') or ''
            if isinstance(s, list):
                s = ' '.join(str(x) for x in s)
            v = money(s)
            return (v + ' base') if v and is_base(s) else v
    return None


def greenhouse(url):
    m = re.search(r'greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    if not m:
        return None
    host = 'boards-api.eu.greenhouse.io' if '.eu.' in url else 'boards-api.greenhouse.io'
    j = get(f'https://{host}/v1/boards/{m.group(1)}/jobs/{m.group(2)}')
    if not j:
        return None
    for r in (j.get('pay_input_ranges') or []):
        v = money(f"${r.get('min_cents',0)//100}-${r.get('max_cents',0)//100}")
        if v:
            return (v + ' base') if is_base(r.get('title', '')) else v
    content = j.get('content', '')
    for line in re.split(r'<[^>]+>|\n', content):
        if re.search(r'\$\s?[\d,]{4,}', line) and re.search(r'salary|compensation|base|range|ote|pay', line, re.I):
            v = money(line)
            if v:
                return (v + ' base') if is_base(line) else v
    return None


def lever(url):
    m = re.search(r'lever\.co/([^/]+)/([0-9a-f-]{36})', url, re.I)
    if not m:
        return None
    posts = get(f'https://api.lever.co/v0/postings/{m.group(1)}?mode=json')
    if not posts:
        return None
    for p in posts:
        if p.get('id') == m.group(2):
            sr = p.get('salaryRange') or {}
            if sr.get('min'):
                return money(f"${int(sr['min'])}-${int(sr.get('max') or sr['min'])}")
            return ''
    return None


HANDLERS = (('ashbyhq.com', ashby), ('greenhouse.io', greenhouse), ('lever.co', lever))


def main():
    write = '--write' in sys.argv
    rows = list(csv.DictReader(open(CSV)))
    fields = rows[0].keys()
    filled = skipped = needs_browser = 0

    for r in rows:
        if r['OTE'].strip():
            continue
        url = r['Job Posting URL']
        host = urlparse(url).netloc
        fn = next((f for h, f in HANDLERS if h in host), None)
        if not fn:
            needs_browser += 1
            print(f'  NEEDS_BROWSER  {r["Company"]:<28} {host}')
            continue
        val = fn(url)
        if val:
            print(f'  FILL           {r["Company"]:<28} {val}')
            r['OTE'] = val
            filled += 1
        else:
            skipped += 1

    print(f'\nfilled {filled} | no comp published {skipped} | needs browser {needs_browser}')
    if write and filled:
        with open(CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f'wrote {CSV}')
    elif not write:
        print('(dry run - pass --write to apply)')


if __name__ == '__main__':
    main()
