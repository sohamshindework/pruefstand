"""Conservative pattern-based data screening. Never a GDPR certification."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

PATTERNS = {
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b"),
    "email": re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "steuer_id_candidate": re.compile(r"(?<!\d)\d{11}(?!\d)"),
    "german_address_candidate": re.compile(r"\b[\wÄÖÜäöüß.-]*(?:straße|strasse|str\.|weg|platz)\s+\d+[a-z]?\b", re.I),
    "health_data_candidate": re.compile(r"\b(?:Diagnose|diagnosis|HIV|Diabetes|Krebs|depression|patient)\b", re.I),
    "api_key": re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{15,}|Bearer\s+[A-Za-z0-9._~+/-]{12,})"),
}
SENSITIVE_KEYS = {"authorization", "api_key", "apikey", "password", "secret", "token", "access_token", "cookie", "set-cookie"}


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    count: int


def scrub(value: Any, path: str = "$", redact: bool = True) -> tuple[Any, list[dict]]:
    """Return a JSON-safe copy and findings containing no matched values."""
    findings: list[dict] = []
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key = str(key)
            if key.lower().replace("-", "_") in {k.replace("-", "_") for k in SENSITIVE_KEYS}:
                findings.append(asdict(Finding("secret", f"{path}.{key}", 1)))
                cleaned[key] = "[REDACTED:secret]" if redact else item
            else:
                cleaned[key], found = scrub(item, f"{path}.{key}", redact)
                findings.extend(found)
        return cleaned, findings
    if isinstance(value, (list, tuple)):
        cleaned = []
        for index, item in enumerate(value):
            item, found = scrub(item, f"{path}[{index}]", redact)
            cleaned.append(item)
            findings.extend(found)
        return cleaned, findings
    if isinstance(value, str):
        for category, pattern in PATTERNS.items():
            count = len(pattern.findall(value))
            if count:
                findings.append(asdict(Finding(category, path, count)))
                if redact:
                    value = pattern.sub(f"[REDACTED:{category}]", value)
        return value, findings
    if value is None or isinstance(value, (bool, int, float)):
        return value, findings
    return scrub(str(value), path, redact)


def endpoint_assessment(endpoint: str, eu_hosts: list[str]) -> dict:
    """A user-declared hostname allowlist; geography cannot be inferred from a URL."""
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    return {"host": host, "declared_eu": host in eu_hosts, "verified_residency": False,
            "transport_tls": parsed.scheme == "https", "basis": "operator-declared hostname allowlist"}
