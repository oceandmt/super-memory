from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from super_memory.graph import _hash, _safe_token
from super_memory.hybrid_recall import HybridRecall, _tfidf_like, _tokens

TEXT = st.text(min_size=0, max_size=500)
SAFE_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    min_size=0,
    max_size=500,
)


@given(TEXT)
@settings(max_examples=50)
def test_hybrid_tokens_never_empty_short_tokens(text: str) -> None:
    tokens = _tokens(text)
    assert all(token == token.lower() for token in tokens)
    assert all(len(token) > 1 for token in tokens)
    assert all(token.replace("_", "").isalnum() for token in tokens)


@given(SAFE_TEXT, SAFE_TEXT)
@settings(max_examples=50)
def test_tfidf_like_score_is_bounded(query: str, content: str) -> None:
    score = _tfidf_like(query, content)
    assert 0.0 <= score <= 1.0


@given(SAFE_TEXT)
@settings(max_examples=50)
def test_tfidf_like_exact_phrase_scores_nonzero(text: str) -> None:
    assume_text = " ".join(_tokens(text))
    if not assume_text:
        return
    score = _tfidf_like(assume_text, f"prefix {assume_text} suffix")
    assert score > 0.0


@given(TEXT)
@settings(max_examples=50)
def test_graph_safe_token_constraints(text: str) -> None:
    token = _safe_token(text)
    assert token
    assert len(token) <= 48
    assert token.strip("-") == token
    assert all(ch.isalnum() or ch in "_.:-" for ch in token)


@given(SAFE_TEXT)
@settings(max_examples=50)
def test_graph_hash_is_stable_sha256_hex(text: str) -> None:
    value = _hash(text)
    assert value == _hash(text)
    assert len(value) == 64
    assert all(ch in "0123456789abcdef" for ch in value)


@settings(max_examples=25)
@given(st.lists(TEXT, min_size=0, max_size=20), st.integers(min_value=1, max_value=100))
def test_hybrid_truncate_respects_budget(contents: list[str], max_tokens: int) -> None:
    rows = [{"id": str(i), "content": content} for i, content in enumerate(contents)]
    out = HybridRecall._truncate(None, rows, max_tokens=max_tokens)
    budget = int(max_tokens * 3.5)
    assert sum(len(row["content"] or "") for row in out) <= budget
    assert len(out) <= len(rows)