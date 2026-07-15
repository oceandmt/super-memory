"""
Task State Recovery Tool

Enables resuming interrupted tasks from plan files and checkpoints.
Addresses memory loss pattern: multi-turn task forgetting.

Usage:
    from task_recovery import TaskRecovery
    
    recovery = TaskRecovery()
    incomplete = recovery.find_incomplete_tasks()
    
    for task in incomplete:
        state = recovery.load_task_state(task['plan_file'])
        recovery.resume_from_step(state)
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class TaskRecovery:
    """Task state recovery and resumption system"""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.tmp_dir = self.workspace_root / ".openclaw" / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
    
    def find_incomplete_tasks(self, max_age_hours: int = 72) -> List[Dict]:
        """
        Find all incomplete tasks from plan files
        
        Args:
            max_age_hours: Only include tasks modified within this window
        
        Returns:
            List of incomplete task metadata
        """
        incomplete = []
        cutoff = datetime.now().timestamp() - (max_age_hours * 3600)
        
        # Search for plan files
        plan_files = list(self.tmp_dir.rglob("*-plan.md"))
        
        for plan_file in plan_files:
            # Skip old files
            if plan_file.stat().st_mtime < cutoff:
                continue
            
            # Parse plan file
            task_info = self._parse_plan_file(plan_file)
            
            # Check if incomplete
            if task_info["status"] not in ["completed", "failed"]:
                task_info["plan_file"] = str(plan_file)
                task_info["age_hours"] = (datetime.now().timestamp() - plan_file.stat().st_mtime) / 3600
                incomplete.append(task_info)
        
        # Sort by most recent first
        incomplete.sort(key=lambda x: x["age_hours"])
        
        return incomplete
    
    def load_task_state(self, plan_file: Path) -> Dict[str, Any]:
        """
        Load complete task state from plan file and checkpoints
        
        Args:
            plan_file: Path to task plan file
        
        Returns:
            Complete task state dictionary
        """
        if isinstance(plan_file, str):
            plan_file = Path(plan_file)
        
        if not plan_file.exists():
            raise FileNotFoundError(f"Plan file not found: {plan_file}")
        
        # Parse plan
        task_info = self._parse_plan_file(plan_file)
        
        # Load checkpoints
        run_dir = plan_file.parent
        checkpoint_files = sorted(run_dir.glob("*-checkpoint-*.md"))
        checkpoints = self._load_checkpoints(checkpoint_files)
        
        # Load deliverables
        deliverables = self._find_deliverables(run_dir)
        
        # Determine last completed step
        last_completed = self._find_last_completed_step(task_info, checkpoints)
        
        # Build resumable state
        state = {
            "task_id": task_info.get("task_id", plan_file.stem),
            "task_name": task_info["task_name"],
            "plan_file": str(plan_file),
            "run_dir": str(run_dir),
            "status": task_info["status"],
            "steps": task_info["steps"],
            "total_steps": len(task_info["steps"]),
            "last_completed_step": last_completed,
            "remaining_steps": task_info["steps"][last_completed:] if last_completed < len(task_info["steps"]) else [],
            "checkpoints": checkpoints,
            "deliverables": deliverables,
            "created_at": task_info.get("created_at"),
            "updated_at": task_info.get("updated_at")
        }
        
        return state
    
    def resume_from_step(self, task_state: Dict) -> str:
        """
        Generate resumption context from task state
        
        Args:
            task_state: Task state from load_task_state()
        
        Returns:
            Formatted resumption context for agent
        """
        context = f"""# Task Resumption: {task_state['task_name']}

## Current Status
- Task ID: {task_state['task_id']}
- Progress: Step {task_state['last_completed_step']}/{task_state['total_steps']} completed
- Status: {task_state['status']}
- Deliverables: {len(task_state['deliverables'])} created

## Completed Work
"""
        
        # Summarize completed steps
        for i, step in enumerate(task_state['steps'][:task_state['last_completed_step']], 1):
            context += f"{i}. ✓ {step}\n"
        
        # Add checkpoint summaries
        if task_state['checkpoints']:
            context += "\n## Recent Checkpoints\n"
            for cp in task_state['checkpoints'][-3:]:  # Last 3 checkpoints
                context += f"- Step {cp['step']}: {cp['summary'][:150]}...\n"
        
        # List deliverables
        if task_state['deliverables']:
            context += "\n## Deliverables Created\n"
            for deliverable in task_state['deliverables']:
                context += f"- {deliverable}\n"
        
        # Show remaining work
        context += f"\n## Remaining Steps ({len(task_state['remaining_steps'])})\n"
        start_idx = task_state['last_completed_step']
        for i, step in enumerate(task_state['remaining_steps'], start_idx + 1):
            context += f"{i}. {step}\n"
        
        # Add resumption instructions
        context += f"""
## Resumption Instructions
1. Review completed work in: {task_state['run_dir']}
2. Continue from Step {task_state['last_completed_step'] + 1}
3. Generate checkpoints at each step completion
4. Track deliverables as they are created
5. Update task status upon completion

**Next Action**: Begin Step {task_state['last_completed_step'] + 1}
"""
        
        return context
    
    def create_recovery_report(self) -> str:
        """
        Generate comprehensive recovery report for all incomplete tasks
        
        Returns:
            Markdown-formatted recovery report
        """
        incomplete = self.find_incomplete_tasks()
        
        report = f"""# Task Recovery Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- Total incomplete tasks: {len(incomplete)}
- Recoverable: {sum(1 for t in incomplete if t['status'] in ['running', 'stalled'])}
- Failed: {sum(1 for t in incomplete if t['status'] == 'failed')}

