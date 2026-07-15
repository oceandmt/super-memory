"""
Super-Memory MCP Tools for Execution Patterns

Provides MCP tools that expose execution patterns to OpenClaw agents.
Agents can use these tools to prevent memory loss and improve task completion.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path


def route_task(
    duration_min: int,
    steps: int,
    files: int = 0,
    complexity: str = "medium"
) -> Dict[str, Any]:
    """
    Route task to correct execution mode (inline vs subagent).
    
    Use this tool BEFORE starting multi-step tasks to determine
    the appropriate execution mode.
    
    Args:
        duration_min: Estimated duration in minutes
        steps: Number of steps/phases in task
        files: Number of files to process (optional)
        complexity: Task complexity (low|medium|high)
    
    Returns:
        {
            "mode": "inline" | "subagent",
            "confidence": "LOW" | "MEDIUM" | "HIGH",
            "reason": "explanation",
            "recommendation": "detailed guidance"
        }
    
    Example:
        result = route_task(duration_min=40, steps=10, files=100)
        if result['mode'] == 'subagent':
            # Use sessions_spawn
            pass
    """
    from super_memory.execution_patterns import TaskRouter
    
    router = TaskRouter()
    return router.recommend_mode(
        duration_min=duration_min,
        steps=steps,
        files=files,
        complexity=complexity
    )


def create_execution_contract(
    task: str,
    mode: str,
    steps: int,
    estimated_time: str,
    checkpoints: List[str],
    auto_continue: bool = True
) -> str:
    """
    Create execution contract for multi-step task.
    
    This declares task parameters BEFORE execution and creates
    a contract file that survives session compaction.
    
    Args:
        task: Task description
        mode: Execution mode ("inline" or "subagent")
        steps: Number of steps
        estimated_time: Duration estimate (e.g. "30 min")
        checkpoints: List of checkpoint descriptions
        auto_continue: Enable auto-continuation (default True)
    
    Returns:
        Path to created contract file
    
    Example:
        contract_file = create_execution_contract(
            task="Deep code analysis",
            mode="subagent",
            steps=10,
            estimated_time="40 min",
            checkpoints=["Read files", "Analyze", "Report"]
        )
    """
    from super_memory.execution_patterns import ExecutionContract
    
    contract = ExecutionContract(
        task=task,
        mode=mode,
        steps=steps,
        estimated_time=estimated_time,
        checkpoints=checkpoints,
        auto_continue=auto_continue
    )
    
    contract_file = contract.write_to_file()
    return str(contract_file)


def create_plan_file(
    task_description: str,
    steps: List[Dict[str, str]],
    mode: str,
    estimated_time: str,
    session_id: Optional[str] = None
) -> str:
    """
    Create plan file that survives session compaction.
    
    Plan files persist task state beyond context window limits.
    They enable task resumption after compaction or interruption.
    
    Args:
        task_description: Task description
        steps: List of step dicts with "step" and "status" keys
               Example: [{"step": "Read files", "status": "pending"}]
        mode: Execution mode ("inline" or "subagent")
        estimated_time: Duration estimate
        session_id: Optional session ID for tracking
    
    Returns:
        Path to created plan file
    
    Example:
        plan_file = create_plan_file(
            task_description="Deep analysis",
            steps=[
                {"step": "Read codebase", "status": "pending"},
                {"step": "Analyze patterns", "status": "pending"},
                {"step": "Generate report", "status": "pending"}
            ],
            mode="subagent",
            estimated_time="30 min"
        )
    """
    from super_memory.execution_patterns import PlanEnforcer
    
    enforcer = PlanEnforcer()
    plan_file = enforcer.create_plan_file(
        task_description=task_description,
        steps=steps,
        mode=mode,
        estimated_time=estimated_time,
        session_id=session_id
    )
    
    return str(plan_file)


def update_plan_progress(
    plan_file: str,
    step_index: int,
    status: str
) -> bool:
    """
    Update progress in plan file.
    
    Call this as you complete each step to maintain
    accurate task state that survives compaction.
    
    Args:
        plan_file: Path to plan file (from create_plan_file)
        step_index: Zero-based step index to update
        status: New status ("pending" | "in_progress" | "completed" | "failed")
    
    Returns:
        True if update successful, False otherwise
    
    Example:
        # After completing step 0
        update_plan_progress(plan_file, 0, "completed")
        # Starting step 1
        update_plan_progress(plan_file, 1, "in_progress")
    """
    from super_memory.execution_patterns import PlanEnforcer
    from pathlib import Path
    
    enforcer = PlanEnforcer()
    return enforcer.update_progress(
        plan_file=Path(plan_file),
        step_index=step_index,
        status=status
    )


def recover_incomplete_tasks(
    max_age_hours: int = 24,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Find and recover incomplete tasks from plan files.
    
    Use this to resume work after interruption or context loss.
    
    Args:
        max_age_hours: Maximum age of tasks to recover (default 24)
        limit: Maximum number of tasks to return (default 10)
    
    Returns:
        List of incomplete task dicts with keys:
        - plan_file: Path to plan file
        - task_name: Task description
        - age_hours: Hours since task started
        - last_checkpoint_step: Last completed step index
        - mode: Execution mode
    
    Example:
        incomplete = recover_incomplete_tasks(max_age_hours=24)
        for task in incomplete:
            print(f"Resume: {task['task_name']}")
            print(f"  Last step: {task['last_checkpoint_step']}")
    """
    from super_memory.execution_patterns import TaskRecovery
    
    recovery = TaskRecovery()
    return recovery.find_incomplete_tasks(
        max_age_hours=max_age_hours,
        limit=limit
    )


def detect_memory_loss() -> Dict[str, Any]:
    """
    Detect memory loss patterns in current session.
    
    Returns alert information if memory loss is detected,
    including recommended corrective actions.
    
    Returns:
        {
            "memory_loss_detected": bool,
            "alert": {
                "severity": "low" | "medium" | "high",
                "message": "description",
                "recommended_action": "what to do"
            } | None
        }
    
    Example:
        status = detect_memory_loss()
        if status['memory_loss_detected']:
            alert = status['alert']
            print(f"Warning: {alert['message']}")
            print(f"Action: {alert['recommended_action']}")
    """
    from super_memory.execution_patterns import MemoryLossDetector
    
    detector = MemoryLossDetector()
    
    if detector.check_memory_loss():
        alert = detector.get_alert()
        return {
            "memory_loss_detected": True,
            "alert": alert
        }
    else:
        return {
            "memory_loss_detected": False,
            "alert": None
        }


# MCP Tool Registration
MCP_TOOLS = {
    "super_memory_route_task": {
        "function": route_task,
        "description": "Route task to correct execution mode (inline vs subagent) to prevent memory loss",
        "category": "execution"
    },
    "super_memory_create_execution_contract": {
        "function": create_execution_contract,
        "description": "Create execution contract for multi-step task that survives compaction",
        "category": "execution"
    },
    "super_memory_create_plan": {
        "function": create_plan_file,
        "description": "Create plan file that persists task state beyond context window",
        "category": "execution"
    },
    "super_memory_update_plan_progress": {
        "function": update_plan_progress,
        "description": "Update progress in plan file to maintain accurate state",
        "category": "execution"
    },
    "super_memory_recover_incomplete_tasks": {
        "function": recover_incomplete_tasks,
        "description": "Find and recover incomplete tasks after interruption",
        "category": "execution"
    },
    "super_memory_detect_memory_loss": {
        "function": detect_memory_loss,
        "description": "Detect memory loss patterns and get corrective actions",
        "category": "execution"
    }
}
