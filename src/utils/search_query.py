"""Derive short search phrases for Wikipedia / arXiv from natural-language questions."""
from __future__ import annotations

import re

_QUESTION_PREFIXES = (
    "what is ",
    "what are ",
    "what was ",
    "what were ",
    "how does ",
    "how do ",
    "how did ",
    "why is ",
    "why are ",
    "why do ",
    "when did ",
    "when was ",
    "where is ",
    "where are ",
    "who is ",
    "who are ",
    "explain ",
    "describe ",
    "tell me about ",
)

_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "but",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "have", "has", "had", "will", "would", "can", "could", "should", "may",
    "might", "must", "shall", "this", "that", "these", "those", "it", "its",
    "with", "from", "by", "about", "into", "through", "during", "before",
    "after", "above", "below", "between", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only",
    "own", "same", "so", "than", "too", "very", "just", "also", "now",
})


def search_query_from_question(question: str) -> str:
    """Return a compact phrase suitable for Wikipedia opensearch and arXiv API.

    Full-sentence questions (e.g. "What is photosynthesis?") often return no
    Wikipedia titles and trigger arXiv rate limits. Keyword-style queries work
    reliably for both APIs.
    """
    q = question.strip()
    q = re.sub(r"\s+", " ", q)
    q = q.strip("?!.,;:\"'")

    lowered = q.lower()
    for prefix in _QUESTION_PREFIXES:
        if lowered.startswith(prefix):
            q = q[len(prefix):].strip()
            lowered = q.lower()
            break

    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9'-]*", q)
    keywords = [w for w in words if w.lower() not in _STOP_WORDS]

    if keywords:
        return " ".join(keywords[:10])

    return q or question.strip()


def arxiv_api_query(keywords: str) -> str:
    """Build the query fragment passed to ``ai.fetch_arxiv`` (wrapped as ``all:{query}``).

    Multi-word phrases use arXiv AND syntax; single terms are passed through unchanged.
    """
    terms = [t for t in re.split(r"\s+", keywords.strip()) if t]
    if not terms:
        return keywords.strip()
    if len(terms) == 1:
        return terms[0]
    return "+AND+".join(terms)
