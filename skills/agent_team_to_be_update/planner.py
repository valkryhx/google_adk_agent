#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Team Task Queue System - LLM-Assisted Task Planner

This module provides the TaskPlanner class that orchestrates task planning
by combining dependency analysis with task queue management. It computes
execution waves for parallel task execution using topological sorting.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Set, Any, Optional, Tuple
from collections import defaultdict, deque

try:
    from .models import Task
    from .task_queue import TaskQueue
    from .dependency_analyzer import TaskDependencyAnalyzer
except ImportError:
    from models import Task
    from task_queue import TaskQueue
    from dependency_analyzer import TaskDependencyAnalyzer


@dataclass
class PlanResult:
    """Result of task planning operation.
    
    Contains the complete plan with tasks organized into execution waves
    for parallel processing, along with a summary of the plan.
    """
    tasks: List[Task] = field(default_factory=list)
    waves: List[List[str]] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert plan result to dictionary representation."""
        return {
            "tasks": [task.to_json() for task in self.tasks],
            "waves": self.waves,
            "summary": self.summary
        }
    
    def get_wave_count(self) -> int:
        """Get the total number of execution waves."""
        return len(self.waves)
    
    def get_tasks_in_wave(self, wave_index: int) -> List[Task]:
        """Get all tasks in a specific wave.
        
        Args:
            wave_index: Index of the wave (0-based)
            
        Returns:
            List of Task objects in that wave
        """
        if wave_index < 0 or wave_index >= len(self.waves):
            return []
        task_ids = self.waves[wave_index]
        return [t for t in self.tasks if t.id in task_ids]
    
    def get_parallelizable_tasks(self) -> List[List[str]]:
        """Get tasks grouped by execution waves for parallel execution.
        
        Returns:
            List of waves, where each wave is a list of task IDs that can
            be executed in parallel.
        """
        return self.waves


class TaskPlanner:
    """LLM-assisted task planner with dependency management.
    
    Orchestrates the complete task planning workflow:
    1. Analyzes user requests to break them into atomic tasks
    2. Creates tasks in the task queue
    3. Computes execution waves using topological sort
    4. Provides plan summary and execution guidance
    """
    
    def __init__(
        self,
        team_id: str,
        base_dir: str,
        llm_client=None
    ):
        """Initialize the task planner.
        
        Args:
            team_id: Unique identifier for the team/session
            base_dir: Base directory for task queue storage
            llm_client: Optional LLM client for dependency analysis
        """
        self.team_id = team_id
        self.base_dir = base_dir
        self.task_queue = TaskQueue(team_id, base_dir)
        self.dependency_analyzer = TaskDependencyAnalyzer(llm_client)
    
    def plan(self, user_request: str) -> PlanResult:
        """Main entry point for task planning.
        
        Analyzes a user request, creates tasks in the queue, and computes
        execution waves for parallel processing.
        
        Args:
            user_request: The user's complex request describing work to be done
            
        Returns:
            PlanResult containing tasks, execution waves, and summary
        """
        # Step 1: Analyze the request and get task definitions
        task_definitions = self.dependency_analyzer.analyze(user_request)
        
        # Step 2: Create tasks in the queue
        created_tasks = self._create_tasks_from_definitions(task_definitions)
        
        # Step 3: Compute execution waves using topological sort
        waves = self._compute_waves(created_tasks)
        
        # Step 4: Generate summary
        summary = self._generate_summary(created_tasks, waves, user_request)
        
        return PlanResult(
            tasks=created_tasks,
            waves=waves,
            summary=summary
        )
    
    def _create_tasks_from_definitions(
        self,
        task_definitions: List[Dict[str, Any]]
    ) -> List[Task]:
        """Create Task objects from analyzed definitions and store in queue.
        
        Args:
            task_definitions: List of task definition dictionaries from analyzer
            
        Returns:
            List of created Task objects
        """
        created_tasks = []
        
        for definition in task_definitions:
            task = self.task_queue.create_task(
                name=definition.get("name", "Unnamed Task"),
                description=definition.get("description", ""),
                blocked_by=definition.get("blockedBy", []),
                expected_artifacts=definition.get("expectedArtifacts", []),
                writable_files=definition.get("writableFiles", []),
                read_only_files=definition.get("readOnlyFiles", []),
                verification_commands=definition.get("verificationCommands", [])
            )
            
            # Override the auto-generated ID with the planned ID if provided
            planned_id = definition.get("id")
            if planned_id and planned_id != task.id:
                # Update task ID while preserving other properties
                old_id = task.id
                task.id = planned_id
                
                # Save with new ID
                self.task_queue._save_task(task)
                
                # Delete old task file
                old_path = self.task_queue._get_task_path(old_id)
                if os.path.exists(old_path):
                    os.remove(old_path)
                
                # Update references in other tasks' blocked_by lists
                self._update_task_references(old_id, planned_id)
            
            created_tasks.append(task)
        
        return created_tasks
    
    def _update_task_references(self, old_id: str, new_id: str):
        """Update task ID references in all tasks' dependency lists.
        
        Args:
            old_id: The old task ID to replace
            new_id: The new task ID to use
        """
        for task in self.task_queue.list_tasks():
            updated = False
            if old_id in task.blocked_by:
                task.blocked_by = [
                    new_id if dep_id == old_id else dep_id
                    for dep_id in task.blocked_by
                ]
                updated = True
            if old_id in task.blocks:
                task.blocks = [
                    new_id if dep_id == old_id else dep_id
                    for dep_id in task.blocks
                ]
                updated = True
            if updated:
                self.task_queue._save_task(task)
    
    def _compute_waves(self, tasks: List[Task]) -> List[List[str]]:
        """Compute execution waves using topological sort.
        
        Groups tasks into waves where each wave contains tasks that can
        be executed in parallel (no dependencies within the wave).
        
        Args:
            tasks: List of all tasks to organize
            
        Returns:
            List of waves, where each wave is a list of task IDs
        """
        if not tasks:
            return []
        
        # Build dependency graph
        task_ids = {t.id for t in tasks}
        in_degree: Dict[str, int] = defaultdict(int)
        dependents: Dict[str, Set[str]] = defaultdict(set)
        
        # Initialize all tasks with in_degree 0
        for task in tasks:
            in_degree[task.id] = 0
        
        # Build graph edges
        for task in tasks:
            for dep_id in task.blocked_by:
                if dep_id in task_ids:  # Only consider dependencies within this plan
                    in_degree[task.id] += 1
                    dependents[dep_id].add(task.id)
        
        # Kahn's algorithm for topological sort with wave grouping
        waves: List[List[str]] = []
        
        # Start with tasks that have no dependencies
        current_wave = [
            task_id for task_id, degree in in_degree.items()
            if degree == 0
        ]
        
        while current_wave:
            waves.append(current_wave)
            next_wave = []
            
            for task_id in current_wave:
                # Reduce in-degree for all dependent tasks
                for dependent_id in dependents[task_id]:
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        next_wave.append(dependent_id)
            
            current_wave = next_wave
        
        # Check for cycles (tasks remaining with in_degree > 0)
        remaining = [tid for tid, degree in in_degree.items() if degree > 0]
        if remaining:
            # Add remaining tasks as a final wave (cycle detected)
            # In practice, this shouldn't happen with valid dependencies
            waves.append(remaining)
        
        return waves
    
    def _generate_summary(
        self,
        tasks: List[Task],
        waves: List[List[str]],
        original_request: str
    ) -> Dict[str, Any]:
        """Generate a summary of the plan.
        
        Args:
            tasks: All tasks in the plan
            waves: Execution waves
            original_request: The original user request
            
        Returns:
            Dictionary with summary statistics and information
        """
        total_tasks = len(tasks)
        total_waves = len(waves)
        
        # Calculate parallelization metrics
        tasks_per_wave = [len(wave) for wave in waves]
        max_parallel = max(tasks_per_wave) if tasks_per_wave else 0
        avg_parallel = sum(tasks_per_wave) / len(tasks_per_wave) if tasks_per_wave else 0
        
        # Count tasks by dependency status
        tasks_with_deps = len([t for t in tasks if t.blocked_by])
        tasks_without_deps = total_tasks - tasks_with_deps
        
        # Calculate critical path length (longest dependency chain)
        critical_path_length = self._calculate_critical_path_length(tasks)
        
        return {
            "originalRequest": original_request,
            "totalTasks": total_tasks,
            "totalWaves": total_waves,
            "tasksWithDependencies": tasks_with_deps,
            "tasksWithoutDependencies": tasks_without_deps,
            "maxParallelTasks": max_parallel,
            "averageParallelTasks": round(avg_parallel, 2),
            "criticalPathLength": critical_path_length,
            "tasksPerWave": tasks_per_wave,
            "estimatedEfficiency": round(
                total_tasks / (total_waves * max_parallel) * 100, 2
            ) if max_parallel > 0 else 0
        }
    
    def _calculate_critical_path_length(self, tasks: List[Task]) -> int:
        """Calculate the length of the longest dependency chain.
        
        Args:
            tasks: All tasks in the plan
            
        Returns:
            Length of the critical path (longest chain of dependencies)
        """
        task_map = {t.id: t for t in tasks}
        memo: Dict[str, int] = {}
        
        def get_path_length(task_id: str) -> int:
            if task_id in memo:
                return memo[task_id]
            
            task = task_map.get(task_id)
            if not task:
                return 0
            
            if not task.blocked_by:
                memo[task_id] = 1
                return 1
            
            max_dep_length = max(
                get_path_length(dep_id) for dep_id in task.blocked_by
                if dep_id in task_map
            )
            memo[task_id] = max_dep_length + 1
            return memo[task_id]
        
        if not tasks:
            return 0
        
        return max(get_path_length(t.id) for t in tasks)
    
    def get_execution_plan(self) -> PlanResult:
        """Get the current execution plan from the task queue.
        
        Reconstructs the plan from existing tasks in the queue.
        Useful for resuming or inspecting an existing plan.
        
        Returns:
            PlanResult with current tasks and waves
        """
        tasks = self.task_queue.list_tasks()
        waves = self._compute_waves(tasks)
        
        summary = self._generate_summary(tasks, waves, "Existing plan")
        
        return PlanResult(
            tasks=tasks,
            waves=waves,
            summary=summary
        )
    
    def get_next_available_tasks(self, agent_id: str = None) -> List[Task]:
        """Get tasks that are ready to be claimed.
        
        Convenience method that delegates to TaskQueue.
        
        Args:
            agent_id: Optional agent ID for claiming
            
        Returns:
            List of tasks available for execution
        """
        return self.task_queue.get_available_tasks(agent_id)
    
    def claim_task(self, task_id: str, agent_id: str) -> bool:
        """Claim a task for execution.
        
        Convenience method that delegates to TaskQueue.
        
        Args:
            task_id: ID of the task to claim
            agent_id: ID of the agent claiming the task
            
        Returns:
            True if successfully claimed, False otherwise
        """
        return self.task_queue.claim_task(task_id, agent_id)
    
    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed.
        
        Convenience method that delegates to TaskQueue.
        
        Args:
            task_id: ID of the task to complete
            
        Returns:
            True if successfully completed, False otherwise
        """
        return self.task_queue.complete_task(task_id)
    
    def get_plan_progress(self) -> Dict[str, Any]:
        """Get current progress of the plan execution.
        
        Returns:
            Dictionary with progress statistics
        """
        stats = self.task_queue.get_task_stats()
        total = stats["total"]
        completed = stats["completed"]
        in_progress = stats["in_progress"]
        
        progress_percentage = (
            (completed / total * 100) if total > 0 else 0
        )
        
        return {
            "totalTasks": total,
            "completedTasks": completed,
            "inProgressTasks": in_progress,
            "pendingTasks": stats["pending"],
            "progressPercentage": round(progress_percentage, 2),
            "isComplete": completed == total and total > 0
        }
