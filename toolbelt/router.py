"""Tool routing: with hundreds of tools you cannot put every schema in the prompt. Rank tools for a query with BM25."""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("the a an of to in and or for on with is are be by that this it as at from i me my you please can could would want need how what do".split())
SYN = {"sum": "add", "plus": "add", "total": "add", "hash": "sha256", "checksum": "sha256", "digest": "sha256", "slug": "slugify", "url": "slugify",
       "mail": "email", "emails": "email", "convert": "convert_units", "miles": "convert_units", "kilometers": "convert_units", "celsius": "convert_units",
       "fahrenheit": "convert_units", "pounds": "convert_units", "kilograms": "convert_units", "days": "days_between", "between": "days_between", "dates": "days_between"}


def toks(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")):
        if w not in STOP:
            out.append(w)
            if w in SYN:
                out += SYN[w].split("_") if "_" in SYN[w] else [SYN[w]]
    return out


class ToolRouter:
    def __init__(self, tools: list[dict], k1: float = 1.4, b: float = 0.6):
        self.tools, self.k1, self.b = tools, k1, b
        self.docs = [toks(t["name"] + " " + t["name"] + " " + t.get("description", "") + " " + " ".join(t.get("inputSchema", {}).get("properties", {}))) for t in tools]
        self.avg = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(w for d in self.docs for w in set(d))
        self.idf = {w: math.log(1 + (len(tools) - n + 0.5) / (n + 0.5)) for w, n in df.items()}

    def select(self, query: str, k: int = 3) -> list[dict]:
        q = toks(query)
        scored = []
        for tool, d in zip(self.tools, self.docs):
            tf, s = Counter(d), 0.0
            for w in q:
                if w in tf:
                    s += self.idf[w] * tf[w] * (self.k1 + 1) / (tf[w] + self.k1 * (1 - self.b + self.b * len(d) / self.avg))
            scored.append((s, tool))
        scored.sort(key=lambda x: -x[0])
        return [t for s, t in scored[:k] if s > 0]

    def savings(self, query: str, k: int = 3) -> float:
        """Fraction of schema characters saved by sending only the selected tools."""
        full = sum(len(str(t)) for t in self.tools)
        return 1 - sum(len(str(t)) for t in self.select(query, k)) / full
