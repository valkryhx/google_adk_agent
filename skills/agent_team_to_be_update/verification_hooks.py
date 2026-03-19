#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task Verification Hooks (Anti-Slacking)

This module provides hooks to verify that workers have actually completed their work
before allowing them to mark tasks as complete or enter idle state.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")


@dataclass
class VerificationResult:
    """Result of a verification check."""

    allowed: bool
    reason: str
    action: str  # e.g., "continue_work", "commit_first", "fix_and_retry", "reject_completion"

    def __bool__(self) -> bool:
        """Allow using VerificationResult in boolean contexts."""
        return self.allowed


class TeammateIdleHook:
    """
    Hook that runs when a worker enters idle state.
    Verifies that completed work has all expected artifacts and passes quality checks.
    """

    def __init__(self, workdir: str):
        self.workdir = Path(workdir)
        self.artifacts: List[str] = []
        self.verification_commands: List[str] = []

    def set_expected_artifacts(self, artifacts: List[str]) -> None:
        """Set the list of expected artifact files/paths."""
        self.artifacts = artifacts

    def set_verification_commands(self, commands: List[str]) -> None:
        """Set the list of commands to run for verification."""
        self.verification_commands = commands

    def _check_artifacts_exist(self) -> tuple[bool, List[str]]:
        """Check if all expected artifacts exist."""
        missing = []
        for artifact in self.artifacts:
            artifact_path = self.workdir / artifact
            if not artifact_path.exists():
                missing.append(artifact)
        return len(missing) == 0, missing

    def _check_git_status(self) -> tuple[bool, str]:
        """Check git status for uncommitted changes."""
        try:
            # Check if this is a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=True if sys.platform == "win32" else False,
            )
            if result.returncode != 0:
                return True, "Not a git repository"

            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=True if sys.platform == "win32" else False,
            )
            if result.returncode != 0:
                return False, f"Git status failed: {result.stderr}"

            if result.stdout.strip():
                return False, "Uncommitted changes detected"

            return True, "Git repository is clean"
        except Exception as e:
            return False, f"Git check failed: {str(e)}"

    def _run_verification_commands(self) -> tuple[bool, List[str]]:
        """Run verification commands and return results."""
        failures = []
        for cmd in self.verification_commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.workdir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    shell=True,
                )
                if result.returncode != 0:
                    failures.append(f"Command '{cmd}' failed: {result.stderr}")
            except Exception as e:
                failures.append(f"Command '{cmd}' error: {str(e)}")
        return len(failures) == 0, failures

    def verify(self) -> VerificationResult:
        """
        Run full verification before allowing worker to enter idle state.
        Returns VerificationResult indicating whether idle is allowed.
        """
        # Check artifacts
        artifacts_ok, missing = self._check_artifacts_exist()
        if not artifacts_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Missing expected artifacts: {', '.join(missing)}",
                action="continue_work",
            )

        # Check git status
        git_ok, git_msg = self._check_git_status()
        if not git_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Git check failed: {git_msg}",
                action="commit_first",
            )

        # Run verification commands
        commands_ok, failures = self._run_verification_commands()
        if not commands_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Verification failed: {'; '.join(failures)}",
                action="fix_and_retry",
            )

        return VerificationResult(
            allowed=True,
            reason="All verification checks passed",
            action="continue_work",
        )


class TaskCompletedHook:
    """
    Hook that runs when a task is marked as completed.
    Quality gate - must pass all verification commands before allowing completion.
    """

    def __init__(self, workdir: str):
        self.workdir = Path(workdir)
        self.verification_commands: List[str] = []
        self.required_files: List[str] = []
        self.require_git_clean: bool = True

    def set_verification_commands(self, commands: List[str]) -> None:
        """Set the list of commands that must pass for task completion."""
        self.verification_commands = commands

    def set_required_files(self, files: List[str]) -> None:
        """Set the list of files that must exist for task completion."""
        self.required_files = files

    def set_require_git_clean(self, required: bool) -> None:
        """Set whether git clean status is required for completion."""
        self.require_git_clean = required

    def _check_required_files(self) -> tuple[bool, List[str]]:
        """Check if all required files exist."""
        missing = []
        for file in self.required_files:
            file_path = self.workdir / file
            if not file_path.exists():
                missing.append(file)
        return len(missing) == 0, missing

    def _check_git_committed(self) -> tuple[bool, str]:
        """Check if all changes are committed."""
        if not self.require_git_clean:
            return True, "Git check skipped"

        try:
            # Check if this is a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=True if sys.platform == "win32" else False,
            )
            if result.returncode != 0:
                return True, "Not a git repository"

            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                shell=True if sys.platform == "win32" else False,
            )
            if result.returncode != 0:
                return False, f"Git status failed: {result.stderr}"

            if result.stdout.strip():
                # Parse uncommitted files
                lines = result.stdout.strip().split("\n")
                uncommitted = [line[3:] for line in lines if len(line) > 3]
                return False, f"Uncommitted files: {', '.join(uncommitted)}"

            return True, "All changes committed"
        except Exception as e:
            return False, f"Git check failed: {str(e)}"

    def _run_verification_commands(self) -> tuple[bool, List[str]]:
        """Run verification commands and return results."""
        failures = []
        for cmd in self.verification_commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.workdir,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    shell=True,
                )
                if result.returncode != 0:
                    failures.append(f"Command '{cmd}' failed: {result.stderr}")
            except Exception as e:
                failures.append(f"Command '{cmd}' error: {str(e)}")
        return len(failures) == 0, failures

    def verify(self) -> VerificationResult:
        """
        Run full verification before allowing task to be marked complete.
        Returns VerificationResult indicating whether completion is allowed.
        """
        # Check required files
        files_ok, missing = self._check_required_files()
        if not files_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Missing required files: {', '.join(missing)}",
                action="continue_work",
            )

        # Check git status
        git_ok, git_msg = self._check_git_committed()
        if not git_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Git check failed: {git_msg}",
                action="commit_first",
            )

        # Run verification commands
        commands_ok, failures = self._run_verification_commands()
        if not commands_ok:
            return VerificationResult(
                allowed=False,
                reason=f"Quality checks failed: {'; '.join(failures)}",
                action="fix_and_retry",
            )

        return VerificationResult(
            allowed=True,
            reason="All quality gates passed - task can be marked complete",
            action="continue_work",
        )


class VerificationHooksManager:
    """Manager for all verification hooks."""

    def __init__(self, workdir: str):
        self.workdir = workdir
        self.idle_hook = TeammateIdleHook(workdir)
        self.completed_hook = TaskCompletedHook(workdir)

    def get_idle_hook(self) -> TeammateIdleHook:
        """Get the idle hook instance."""
        return self.idle_hook

    def get_completed_hook(self) -> TaskCompletedHook:
        """Get the completed hook instance."""
        return self.completed_hook

    def verify_idle(self) -> VerificationResult:
        """Run idle verification."""
        return self.idle_hook.verify()

    def verify_completion(self) -> VerificationResult:
        """Run completion verification."""
        return self.completed_hook.verify()
