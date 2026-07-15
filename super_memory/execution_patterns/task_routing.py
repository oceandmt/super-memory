"""
Task Routing Decision Tree

Determines optimal execution mode (inline vs subagent) based on task characteristics.

Usage:
    from super_memory.execution_patterns import TaskRouter
    
    router = TaskRouter()
    
    recommendation = router.recommend_mode(
        duration_min=40,
        steps=11,
        files=100,
        complexity="high"
    )
    
    print(recommendation["mode"])  # "subagent"
    print(recommendation["confidence"])  # "HIGH"
    print(recommendation["reason"])  # Explanation
"""

from dataclasses import dataclass
from typing import Literal, Optional, Dict, Any

@dataclass
class TaskCharacteristics:
    """Task characteristics for routing decision"""
    duration_min: int
    steps: int
    files: int
    complexity: Literal["low", "medium", "high"]
    user_interaction: bool = False
    requires_context: bool = False


class TaskRouter:
    """Task execution mode router"""
    
    # Thresholds
    DURATION_THRESHOLD = 15  # minutes
    STEPS_THRESHOLD = 5
    FILES_THRESHOLD = 20
    
    def __init__(self):
        pass
    
    def recommend_mode(
        self,
        duration_min: int,
        steps: int,
        files: int,
        complexity: str = "medium",
        user_interaction: bool = False,
        requires_context: bool = False
    ) -> Dict[str, Any]:
        """
        Recommend execution mode based on task characteristics
        
        Args:
            duration_min: Estimated duration in minutes
            steps: Number of execution steps
            files: Number of files to process
            complexity: Task complexity (low, medium, high)
            user_interaction: Whether user interaction is needed
            requires_context: Whether main session context is required
        
        Returns:
            Recommendation dict with mode, confidence, and reason
        """
        characteristics = TaskCharacteristics(
            duration_min=duration_min,
            steps=steps,
            files=files,
            complexity=complexity,
            user_interaction=user_interaction,
            requires_context=requires_context
        )
        
        # Apply decision tree
        decision = self._apply_decision_tree(characteristics)
        
        return decision
    
    def _apply_decision_tree(self, char: TaskCharacteristics) -> Dict[str, Any]:
        """Apply decision tree logic"""
        
        # Force inline if requires context or user interaction
        if char.requires_context or char.user_interaction:
            return {
                "mode": "inline",
                "confidence": "HIGH",
                "reason": "Requires main session context or user interaction",
                "characteristics": char.__dict__
            }
        
        # Check subagent indicators
        subagent_score = 0
        reasons = []
        
        if char.duration_min > self.DURATION_THRESHOLD:
            subagent_score += 3
            reasons.append(f"Duration {char.duration_min} min > {self.DURATION_THRESHOLD} min threshold")
        
        if char.steps > self.STEPS_THRESHOLD:
            subagent_score += 2
            reasons.append(f"Steps {char.steps} > {self.STEPS_THRESHOLD} threshold")
        
        if char.files > self.FILES_THRESHOLD:
            subagent_score += 2
            reasons.append(f"Files {char.files} > {self.FILES_THRESHOLD} threshold")
        
        if char.complexity == "high":
            subagent_score += 2
            reasons.append("High complexity task")
        
        # Decision based on score
        if subagent_score >= 4:
            confidence = "HIGH"
            mode = "subagent"
        elif subagent_score >= 2:
            confidence = "MEDIUM"
            mode = "subagent"
        else:
            confidence = "HIGH"
            mode = "inline"
            reasons = ["Simple task suitable for inline execution"]
        
        return {
            "mode": mode,
            "confidence": confidence,
            "score": subagent_score,
            "reason": "; ".join(reasons),
            "characteristics": char.__dict__
        }
    
    def get_decision_tree_markdown(self) -> str:
        """Get decision tree as markdown documentation"""
        return f"""# Task Routing Decision Tree

## Thresholds

- Duration: > {self.DURATION_THRESHOLD} minutes → SUBAGENT
- Steps: > {self.STEPS_THRESHOLD} → SUBAGENT
- Files: > {self.FILES_THRESHOLD} → SUBAGENT
- Complexity: HIGH → SUBAGENT

## Decision Flow

```
START
  │
  ├─ User interaction needed? ─────────> YES → INLINE
  │
  ├─ Requires main context? ───────────> YES → INLINE
  │
  ├─ Duration > 15 min? ───────────────> YES → SUBAGENT (score +3)
  │
  ├─ Steps > 5? ───────────────────────> YES → SUBAGENT (score +2)
  │
  ├─ Files > 20? ──────────────────────> YES → SUBAGENT (score +2)
  │
  ├─ Complexity HIGH? ─────────────────> YES → SUBAGENT (score +2)
  │
  └─ Score >= 4? ──────────────────────> YES → SUBAGENT (HIGH confidence)
     Score >= 2? ──────────────────────> YES → SUBAGENT (MEDIUM confidence)
     Otherwise ────────────────────────> INLINE (HIGH confidence)
```

## Examples

### Example 1: Simple File Edit
- Duration: 2 min
- Steps: 1
- Files: 1
- Complexity: low
**→ INLINE** (score: 0)

### Example 2: Deep Analysis
- Duration: 40 min
- Steps: 11
- Files: 100
- Complexity: high
**→ SUBAGENT** (score: 9, HIGH confidence)

### Example 3: Interactive Debugging
- Duration: 30 min
- User interaction: YES
**→ INLINE** (requires interaction)
"""


# Convenience function
def route_task(
    duration_min: int,
    steps: int,
    files: int = 0,
    complexity: str = "medium"
) -> str:
    """
    Quick task routing (convenience function)
    
    Returns: "inline" or "subagent"
    """
    router = TaskRouter()
    result = router.recommend_mode(duration_min, steps, files, complexity)
    return result["mode"]
