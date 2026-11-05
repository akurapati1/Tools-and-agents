"""Example tools. Run as a server:  python -m toolbelt.examples"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Literal

from .server import ToolError, ToolServer

server = ToolServer("toolbelt-examples")
UNITS = {("km", "mi"): 0.621371, ("mi", "km"): 1.609344, ("kg", "lb"): 2.204623, ("lb", "kg"): 0.453592, ("c", "f"): None, ("f", "c"): None}


@server.tool
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@server.tool
def word_count(text: str) -> dict:
    """Count words, characters and lines in a text."""
    return {"words": len(text.split()), "chars": len(text), "lines": len(text.splitlines()) or 1}


@server.tool
def slugify(text: str) -> str:
    """Turn a title into a URL-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@server.tool
def sha256(text: str) -> str:
    """Compute the SHA-256 hex digest of a text."""
    return hashlib.sha256(text.encode()).hexdigest()


@server.tool
def days_between(start: str, end: str) -> int:
    """Number of days between two ISO dates (YYYY-MM-DD)."""
    try:
        return (date.fromisoformat(end) - date.fromisoformat(start)).days
    except ValueError as exc:
        raise ToolError(f"dates must be ISO formatted: {exc}") from None


@server.tool
def convert_units(value: float, frm: Literal["km", "mi", "kg", "lb", "c", "f"], to: Literal["km", "mi", "kg", "lb", "c", "f"]) -> float:
    """Convert distance, weight or temperature between units."""
    if (frm, to) == ("c", "f"):
        return round(value * 9 / 5 + 32, 4)
    if (frm, to) == ("f", "c"):
        return round((value - 32) * 5 / 9, 4)
    factor = UNITS.get((frm, to))
    if factor is None:
        raise ToolError(f"cannot convert {frm} to {to}")
    return round(value * factor, 4)


@server.tool
def extract_emails(text: str) -> list[str]:
    """Find all email addresses in a text."""
    return re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", text)


if __name__ == "__main__":
    server.serve_stdio()
