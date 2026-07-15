"""
Execution Patterns - Auto-Detection Module

Automatically detects multi-step tasks and applies execution patterns.
Integrated into super-memory remember() lifecycle.
"""

from typing import Dict, Any, Optional
import re


def is_multi_step_task(content: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Detect if content represents a multi-step task.
    
    Returns:
        {
            "is_multi_step": bool,
            "confidence": float (0-1),
            "estimated_steps": int,
            "estimated_duration_min": int,
            "indicators": list[str]
        }
    """
    indicators = []
    estimated_steps = 0
    estimated_duration_min = 0
    
    # Check content length (long content = likely multi-step)
    if len(content) > 500:
        indicators.append("long_content")
        estimated_duration_min += 15
    
    # Check for step indicators
    step_patterns = [
        r'\b(?:step|phase|stage)\s*\d+',
        r'\b(?:first|second|third|then|next|after|finally)',
        r'\d+\.\s+\w+',  # numbered lists
        r'-\s+\w+.*\n-\s+\w+',  # bullet lists with multiple items
    ]
    
    for pattern in step_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            indicators.append(f"pattern_{pattern[:20]}")
            estimated_steps += len(matches)
    
    # Check for task-related keywords
    task_keywords = [
        'implement', 'create', 'build', 'develop', 'design',
        'analyze', 'investigate', 'research', 'debug',
        'integrate', 'deploy', 'test', 'validate'
    ]
    
    task_keyword_count = sum(1 for kw in task_keywords if kw in content.lower())
    if task_keyword_count >= 2:
        indicators.append("multiple_task_keywords")
        estimated_duration_min += 10
    
    # Check metadata hints
    if metadata:
        if metadata.get('type') == 'task':
            indicators.append("metadata_type_task")
            estimated_duration_min += 20
        
        if 'project' in metadata:
            indicators.append("has_project")
            estimated_duration_min += 10
    
    # Calculate confidence
    confidence = min(1.0, len(indicators) * 0.15)
    
    # Adjust estimates
    if estimated_steps == 0 and len(indicators) > 0:
        estimated_steps = max(3, len(indicators))
    
    if estimated_duration_min == 0 and len(indicators) > 0:
        estimated_duration_min = estimated_steps * 5
    
    is_multi_step = confidence > 0.3 or estimated_steps >= 3
    
    return {
        "is_multi_step": is_multi_step,
        "confidence": confidence,
        "estimated_steps": estimated_steps,
        "estimated_duration_min": estimated_duration_min,
        "indicators": indicators
    }


def auto_create_execution_state(
    content: str,
    metadata: Dict[str, Any],
    detection: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Auto-create execution contract and plan file if task detected.
    
    Returns:
        {
            "contract_file": str,
            "plan_file": str,
            "mode": str
        } or None if not applicable
    """
    if not detection["is_multi_step"]:
        return None
    
    try:
        from . import mcp_execution_tools
        
        # Route task
        routing = mcp_execution_tools.route_task(
            duration_min=detection["estimated_duration_min"],
            steps=detection["estimated_steps"],
            files=0,
            complexity="medium"
        )
        
        # Create execution contract
        task_description = content[:200] + "..." if len(content) > 200 else content
        
        contract_file = mcp_execution_tools.create_execution_contract(
            task=task_description,
            mode=routing["mode"],
            steps=detection["estimated_steps"],
            estimated_time=f"{detection['estimated_duration_min']} min",
            checkpoints=[f"Step {i+1}" for i in range(min(detection["estimated_steps"], 5))],
            auto_continue=True
        )
        
        # Create plan file
        steps = [
            {"step": f"Step {i+1}", "status": "pending"}
            for i in range(detection["estimated_steps"])
        ]
        
        plan_file = mcp_execution_tools.create_plan_file(
            task_description=task_description,
            steps=steps,
            mode=routing["mode"],
            estimated_time=f"{detection['estimated_duration_min']} min",
            session_id=metadata.get("session_id")
        )
        
        return {
            "contract_file": contract_file,
            "plan_file": plan_file,
            "mode": routing["mode"],
            "detection": detection
        }
        
    except Exception as e:
        # Silently fail - don't break remember() if execution patterns have issues
        return None


def should_auto_apply_patterns(content: str, type_hint: str = None) -> bool:
    """
    Quick check if execution patterns should be auto-applied.
    
    Args:
        content: Memory content
        type_hint: Optional type hint ("task", "context", etc.)
    
    Returns:
        True if patterns should be applied
    """
    # Don't apply for short content
    if len(content) < 100:
        return False
    
    # Don't apply for non-task types
    if type_hint and type_hint not in ["task", "context", "decision"]:
        return False
    
    # Apply for content with clear task indicators
    task_indicators = ["implement", "create", "build", "phase", "step"]
    return any(indicator in content.lower() for indicator in task_indicators)
