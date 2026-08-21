#!/usr/bin/env python3
"""Backfill the Title column in data/latest.csv from each ATS's JSON API.

The dataset stored a company and a URL but never the role's own title, so two
postings at the same company were indistinguishable - six Armadin rows were
byte-identical apart from the URL, even though their titles carry the territory
(Southwest, TOLA, New England...). build.py's per-company dedupe needs the title
to apply the "furthest west" tie-break, and the title is useful on its own.

Adds the column if missing and fills any blank Title cell it can resolve.

Usage:
    python3 scripts/backfill_titles.py            # dry run
    python3 scripts/backfill_titles.py --write    # apply
"""
import csv, json, re, sys, urllib.request
from urllib.parse import urlparse

CSV = 'data/latest.csv'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; ae-market-map/1.0)'}
_cache = {}


def get(url):
    if url not in _cache:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                _cache[url] = json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            _cache[url] = None
    return _cache[url]


def ashby(url):
    m = re.search(r'ashbyhq\.com/([^/]+)/([0-9a-f-]{36})', url, re.I)
    if not m:
        return None
    b = get(f'https://api.ashbyhq.com/posting-api/job-board/{m.group(1)}?includeCompensation=true')
    if not b:
        return None
    for j in b.get('jobs', []):
        if j.get('id') == m.group(2) or m.group(2) in json.dumps(j):
            return j.get('title')
    return None


def greenhouse(url):
    m = re.search(r'greenhouse\.io/([^/]+)/jobs/(\d+)', url)
    if not m:
        return None
    host = 'boards-api.eu.greenhouse.io' if '.eu.' in url else 'boards-api.greenhouse.io'
    j = get(f'https://{host}/v1/boards/{m.group(1)}/jobs/{m.group(2)}')
    return (j or {}).get('title')


def lever(url):
    m = re.search(r'lever\.co/([^/]+)/([0-9a-f-]{36})', url, re.I)
    if not m:
        return None
    posts = get(f'https://api.lever.co/v0/postings/{m.group(1)}?mode=json')
    for p in (posts or []):
        if p.get('id') == m.group(2):
            return p.get('text')
    return None


HANDLERS = (('ashbyhq.com', ashby), ('greenhouse.io', greenhouse), ('lever.co', lever))


def main():
    write = '--write' in sys.argv
    rows = list(csv.DictReader(open(CSV)))
    fields = list(rows[0].keys())
    if 'Title' not in fields:
        fields.insert(fields.index('Segment'), 'Title')
        for r in rows:
            r.setdefault('Title', '')

    filled = miss = 0
    for r in rows:
        if (r.get('Title') or '').strip():
            continue
        url = r['Job Posting URL']
        fn = next((f for h, f in HANDLERS if h in urlparse(url).netloc), None)
        t = fn(url) if fn else None
        if t:
            # The dash characters below are the ONES BEING STRIPPED, not prose.
            # A dash sweep over this repo must skip this line: replacing them
            # would disable the normalizer that keeps published titles clean.
            r['Title'] = re.sub(r'\s+', ' ', t).replace('—', '-').replace('–', '-').strip()
            filled += 1
        else:
            r['Title'] = r.get('Title') or ''
            miss += 1

    print(f'titles filled {filled} | unresolved {miss}')
    if write:
        with open(CSV, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f'wrote {CSV}')
    else:
        print('(dry run - pass --write to apply)')


if __name__ == '__main__':
    main()
