"""
Streamlit Web UI for the Async Research Assistant (+2 bonus points).

Run: streamlit run app.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="Async Research Assistant",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Async Research Assistant")
st.caption("Queries Wikipedia · arXiv · Web in parallel and synthesizes a cited answer.")

with st.sidebar:
    st.header("Settings")
    sources_options = st.multiselect(
        "Sources to query",
        options=["wiki", "arxiv", "web"],
        default=["wiki", "arxiv", "web"],
    )
    no_cache = st.checkbox("Bypass cache (--no-cache)", value=False)
    st.divider()
    st.subheader("History")
    show_history = st.button("Refresh history")

question = st.text_input(
    "Research question",
    placeholder="e.g. What is photosynthesis and what are its main stages?",
    key="question_input",
)

ask_button = st.button("Ask", type="primary", disabled=not question)

if ask_button and question:
    from src.models import QuestionRequest
    from src.core.researcher import ResearchEngine
    from src.services.cache import FilesystemCache

    try:
        request = QuestionRequest(
            question=question,
            sources=sources_options or ["wiki", "arxiv", "web"],
            no_cache=no_cache,
        )
    except Exception as exc:
        st.error(f"Invalid input: {exc}")
        st.stop()

    cache = FilesystemCache()
    engine = ResearchEngine(cache=cache)

    with st.spinner("Querying sources in parallel..."):
        try:
            result = asyncio.run(engine.research(request))
        except Exception as exc:
            st.error(f"Research failed: {exc}")
            st.stop()

    st.success(f"Done in {result.elapsed_seconds:.2f}s")

    st.subheader("Answer")
    st.write(result.answer)

    if result.citations:
        st.subheader("References")
        for c in result.citations:
            st.markdown(f"**[{c.index}]** ({c.origin}) [{c.title}]({c.url})")

    if result.sources_failed:
        st.warning(f"Sources that could not be reached: {', '.join(result.sources_failed)}")

    with st.expander("Raw sources retrieved"):
        for s in result.sources_used:
            st.markdown(f"- **{s.title}** ({s.origin})  \n  {s.url}")

if show_history:
    from src.core.researcher import ResearchEngine

    engine = ResearchEngine()
    try:
        sessions = asyncio.run(engine.get_history(limit=10))
    except Exception as exc:
        st.sidebar.error(f"Could not load history: {exc}")
        sessions = []

    if sessions:
        st.sidebar.write(f"Last {len(sessions)} session(s):")
        for s in sessions:
            q = s["question"][:50] + "..." if len(s["question"]) > 50 else s["question"]
            st.sidebar.markdown(f"- {q}  \n  ⏱ {s['elapsed_s']:.1f}s")
    else:
        st.sidebar.info("No sessions yet.")
