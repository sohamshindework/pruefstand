"""Rule-based German task checks. Explicit expectations make every verdict inspectable."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_amount(text: str) -> Decimal:
    cleaned = text.strip().replace("€", "").replace("EUR", "").strip()
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}", cleaned):
        raise ValueError("Expected a German amount such as 1.234,56 €")
    try:
        return Decimal(cleaned.replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("Invalid German amount") from exc


def check_german(text: str, *, formal: bool = True, amount: str | None = None,
                 date: str | None = None, required_terms: list[str] | None = None,
                 disclosure: bool = False) -> dict:
    checks = {}
    if formal:
        checks["formal_address"] = bool(re.search(r"\b(?:Sie|Ihnen|Ihre|Ihr)\b", text)) and not bool(re.search(r"\b(?:du|dich|dir|dein|euch)\b", text, re.I))
    if amount is not None:
        expected = parse_amount(amount)
        candidates = re.findall(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}\s*(?:€|EUR)", text)
        checks["german_amount"] = any(parse_amount(c) == expected for c in candidates)
    if date is not None:
        datetime.strptime(date, "%d.%m.%Y")
        checks["german_date"] = date in text
    if required_terms:
        checks["terminology"] = all(term in text for term in required_terms)
    if disclosure:
        checks["bot_disclosure"] = bool(re.search(r"\b(?:KI-Assistent|KI-System|künstliche Intelligenz|AI assistant)\b", text, re.I))
    return {"passed": all(checks.values()), "checks": checks, "method": "explicit lexical rules, not a general language-quality score"}
