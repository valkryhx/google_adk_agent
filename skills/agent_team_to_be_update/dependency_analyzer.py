#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Team Task Queue System - LLM-Based Dependency Analyzer

This module provides LLM-assisted task decomposition and dependency analysis.
It breaks down complex user requests into atomic subtasks with proper dependency relationships.
"""

import json
import re
from typing import List, Dict, Any, Optional


SYSTEM_PROMPT = """You are an expert task planner and dependency analyzer for a multi-agent software development system.

Your job is to analyze complex user requests and break them down into atomic, actionable subtasks with clear dependencies.

For each task, identify:
1. Task name (concise, actionable)
2. Detailed description (what needs to be done)
3. Dependencies (which tasks must complete before this one can start)
4. Expected artifacts (files that will be created/modified)
5. File permissions (which files need write access vs read-only)

Rules for dependency analysis:
- Tasks should be as atomic as possible (single responsibility)
- Dependencies should reflect logical ordering, not arbitrary sequencing
- Independent tasks should have NO dependencies (can run in parallel)
- Use "blockedBy" to reference task IDs that must complete first

Output format: JSON array of task objects with these fields:
- id: unique task identifier (use lowercase with hyphens, e.g., "setup-project")
- name: human-readable task name
- description: detailed description of what to do
- blockedBy: list of task IDs that must complete first (can be empty)
- expectedArtifacts: list of file paths expected to be created/modified
- writableFiles: list of files the task needs write access to
- readOnlyFiles: list of files the task only needs to read
- verificationCommands: list of commands to verify task completion

Example output:
[
  {
    "id": "design-schema",
    "name": "Design Database Schema",
    "description": "Create the database schema design document including tables, relationships, and indexes",
    "blockedBy": [],
    "expectedArtifacts": ["docs/schema.md"],
    "writableFiles": ["docs/schema.md"],
    "readOnlyFiles": [],
    "verificationCommands": ["cat docs/schema.md"]
  },
  {
    "id": "implement-models",
    "name": "Implement Data Models",
    "description": "Create SQLAlchemy models based on the schema design",
    "blockedBy": ["design-schema"],
    "expectedArtifacts": ["src/models.py"],
    "writableFiles": ["src/models.py"],
    "readOnlyFiles": ["docs/schema.md"],
    "verificationCommands": ["python -c 'from src.models import *'"]
  }
]

Analyze the user's request carefully and produce a complete task breakdown."""


