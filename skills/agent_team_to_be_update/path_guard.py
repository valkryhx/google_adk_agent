#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Path Security Guard for Agent Team

Prevents unauthorized file access by workers, ensuring they can only access
files within allowed boundaries and cannot modify sensitive directories.
"""

import os
import sys
from pathlib import Path
from typing import List, Optional, Union


class PathAccessError(PermissionError):
    """Custom exception for path access violations."""
    
    def __init__(self, path: str, reason: str = ""):
        self.path = path
        self.reason = reason
        message = f"Access denied for path: {path}"
        if reason:
            message += f" ({reason})"
        super().__init__(message)


class PathGuard:
    """
    Path security guard for preventing unauthorized file access.
    
    Validates file paths to ensure they are within allowed boundaries
    and not in forbidden directories. Used to isolate workers from
    sensitive system and agent directories.
    
    Attributes:
        allowed_root: The root directory workers are allowed to access
        forbidden_paths: List of paths that are explicitly forbidden
    """
    
    def __init__(
        self,
        allowed_root: Union[str, Path],
        forbidden_paths: Optional[List[Union[str, Path]]] = None
    ):
        """
        Initialize the PathGuard.
        
        Args:
            allowed_root: The root directory workers are allowed to access
            forbidden_paths: Optional list of paths that are explicitly forbidden
        """
        self.allowed_root = Path(allowed_root).resolve()
        
        # Normalize forbidden paths
        self.forbidden_paths: List[Path] = []
        if forbidden_paths:
            for path in forbidden_paths:
                try:
                    resolved = Path(path).resolve()
                    self.forbidden_paths.append(resolved)
                except (OSError, ValueError):
                    # Skip invalid paths
                    continue
    
    def is_allowed(self, path: Union[str, Path]) -> bool:
        """
        Check if a path is within allowed boundaries.
        
        Validates that:
        1. The path is not in the forbidden list
        2. The path is within the allowed root directory
        3. The path doesn't contain traversal sequences that escape allowed_root
        
        Args:
            path: The path to validate
            
        Returns:
            True if path is allowed, False otherwise
        """
        try:
            # Resolve to absolute path
            abs_path = Path(path).resolve()
            path_str = str(abs_path)
            
            # Check 1: Path must not be in forbidden list
            for forbidden in self.forbidden_paths:
                forbidden_str = str(forbidden)
                # Check if path is the forbidden path or is inside it
                if path_str == forbidden_str or path_str.startswith(forbidden_str + os.sep):
                    return False
            
            # Check 2: Path must be within allowed root
            allowed_str = str(self.allowed_root)
            if not path_str.startswith(allowed_str):
                return False
            
            # Check 3: Path must not contain parent directory traversal
            # This is already handled by Path.resolve(), but double-check
            try:
                # Ensure the relative path doesn't go outside allowed_root
                rel_path = abs_path.relative_to(self.allowed_root)
                # Check for any '..' components in the relative path
                if '..' in str(rel_path).split(os.sep):
                    return False
            except ValueError:
                # Path is not relative to allowed_root
                return False
            
            return True
            
        except (OSError, ValueError, RuntimeError):
            # Any error during path resolution means deny access
            return False
    
    def validate_or_raise(self, path: Union[str, Path]) -> None:
        """
        Validate a path and raise an exception if not allowed.
        
        Args:
            path: The path to validate
            
        Raises:
            PathAccessError: If the path is not within allowed boundaries
        """
        if not self.is_allowed(path):
            # Determine the reason for denial
            reason = self._get_denial_reason(path)
            raise PathAccessError(str(path), reason)
    
    def _get_denial_reason(self, path: Union[str, Path]) -> str:
        """
        Get the reason why a path was denied.
        
        Args:
            path: The path that was denied
            
        Returns:
            String describing why access was denied
        """
        try:
            abs_path = Path(path).resolve()
            path_str = str(abs_path)
            
            # Check if in forbidden paths
            for forbidden in self.forbidden_paths:
                forbidden_str = str(forbidden)
                if path_str == forbidden_str or path_str.startswith(forbidden_str + os.sep):
                    return f"path is in forbidden directory: {forbidden}"
            
            # Check if outside allowed root
            allowed_str = str(self.allowed_root)
            if not path_str.startswith(allowed_str):
                return f"path is outside allowed root: {self.allowed_root}"
            
            return "path validation failed"
            
        except Exception:
            return "path resolution error"
    
    def get_allowed_root(self) -> str:
        """
        Get the allowed root directory.
        
        Returns:
            String path of the allowed root directory
        """
        return str(self.allowed_root)
    
    def get_forbidden_paths(self) -> List[str]:
        """
        Get the list of forbidden paths.
        
        Returns:
            List of forbidden path strings
        """
        return [str(p) for p in self.forbidden_paths]
    
    def add_forbidden_path(self, path: Union[str, Path]) -> None:
        """
        Add a new forbidden path.
        
        Args:
            path: Path to add to forbidden list
        """
        try:
            resolved = Path(path).resolve()
            if resolved not in self.forbidden_paths:
                self.forbidden_paths.append(resolved)
        except (OSError, ValueError):
            pass
    
    def remove_forbidden_path(self, path: Union[str, Path]) -> bool:
        """
        Remove a path from the forbidden list.
        
        Args:
            path: Path to remove from forbidden list
            
        Returns:
            True if path was removed, False if not found
        """
        try:
            resolved = Path(path).resolve()
            if resolved in self.forbidden_paths:
                self.forbidden_paths.remove(resolved)
                return True
        except (OSError, ValueError):
            pass
        return False
    
    def sanitize_path(self, path: Union[str, Path]) -> Optional[Path]:
        """
        Sanitize a path and return it if allowed.
        
        Args:
            path: The path to sanitize
            
        Returns:
            Resolved Path if allowed, None otherwise
        """
        try:
            abs_path = Path(path).resolve()
            if self.is_allowed(abs_path):
                return abs_path
        except (OSError, ValueError):
            pass
        return None
    
    def check_read_access(self, path: Union[str, Path]) -> bool:
        """
        Check if read access is allowed for a path.
        
        Args:
            path: The path to check
            
        Returns:
            True if read access is allowed
        """
        return self.is_allowed(path)
    
    def check_write_access(self, path: Union[str, Path]) -> bool:
        """
        Check if write access is allowed for a path.
        
        Args:
            path: The path to check
            
        Returns:
            True if write access is allowed
        """
        return self.is_allowed(path)
    
    def safe_join(self, *paths: Union[str, Path]) -> Optional[Path]:
        """
        Safely join paths and validate the result.
        
        Args:
            *paths: Path components to join
            
        Returns:
            Resolved Path if result is allowed, None otherwise
        """
        try:
            # Start from allowed_root for safety
            base = self.allowed_root
            for p in paths:
                base = base / p
            
            resolved = base.resolve()
            if self.is_allowed(resolved):
                return resolved
        except (OSError, ValueError, TypeError):
            pass
        return None
    
    def is_subpath(self, parent: Union[str, Path], child: Union[str, Path]) -> bool:
        """
        Check if child is a subpath of parent.
        
        Args:
            parent: The potential parent path
            child: The potential child path
            
        Returns:
            True if child is within parent
        """
        try:
            parent_path = Path(parent).resolve()
            child_path = Path(child).resolve()
            
            # Check if child starts with parent path
            parent_str = str(parent_path)
            child_str = str(child_path)
            
            if not child_str.startswith(parent_str):
                return False
            
            # Ensure it's actually a subpath (not the same path)
            if child_path == parent_path:
                return True
            
            # Check that the next character is a separator
            if len(child_str) > len(parent_str) and child_str[len(parent_str)] == os.sep:
                return True
            
            return False
            
        except (OSError, ValueError):
            return False
    
    def get_relative_path(self, path: Union[str, Path]) -> Optional[Path]:
        """
        Get the path relative to allowed_root.
        
        Args:
            path: The absolute path
            
        Returns:
            Relative Path if within allowed_root, None otherwise
        """
        try:
            abs_path = Path(path).resolve()
            if self.is_allowed(abs_path):
                return abs_path.relative_to(self.allowed_root)
        except (OSError, ValueError):
            pass
        return None


class WorkerPathGuard(PathGuard):
    """
    Specialized PathGuard for worker agents.
    
    Prevents workers from accessing:
    - Agent system directories
    - Other workers' worktrees
    - System directories
    - Parent directories outside project
    """
    
    DEFAULT_FORBIDDEN_PATTERNS = [
        # System directories
        "/proc", "/sys", "/dev", "/boot", "/etc",
        # User config directories
        "~/.ssh", "~/.gnupg", "~/.config",
        # Common sensitive paths
        "/var/log", "/var/spool",
    ]
    
    def __init__(
        self,
        allowed_root: Union[str, Path],
        agent_root: Optional[Union[str, Path]] = None,
        forbidden_paths: Optional[List[Union[str, Path]]] = None
    ):
        """
        Initialize WorkerPathGuard with default security settings.
        
        Args:
            allowed_root: The project directory workers can access
            agent_root: The agent system directory to forbid
            forbidden_paths: Additional custom forbidden paths
        """
        # Build comprehensive forbidden list
        all_forbidden: List[Union[str, Path]] = []
        
        # Add agent root if provided
        if agent_root:
            all_forbidden.append(agent_root)
        
        # Add default forbidden patterns
        for pattern in self.DEFAULT_FORBIDDEN_PATTERNS:
            expanded = os.path.expanduser(pattern)
            if os.path.exists(expanded):
                all_forbidden.append(expanded)
        
        # Add user-provided forbidden paths
        if forbidden_paths:
            all_forbidden.extend(forbidden_paths)
        
        super().__init__(allowed_root, all_forbidden)
        self.agent_root = Path(agent_root).resolve() if agent_root else None
    
    def is_agent_path(self, path: Union[str, Path]) -> bool:
        """
        Check if a path is within the agent system directory.
        
        Args:
            path: The path to check
            
        Returns:
            True if path is in agent directory
        """
        if not self.agent_root:
            return False
        
        try:
            abs_path = Path(path).resolve()
            path_str = str(abs_path)
            agent_str = str(self.agent_root)
            return path_str.startswith(agent_str)
        except (OSError, ValueError):
            return False
    
    def is_system_path(self, path: Union[str, Path]) -> bool:
        """
        Check if a path is a system directory.
        
        Args:
            path: The path to check
            
        Returns:
            True if path is a system directory
        """
        try:
            abs_path = Path(path).resolve()
            path_str = str(abs_path)
            
            system_paths = ["/proc", "/sys", "/dev", "/boot", "/etc", "/var"]
            for sys_path in system_paths:
                if path_str.startswith(sys_path):
                    return True
            
            return False
        except (OSError, ValueError):
            return False
