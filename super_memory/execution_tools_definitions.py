"""
Execution Patterns MCP Tools - Tool Definitions

Format compatible with super-memory mcp_server.py tool registration.
"""

def _schema(props: dict, required: list = None) -> dict:
    """Generate JSON schema for tool inputs"""
    schema = {
        "type": "object",
        "properties": props
    }
    if required:
        schema["required"] = required
    return schema


# Tool definitions in MCP format
EXECUTION_TOOLS = [
    {
        "name": "super_memory_route_task",
        "description": "Route task to correct execution mode (inline vs subagent) to prevent memory loss after session compaction",
        "inputSchema": _schema({
            "duration_min": {"type": "integer", "description": "Estimated duration in minutes"},
            "steps": {"type": "integer", "description": "Number of steps in task"},
            "files": {"type": "integer", "default": 0, "description": "Number of files to process"},
            "complexity": {"type": "string", "default": "medium", "enum": ["low", "medium", "high"]}
        }, ["duration_min", "steps"])
    },
    {
        "name": "super_memory_create_execution_contract",
        "description": "Create execution contract that declares task parameters and survives session compaction",
        "inputSchema": _schema({
            "task": {"type": "string", "description": "Task description"},
            "mode": {"type": "string", "enum": ["inline", "subagent"]},
            "steps": {"type": "integer"},
            "estimated_time": {"type": "string", "description": "Duration estimate like '30 min'"},
            "checkpoints": {"type": "array", "items": {"type": "string"}},
            "auto_continue": {"type": "boolean", "default": True}
        }, ["task", "mode", "steps", "estimated_time", "checkpoints"])
    },
    {
        "name": "super_memory_create_plan",
        "description": "Create plan file that persists task state beyond context window and survives compaction",
        "inputSchema": _schema({
            "task_description": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object", "properties": {
                "step": {"type": "string"},
                "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"]}
            }}},
            "mode": {"type": "string", "enum": ["inline", "subagent"]},
            "estimated_time": {"type": "string"},
            "session_id": {"type": "string"}
        }, ["task_description", "steps", "mode", "estimated_time"])
    },
    {
        "name": "super_memory_update_plan_progress",
        "description": "Update progress in plan file to maintain accurate state that survives compaction",
        "inputSchema": _schema({
            "plan_file": {"type": "string", "description": "Path to plan file"},
            "step_index": {"type": "integer", "description": "Zero-based step index"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "failed"]}
        }, ["plan_file", "step_index", "status"])
    },
    {
        "name": "super_memory_recover_incomplete_tasks",
        "description": "Find and recover incomplete tasks from plan files after interruption or compaction",
        "inputSchema": _schema({
            "max_age_hours": {"type": "integer", "default": 24},
            "limit": {"type": "integer", "default": 10}
        })
    },
    {
        "name": "super_memory_detect_memory_loss",
        "description": "Detect memory loss patterns in current session and get corrective actions",
        "inputSchema": _schema({})
    }
]
