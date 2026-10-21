"""Reflection step: check a drafted answer against the evidence.

Small models invent figures. Every number in the draft (quantities, amounts,
percentages, days, dates) must appear in what the tools or the searched
records returned, or in the question itself. The check is deterministic, so
it cannot be talked out of a result the way a second model call could.
"""

import re

NUMBER = re.compile(r"(?<![A-Za-z])(?:rs\.?\s*|₹\s*)?(\d[\d,]*(?:\.\d+)?)", re.I)


def _norm(raw: str) -> str:
    value = raw.replace(",", "")
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    return value


def numbers_in(text: str) -> set[str]:
    return {_norm(m.group(1)) for m in NUMBER.finditer(text or "")}


def unsupported_numbers(draft: str, evidence: list[str], question: str = "") -> list[str]:
    """Numbers in `draft` that no evidence text (or the question) contains."""
    known = numbers_in(question)
    for text in evidence:
        found = numbers_in(text)
        known |= found
        # A rounded figure (66.67 -> 67 or 66.7) is still the record's figure.
        for value in [v for v in found if "." in v]:
            known |= {str(round(float(value))), _norm(f"{float(value):.1f}")}
        # Dates in records look like 2026-10-18; answers may say 18 or 18 Oct.
        for y, m, d in re.findall(r"(\d{4})-(\d{2})-(\d{2})", text or ""):
            known |= {_norm(y), str(int(m)), str(int(d))}
    # Record names such as PO-0007 or MR-00012 are identifiers, not figures.
    draft_figures = NUMBER.finditer(re.sub(r"\b[A-Z]{2,4}-\d+\b", " ", draft or ""))
    missing = []
    for match in draft_figures:
        value = _norm(match.group(1))
        if value not in known and value not in missing and not (value.isdigit() and int(value) <= 1):
            missing.append(value)
    return missing
