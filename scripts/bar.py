#!/usr/bin/env python3
"""The qualification bar, in one place.

Extracted from build_unverified.py on 2026-08-21 so the speedrun triage and the
unverified page cannot drift apart on what counts as Mid-Market or what the
experience ceiling is. Both import from here; nothing else defines these.

The bar itself (from the project spec, do not re-derive it):
  - Individual-contributor closing role. Associate AE is IN SCOPE.
  - Experience 0 to ~8 years. THERE IS NO FLOOR, only the ceiling.
  - No salary floor or ceiling. Boards publish BASE, not OTE.
"""
import re

# "client success" joined this list on 2026-08-21. Bayesian Health posted a
# "Client Success Account Executive, Clinical" whose body is implementation,
# adoption and expansion on existing accounts. It carries the words "Account
# Executive" and is not a new-logo closing role, which is what the bar asks for.
# "customer success" was already here; the two phrases are the same job.
BAD = re.compile(r"\b(director|vp|vice president|head of|chief|manager|sdr|bdr|"
                 r"sales development|intern|recruiter|engineer|customer success|"
                 r"client success|account manager|partnerships?)\b", re.I)
AE = re.compile(r"account executive", re.I)
MM_T = re.compile(r"mid-?\s?market|\bcommercial\b", re.I)
ENT_T = re.compile(r"\benterprise\b|\bstrategic\b|major account|named account", re.I)
SMB_T = re.compile(r"\bsmb\b|small business", re.I)
MM_B = re.compile(r"mid-?\s?market|commercial (segment|account|team|book)", re.I)
ENT_B = re.compile(r"enterprise (account|client|customer|segment|deal|logo|prospect)"
                   r"|fortune\s?(500|1000)|large enterprise|strategic account", re.I)


def base(n):
    return re.sub(r"[^a-z0-9]", "", re.split(r"\(", n or "")[0].lower())


def seg(title, body=""):
    if MM_T.search(title): return "MM"
    if SMB_T.search(title): return "SMB"
    if ENT_T.search(title): return "Ent"
    mm, ent = bool(MM_B.search(body)), bool(ENT_B.search(body))
    if mm and not ent: return "MM"
    if ent and not mm: return "Ent"
    if mm and ent: return "MM/Ent"
    return "Unspec"


def yoe_ok(y):
    """True unless the posting demands MORE than ~8 years.

    A blank or unparseable figure passes on purpose. Unstated experience is in
    scope, and there is no floor to test against.
    """
    try:
        return float(y) <= 8
    except (TypeError, ValueError):
        return True
