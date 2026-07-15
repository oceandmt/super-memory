"""
Execution Contract

Declares task execution parameters before starting work.
Prevents the "announce but don't execute" anti-pattern.

Usage:
    from super_memory.execution_patterns import ExecutionContract
    
    contract = ExecutionContract(
        task="Deep compare super-memory vs basement repos",
        mode="subagent",
        steps=11,
        estimated_time="30-45 min",
        checkpoints=["After each repo analysis"],
        auto_continue=True
    )
    
    # Write contract file
    contract_file = contract.write_to_file()
    
    # Later: verify contract was followed
    contract.verify_completion()
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Literal
import json

@dataclass
class ExecutionContract:
    """Execution contract data structure"""
    
    task: str
    mode: Literal["inline", "subagent"]
    steps: int
    estimated_time: str
    checkpoints: List[str]
    auto_continue: bool
    
    # Auto-populated fields
    created_at: Optional[str] = None
    task_id: Optional[str] = None
    contract_file: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.task_id is None:
            self.task_id = self._generate_task_id()
    
    def _generate_task_id(self) -> str:
        """Generate task ID from task name and timestamp"""
        import re
        slug = re.sub(r'[^a-z0-9]+', '-', self.task.lower())
        slug = slug.strip('-')[:50]
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        return f"{slug}-{timestamp}"
    
    def write_to_file(self, output_dir: Optional[Path] = None) -> Path:
        """
        Write contract to markdown file
        
        Args:
            output_dir: Directory to write to (default: .openclaw/tmp)
        
        Returns:
            Path to contract file
        """
        if output_dir is None:
            output_dir = Path.home() / ".openclaw" / "tmp"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{self.task_id}-contract.md"
        contract_file = output_dir / filename
        
        content = self._render_markdown()
        contract_file.write_text(content)
        
        self.contract_file = str(contract_file)
        return contract_file
    
    def _render_markdown(self) -> str:
        """Render contract as markdown"""
        return f"""# Execution Contract

**Task ID**: {self.task_id}  
**Created**: {self.created_at}

---

## Contract Declaration

**Task**: {self.task}  
**Mode**: {self.mode}  
**Estimated steps**: {self.steps}  
**Estimated time**: {self.estimated_time}  
**Auto-continue**: {"YES" if self.auto_continue else "NO"}

---

## Checkpoints

{self._render_checkpoints()}

---

## Progress Tracking

**Contract file**: {self.contract_file or "TBD"}  
**Status**: Not started

---

## Success Criteria

- [ ] All {self.steps} steps completed
- [ ] All checkpoints reached
- [ ] Deliverables created

---

**Contract signed**: {self.created_at}
"""
    
    def _render_checkpoints(self) -> str:
        """Render checkpoint list"""
        if not self.checkpoints:
            return "- No specific checkpoints defined"
        return "\n".join(f"- {cp}" for cp in self.checkpoints)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionContract":
        """Create from dictionary"""
        return cls(**data)
    
    @classmethod
    def from_file(cls, contract_file: Path) -> "ExecutionContract":
        """Load contract from markdown file"""
        # Parse markdown to extract contract fields
        content = contract_file.read_text()
        
        # Simple parsing (could be improved)
        import re
        
        task_match = re.search(r'\*\*Task\*\*: (.+)', content)
        mode_match = re.search(r'\*\*Mode\*\*: (\w+)', content)
        steps_match = re.search(r'\*\*Estimated steps\*\*: (\d+)', content)
        time_match = re.search(r'\*\*Estimated time\*\*: (.+)', content)
        
        return cls(
            task=task_match.group(1) if task_match else "Unknown",
            mode=mode_match.group(1) if mode_match else "inline",
            steps=int(steps_match.group(1)) if steps_match else 0,
            estimated_time=time_match.group(1) if time_match else "Unknown",
            checkpoints=[],
            auto_continue=True,
            contract_file=str(contract_file)
        )
    
    def verify_completion(self) -> dict:
        """
        Verify contract completion
        
        Returns:
            Verification result with status and details
        """
        if not self.contract_file:
            return {
                "status": "error",
                "message": "Contract file not set"
            }
        
        contract_path = Path(self.contract_file)
        if not contract_path.exists():
            return {
                "status": "error",
                "message": "Contract file not found"
            }
        
        # Look for plan file
        plan_file = contract_path.parent / f"{self.task_id}-plan.md"
        plan_exists = plan_file.exists()
        
        # Look for checkpoint files
        checkpoint_files = list(contract_path.parent.glob(f"{self.task_id}-checkpoint-*.md"))
        checkpoint_count = len(checkpoint_files)
        
        # Look for completion marker
        completion_file = contract_path.parent / f"{self.task_id}-complete.md"
        is_complete = completion_file.exists()
        
        return {
            "status": "complete" if is_complete else "in_progress",
            "task_id": self.task_id,
            "contract_file": str(contract_path),
            "plan_exists": plan_exists,
            "checkpoints_found": checkpoint_count,
            "checkpoints_expected": len(self.checkpoints),
            "is_complete": is_complete,
            "verification_time": datetime.now().isoformat()
        }


# Convenience function
def create_contract(
    task: str,
    mode: str = "inline",
    steps: int = 1,
    estimated_time: str = "unknown",
    checkpoints: Optional[List[str]] = None,
    auto_continue: bool = True,
    write_file: bool = True
) -> ExecutionContract:
    """
    Create execution contract (convenience function)
    
    Args:
        task: Task description
        mode: Execution mode (inline | subagent)
        steps: Estimated number of steps
        estimated_time: Time estimate
        checkpoints: List of checkpoint descriptions
        auto_continue: Whether to continue autonomously
        write_file: Whether to write contract file immediately
    
    Returns:
        ExecutionContract instance
    """
    contract = ExecutionContract(
        task=task,
        mode=mode,
        steps=steps,
        estimated_time=estimated_time,
        checkpoints=checkpoints or [],
        auto_continue=auto_continue
    )
    
    if write_file:
        contract.write_to_file()
    
    return contract
