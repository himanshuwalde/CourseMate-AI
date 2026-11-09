"""All prompt text in one place, so it is easy to tune."""
import re
from typing import Dict, List, Optional

from .vectorstore import Hit

NOT_FOUND_TOKEN = "NOT_FOUND"
NOT_FOUND_MESSAGE = "I could not find the answer in the selected documents."

SYSTEM_RAG = f"""You are a careful assistant that answers strictly from the provided context excerpts.
Rules:
- Use ONLY the context. Do not add outside knowledge.
- Cite the excerpts you used with their numbers in square brackets, e.g. [1] or [2][3].
- If the context does not contain the answer, reply with exactly: {NOT_FOUND_TOKEN}
- Be accurate and well organised. Use short paragraphs and bullet points where helpful."""

SYSTEM_GENERAL = """You are a knowledgeable teaching assistant. Answer accurately from your general knowledge.
If you are unsure about something, say so instead of guessing."""

REWRITE_SYSTEM = """Rewrite the user's latest message as one standalone question that can be understood without the chat history.
Return ONLY the rewritten question, nothing else."""

PARSE_SYSTEM = """Extract every exam/study question from the text. Return ONLY a JSON array of strings, one per question,
keeping sub-parts with their parent question. No commentary."""

STYLE_GUIDE = {
    "short": "Answer concisely in 2-4 sentences.",
    "detailed": "Give a thorough, well-structured answer. Use bullet points or short headings where useful.",
    "exam": "Write an exam-style answer: a one or two line definition/introduction, the key points as bullets, "
            "and a one-line conclusion.",
}


def marks_guidance(marks: Optional[int]) -> str:
    if not marks:
        return ""
    if marks <= 2:
        return "Length: about 40-60 words."
    if marks <= 5:
        return "Length: about 120-180 words."
    if marks <= 8:
        return "Length: about 200-300 words."
    return "Length: about 300-450 words."


def build_context(hits: List[Hit]) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        where = f"{h.filename}, page {h.page}" if h.page else h.filename
        blocks.append(f"[{i}] ({where})\n{h.text}")
    return "\n\n".join(blocks)


def rag_messages(question: str, hits: List[Hit], history: Optional[List[Dict]] = None, extra: str = "") -> List[Dict]:
    messages: List[Dict] = [{"role": "system", "content": SYSTEM_RAG}]
    for m in (history or [])[-4:]:
        if m.get("role") in {"user", "assistant"}:
            messages.append({"role": m["role"], "content": str(m.get("content", ""))[:1500]})
    user = f"Context:\n{build_context(hits)}\n\nQuestion: {question}"
    if extra.strip():
        user += f"\n\nFormatting instructions: {extra.strip()}"
    messages.append({"role": "user", "content": user})
    return messages


def general_messages(question: str, extra: str = "") -> List[Dict]:
    user = question + (f"\n\nFormatting instructions: {extra.strip()}" if extra.strip() else "")
    return [{"role": "system", "content": SYSTEM_GENERAL}, {"role": "user", "content": user}]


def rewrite_messages(question: str, history: List[Dict]) -> List[Dict]:
    transcript = "\n".join(f"{m['role']}: {str(m['content'])[:600]}" for m in history[-6:])
    return [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": f"Chat history:\n{transcript}\n\nLatest message: {question}"},
    ]


def is_not_found(text: str) -> bool:
    head = text.strip()[:40].upper().replace(" ", "_")
    return head.startswith(NOT_FOUND_TOKEN)


_CITATION = re.compile(r"\s*(?:\[\d+\])+")


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text).strip()


def cited_indexes(text: str, n: int) -> List[int]:
    found = {int(x) for x in re.findall(r"\[(\d+)\]", text)}
    return sorted(i for i in found if 1 <= i <= n)
