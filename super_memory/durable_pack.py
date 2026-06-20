from __future__ import annotations

from typing import Any

from .models import MemoryScope, MemoryType

DEFAULT_PACK_NAME = "openclaw-super-memory-durable-pack-v1"
DEFAULT_PROJECT = "super-memory"
DEFAULT_AGENTS = ["lucas", "alex", "max", "isol"]


def build_openclaw_pack(pack_name: str = DEFAULT_PACK_NAME, project: str = DEFAULT_PROJECT) -> list[dict[str, Any]]:
    """Return curated durable memories that make raw turn capture useful for agents.

    The pack intentionally stores short, high-signal, cross-agent facts/workflows instead of
    raw transcripts. It is deterministic and safe to re-run because bridge.remember performs
    content-hash deduplication per item.
    """
    base = {
        "scope": MemoryScope.SHARED.value,
        "agent_id": "lucas",
        "project": project,
        "source": "super-memory.durable-pack",
        "trust_score": 0.95,
    }
    common_tags = ["durable-pack", pack_name, "openclaw", "cross-agent"]
    return [
        {
            **base,
            "type": MemoryType.DECISION.value,
            "tags": [*common_tags, "super-memory-v0.2.0", "plugin-fix"],
            "content": (
                "Super Memory v0.2.0 durable fix summary: OpenClaw native plugin now captures "
                "real Discord inbound turns for Lucas, Alex, Max, and Isol through "
                "before_agent_finalize and agent_end. Root cause was api.config exposing global "
                "OpenClaw config instead of plugin-specific config; plugin now reads "
                "plugins.entries['super-memory'].config so autoSyncTurns, mode, and agentChannelMap "
                "are honored. Runtime, projects/super-memory-github, and GitHub oceandmt/super-memory "
                "were synced."
            ),
        },
        {
            **base,
            "type": MemoryType.FACT.value,
            "tags": [*common_tags, "agent-routing", "discord"],
            "content": (
                "OpenClaw Super Memory agent routing: Discord channel IDs map to agent IDs via "
                "agentChannelMap. Lucas channel 1516033294636941462, Alex channel 1486875638139981967, "
                "Max channel 1486875702258303160, Isol channel 1509390937938460792. Captured turns are "
                "saved to workspace_markdown, mempalace, honcho, and neural_memory layers."
            ),
        },
        {
            **base,
            "type": MemoryType.WORKFLOW.value,
            "tags": [*common_tags, "capture-workflow", "content-cleanliness"],
            "content": (
                "Super Memory turn capture workflow: save the user text plus only the final assistant "
                "text reply. Do not persist intermediate assistant tool-call JSON. Discord content array "
                "blocks must be flattened by extracting text/content/value fields. New turns verified clean "
                "for Lucas, Alex, Max, and Isol with the prompt 'Bạn biết vẽ chứ'."
            ),
        },
        {
            **base,
            "type": MemoryType.WORKFLOW.value,
            "tags": [*common_tags, "recall-policy", "intelligence"],
            "content": (
                "How OpenClaw agents should use Super Memory: before answering project/history/role/debug "
                "questions, recall shared and agent-specific Super Memory context. Prefer curated durable "
                "memories (decisions, facts, workflows, lessons) over raw turn transcripts. Use raw transcripts "
                "for audit only. This improves continuity, cross-agent awareness, and behavior consistency."
            ),
        },
        {
            **base,
            "type": MemoryType.FACT.value,
            "tags": [*common_tags, "agent-roles"],
            "content": (
                "OpenClaw agent role baseline: Lucas is the primary engineering/debugging agent for code, "
                "gateway, plugin, and system fixes. Max focuses on memory systems, trading, automation, browser, "
                "and technical operations. Isol focuses on sales/business workflow. Alex is a cross-agent assistant "
                "that can consult shared Super Memory and collaborate through the shared memory layer."
            ),
        },
        {
            **base,
            "type": MemoryType.LESSON.value,
            "tags": [*common_tags, "quality", "consolidation"],
            "content": (
                "Super Memory quality lesson: raw transcript capture is necessary for audit but not sufficient "
                "for agent intelligence. Durable curated packs should summarize important fixes, roles, policies, "
                "and workflows. Periodically deduplicate or consolidate before_agent_finalize/agent_end duplicates "
                "and promote high-signal memories to shared/project scope."
            ),
        },
    ]


def qualification_queries() -> list[str]:
    return [
        "Super Memory v0.2.0 durable fix summary api.config agentChannelMap",
        "OpenClaw agent routing Lucas Alex Max Isol Discord channel IDs",
        "Discord content array blocks final assistant text tool call JSON",
        "raw transcript capture necessary audit sufficient agent intelligence",
        "OpenClaw agent role baseline Lucas Max Isol Alex",
    ]
