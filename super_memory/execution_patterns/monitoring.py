"""
Memory Loss Detector

Real-time detection of memory loss patterns during task execution.
Monitors context window usage, task state persistence, and subagent visibility.

Usage:
    from memory_loss_detector import MemoryLossDetector
    
    detector = MemoryLossDetector()
    detector.start_monitoring(task_id)
    
    # During execution
    if detector.check_memory_loss():
        alert = detector.get_alert()
        print(alert['message'])
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict


@dataclass
class MemoryLossAlert:
    """Memory loss alert data structure"""
    alert_id: str
    timestamp: str
    severity: str  # low | medium | high | critical
    pattern: str
    task_id: Optional[str]
    description: str
    indicators: Dict[str, Any]
    recommendations: List[str]


class MemoryLossDetector:
    """Real-time memory loss pattern detector"""
    
    def __init__(self):
        self.tmp_dir = Path(".openclaw/tmp")
        self.task_registry = self.tmp_dir / "task_registry.json"
        self.memory_log = self.tmp_dir / "task_memory_log.jsonl"
        self.alerts_log = self.tmp_dir / "memory_loss_alerts.jsonl"
        self.monitoring_state = self.tmp_dir / "memory_monitoring_state.json"
        
        self.active_monitors: Dict[str, Dict] = {}
        self.alert_thresholds = self._default_thresholds()
    
    def _default_thresholds(self) -> Dict[str, Any]:
        """Default detection thresholds"""
        return {
            "context_window_usage": 0.80,  # Alert at 80% usage
            "max_silent_duration_minutes": 30,
            "min_checkpoint_frequency": 0.2,  # At least 20% of steps
            "max_progress_stall_minutes": 15,
            "subagent_visibility_timeout_minutes": 10
        }
    
    def start_monitoring(self, task_id: str, task_metadata: Optional[Dict] = None):
        """
        Start monitoring a task for memory loss patterns
        
        Args:
            task_id: Task identifier
            task_metadata: Optional task metadata
        """
        self.active_monitors[task_id] = {
            "task_id": task_id,
            "started_at": datetime.now().isoformat(),
            "last_checkpoint": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "checkpoint_count": 0,
            "alert_count": 0,
            "metadata": task_metadata or {}
        }
        
        self._save_monitoring_state()
    
    def stop_monitoring(self, task_id: str):
        """Stop monitoring a task"""
        if task_id in self.active_monitors:
            del self.active_monitors[task_id]
            self._save_monitoring_state()
    
    def check_memory_loss(self, task_id: Optional[str] = None) -> List[MemoryLossAlert]:
        """
        Check for memory loss patterns
        
        Args:
            task_id: Optional specific task ID to check (checks all if None)
        
        Returns:
            List of memory loss alerts
        """
        alerts = []
        
        tasks_to_check = [task_id] if task_id else list(self.active_monitors.keys())
        
        for tid in tasks_to_check:
            if tid not in self.active_monitors:
                continue
            
            # Pattern 1: Context window pressure
            context_alert = self._check_context_window_pressure(tid)
            if context_alert:
                alerts.append(context_alert)
            
            # Pattern 2: Silent execution (no activity)
            silent_alert = self._check_silent_execution(tid)
            if silent_alert:
                alerts.append(silent_alert)
            
            # Pattern 3: Checkpoint gap
            checkpoint_alert = self._check_checkpoint_gap(tid)
            if checkpoint_alert:
                alerts.append(checkpoint_alert)
            
            # Pattern 4: Progress stall
            stall_alert = self._check_progress_stall(tid)
            if stall_alert:
                alerts.append(stall_alert)
            
            # Pattern 5: Subagent visibility loss
            subagent_alert = self._check_subagent_visibility(tid)
            if subagent_alert:
                alerts.append(subagent_alert)
            
            # Pattern 6: Task state persistence failure
            persistence_alert = self._check_state_persistence(tid)
            if persistence_alert:
                alerts.append(persistence_alert)
        
        # Save alerts
        for alert in alerts:
            self._save_alert(alert)
        
        return alerts
    
    def _check_context_window_pressure(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect context window pressure pattern"""
        # Estimate context usage from task complexity
        task_data = self._load_task(task_id)
        
        if not task_data:
            return None
        
        # Heuristics for context pressure
        estimated_steps = task_data.get("estimated_steps", 0)
        current_step = task_data.get("current_step", 0)
        deliverables = len(task_data.get("deliverables", []))
        
        # Calculate complexity score
        complexity_score = (estimated_steps * 2 + deliverables * 5 + current_step * 3) / 100
        
        if complexity_score > 0.8:
            return MemoryLossAlert(
                alert_id=f"ctx-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="high" if complexity_score > 0.9 else "medium",
                pattern="context_window_pressure",
                task_id=task_id,
                description=f"High context window pressure detected (complexity score: {complexity_score:.2f})",
                indicators={
                    "complexity_score": complexity_score,
                    "estimated_steps": estimated_steps,
                    "current_step": current_step,
                    "deliverables_count": deliverables
                },
                recommendations=[
                    "Create checkpoints to preserve state",
                    "Break task into smaller subtasks",
                    "Use Super Memory to offload context",
                    "Generate intermediate summary"
                ]
            )
        
        return None
    
    def _check_silent_execution(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect silent execution pattern (no activity)"""
        monitor = self.active_monitors.get(task_id)
        
        if not monitor:
            return None
        
        last_activity = datetime.fromisoformat(monitor["last_activity"])
        silent_duration = (datetime.now() - last_activity).total_seconds() / 60
        
        threshold = self.alert_thresholds["max_silent_duration_minutes"]
        
        if silent_duration > threshold:
            return MemoryLossAlert(
                alert_id=f"silent-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="high",
                pattern="silent_execution",
                task_id=task_id,
                description=f"No activity detected for {silent_duration:.1f} minutes",
                indicators={
                    "silent_duration_minutes": silent_duration,
                    "last_activity": monitor["last_activity"],
                    "threshold_minutes": threshold
                },
                recommendations=[
                    "Check if task is stalled",
                    "Review last checkpoint for clues",
                    "Verify execution environment is responsive",
                    "Consider restarting task"
                ]
            )
        
        return None
    
    def _check_checkpoint_gap(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect checkpoint generation gaps"""
        task_data = self._load_task(task_id)
        
        if not task_data:
            return None
        
        current_step = task_data.get("current_step", 0)
        estimated_steps = task_data.get("estimated_steps", 1)
        
        # Count actual checkpoints
        plan_file = Path(task_data.get("plan_file", ""))
        checkpoint_count = 0
        
        if plan_file.exists():
            run_dir = plan_file.parent
            checkpoint_count = len(list(run_dir.glob("*-checkpoint-*.md")))
        
        # Calculate checkpoint frequency
        checkpoint_frequency = checkpoint_count / estimated_steps if estimated_steps > 0 else 0
        threshold = self.alert_thresholds["min_checkpoint_frequency"]
        
        if current_step > 2 and checkpoint_frequency < threshold:
            return MemoryLossAlert(
                alert_id=f"ckpt-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="medium",
                pattern="checkpoint_gap",
                task_id=task_id,
                description=f"Low checkpoint frequency: {checkpoint_frequency:.1%}",
                indicators={
                    "checkpoint_count": checkpoint_count,
                    "current_step": current_step,
                    "estimated_steps": estimated_steps,
                    "checkpoint_frequency": checkpoint_frequency,
                    "threshold": threshold
                },
                recommendations=[
                    "Generate checkpoint for current progress",
                    "Ensure track_checkpoint() is being called",
                    "Increase checkpoint frequency",
                    "Verify checkpoint storage is working"
                ]
            )
        
        return None
    
    def _check_progress_stall(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect progress stall pattern"""
        task_data = self._load_task(task_id)
        
        if not task_data:
            return None
        
        updated_at = datetime.fromisoformat(task_data.get("updated_at", datetime.now().isoformat()))
        stall_duration = (datetime.now() - updated_at).total_seconds() / 60
        
        threshold = self.alert_thresholds["max_progress_stall_minutes"]
        current_step = task_data.get("current_step", 0)
        
        if stall_duration > threshold and current_step > 0:
            return MemoryLossAlert(
                alert_id=f"stall-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="high",
                pattern="progress_stall",
                task_id=task_id,
                description=f"Progress stalled at step {current_step} for {stall_duration:.1f} minutes",
                indicators={
                    "stall_duration_minutes": stall_duration,
                    "current_step": current_step,
                    "last_updated": task_data.get("updated_at"),
                    "threshold_minutes": threshold
                },
                recommendations=[
                    "Investigate what's blocking progress",
                    "Check for resource contention",
                    "Review step execution logic",
                    "Consider manual intervention"
                ]
            )
        
        return None
    
    def _check_subagent_visibility(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect subagent visibility loss"""
        task_data = self._load_task(task_id)
        
        if not task_data:
            return None
        
        # Only check for subagent tasks
        if task_data.get("execution_mode") != "subagent":
            return None
        
        parent_task_id = task_data.get("parent_task_id")
        
        if not parent_task_id:
            return MemoryLossAlert(
                alert_id=f"subvis-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="medium",
                pattern="subagent_visibility_loss",
                task_id=task_id,
                description="Subagent task has no parent task ID (orphaned)",
                indicators={
                    "execution_mode": "subagent",
                    "parent_task_id": None
                },
                recommendations=[
                    "Link subagent to parent task",
                    "Ensure parent can track subagent progress",
                    "Use SubagentMonitor for visibility"
                ]
            )
        
        # Check if parent can see subagent progress
        updated_at = datetime.fromisoformat(task_data.get("updated_at", datetime.now().isoformat()))
        age_minutes = (datetime.now() - updated_at).total_seconds() / 60
        
        threshold = self.alert_thresholds["subagent_visibility_timeout_minutes"]
        
        if age_minutes > threshold:
            return MemoryLossAlert(
                alert_id=f"subvis-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="medium",
                pattern="subagent_visibility_loss",
                task_id=task_id,
                description=f"Subagent progress not visible to parent for {age_minutes:.1f} minutes",
                indicators={
                    "age_minutes": age_minutes,
                    "parent_task_id": parent_task_id,
                    "threshold_minutes": threshold
                },
                recommendations=[
                    "Verify subagent status reporting",
                    "Check parent-child communication",
                    "Use SubagentMonitor.get_status()"
                ]
            )
        
        return None
    
    def _check_state_persistence(self, task_id: str) -> Optional[MemoryLossAlert]:
        """Detect task state persistence failures"""
        # Check if task state is being saved to registry
        task_data = self._load_task(task_id)
        
        if not task_data:
            return MemoryLossAlert(
                alert_id=f"persist-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="critical",
                pattern="state_persistence_failure",
                task_id=task_id,
                description="Task not found in registry (state not persisted)",
                indicators={
                    "registry_exists": self.task_registry.exists(),
                    "task_found": False
                },
                recommendations=[
                    "Initialize task with track_task_start()",
                    "Verify registry file permissions",
                    "Check for file system errors"
                ]
            )
        
        # Check if memory events are being logged
        memory_events = self._count_memory_events(task_id)
        
        if memory_events == 0 and task_data.get("current_step", 0) > 0:
            return MemoryLossAlert(
                alert_id=f"persist-{task_id}-{int(time.time())}",
                timestamp=datetime.now().isoformat(),
                severity="high",
                pattern="state_persistence_failure",
                task_id=task_id,
                description="No memory events logged despite task progress",
                indicators={
                    "memory_events": 0,
                    "current_step": task_data.get("current_step", 0)
                },
                recommendations=[
                    "Ensure track_checkpoint() is being called",
                    "Verify memory log write permissions",
                    "Check Super Memory integration"
                ]
            )
        
        return None
    
    def update_activity(self, task_id: str, activity_type: str = "generic"):
        """
        Update last activity timestamp for a task
        
        Args:
            task_id: Task identifier
            activity_type: Type of activity (checkpoint, progress, etc.)
        """
        if task_id in self.active_monitors:
            self.active_monitors[task_id]["last_activity"] = datetime.now().isoformat()
            
            if activity_type == "checkpoint":
                self.active_monitors[task_id]["checkpoint_count"] += 1
                self.active_monitors[task_id]["last_checkpoint"] = datetime.now().isoformat()
            
            self._save_monitoring_state()
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get summary of current monitoring state"""
        return {
            "active_monitors": len(self.active_monitors),
            "tasks": list(self.active_monitors.keys()),
            "alert_counts": {
                tid: monitor["alert_count"]
                for tid, monitor in self.active_monitors.items()
            }
        }
    
    def generate_alert_report(self, alerts: List[MemoryLossAlert]) -> str:
        """Generate human-readable alert report"""
        if not alerts:
            return "# Memory Loss Detection Report\n\nNo memory loss patterns detected.\n"
        
        report = f"""# Memory Loss Detection Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Total Alerts**: {len(alerts)}
- **Critical**: {sum(1 for a in alerts if a.severity == 'critical')}
- **High**: {sum(1 for a in alerts if a.severity == 'high')}
- **Medium**: {sum(1 for a in alerts if a.severity == 'medium')}
- **Low**: {sum(1 for a in alerts if a.severity == 'low')}

## Alerts

"""
        
        for alert in alerts:
            severity_icon = {
                "critical": "🚨",
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"
            }.get(alert.severity, "⚪")
            
            report += f"### {severity_icon} {alert.pattern.replace('_', ' ').title()}\n"
            report += f"- **Task**: {alert.task_id}\n"
            report += f"- **Severity**: {alert.severity}\n"
            report += f"- **Description**: {alert.description}\n"
            report += f"- **Time**: {alert.timestamp}\n\n"
            
            report += "**Indicators**:\n"
            for key, value in alert.indicators.items():
                report += f"  - {key}: {value}\n"
            
            report += "\n**Recommendations**:\n"
            for i, rec in enumerate(alert.recommendations, 1):
                report += f"  {i}. {rec}\n"
            
            report += "\n"
        
        return report
    
    def _load_task(self, task_id: str) -> Optional[Dict]:
        """Load task data from registry"""
        if not self.task_registry.exists():
            return None
        
        try:
            registry = json.loads(self.task_registry.read_text())
            return registry.get("tasks", {}).get(task_id)
        except:
            return None
    
    def _count_memory_events(self, task_id: str) -> int:
        """Count memory events for a task"""
        if not self.memory_log.exists():
            return 0
        
        count = 0
        with self.memory_log.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if task_id in data.get("tags", []):
                        count += 1
                except:
                    pass
        
        return count
    
    def _save_alert(self, alert: MemoryLossAlert):
        """Save alert to log"""
        self.alerts_log.parent.mkdir(parents=True, exist_ok=True)
        
        with self.alerts_log.open("a") as f:
            f.write(json.dumps(asdict(alert)) + "\n")
        
        # Update monitor alert count
        if alert.task_id and alert.task_id in self.active_monitors:
            self.active_monitors[alert.task_id]["alert_count"] += 1
    
    def _save_monitoring_state(self):
        """Save monitoring state to disk"""
        self.monitoring_state.parent.mkdir(parents=True, exist_ok=True)
        self.monitoring_state.write_text(json.dumps(self.active_monitors, indent=2))
    
    def _load_monitoring_state(self):
        """Load monitoring state from disk"""
        if self.monitoring_state.exists():
            self.active_monitors = json.loads(self.monitoring_state.read_text())


# CLI interface
def main():
    """Command-line interface for memory loss detector"""
    import sys
    
    detector = MemoryLossDetector()
    
    if len(sys.argv) < 2:
        print("Usage: python memory-loss-detector.py <command> [args]")
        print("Commands:")
        print("  check [task_id]    - Check for memory loss patterns")
        print("  monitor <task_id>  - Start monitoring a task")
        print("  stop <task_id>     - Stop monitoring a task")
        print("  summary            - Get monitoring summary")
        return
    
    command = sys.argv[1]
    
    if command == "check":
        task_id = sys.argv[2] if len(sys.argv) > 2 else None
        alerts = detector.check_memory_loss(task_id)
        
        if alerts:
            report = detector.generate_alert_report(alerts)
            print(report)
        else:
            print("No memory loss patterns detected")
    
    elif command == "monitor":
        if len(sys.argv) < 3:
            print("Error: task_id required")
            return
        
        task_id = sys.argv[2]
        detector.start_monitoring(task_id)
        print(f"Started monitoring task: {task_id}")
    
    elif command == "stop":
        if len(sys.argv) < 3:
            print("Error: task_id required")
            return
        
        task_id = sys.argv[2]
        detector.stop_monitoring(task_id)
        print(f"Stopped monitoring task: {task_id}")
    
    elif command == "summary":
        summary = detector.get_monitoring_summary()
        print(json.dumps(summary, indent=2))
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
