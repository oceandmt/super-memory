"""Evals package — benchmark, curriculum, and quality assessment for Super Memory.

P0:
- recall_cases.py: recall case management

P2:
- curriculum.py: self-education curriculum — analyze failures, generate training cases + tests
"""

from . import curriculum as curriculum_mod

run_curriculum = curriculum_mod.run_curriculum
run_benchmarks = curriculum_mod.run_benchmarks
analyze_feedback_patterns = curriculum_mod.analyze_feedback_patterns