## Incomplete Tasks
"""
        
        for task in incomplete:
            report += f"""
### {task['task_name']}
- **Status**: {task['status']}
- **Age**: {task['age_hours']:.1f} hours
- **Progress**: Step {task['last_completed_step']}/{task['total_steps']}
- **Plan File**: `{task['plan_file']}`
- **Estimated Remaining**: {task['estimated_remaining']}

"""
        
        if not incomplete:
            report += "\n*No incomplete tasks found.*\n"
        
        return report
    
    def _parse_plan_file(self, plan_file: Path) -> Dict:
        """Parse plan file to extract task metadata and steps"""
        content = plan_file.read_text()
        
        # Extract task name
        task_name = "Unknown Task"
        name_match = re.search(r'^#\s+(.+?)(?:\n|$)', content, re.MULTILINE)
        if name_match:
            task_name = name_match.group(1).strip()
        
        # Extract steps
        steps = []
        step_pattern = r'^\d+\.\s+\*\*(.+?)\*\*'
        for match in re.finditer(step_pattern, content, re.MULTILINE):
            steps.append(match.group(1).strip())
        
        # Extract status markers
        status = "unknown"
        if re.search(r'\[x\]\s+All.*complete', content, re.IGNORECASE):
            status = "completed"
        elif re.search(r'FAILED|ERROR', content):
            status = "failed"
        elif re.search(r'in.progress|running', content, re.IGNORECASE):
            status = "running"
        else:
            # Infer from file age
            age_minutes = (datetime.now().timestamp() - plan_file.stat().st_mtime) / 60
            if age_minutes > 30:
                status = "stalled"
            else:
                status = "running"
        
        # Extract timestamps
        created_at = datetime.fromtimestamp(plan_file.stat().st_ctime).isoformat()
        updated_at = datetime.fromtimestamp(plan_file.stat().st_mtime).isoformat()
        
        # Count completed steps from checkboxes
        completed_count = len(re.findall(r'\[x\]', content, re.IGNORECASE))
        
        # Estimate remaining time
        estimated_remaining = "Unknown"
        duration_match = re.search(r'Estimated.*?:\s*(.+?)(?:\n|$)', content, re.IGNORECASE)
        if duration_match:
            estimated_remaining = duration_match.group(1).strip()
        
        return {
            "task_name": task_name,
            "status": status,
            "steps": steps,
            "total_steps": len(steps),
            "last_completed_step": completed_count,
            "created_at": created_at,
            "updated_at": updated_at,
            "estimated_remaining": estimated_remaining
        }
    
    def _load_checkpoints(self, checkpoint_files: List[Path]) -> List[Dict]:
        """Load checkpoint data from files"""
        checkpoints = []
        
        for cp_file in checkpoint_files:
            content = cp_file.read_text()
            
            # Extract step number
            step_match = re.search(r'checkpoint-(\d+)', cp_file.name)
            step_num = int(step_match.group(1)) if step_match else 0
            
            # Extract summary
            summary = ""
            summary_match = re.search(r'##\s*(?:Summary|Progress)\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
            if summary_match:
                summary = summary_match.group(1).strip()[:300]
            
            checkpoints.append({
                "step": step_num,
                "file": str(cp_file),
                "timestamp": datetime.fromtimestamp(cp_file.stat().st_mtime).isoformat(),
                "summary": summary
            })
        
        return sorted(checkpoints, key=lambda x: x["step"])
    
    def _find_deliverables(self, run_dir: Path) -> List[str]:
        """Find deliverable files in run directory"""
        deliverables = []
        
        patterns = ["*.py", "*.md", "*.json", "*.yaml", "*.yml", "*.sh", "*.txt"]
        
        for pattern in patterns:
            for file in run_dir.glob(pattern):
                # Skip plan and checkpoint files
                if "plan" in file.name or "checkpoint" in file.name:
                    continue
                deliverables.append(str(file.relative_to(run_dir)))
        
        return sorted(deliverables)
    
    def _find_last_completed_step(self, task_info: Dict, checkpoints: List[Dict]) -> int:
        """Determine the last completed step"""
        # Use checkpoint data if available
        if checkpoints:
            return max(cp["step"] for cp in checkpoints)
        
        # Fall back to task info
        return task_info.get("last_completed_step", 0)


# CLI interface
def main():
    """Command-line interface for task recovery"""
    import sys
    
    recovery = TaskRecovery()
    
    if len(sys.argv) < 2:
        print("Usage: python task-recovery.py <command> [args]")
        print("Commands:")
        print("  find              - Find incomplete tasks")
        print("  load <plan_file>  - Load task state")
        print("  resume <plan_file> - Generate resumption context")
        print("  report            - Generate recovery report")
        return
    
    command = sys.argv[1]
    
    if command == "find":
        incomplete = recovery.find_incomplete_tasks()
        print(json.dumps(incomplete, indent=2))
    
    elif command == "load":
        if len(sys.argv) < 3:
            print("Error: plan_file required")
            return
        
        plan_file = Path(sys.argv[2])
        state = recovery.load_task_state(plan_file)
        print(json.dumps(state, indent=2, default=str))
    
    elif command == "resume":
        if len(sys.argv) < 3:
            print("Error: plan_file required")
            return
        
        plan_file = Path(sys.argv[2])
        state = recovery.load_task_state(plan_file)
        context = recovery.resume_from_step(state)
        print(context)
    
    elif command == "report":
        report = recovery.create_recovery_report()
        print(report)
    
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