class TaskDependencyAnalyzer:
    """LLM-assisted task dependency analyzer.
    
    Uses a language model to break down complex user requests into atomic subtasks
    with proper dependency relationships for parallel execution.
    """
    
    def __init__(self, llm_client=None):
        """Initialize the dependency analyzer.
        
        Args:
            llm_client: Optional LLM client for making API calls.
                        If not provided, uses a mock implementation for testing.
        """
        self.llm_client = llm_client
        self.system_prompt = SYSTEM_PROMPT
    
    def analyze(self, user_request: str) -> List[Dict[str, Any]]:
        """Analyze a user request and break it down into tasks with dependencies.
        
        Args:
            user_request: The user's complex request describing what needs to be done.
            
        Returns:
            List of task definition dictionaries, each containing:
            - id: unique task identifier
            - name: human-readable task name
            - description: detailed task description
            - blockedBy: list of task IDs that must complete first
            - expectedArtifacts: list of expected output files
            - writableFiles: list of files needing write access
            - readOnlyFiles: list of files needing read-only access
            - verificationCommands: list of verification commands
        """
        if self.llm_client:
            return self._analyze_with_llm(user_request)
        else:
            return self._analyze_with_heuristics(user_request)
    
    def _analyze_with_llm(self, user_request: str) -> List[Dict[str, Any]]:
        """Use LLM to analyze the request and generate tasks."""
        prompt = f"User Request: {user_request}\n\nProvide the task breakdown as JSON:"
        
        try:
            response = self.llm_client.complete(
                system_prompt=self.system_prompt,
                user_prompt=prompt,
                temperature=0.2
            )
            return self._parse_task_response(response)
        except ValueError as e:
            # LLM 输出解析失败：记录警告后 fallback，让调用方可感知
            print(f"[WARNING] dependency_analyzer: {e}")
            return self._analyze_with_heuristics(user_request)
        except Exception as e:
            # LLM 调用本身失败：静默 fallback 到启发式分析
            return self._analyze_with_heuristics(user_request)
    
    def _analyze_with_heuristics(self, user_request: str) -> List[Dict[str, Any]]:
        """Fallback heuristic-based task analysis.
        
        Uses pattern matching to identify common task types and create
        a reasonable task breakdown without LLM assistance.
        """
        tasks = []
        request_lower = user_request.lower()
        
        # Pattern matching for common development tasks
        if any(kw in request_lower for kw in ['create', 'build', 'implement', 'write']):
            # Check for multi-component requests
            has_frontend = any(kw in request_lower for kw in ['frontend', 'ui', 'react', 'vue', 'angular'])
            has_backend = any(kw in request_lower for kw in ['backend', 'api', 'server', 'database'])
            has_tests = any(kw in request_lower for kw in ['test', 'testing'])
            
            task_id = 1
            
            # Design task (always first, no dependencies)
            design_task = {
                "id": f"task-{task_id:03d}",
                "name": "Design Architecture",
                "description": f"Analyze requirements and design the architecture for: {user_request}",
                "blockedBy": [],
                "expectedArtifacts": ["docs/design.md"],
                "writableFiles": ["docs/design.md"],
                "readOnlyFiles": [],
                "verificationCommands": ["test -f docs/design.md"]
            }
            tasks.append(design_task)
            task_id += 1
            
            deps = [design_task["id"]]
            
            if has_backend:
                backend_task = {
                    "id": f"task-{task_id:03d}",
                    "name": "Implement Backend",
                    "description": "Create the backend API and server logic",
                    "blockedBy": deps.copy(),
                    "expectedArtifacts": ["src/backend/main.py"],
                    "writableFiles": ["src/backend/"],
                    "readOnlyFiles": ["docs/design.md"],
                    "verificationCommands": ["python -m py_compile src/backend/main.py"]
                }
                tasks.append(backend_task)
                task_id += 1
            
            if has_frontend:
                frontend_deps = deps.copy()
                if has_backend:
                    frontend_deps.append(f"task-{task_id-1:03d}")
                frontend_task = {
                    "id": f"task-{task_id:03d}",
                    "name": "Implement Frontend",
                    "description": "Create the frontend UI components",
                    "blockedBy": frontend_deps,
                    "expectedArtifacts": ["src/frontend/App.jsx"],
                    "writableFiles": ["src/frontend/"],
                    "readOnlyFiles": ["docs/design.md"],
                    "verificationCommands": ["test -f src/frontend/App.jsx"]
                }
                tasks.append(frontend_task)
                task_id += 1
            
            if has_tests:
                test_deps = []
                if has_backend:
                    test_deps.append(f"task-{task_id-2:03d}" if has_frontend else f"task-{task_id-1:03d}")
                if has_frontend:
                    test_deps.append(f"task-{task_id-1:03d}")
                
                test_task = {
                    "id": f"task-{task_id:03d}",
                    "name": "Write Tests",
                    "description": "Create unit and integration tests",
                    "blockedBy": test_deps if test_deps else deps.copy(),
                    "expectedArtifacts": ["tests/"],
                    "writableFiles": ["tests/"],
                    "readOnlyFiles": ["docs/design.md"],
                    "verificationCommands": ["python -m pytest tests/ --collect-only"]
                }
                tasks.append(test_task)
        else:
            # Generic single task
            tasks.append({
                "id": "task-001",
                "name": "Execute Request",
                "description": user_request,
                "blockedBy": [],
                "expectedArtifacts": [],
                "writableFiles": [],
                "readOnlyFiles": [],
                "verificationCommands": []
            })
        
        return tasks
    
    def _parse_task_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse LLM response into task definitions.
        
        Args:
            response: Raw LLM response string (should contain JSON).
            
        Returns:
            List of parsed task dictionaries.
        """
        # Try to extract JSON from the response
        try:
            # Look for JSON array in the response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                tasks = json.loads(json_match.group())
            else:
                # Try parsing the whole response as JSON
                tasks = json.loads(response)
            
            # Validate task structure
            validated_tasks = []
            for task in tasks:
                validated_task = {
                    "id": task.get("id", f"task-{len(validated_tasks)+1:03d}"),
                    "name": task.get("name", "Unnamed Task"),
                    "description": task.get("description", ""),
                    "blockedBy": task.get("blockedBy", []),
                    "expectedArtifacts": task.get("expectedArtifacts", []),
                    "writableFiles": task.get("writableFiles", []),
                    "readOnlyFiles": task.get("readOnlyFiles", []),
                    "verificationCommands": task.get("verificationCommands", [])
                }
                validated_tasks.append(validated_task)
            
            return validated_tasks
        except json.JSONDecodeError as e:
            raise ValueError(
                f"[parse_error] LLM 输出无法解析为 JSON: {e}\n"
                f"原始输出 (前500字符): {response[:500]}"
            ) from e
