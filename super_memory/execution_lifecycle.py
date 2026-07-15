"""
Execution Patterns - Lifecycle Integration Module

Hooks into super-memory lifecycle events to maintain execution state
across context compaction, session changes, and interruptions.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import time


class ExecutionLifecycle:
    """Manages execution pattern lifecycle events"""
    
    def __init__(self):
        self.plan_registry_file = Path.home() / ".openclaw/tmp/execution-plan-registry.json"
        self._ensure_registry()
    
    def _ensure_registry(self):
        """Ensure plan registry file exists"""
        self.plan_registry_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.plan_registry_file.exists():
            self.plan_registry_file.write_text(json.dumps({"sessions": {}, "plans": {}}))
    
    def _load_registry(self) -> Dict:
        """Load plan registry"""
        try:
            return json.loads(self.plan_registry_file.read_text())
        except:
            return {"sessions": {}, "plans": {}}
    
    def _save_registry(self, registry: Dict):
        """Save plan registry"""
        try:
            self.plan_registry_file.write_text(json.dumps(registry, indent=2))
        except:
            pass
    
    def register_plan(self, plan_file: str, session_id: str = None, metadata: Dict = None):
        """
        Register a plan file for tracking and recovery.
        
        Args:
            plan_file: Path to plan file
            session_id: Optional session ID
            metadata: Optional metadata (task description, mode, etc.)
        """
        registry = self._load_registry()
        
        plan_id = Path(plan_file).stem
        registry["plans"][plan_id] = {
            "plan_file": plan_file,
            "session_id": session_id,
            "created_at": time.time(),
            "metadata": metadata or {},
            "status": "active"
        }
        
        if session_id:
            if session_id not in registry["sessions"]:
                registry["sessions"][session_id] = []
            registry["sessions"][session_id].append(plan_id)
        
        self._save_registry(registry)
    
    def update_plan_status(self, plan_file: str, status: str):
        """Update plan status in registry"""
        registry = self._load_registry()
        plan_id = Path(plan_file).stem
        
        if plan_id in registry["plans"]:
            registry["plans"][plan_id]["status"] = status
            registry["plans"][plan_id]["updated_at"] = time.time()
            self._save_registry(registry)
    
    def get_session_plans(self, session_id: str) -> List[Dict]:
        """Get all plans for a session"""
        registry = self._load_registry()
        plan_ids = registry["sessions"].get(session_id, [])
        return [registry["plans"][pid] for pid in plan_ids if pid in registry["plans"]]
    
    def get_active_plans(self, max_age_hours: int = 24) -> List[Dict]:
        """Get all active plans within max_age"""
        registry = self._load_registry()
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        active = []
        for plan_id, plan_data in registry["plans"].items():
            if plan_data.get("status") == "active":
                created_at = plan_data.get("created_at", 0)
                if created_at > cutoff_time:
                    active.append(plan_data)
        
        return active
    
    def on_memory_save(self, record: Any, execution_state: Dict = None):
        """
        Hook called when memory is saved.
        
        If execution_state exists, register the plan and sync progress.
        """
        if not execution_state:
            return
        
        plan_file = execution_state.get("plan_file")
        if not plan_file:
            return
        
        # Register plan
        self.register_plan(
            plan_file=plan_file,
            session_id=getattr(record, "session_id", None),
            metadata={
                "task": record.content[:200] if hasattr(record, "content") else "",
                "mode": execution_state.get("mode"),
                "confidence": execution_state.get("confidence")
            }
        )
    
    def on_compaction_start(self, session_id: str = None):
        """
        Hook called when context compaction starts.
        
        Ensure all active plan files are synced and saved.
        """
        if session_id:
            plans = self.get_session_plans(session_id)
        else:
            plans = self.get_active_plans(max_age_hours=2)
        
        # Mark plans as "compaction-safe"
        for plan_data in plans:
            plan_file = plan_data.get("plan_file")
            if plan_file and Path(plan_file).exists():
                # Plan file already persisted to disk - safe across compaction
                self.update_plan_status(plan_file, "compaction-safe")
    
    def on_session_start(self, session_id: str):
        """
        Hook called when session starts.
        
        Check for incomplete plans and trigger recovery if needed.
        """
        plans = self.get_session_plans(session_id)
        incomplete = [p for p in plans if p.get("status") in ["active", "compaction-safe"]]
        
        if incomplete:
            # Return recovery info
            return {
                "recovery_needed": True,
                "incomplete_plans": incomplete,
                "count": len(incomplete)
            }
        
        return {"recovery_needed": False}
    
    def mark_plan_complete(self, plan_file: str):
        """Mark plan as completed"""
        self.update_plan_status(plan_file, "completed")
    
    def mark_plan_failed(self, plan_file: str, reason: str = ""):
        """Mark plan as failed"""
        registry = self._load_registry()
        plan_id = Path(plan_file).stem
        
        if plan_id in registry["plans"]:
            registry["plans"][plan_id]["status"] = "failed"
            registry["plans"][plan_id]["failure_reason"] = reason
            registry["plans"][plan_id]["failed_at"] = time.time()
            self._save_registry(registry)


# Global lifecycle instance
_lifecycle = None

def get_lifecycle() -> ExecutionLifecycle:
    """Get global lifecycle instance"""
    global _lifecycle
    if _lifecycle is None:
        _lifecycle = ExecutionLifecycle()
    return _lifecycle


# Convenience functions for hooks
def hook_memory_save(record: Any, execution_state: Dict = None):
    """Hook for memory save events"""
    get_lifecycle().on_memory_save(record, execution_state)


def hook_compaction_start(session_id: str = None):
    """Hook for compaction start events"""
    get_lifecycle().on_compaction_start(session_id)


def hook_session_start(session_id: str):
    """Hook for session start events"""
    return get_lifecycle().on_session_start(session_id)
