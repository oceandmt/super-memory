"""
Execution Patterns - Auto-Debug Module

Automatically detects and fixes execution pattern issues.
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import json
import time
from datetime import datetime, timedelta


class ExecutionDebug:
    """Auto-debug execution pattern issues"""
    
    def __init__(self):
        self.debug_log_file = Path.home() / ".openclaw/tmp/execution-debug.log"
        self._ensure_log()
    
    def _ensure_log(self):
        """Ensure debug log exists"""
        self.debug_log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.debug_log_file.exists():
            self.debug_log_file.write_text("# Execution Patterns Debug Log\n")
    
    def _log(self, level: str, message: str):
        """Log debug message"""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] {level}: {message}\n"
        
        try:
            with open(self.debug_log_file, 'a') as f:
                f.write(entry)
        except:
            pass
    
    def check_plan_file(self, plan_file: str) -> Dict[str, Any]:
        """
        Check plan file for issues.
        
        Returns:
            {
                "exists": bool,
                "readable": bool,
                "has_steps": bool,
                "issues": list[str]
            }
        """
        issues = []
        plan_path = Path(plan_file)
        
        # Check existence
        if not plan_path.exists():
            issues.append("Plan file missing")
            return {
                "exists": False,
                "readable": False,
                "has_steps": False,
                "issues": issues
            }
        
        # Check readability
        try:
            content = plan_path.read_text()
            readable = True
        except:
            issues.append("Plan file not readable")
            return {
                "exists": True,
                "readable": False,
                "has_steps": False,
                "issues": issues
            }
        
        # Check for steps
        has_steps = "step" in content.lower() or "##" in content
        if not has_steps:
            issues.append("Plan file has no steps")
        
        return {
            "exists": True,
            "readable": True,
            "has_steps": has_steps,
            "issues": issues
        }
    
    def detect_stale_tasks(self, max_age_hours: int = 48) -> List[Dict]:
        """
        Detect stale tasks (active for too long without completion).
        
        Returns list of stale task info
        """
        from .execution_lifecycle import get_lifecycle
        
        lifecycle = get_lifecycle()
        active_plans = lifecycle.get_active_plans(max_age_hours=max_age_hours * 2)
        
        cutoff_time = time.time() - (max_age_hours * 3600)
        stale = []
        
        for plan_data in active_plans:
            created_at = plan_data.get("created_at", time.time())
            if created_at < cutoff_time:
                age_hours = (time.time() - created_at) / 3600
                stale.append({
                    "plan_file": plan_data["plan_file"],
                    "age_hours": age_hours,
                    "metadata": plan_data.get("metadata", {}),
                    "session_id": plan_data.get("session_id")
                })
                
                self._log("WARN", f"Stale task detected: {plan_data['plan_file']} (age: {age_hours:.1f}h)")
        
        return stale
    
    def auto_fix_missing_plan(self, task_description: str, mode: str = "inline") -> Optional[str]:
        """
        Auto-create a plan file if missing.
        
        Returns path to created plan file or None if failed
        """
        try:
            from . import mcp_execution_tools
            
            # Create basic plan
            steps = [
                {"step": "Review task requirements", "status": "pending"},
                {"step": "Execute task", "status": "pending"},
                {"step": "Verify completion", "status": "pending"}
            ]
            
            plan_file = mcp_execution_tools.create_plan_file(
                task_description=task_description,
                steps=steps,
                mode=mode,
                estimated_time="30 min"
            )
            
            self._log("FIX", f"Auto-created missing plan file: {plan_file}")
            return plan_file
            
        except Exception as e:
            self._log("ERROR", f"Failed to auto-create plan: {e}")
            return None
    
    def auto_fix_stale_tasks(self, stale_tasks: List[Dict]) -> Dict[str, int]:
        """
        Auto-fix stale tasks by marking them for review.
        
        Returns count of fixed tasks
        """
        from .execution_lifecycle import get_lifecycle
        
        lifecycle = get_lifecycle()
        fixed = 0
        
        for task in stale_tasks:
            plan_file = task["plan_file"]
            age_hours = task["age_hours"]
            
            # Mark as stale (not failed, just needs review)
            lifecycle.update_plan_status(plan_file, "stale")
            
            self._log("FIX", f"Marked stale task for review: {plan_file} ({age_hours:.1f}h old)")
            fixed += 1
        
        return {"fixed": fixed}
    
    def run_diagnostics(self) -> Dict[str, Any]:
        """
        Run full diagnostics on execution patterns.
        
        Returns diagnostic report
        """
        from .execution_lifecycle import get_lifecycle
        
        lifecycle = get_lifecycle()
        
        # Get active plans
        active_plans = lifecycle.get_active_plans(max_age_hours=72)
        
        # Check each plan
        plan_issues = []
        for plan_data in active_plans:
            plan_file = plan_data["plan_file"]
            check_result = self.check_plan_file(plan_file)
            
            if check_result["issues"]:
                plan_issues.append({
                    "plan_file": plan_file,
                    "issues": check_result["issues"]
                })
        
        # Detect stale tasks
        stale = self.detect_stale_tasks(max_age_hours=48)
        
        # Generate report
        report = {
            "timestamp": datetime.now().isoformat(),
            "active_plans_count": len(active_plans),
            "plans_with_issues": len(plan_issues),
            "stale_tasks_count": len(stale),
            "issues": plan_issues,
            "stale_tasks": stale,
            "health_status": "healthy" if not plan_issues and not stale else "issues_detected"
        }
        
        self._log("DIAGNOSTIC", f"Ran diagnostics: {len(active_plans)} active, {len(plan_issues)} issues, {len(stale)} stale")
        
        return report
    
    def auto_repair(self) -> Dict[str, Any]:
        """
        Auto-repair detected issues.
        
        Returns repair summary
        """
        # Run diagnostics
        diagnostics = self.run_diagnostics()
        
        # Fix stale tasks
        stale_fixed = 0
        if diagnostics["stale_tasks"]:
            result = self.auto_fix_stale_tasks(diagnostics["stale_tasks"])
            stale_fixed = result["fixed"]
        
        # Note: Don't auto-recreate missing plan files - too risky
        # Just flag them for human review
        
        return {
            "diagnostics_run": True,
            "stale_tasks_fixed": stale_fixed,
            "issues_flagged": len(diagnostics["issues"]),
            "health_status": diagnostics["health_status"]
        }


# Global debug instance
_debug = None

def get_debug() -> ExecutionDebug:
    """Get global debug instance"""
    global _debug
    if _debug is None:
        _debug = ExecutionDebug()
    return _debug
