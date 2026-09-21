"""Text normalisation shared by checkers (CJK-aware, stdlib only)."""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

_PUNCT = re.compile(
    r"[\s\.,;:!\?'\"`\(\)\[\]\{\}<>/\\\-_=\+\*&\^%\$#@~\|"
    r"\u3000-\u303f\uff01-\uff5e\u2018\u2019\u201c\u201d]+"
)
_NUM_RE = re.compile(r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
_CODE_FENCE = re.compile(r"```(?P<lang>[A-Za-z0-9_+\-]*)\n(?P<body>.*?)```", re.S)


def normalize_text(s: str, *, drop_punct: bool = True, casefold: bool = True) -> str:
    """NFKC + optional casefold + punctuation/space squashing.

    Full-width digits/letters collapse to ASCII, so 「１２３」 == 「123」.
    """
    if s is None:
        return ""
    out = unicodedata.normalize("NFKC", str(s))
    if casefold:
        out = out.casefold()
    if drop_punct:
        out = _PUNCT.sub(" ", out)
    return " ".join(out.split())


def tokenize(s: str) -> List[str]:
    """Latin words + individual CJK characters."""
    norm = normalize_text(s)
    toks: List[str] = []
    buf = []
    for ch in norm:
        if "\u4e00" <= ch <= "\u9fff":
            if buf:
                toks.append("".join(buf))
                buf = []
            toks.append(ch)
        elif ch.isspace():
            if buf:
                toks.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        toks.append("".join(buf))
    return toks


def contains_all(haystack: str, needles: List[str]) -> bool:
    h = normalize_text(haystack)
    return all(normalize_text(n) in h for n in needles)


def numbers_in(s: str) -> List[float]:
    out: List[float] = []
    for m in _NUM_RE.finditer(s or ""):
        raw = m.group(0).replace(",", "")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


def extract_code_block(text: str, lang: Optional[str] = None) -> str:
    """Return the first fenced block (optionally filtered by language tag).

    Falls back to the whole text when no fence is present -- models often
    answer with bare code.
    """
    if not text:
        return ""
    blocks = [(m.group("lang") or "").lower().strip() for m in _CODE_FENCE.finditer(text)]
    bodies = [m.group("body") for m in _CODE_FENCE.finditer(text)]
    if not bodies:
        return text.strip()
    if lang:
        for tag, body in zip(blocks, bodies):
            if tag == lang.lower():
                return body.strip()
    return bodies[0].strip()


def extract_sql(text: str) -> str:
    """Pull a single SQL statement out of a model answer."""
    body = extract_code_block(text, "sql")
    body = body.strip()
    # drop trailing prose after the statement terminator
    if ";" in body:
        head, _sep, _tail = body.partition(";")
        if head.strip():
            body = head
    return body.strip().rstrip(";").strip()
