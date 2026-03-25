#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mailbox Communication System for Agent Team.

Provides peer-to-peer message passing between agents using JSONL file format.
Supports message types: text, shutdown_request, task_assignment.
"""

import json
import os
import time
import uuid
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 进程内按文件路径分组的互斥锁，防止同进程多线程并发写入损坏 JSONL
_inbox_locks: Dict[str, threading.Lock] = {}
_inbox_locks_meta = threading.Lock()


def _get_inbox_lock(path: str) -> threading.Lock:
    """获取或创建指定收件箱文件的进程内互斥锁。"""
    with _inbox_locks_meta:
        if path not in _inbox_locks:
            _inbox_locks[path] = threading.Lock()
        return _inbox_locks[path]


@dataclass
class Message:
    """Message data model for agent-to-agent communication.
    
    Attributes:
        id: Unique message identifier
        from_agent: Sender agent ID
        to_agent: Recipient agent ID
        content: Message content/payload
        timestamp: Unix timestamp when message was sent
        msg_type: Type of message (text/shutdown_request/task_assignment)
        read: Whether the message has been read
        metadata: Additional key-value data
    """
    id: str
    from_agent: str
    to_agent: str
    content: str
    timestamp: float = field(default_factory=time.time)
    msg_type: str = "text"  # text / shutdown_request / task_assignment
    read: bool = False
    metadata: Optional[Dict] = None

    def to_json(self) -> Dict:
        """Serialize message to JSON-compatible dictionary.
        
        Returns:
            Dictionary representation of the message
        """
        return {
            "id": self.id,
            "from": self.from_agent,
            "to": self.to_agent,
            "content": self.content,
            "timestamp": self.timestamp,
            "type": self.msg_type,
            "read": self.read,
            "metadata": self.metadata or {}
        }

    @classmethod
    def from_json(cls, data: Dict) -> "Message":
        """Deserialize message from dictionary.
        
        Args:
            data: Dictionary containing message data
            
        Returns:
            Message instance
        """
        return cls(
            id=data["id"],
            from_agent=data["from"],
            to_agent=data["to"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            msg_type=data.get("type", "text"),
            read=data.get("read", False),
            metadata=data.get("metadata")
        )


class Mailbox:
    """Agent-to-agent communication system using file-based storage.
    
    Uses JSONL format (one message per line) for append-only message storage.
    Supports Windows file locking for concurrent access safety.
    
    Attributes:
        base_dir: Root directory for mailbox storage
    """

    def __init__(self, base_dir: str):
        """Initialize mailbox with base directory.
        
        Args:
            base_dir: Root directory for mailbox storage
        """
        self.base_dir = os.path.join(base_dir, "mailbox")
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_inbox_path(self, agent_id: str) -> str:
        """Get the file path for an agent's inbox.
        
        Args:
            agent_id: Target agent identifier
            
        Returns:
            Absolute path to the inbox JSONL file
        """
        return os.path.join(self.base_dir, f"{agent_id}_inbox.jsonl")

    def _acquire_file_lock(self, file_handle, exclusive: bool = True) -> bool:
        """Acquire file lock with Windows compatibility.
        
        Args:
            file_handle: Open file handle
            exclusive: True for exclusive lock, False for shared
            
        Returns:
            True if lock acquired, False otherwise
        """
        try:
            import msvcrt
            import struct
            
            # Windows uses LockFileEx via msvcrt
            # Lock the entire file (offset=0, length=0 means entire file)
            overlapped = struct.pack('QQ', 0, 0)  # Offset and length
            
            if exclusive:
                # Exclusive lock — nbytes 必须 >= 1，0 表示锁 0 字节（无效）
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            else:
                # Shared lock not directly supported, use exclusive
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                return True
        except ImportError:
            # Fallback for non-Windows systems
            try:
                import fcntl
                if exclusive:
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                else:
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
                return True
            except (ImportError, IOError):
                return False
        except IOError:
            return False

    def _release_file_lock(self, file_handle) -> None:
        """Release file lock.
        
        Args:
            file_handle: Open file handle with acquired lock
        """
        try:
            import msvcrt
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except (ImportError, OSError):
            try:
                import fcntl
                fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass

    def send_message(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        msg_type: str = "text",
        metadata: Optional[Dict] = None
    ) -> str:
        """Send a message to a recipient agent.
        
        Appends the message to the recipient's inbox file atomically.
        
        Args:
            from_agent: Sender agent ID
            to_agent: Recipient agent ID
            content: Message content
            msg_type: Message type (text/shutdown_request/task_assignment)
            metadata: Optional additional data
            
        Returns:
            Generated message ID
        """
        msg = Message(
            id=f"msg-{uuid.uuid4().hex[:8]}",
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            timestamp=time.time(),
            msg_type=msg_type,
            metadata=metadata
        )

        inbox_path = self._get_inbox_path(to_agent)
        line = json.dumps(msg.to_json(), ensure_ascii=False) + "\n"

        # 进程内互斥锁，防止同进程多线程并发写入同一收件箱损坏 JSONL
        # [修复] Windows 多进程并发 open() 同一文件可能抛 PermissionError，
        # 增加重试机制避免瞬时文件锁冲突导致整个守护进程崩溃。
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with _get_inbox_lock(inbox_path):
                    with open(inbox_path, 'a', encoding='utf-8') as f:
                        if self._acquire_file_lock(f, exclusive=True):
                            f.write(line)
                            f.flush()
                            os.fsync(f.fileno())
                        else:
                            f.write(line)
                            f.flush()
                break  # 成功写入，跳出重试
            except PermissionError:
                if attempt < max_retries - 1:
                    time.sleep(0.1 * (attempt + 1))  # 退避重试
                else:
                    raise  # 重试耗尽，向上抛出

        return msg.id

    def read_messages(
        self,
        agent_id: str,
        mark_read: bool = True,
        msg_type: Optional[str] = None
    ) -> List[Message]:
        """Read unread messages from an agent's inbox.
        
        Args:
            agent_id: Agent whose inbox to read
            mark_read: Whether to mark returned messages as read
            msg_type: Filter by message type (None for all)
            
        Returns:
            List of unread messages matching criteria
        """
        inbox_path = self._get_inbox_path(agent_id)
        if not os.path.exists(inbox_path):
            return []

        messages = []
        all_messages = []

        # Read all messages
        with open(inbox_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = Message.from_json(json.loads(line))
                        all_messages.append(msg)
                        # Filter: unread and matching type
                        if not msg.read:
                            if msg_type is None or msg.msg_type == msg_type:
                                messages.append(msg)
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed lines
                        continue

        # Mark messages as read if requested
        if mark_read and messages:
            msg_ids = [m.id for m in messages]
            self._mark_read(inbox_path, msg_ids)

        return messages

    def check_new_messages(
        self,
        agent_id: str,
        unread_only: bool = True
    ) -> List["Message"]:
        """快速检查新消息（不自动标记已读）

        与 read_messages 的区别：
        - check_new_messages: 不修改文件，只读取（无锁）
        - read_messages: 读取并可选标记已读（有锁）

        用于 PollingDaemon 的高频轮询，避免频繁写锁

        Args:
            agent_id: 目标 agent ID
            unread_only: True = 只返回未读消息

        Returns:
            消息列表
        """
        inbox_path = self._get_inbox_path(agent_id)
        if not os.path.exists(inbox_path):
            return []

        messages = []
        try:
            with open(inbox_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            msg = Message.from_json(json.loads(line))
                            if not unread_only or not msg.read:
                                messages.append(msg)
                        except (json.JSONDecodeError, KeyError):
                            continue
        except IOError:
            pass

        return messages

    def _mark_read(self, inbox_path: str, msg_ids: List[str]) -> None:
        """Atomically mark specified messages as read.
        
        Rewrites the entire inbox file with updated read status.
        Uses file locking for thread/process safety.
        
        Args:
            inbox_path: Path to the inbox file
            msg_ids: List of message IDs to mark as read
        """
        if not os.path.exists(inbox_path):
            return

        # 进程内互斥锁，防止 _mark_read 重写时与并发 send_message 竞争
        with _get_inbox_lock(inbox_path):
            self._mark_read_locked(inbox_path, msg_ids)

    def _mark_read_locked(self, inbox_path: str, msg_ids: list) -> None:
        """Internal: rewrite inbox with read flags updated (must be called under inbox lock)."""
        msg_id_set = set(msg_ids)
        all_messages = []

        # Read all messages
        with open(inbox_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = Message.from_json(json.loads(line))
                        if msg.id in msg_id_set:
                            msg.read = True
                        all_messages.append(msg)
                    except (json.JSONDecodeError, KeyError):
                        # Preserve malformed lines
                        all_messages.append(line)

        # Write back with lock
        temp_path = inbox_path + ".tmp"
        with open(temp_path, 'w', encoding='utf-8') as f:
            if self._acquire_file_lock(f, exclusive=True):
                try:
                    for msg in all_messages:
                        if isinstance(msg, Message):
                            f.write(json.dumps(msg.to_json(), ensure_ascii=False) + "\n")
                        else:
                            f.write(msg + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    self._release_file_lock(f)
            else:
                # Best effort without lock
                for msg in all_messages:
                    if isinstance(msg, Message):
                        f.write(json.dumps(msg.to_json(), ensure_ascii=False) + "\n")
                    else:
                        f.write(msg + "\n")
                f.flush()

        # Atomic replace
        os.replace(temp_path, inbox_path)

    def broadcast(
        self,
        from_agent: str,
        content: str,
        agent_ids: List[str],
        msg_type: str = "text",
        metadata: Optional[Dict] = None
    ) -> List[str]:
        """Broadcast a message to multiple agents.
        
        Args:
            from_agent: Sender agent ID
            content: Message content
            agent_ids: List of recipient agent IDs
            msg_type: Message type
            metadata: Optional additional data
            
        Returns:
            List of generated message IDs
        """
        msg_ids = []
        for agent_id in agent_ids:
            msg_id = self.send_message(
                from_agent=from_agent,
                to_agent=agent_id,
                content=content,
                msg_type=msg_type,
                metadata=metadata
            )
            msg_ids.append(msg_id)
        return msg_ids

    def get_all_messages(
        self,
        agent_id: str,
        include_read: bool = True
    ) -> List[Message]:
        """Get all messages from an agent's inbox.
        
        Args:
            agent_id: Agent whose inbox to read
            include_read: Whether to include already-read messages
            
        Returns:
            List of all messages
        """
        inbox_path = self._get_inbox_path(agent_id)
        if not os.path.exists(inbox_path):
            return []

        messages = []
        with open(inbox_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = Message.from_json(json.loads(line))
                        if include_read or not msg.read:
                            messages.append(msg)
                    except (json.JSONDecodeError, KeyError):
                        continue

        return messages

    def clear_inbox(self, agent_id: str) -> int:
        """Clear all messages from an agent's inbox.
        
        Args:
            agent_id: Agent whose inbox to clear
            
        Returns:
            Number of messages cleared
        """
        inbox_path = self._get_inbox_path(agent_id)
        if not os.path.exists(inbox_path):
            return 0

        count = 0
        with open(inbox_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    count += 1

        # Clear file
        open(inbox_path, 'w').close()
        return count
