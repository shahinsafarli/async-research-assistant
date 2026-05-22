"""Tests for search query normalization."""
from __future__ import annotations

from src.utils.search_query import arxiv_api_query, search_query_from_question


def test_strips_question_prefix():
    assert search_query_from_question("What is photosynthesis?") == "photosynthesis"


def test_keeps_multi_word_topics():
    q = search_query_from_question("What were the main causes of the 2008 financial crisis?")
    assert "2008" in q
    assert "financial" in q
    assert "crisis" in q


def test_short_query_unchanged():
    assert search_query_from_question("CRISPR") == "CRISPR"


def test_arxiv_api_query_single_term():
    assert arxiv_api_query("photosynthesis") == "photosynthesis"


def test_arxiv_api_query_multi_term():
    assert arxiv_api_query("fusion energy") == "fusion+AND+energy"
