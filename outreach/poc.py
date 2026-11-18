"""Step 4 - find the point of contact.

Source (case: "Hunter.io API, 25 free searches/month, or Apollo looked up manually"):
  1. Hunter.io Domain Search (one query per domain; repeats in the same billing period are free)
  2. fallback: a manually looked-up Apollo contact (MANUAL_POCS_JSON env var or data/manual_pocs.json)

Choosing the person is NOT left to a model. A fixed ranking rule in code picks the
buyer persona for a compliance-automation product, so "why this person" always has
the same, checkable answer. This guards against the failure the brief names:
"finding the nearest person with 'manager' in their title".
"""
import json
import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import httpx

from .models import Contact, PocSelection

HUNTER_URL = "https://api.hunter.io/v2/domain-search"

# (tier score, label, title pattern). First match wins; higher tier = better buyer for Sprinto.
PERSONAS: List[Tuple[int, str, re.Pattern]] = [
    (100, "owns security/compliance", re.compile(
        r"\b(ciso|chief (information )?security|security|compliance|grc|governance|risk|trust|privacy|audit)\b", re.I)),
    (85, "owns engineering/infra (usually owns SOC 2 at Series A-C)", re.compile(
        r"\b(cto|chief technology|vp,? (of )?engineering|head of engineering|engineering director|"
        r"director of engineering|vp,? (of )?infrastructure|head of (infrastructure|platform|devops|it)|it director)\b", re.I)),
    (70, "founder/exec (owns deals blocked by security reviews)", re.compile(
        r"\b(ceo|chief executive|co-?founder|founder|coo|chief operating|president)\b", re.I)),
    (40, "senior engineering/ops leader", re.compile(
        r"\b(vp|vice president|head|director)\b.*\b(engineering|technology|operations|product|it)\b", re.I)),
]
EXCLUDE = re.compile(r"\b(intern|assistant|recruit|talent|sales|marketing|sdr|bdr|account executive|"
                     r"customer success|support|designer|hr|people)\b", re.I)

RANKING_RULE = (
    "Personal emails only, first name required. Titles matching sales/marketing/HR/support/intern are excluded. "
    "Persona tier decides (security/compliance owner > CTO/VP Eng/infra > founder/CEO/COO > other senior "
    "eng/ops leader); within a tier: +10 executive, +5 senior (Hunter seniority), + Hunter confidence/20, "
    "+5 if the address is verified. Highest score wins. No match -> no contact."
)


def score_contact(c: Contact, seniority: Optional[str] = None, verified: bool = False) -> Tuple[float, str]:
    title = c.position or ""
    if not c.first_name or (title and EXCLUDE.search(title)):
        return 0.0, "excluded"
    for tier, label, pat in PERSONAS:
        if title and pat.search(title):
            bonus = {"executive": 10, "senior": 5}.get(seniority or "", 0)
            # tier x10 so persona always dominates; bonuses (max 25) only break ties within a tier
            return tier * 10 + bonus + (c.confidence or 0) / 20 + (5 if verified else 0), label
    return 0.0, "no buyer persona in title"


def _manual_pocs(path: Path) -> Dict[str, dict]:
    raw = os.getenv("MANUAL_POCS_JSON", "")
    if raw:
        return json.loads(raw)
    if path.exists():
        return json.loads(path.read_text())
    return {}


class PocFinder:
    def __init__(self, hunter_key: str, manual_path: Path, http: Optional[httpx.Client] = None):
        self.hunter_key = hunter_key
        self.manual_path = manual_path
        self.http = http or httpx.Client(timeout=20.0)

    def _hunter(self, domain: str) -> Tuple[List[Tuple[Contact, Optional[str], bool]], str]:
        if not self.hunter_key:
            return [], "HUNTER_API_KEY not set"
        r = self.http.get(HUNTER_URL, params={"domain": domain, "type": "personal", "limit": 10},
                          headers={"X-API-KEY": self.hunter_key})
        if r.status_code == 401:
            return [], "Hunter rejected the API key"
        if r.status_code == 429:
            return [], "Hunter monthly search quota used up"
        if r.status_code != 200:
            return [], f"Hunter HTTP {r.status_code}"
        out = []
        for e in r.json().get("data", {}).get("emails", []):
            if not e.get("first_name"):
                continue
            c = Contact(first_name=e["first_name"], last_name=e.get("last_name"), position=e.get("position"),
                        email=e.get("value"), confidence=e.get("confidence"), linkedin=e.get("linkedin"),
                        source="hunter")
            verified = (e.get("verification") or {}).get("status") == "valid"
            out.append((c, e.get("seniority"), verified))
        return out, f"Hunter returned {len(out)} named contact(s)"

    def find(self, domain: str) -> PocSelection:
        found, note = self._hunter(domain)
        scored = sorted(((score_contact(c, sen, ver), c) for c, sen, ver in found),
                        key=lambda x: x[0][0], reverse=True)
        candidates = [c for _, c in scored]
        best = next(((s, c) for s, c in scored if s[0] > 0), None)
        if best:
            (score, label), c = best
            return PocSelection(domain=domain, chosen=c, candidates=candidates, ranking_rule=RANKING_RULE,
                                reason=f"{c.first_name} {c.last_name or ''} ({c.position}) - {label}; "
                                       f"score {score:.1f}, Hunter confidence {c.confidence}. {note}.")
        manual = _manual_pocs(self.manual_path).get(domain)
        if manual:
            c = Contact(**{**manual, "source": "apollo_manual"})
            return PocSelection(domain=domain, chosen=c, candidates=candidates, ranking_rule=RANKING_RULE,
                                reason=f"No Hunter contact matched a buyer persona ({note}); using the manually "
                                       f"looked-up Apollo contact {c.first_name} ({c.position}).")
        return PocSelection(domain=domain, chosen=None, candidates=candidates, ranking_rule=RANKING_RULE,
                            reason=f"No contact matching a buyer persona ({note}). Add one from Apollo to "
                                   f"MANUAL_POCS_JSON to continue.")
