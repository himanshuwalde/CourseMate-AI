"""Pull individual questions out of a question-bank file. Regex first, LLM as a fallback."""
import json
import re
from typing import Dict, List, Optional

from . import llm
from .prompts import PARSE_SYSTEM

Q_START = re.compile(r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[\.\):\-\u2013]\s+(\S.*)$", re.I)
TABLE_ROW = re.compile(r"^\s*(\d{1,3})\s*\|\s*(.+?)(?:\s*\|\s*(\d{1,2}))?\s*$")
HEADING = re.compile(r"^\s*(unit|module|chapter|section|part)\b", re.I)
MARKS_A = re.compile(r"[\(\[]\s*(\d{1,2})\s*(?:marks?|mks?|m|pts?|points?)\s*[\)\]]", re.I)
MARKS_B = re.compile(r"\b(\d{1,2})\s*marks?\b", re.I)
MAX_QUESTIONS = 150


def _extract_marks(text: str) -> tuple[str, Optional[int]]:
    for pattern in (MARKS_A, MARKS_B):
        m = pattern.search(text)
        if m:
            marks = int(m.group(1))
            cleaned = (text[:m.start()] + text[m.end():]).strip(" -:,")
            return cleaned, marks
    return text.strip(), None


def parse_with_regex(text: str) -> List[Dict]:
    items: List[Dict] = []
    current: Optional[Dict] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if HEADING.match(line):
            current = None
            continue
        m = TABLE_ROW.match(line)
        if m:
            current = {"number": m.group(1), "text": m.group(2), "marks": int(m.group(3)) if m.group(3) else None}
            items.append(current)
            continue
        m = Q_START.match(line)
        if m:
            current = {"number": m.group(1), "text": m.group(2), "marks": None}
            items.append(current)
        elif current is not None:
            current["text"] += " " + line

    result = []
    for it in items[:MAX_QUESTIONS]:
        cleaned, marks = _extract_marks(it["text"])
        result.append({"number": it["number"], "text": re.sub(r"\s+", " ", cleaned), "marks": it["marks"] or marks})
    return [r for r in result if len(r["text"]) > 3]


def _json_list(text: str) -> List[str]:
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return []
    return [str(x).strip() for x in data if isinstance(x, (str, int, float)) and str(x).strip()]


async def parse_with_llm(text: str, model: Optional[str] = None) -> List[Dict]:
    questions: List[str] = []
    for i in range(0, min(len(text), 30000), 5000):
        piece = text[i:i + 5000]
        reply = await llm.chat(
            [{"role": "system", "content": PARSE_SYSTEM}, {"role": "user", "content": piece}], model, temperature=0.0
        )
        questions.extend(_json_list(reply))
    if not questions:  # last resort: any line that ends with a question mark
        questions = [ln.strip() for ln in text.splitlines() if ln.strip().endswith("?")]
    out = []
    for i, q in enumerate(questions[:MAX_QUESTIONS], start=1):
        cleaned, marks = _extract_marks(q)
        out.append({"number": str(i), "text": cleaned, "marks": marks})
    return out


async def parse_questions(text: str, model: Optional[str] = None) -> List[Dict]:
    found = parse_with_regex(text)
    if len(found) >= 2:
        return found
    try:
        fallback = await parse_with_llm(text, model)
    except llm.LLMError:
        fallback = []
    return fallback or found
