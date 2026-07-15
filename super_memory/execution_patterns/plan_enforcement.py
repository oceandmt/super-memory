"""
Plan Enforcement

Automatically creates and maintains plan files for task execution.
Ensures task state persists beyond context window limitations.

Usage:
    from super_memory.execution_patterns import PlanEnforcer
    
    enforcer = PlanEnforcer()
    
    # Create plan file
    plan_file = enforcer.create_plan_file(
        task_description="Deep code analysis",
        steps=[
            {"step": "Read codebase", "status": "pending"},
            {"step": "Analyze patterns", "status": "pending"},
            {"step": "Generate report", "status": "pending"}
        ],
        mode="subagent",
        estimated_time="30 min"
    )
    
    # Update progress
    enforcer.update_progress(plan_file, step_index=0, status="completed")
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import json
import re


class PlanEnforcer:
    """Enforces plan file creation and maintenance"""
    
    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.tmp_dir = Path.home() / ".openclaw" / "tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
    
    def create_plan_file(
        self,
        task_description: str,
        steps: List[Dict[str, str]],
        mode: str = "inline",
        estimated_time: str = "unknown",
        session_id: Optional[str] = None
    ) -> Path:
        """
        Create a plan file for a task
        
        Args:
            task_description: Description of the task
            steps: List of step dicts with "step" and "status" keys
            mode: Execution mode (inline | subagent)
            estimated_time: Time estimate
            session_id: Optional session identifier
        
        Returns:
            Path to created plan file
        """
        # Generate task ID
        task_id = self._generate_task_id(task_description)
        
        # Create plan content
        content = self._render_plan_markdown(
            task_id=task_id,
            task_description=task_description,
            steps=steps,
            mode=mode,
            estimated_time=estimated_time,
            session_id=session_id
        )
        
        # Write plan file
        plan_file = self.tmp_dir / f"{task_id}-plan.md"
        plan_file.write_text(content)
        
        # Create metadata file
        metadata = {
            "task_id": task_id,
            "task_description": task_description,
            "mode": mode,
            "estimated_time": estimated_time,
            "total_steps": len(steps),
            "completed_steps": 0,
            "status": "in_progress",
            "created_at": datetime.now().isoformat(),
            "plan_file": str(plan_file),
            "session_id": session_id
        }
        
        metadata_file = self.tmp_dir / f"{task_id}-metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))
        
        return plan_file
    
    def _generate_task_id(self, task_description: str) -> str:
        """Generate task ID from description"""
        slug = re.sub(r'[^a-z0-9]+', '-', task_description.lower())
        slug = slug.strip('-')[:50]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        return f"{slug}-{timestamp}"
    
    def _render_plan_markdown(
        self,
        task_id: str,
        task_description: str,
        steps: List[Dict[str, str]],
        mode: str,
        estimated_time: str,
        session_id: Optional[str]
    ) -> str:
        """Render plan as markdown"""
        
        steps_md = "\n".join(
            f"{i+1}. [{s['status'].upper()}] {s['step']}"
            for i, s in enumerate(steps)
        )
        
        return f"""# Task Plan: {task_description}

**Task ID**: {task_id}  
**Mode**: {mode}  
**Estimated time**: {estimated_time}  
**Session ID**: {session_id or "N/A"}  
**Created**: {datetime.now().isoformat()}

---

## Steps

{steps_md}

---

## Progress

- Total steps: {len(steps)}
- Completed: 0
- Pending: {len(steps)}

---

## Status: IN_PROGRESS
"""
    
    def update_progress(
        self,
        plan_file: Path,
        step_index: int,
        status: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Update step status in plan file
        
        Args:
            plan_file: Path to plan file
            step_index: Index of step to update (0-based)
            status: New status (pending | in_progress | completed | failed)
            notes: Optional notes to append
        
        Returns:
            True if successful
        """
        if not plan_file.exists():
            return False
        
        content = plan_file.read_text()
        
        # Update step status in markdown
        lines = content.split('\n')
        updated = False
        
        for i, line in enumerate(lines):
            if line.startswith(f"{step_index + 1}. ["):
                # Update status
                match = re.match(r'(\d+\. )\[.+?\] (.+)', line)
                if match:
                    lines[i] = f"{match.group(1)}[{status.upper()}] {match.group(2)}"
                    updated = True
                    break
        
        if updated:
            # Update progress section
            completed = sum(1 for line in lines if '[COMPLETED]' in line)
            total = sum(1 for line in lines if re.match(r'\d+\. \[', line))
            
            for i, line in enumerate(lines):
                if line.startswith('- Completed:'):
                    lines[i] = f'- Completed: {completed}'
                elif line.startswith('- Pending:'):
                    lines[i] = f'- Pending: {total - completed}'
            
            # Add notes if provided
            if notes:
                lines.append(f"\n### Note ({datetime.now().strftime('%H:%M')})\n{notes}")
            
            # Write back
            plan_file.write_text('\n'.join(lines))
            
            # Update metadata
            task_id = plan_file.stem.replace('-plan', '')
            metadata_file = plan_file.parent / f"{task_id}-metadata.json"
            if metadata_file.exists():
                metadata = json.loads(metadata_file.read_text())
                metadata['completed_steps'] = completed
                metadata['updated_at'] = datetime.now().isoformat()
                if completed == total:
                    metadata['status'] = 'completed'
                metadata_file.write_text(json.dumps(metadata, indent=2))
        
        return updated
    
    def mark_complete(self, plan_file: Path, deliverables: List[str] = None) -> bool:
        """Mark plan as complete"""
        if not plan_file.exists():
            return False
        
        content = plan_file.read_text()
        
        # Update status
        content = content.replace('## Status: IN_PROGRESS', '## Status: COMPLETED')
        
        # Add completion section
        completion_section = f"""

---

## Completion

**Completed at**: {datetime.now().isoformat()}

"""
        
        if deliverables:
            completion_section += "**Deliverables**:\n"
            completion_section += "\n".join(f"- {d}" for d in deliverables)
        
        content += completion_section
        plan_file.write_text(content)
        
        # Update metadata
        task_id = plan_file.stem.replace('-plan', '')
        metadata_file = plan_file.parent / f"{task_id}-metadata.json"
        if metadata_file.exists():
            metadata = json.loads(metadata_file.read_text())
            metadata['status'] = 'completed'
            metadata['completed_at'] = datetime.now().isoformat()
            if deliverables:
                metadata['deliverables'] = deliverables
            metadata_file.write_text(json.dumps(metadata, indent=2))
        
        return True
