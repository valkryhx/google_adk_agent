#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git Worktree Manager for Agent Team

Manages Git worktrees for worker isolation, enabling multiple agents to work
on the same repository without file conflicts.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any


class WorktreeManager:
    """
    Git Worktree isolation manager for Agent Team.
    
    Creates isolated worktrees for each worker to prevent file conflicts
    and enable parallel development.
    
    Attributes:
        project_root: The root directory of the git repository
        worktree_base: The base directory where worktrees are created
    """
    
    def __init__(self, project_root: str, worktree_base: Optional[str] = None):
        """
        Initialize the WorktreeManager.
        
        Args:
            project_root: Path to the git repository root
            worktree_base: Optional custom path for worktrees (default: .worktrees in project_root)
        """
        self.project_root = Path(project_root).resolve()
        self.worktree_base = Path(worktree_base) if worktree_base else self.project_root / ".worktrees"
        
        # Ensure worktree base directory exists
        os.makedirs(self.worktree_base, exist_ok=True)
        
        # Configure git safety settings
        self._configure_git_safety()
    
    def _configure_git_safety(self) -> None:
        """
        Configure git safety settings for the repository.
        
        Sets up:
        - safe.directory: Allows git operations in the project directory
        - core.hooksPath: Disables hooks to prevent malicious execution
        """
        try:
            # Configure safe.directory for project root
            subprocess.run(
                ["git", "config", "--local", "safe.directory", str(self.project_root)],
                cwd=str(self.project_root),
                capture_output=True,
                check=False
            )
            
            # Disable git hooks for security
            subprocess.run(
                ["git", "config", "--local", "core.hooksPath", ""],
                cwd=str(self.project_root),
                capture_output=True,
                check=False
            )
        except Exception:
            # Silently fail if git is not available or permissions issue
            pass
    
    def _run_git_command(
        self, 
        args: list, 
        cwd: Optional[str] = None,
        check: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Execute a git command with proper error handling.
        
        Args:
            args: List of git command arguments
            cwd: Working directory for the command
            check: Whether to raise exception on non-zero exit
            
        Returns:
            CompletedProcess instance with return code and output
        """
        cmd = ["git"] + args
        working_dir = cwd if cwd else str(self.project_root)
        
        result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if check and result.returncode != 0:
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{result.stderr}")
        
        return result
    
    def create_worktree(
        self,
        worker_id: str,
        branch_name: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Create a new git worktree for a worker.
        
        Args:
            worker_id: Unique identifier for the worker (e.g., "worker-8001")
            branch_name: Optional custom branch name (default: worker-{worker_id})
            
        Returns:
            Dictionary containing:
                - worktree_path: Absolute path to the worktree
                - branch_name: Name of the created branch
                - worktree_name: Name of the worktree directory
                
        Raises:
            RuntimeError: If worktree creation fails
        """
        if branch_name is None:
            branch_name = f"worker-{worker_id}"
        
        worktree_name = worker_id
        worktree_path = self.worktree_base / worktree_name
        
        # Clean up existing worktree if it exists
        if worktree_path.exists():
            self.remove_worktree(worker_id)
        
        # Create new worktree with a new branch
        result = self._run_git_command(
            [
                "worktree", "add",
                "-b", branch_name,
                str(worktree_path),
                "HEAD"
            ],
            check=False
        )
        
        if result.returncode != 0:
            # Try without -b flag in case branch already exists
            result = self._run_git_command(
                ["worktree", "add", str(worktree_path), branch_name],
                check=False
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create worktree: {result.stderr}")
        
        # Configure safe.directory in the worktree
        try:
            subprocess.run(
                ["git", "config", "safe.directory", str(worktree_path)],
                cwd=str(worktree_path),
                capture_output=True,
                check=False
            )
        except Exception:
            pass
        
        return {
            "worktree_path": str(worktree_path),
            "branch_name": branch_name,
            "worktree_name": worktree_name
        }
    
    def remove_worktree(self, worker_id: str) -> bool:
        """
        Remove a worker's worktree.
        
        Args:
            worker_id: The worker's identifier
            
        Returns:
            True if worktree was removed or didn't exist, False on error
        """
        worktree_path = self.worktree_base / worker_id
        
        if not worktree_path.exists():
            return True
        
        try:
            # Remove worktree using git worktree remove
            self._run_git_command(
                ["worktree", "remove", "--force", str(worktree_path)],
                check=False
            )
            
            # Clean up directory if git command didn't remove it
            if worktree_path.exists():
                import shutil
                shutil.rmtree(worktree_path, ignore_errors=True)
            
            return True
        except Exception:
            # Fallback: try to manually remove the directory
            try:
                import shutil
                shutil.rmtree(worktree_path, ignore_errors=True)
                return True
            except Exception:
                return False
    
    def merge_and_cleanup(
        self,
        worker_id: str,
        target_branch: str = "main",
        commit_message: Optional[str] = None
    ) -> bool:
        """
        Merge worker's changes into target branch and clean up.
        
        Args:
            worker_id: The worker's identifier
            target_branch: Branch to merge into (default: main)
            commit_message: Optional custom merge commit message
            
        Returns:
            True if merge succeeded, False if there were conflicts
            
        Raises:
            RuntimeError: If git operations fail unexpectedly
        """
        branch_name = f"worker-{worker_id}"
        
        # Get current branch to restore later
        result = self._run_git_command(
            ["rev-parse", "--abbrev-ref", "HEAD"],
            check=False
        )
        original_branch = result.stdout.strip() if result.returncode == 0 else target_branch
        
        try:
            # Fetch latest changes
            self._run_git_command(["fetch", "origin"], check=False)
            
            # Checkout target branch
            self._run_git_command(["checkout", target_branch], check=False)
            
            # Pull latest changes
            self._run_git_command(["pull", "origin", target_branch], check=False)
            
            # Merge worker branch
            msg = commit_message or f"Merge changes from {worker_id}"
            result = self._run_git_command(
                ["merge", "--no-ff", "-m", msg, branch_name],
                check=False
            )
            
            if result.returncode != 0:
                # Merge conflict - abort and return False
                self._run_git_command(["merge", "--abort"], check=False)
                self._run_git_command(["checkout", original_branch], check=False)
                return False
            
            # Push merged changes
            self._run_git_command(["push", "origin", target_branch], check=False)
            
            # Clean up worktree
            self.remove_worktree(worker_id)
            
            # Delete the worker branch
            self._run_git_command(["branch", "-D", branch_name], check=False)
            
            # Restore original branch
            if original_branch != target_branch:
                self._run_git_command(["checkout", original_branch], check=False)
            
            return True
            
        except Exception as e:
            # Try to restore original branch on error
            try:
                self._run_git_command(["checkout", original_branch], check=False)
            except Exception:
                pass
            raise RuntimeError(f"Merge failed: {str(e)}")
    
    def list_worktrees(self) -> list:
        """
        List all active worktrees.
        
        Returns:
            List of dictionaries containing worktree information
        """
        try:
            result = self._run_git_command(["worktree", "list", "--porcelain"], check=False)
            
            if result.returncode != 0:
                return []
            
            worktrees = []
            current = {}
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    if current:
                        worktrees.append(current)
                        current = {}
                elif line.startswith('worktree '):
                    current['path'] = line[9:]
                elif line.startswith('HEAD '):
                    current['head'] = line[5:]
                elif line.startswith('branch '):
                    current['branch'] = line[7:]
                elif line == 'bare':
                    current['bare'] = True
                elif line == 'detached':
                    current['detached'] = True
            
            if current:
                worktrees.append(current)
            
            return worktrees
            
        except Exception:
            return []
    
    def get_worktree_path(self, worker_id: str) -> Optional[str]:
        """
        Get the path to a worker's worktree.
        
        Args:
            worker_id: The worker's identifier
            
        Returns:
            Absolute path to worktree, or None if it doesn't exist
        """
        worktree_path = self.worktree_base / worker_id
        if worktree_path.exists():
            return str(worktree_path)
        return None
    
    def is_worktree_clean(self, worker_id: str) -> bool:
        """
        Check if a worktree has uncommitted changes.
        
        Args:
            worker_id: The worker's identifier
            
        Returns:
            True if worktree is clean (no uncommitted changes), False otherwise
        """
        worktree_path = self.worktree_base / worker_id
        
        if not worktree_path.exists():
            return True
        
        try:
            result = self._run_git_command(
                ["status", "--porcelain"],
                cwd=str(worktree_path),
                check=False
            )
            return len(result.stdout.strip()) == 0
        except Exception:
            return False
    
    def commit_changes(
        self,
        worker_id: str,
        message: str,
        add_all: bool = True
    ) -> bool:
        """
        Commit changes in a worktree.
        
        Args:
            worker_id: The worker's identifier
            message: Commit message
            add_all: Whether to stage all changes before commit
            
        Returns:
            True if commit succeeded, False otherwise
        """
        worktree_path = self.worktree_base / worker_id
        
        if not worktree_path.exists():
            return False
        
        try:
            if add_all:
                self._run_git_command(
                    ["add", "-A"],
                    cwd=str(worktree_path),
                    check=False
                )
            
            self._run_git_command(
                ["commit", "-m", message],
                cwd=str(worktree_path),
                check=False
            )
            
            return True
        except Exception:
            return False
