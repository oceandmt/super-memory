"""
Execution Patterns - Auto-Audit Module

Tracks execution pattern usage, effectiveness, and provides metrics.
"""

from typing import Dict, Any, List
from pathlib import Path
import json
import time
from datetime import datetime


class ExecutionAudit:
    """Audit execution pattern usage and effectiveness"""
    
    def __init__(self):
        self.audit_log_file = Path.home() / ".openclaw/tmp/execution-audit.log"
        self.metrics_file = Path.home() / ".openclaw/tmp/execution-metrics.json"
        self._ensure_files()
    
    def _ensure_files(self):
        """Ensure audit files exist"""
        self.audit_log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.audit_log_file.exists():
            self.audit_log_file.write_text("# Execution Patterns Audit Log\n")
        if not self.metrics_file.exists():
            self.metrics_file.write_text(json.dumps({
                "total_detections": 0,
                "auto_applied": 0,
                "successful_completions": 0,
                "failed_tasks": 0,
                "recovery_events": 0,
                "average_confidence": 0.0,
                "mode_distribution": {"inline": 0, "subagent": 0}
            }))
    
    def log_detection(self, detection: Dict, execution_state: Dict = None):
        """Log a task detection event"""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] DETECT: steps={detection['estimated_steps']}, " \
                f"duration={detection['estimated_duration_min']}min, " \
                f"confidence={detection['confidence']:.2f}, " \
                f"applied={'yes' if execution_state else 'no'}\n"
        
        try:
            with open(self.audit_log_file, 'a') as f:
                f.write(entry)
        except:
            pass
        
        # Update metrics
        self._update_metrics({
            "total_detections": 1,
            "auto_applied": 1 if execution_state else 0
        })
    
    def log_completion(self, plan_file: str, success: bool = True, duration_min: float = None):
        """Log task completion"""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] COMPLETE: plan={Path(plan_file).name}, " \
                f"success={success}, duration={duration_min}min\n"
        
        try:
            with open(self.audit_log_file, 'a') as f:
                f.write(entry)
        except:
            pass
        
        # Update metrics
        self._update_metrics({
            "successful_completions": 1 if success else 0,
            "failed_tasks": 0 if success else 1
        })
    
    def log_recovery(self, plan_file: str, recovered: bool = True):
        """Log task recovery event"""
        timestamp = datetime.now().isoformat()
        entry = f"[{timestamp}] RECOVERY: plan={Path(plan_file).name}, " \
                f"recovered={recovered}\n"
        
        try:
            with open(self.audit_log_file, 'a') as f:
                f.write(entry)
        except:
            pass
        
        # Update metrics
        if recovered:
            self._update_metrics({"recovery_events": 1})
    
    def _update_metrics(self, updates: Dict):
        """Update metrics file"""
        try:
            metrics = json.loads(self.metrics_file.read_text())
            for key, value in updates.items():
                if key in metrics:
                    metrics[key] += value
            self.metrics_file.write_text(json.dumps(metrics, indent=2))
        except:
            pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        try:
            return json.loads(self.metrics_file.read_text())
        except:
            return {}
    
    def get_recent_events(self, limit: int = 50) -> List[str]:
        """Get recent audit events"""
        try:
            with open(self.audit_log_file, 'r') as f:
                lines = f.readlines()
                return lines[-limit:]
        except:
            return []
    
    def generate_report(self) -> str:
        """Generate audit report"""
        metrics = self.get_metrics()
        recent = self.get_recent_events(20)
        
        report = [
            "=" * 70,
            "Execution Patterns Audit Report",
            "=" * 70,
            "",
            "Metrics:",
            f"  Total detections: {metrics.get('total_detections', 0)}",
            f"  Auto-applied: {metrics.get('auto_applied', 0)}",
            f"  Successful completions: {metrics.get('successful_completions', 0)}",
            f"  Failed tasks: {metrics.get('failed_tasks', 0)}",
            f"  Recovery events: {metrics.get('recovery_events', 0)}",
            "",
            "Success Rate:",
            f"  {self._calculate_success_rate(metrics):.1f}%",
            "",
            "Recent Events (last 20):",
        ]
        
        for event in recent:
            report.append(f"  {event.strip()}")
        
        report.append("")
        report.append("=" * 70)
        
        return "\n".join(report)
    
    def _calculate_success_rate(self, metrics: Dict) -> float:
        """Calculate success rate"""
        completed = metrics.get('successful_completions', 0)
        failed = metrics.get('failed_tasks', 0)
        total = completed + failed
        
        if total == 0:
            return 0.0
        
        return (completed / total) * 100


# Global audit instance
_audit = None

def get_audit() -> ExecutionAudit:
    """Get global audit instance"""
    global _audit
    if _audit is None:
        _audit = ExecutionAudit()
    return _audit
