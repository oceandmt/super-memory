"""
Execution Patterns for OpenClaw

Provides task execution discipline, planning, and monitoring
to prevent memory loss and improve task completion rates.

Usage:
    from super_memory.execution_patterns import (
        ExecutionContract,
        PlanEnforcement,
        TaskRouter
    )
    
    # Declare execution contract
    contract = ExecutionContract(
        task="Deep analysis",
        mode="subagent",
        steps=10,
        estimated_time="30-45 min"
    )
    
    # Auto-enforce plan creation
    enforcer = PlanEnforcement()
    plan_file = enforcer.create_plan_file(contract)
    
    # Route to correct execution mode
    router = TaskRouter()
    mode = router.recommend_mode(
        duration_min=40,
        steps=10,
        files=100
    )  # Returns: "subagent"
"""

from .contract import ExecutionContract
from .plan_enforcement import PlanEnforcement
from .task_routing import TaskRouter
from .recovery import TaskRecovery
from .monitoring import ProgressMonitor

__all__ = [
    'ExecutionContract',
    'PlanEnforcement',
    'TaskRouter',
    'TaskRecovery',
    'ProgressMonitor',
]

__version__ = '1.0.0'

# Convenience imports for common patterns
from .contract import create_contract
from .task_routing import route_task

__all__.extend(['create_contract', 'route_task'])
