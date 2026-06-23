"""Cross-agent recall semantic reorder contract."""

import inspect

from super_memory.cross_agent import CrossAgentTools, _pseudo_semantic_score


def test_cross_agent_recall_semantic_reorder_enabled_by_default():
    sig = inspect.signature(CrossAgentTools.cross_agent_recall)
    assert sig.parameters["semantic_reorder"].default is True


def test_pseudo_semantic_score_orders_related_content_above_unrelated():
    related = _pseudo_semantic_score(
        "canonical memory layer",
        "canonical workspace markdown memory layer stores durable facts",
    )
    partial = _pseudo_semantic_score(
        "api authentication",
        "configure JWT bearer token for API auth",
    )
    unrelated = _pseudo_semantic_score("fishing", "quantum physics equations")

    assert related > partial > unrelated
