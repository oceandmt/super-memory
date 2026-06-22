"""Quality scoring — memory quality assessment on save.

Evaluates each memory on:
1. **Fidelity** — does the saved text capture a single coherent essence?
   (measures topic concentration, signal-to-noise ratio)
2. **Sufficiency** — is the memory self-contained and actionable?
   (measures information density, completeness)
3. **Importance** — how valuable is this memory likely to be?
   (based on content patterns, sentiment, specificity)

All scoring is best-effort and non-blocking. Scores are attached to memory
metadata for later recall-time filtering.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "QualityConfig", "QualityScore", "score_memory",
    "fidelity_score", "sufficiency_score", "importance_score",
]

logger = logging.getLogger("super-memory.quality")


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class QualityConfig:
    """Configuration for quality scoring.

    Attributes:
        enabled: Set False to skip scoring (save CPU).
        track_fidelity: Score essence concentration.
        track_sufficiency: Score self-contained completeness.
        track_importance: Score likely value/priority.
        min_content_chars: Skip scoring for very short content.
        verbose: Log per-score breakdown (debug level).
    """
    enabled: bool = True
    track_fidelity: bool = True
    track_sufficiency: bool = True
    track_importance: bool = True
    min_content_chars: int = 50
    verbose: bool = False


# ── Score Result ─────────────────────────────────────────────────────────────

@dataclass
class QualityScore:
    """Quality assessment for a single memory.

    All scores are in [0.0, 1.0] where 1.0 = perfect.
    """
    overall: float
    fidelity: float
    sufficiency: float
    importance: float
    warnings: list[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


# ── Fidelity (Essence Concentration) ─────────────────────────────────────────

def fidelity_score(content: str) -> float:
    """Assess how well the content captures a single coherent essence.

    High fidelity = focused topic, low noise, clear signal.
    Penalizes: multi-topic drift, excessive repetition, low entropy.
    """
    if not content or len(content) < 30:
        return 0.0

    sample = content[:2000]
    words = re.findall(r"\w{3,}", sample.lower())
    if len(words) < 5:
        return 0.3

    # Topic focus: ratio of top-10 word frequency to total frequency
    from collections import Counter
    word_freq = Counter(words)
    top10_count = sum(c for _, c in word_freq.most_common(10))
    focus_ratio = top10_count / max(len(words), 1)

    # Very focused (>60% from top 10 words) = good, but too focused (<20% unique) = spam
    unique_ratio = len(word_freq) / max(len(words), 1)

    if unique_ratio < 0.15:
        # Too repetitive
        topic_score = 0.3
    elif focus_ratio > 0.7:
        topic_score = 0.9  # Highly focused
    elif focus_ratio > 0.4:
        topic_score = 0.7
    elif focus_ratio > 0.25:
        topic_score = 0.5
    else:
        topic_score = 0.3

    # Sentence coherence: penalize if content is just one long sentence or too many fragments
    sentences = re.split(r'[.!?]+', sample)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) == 0:
        coherence = 0.3
    elif len(sentences) == 1:
        coherence = 0.6  # Single coherent statement
    elif len(sentences) <= 5:
        coherence = 0.8  # Good paragraph
    elif len(sentences) <= 15:
        coherence = 0.7
    else:
        coherence = 0.5  # Too many fragments

    return round(0.5 * topic_score + 0.5 * coherence, 4)


# ── Sufficiency (Self-containedness) ─────────────────────────────────────────

def sufficiency_score(content: str) -> float:
    """Assess if the memory is self-contained and actionable.

    High sufficiency = specific entities, verbs, numbers, context.
    Penalizes: vague pronouns ('it', 'this thing'), missing actors, no specifics.
    """
    if not content or len(content) < 30:
        return 0.0

    sample = content[:2000]

    # Named entity density (capitalized words = proper nouns)
    capitalized = re.findall(r'\b[A-Z][a-z]{2,}\b', sample)
    entity_count = len(capitalized)
    entity_density = entity_count / max(len(sample.split()), 1)

    # Action verb density
    action_indicators = len(re.findall(
        r'\b(?:implement(?:ed|ing)?|deploy(?:ed|ing)?|fix(?:ed|ing)?|'
        r'add(?:ed|ing)?|change(?:ed|ing)?|create(?:ed|ing)?|'
        r'migrate(?:ed|ing)?|upgrade(?:ed|ing)?|configur(?:ed|ing)?)\b',
        sample, re.IGNORECASE
    ))
    action_density = action_indicators / max(len(sample.split()), 1)

    # Specificity: numbers, code terms, dates
    specifics = len(re.findall(r'\b\d+\b|'  # numbers
                               r'\b(?:[A-Z][a-z]*\.[A-Z][a-z]*)\b|'  # camelCase/Dotted
                               r'\b[A-Z]{2,}\b|'  # Acronyms
                               r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',  # dates
                               sample))
    spec_density = specifics / max(len(sample.split()), 1)

    # Check for vague references
    vagueness = len(re.findall(r'\b(?:it\s+(?:was|is|does|has)|'
                                r'something|thing|stuff|somewhere|'
                                r'someone|somebody|whatever)\b',
                                sample, re.IGNORECASE))

    score = 0.0
    # Entity density: 1+% proper nouns = good
    if entity_density > 0.05:
        score += 0.3
    elif entity_density > 0.02:
        score += 0.2
    elif entity_density > 0.01:
        score += 0.1

    # Action density
    if action_density > 0.02:
        score += 0.25
    elif action_density > 0.005:
        score += 0.15

    # Specificity
    if spec_density > 0.08:
        score += 0.25
    elif spec_density > 0.03:
        score += 0.15

    # Vagueness penalty
    if vagueness > 3:
        score = max(0, score - 0.2)

    # Length bonus (but not too long)
    words = len(sample.split())
    if 20 <= words <= 100:
        score += 0.2
    elif words > 10:
        score += 0.1

    return round(min(score, 1.0), 4)


# ── Importance (Likely Value) ────────────────────────────────────────────────

def importance_score(content: str, memory_type: str = "context") -> float:
    """Assess how important this memory is likely to be for future recall.

    High importance = decisions, errors, workflows, insights, instructions.
    Lower = routine context, observations, logs.
    """
    if not content or len(content) < 20:
        return 0.2

    # Type boost
    type_boost = {
        "decision": 0.3, "insight": 0.25, "instruction": 0.3,
        "workflow": 0.2, "error": 0.3, "boundary": 0.25,
        "fact": 0.1, "preference": 0.15, "todo": 0.15,
    }.get(memory_type, 0.0)

    sample = content[:2000].lower()

    # Decision signal
    decision_signal = len(re.findall(
        r'\b(?:decided|chosen|selected|adopted|chose|elected|'
        r'resolved|determined|concluded)\b', sample
    ))
    decision_score = min(decision_signal * 0.1, 0.3)

    # Error signal
    error_signal = len(re.findall(
        r'\b(?:bug|error|fail(?:ed|ure)?|crash|issue|problem|'
        r'regression|broken|incorrect|wrong|mistake)\b', sample
    ))
    error_score = min(error_signal * 0.1, 0.3)

    # Learning signal
    learning_signal = len(re.findall(
        r'\b(?:learn(?:ed|ing)?|lesson|insight|key\s+takeaway|'
        r'discover(?:ed|y)?|found\s+that|realized)\b', sample
    ))
    learning_score = min(learning_signal * 0.1, 0.2)

    # Urgency signal (dates, versions, deadlines)
    urgency = 1 if re.search(r'\b(?:urgent|critical|breaking|important|'
                              r'immediately|ASAP|deadline|v\d+\.\d+)\b', sample) else 0
    urgency_score = 0.1 if urgency else 0.0

    raw = type_boost + decision_score + error_score + learning_score + urgency_score
    return round(min(raw, 1.0), 4)


# ── Orchestrator ─────────────────────────────────────────────────────────────

def score_memory(content: str, memory_type: str = "context", config: QualityConfig | None = None) -> QualityScore:
    """Run full quality assessment on a memory."""
    try:
        if config is None:
            config = QualityConfig()

        if not config.enabled or len(content) < config.min_content_chars:
            return QualityScore(overall=0.5, fidelity=0.5, sufficiency=0.5, importance=0.5)

        f = fidelity_score(content) if config.track_fidelity else 0.5
        s = sufficiency_score(content) if config.track_sufficiency else 0.5
        i = importance_score(content, memory_type) if config.track_importance else 0.5

        overall = round(0.35 * f + 0.35 * s + 0.30 * i, 4)

        warnings = []
        if f < 0.4:
            warnings.append("Low fidelity: content may be noisy or multi-topic")
        if s < 0.4:
            warnings.append("Low sufficiency: content may be vague or incomplete")
        if i < 0.3:
            warnings.append("Low importance: content may have low recall value")

        qs = QualityScore(overall=overall, fidelity=round(f, 4), sufficiency=round(s, 4), importance=round(i, 4))
        if warnings:
            qs.warnings = warnings

        if config.verbose:
            logger.debug("QualityScore: overall=%.4f fidelity=%.4f sufficiency=%.4f importance=%.4f %s",
                         overall, f, s, i, "⚠ " + "; ".join(warnings) if warnings else "")

        return qs
    except Exception as e:
        logger.warning("quality_score failed: %s", e)
        return QualityScore(overall=0.5, fidelity=0.5, sufficiency=0.5, importance=0.5)
