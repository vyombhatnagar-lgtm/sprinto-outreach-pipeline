"""Input handling: turn whatever the user pastes into clean, unique bare domains."""
import re
from pathlib import Path
from typing import Iterable, List
from urllib.parse import urlparse

_RESERVED_SUFFIXES = (".internal", ".local", ".localhost", ".localdomain", ".lan", ".home", ".corp",
                      ".intranet", ".test", ".invalid", ".example", ".arpa", ".onion")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_domain(raw: str) -> str:
    s = str(raw).strip().lower()[:300]
    if not s:
        raise ValueError("empty domain")
    if "://" not in s:
        s = "http://" + s
    host = urlparse(s).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    if not _DOMAIN_RE.match(host):
        raise ValueError(f"not a valid domain: {str(raw)[:80]!r}")
    if host.endswith(_RESERVED_SUFFIXES):
        raise ValueError(f"not a public domain: {host[:80]!r}")
    return host


def normalize_domains(lines: Iterable[str]) -> List[str]:
    """Normalise, drop comments/blank lines, and dedupe while keeping input order."""
    seen, out = set(), []
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        d = normalize_domain(line)
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def read_domains_file(path: Path) -> List[str]:
    return normalize_domains(path.read_text().splitlines())
