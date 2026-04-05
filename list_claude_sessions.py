"""
现在支持：

默认最近 20 条：
PYTHONIOENCODING=utf-8 python list_claude_sessions.py

指定最近 N 条：
比如最近 5 条：
PYTHONIOENCODING=utf-8 python list_claude_sessions.py 5

输出格式：
现在每条都会附带可直接复制的命令：
[1] 2026-04-06 04:22:37 | 5eee24f9-4610-4e2e-a14b-34fee4c1a845 | ok
    claude --resume 5eee24f9-4610-4e2e-a14b-34fee4c1a845
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def format_timestamp(ts: int) -> str:
    """把毫秒时间戳格式化为本地可读时间。"""
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S")


def parse_limit() -> int:
    """解析命令行中的最近会话数量参数，默认返回 20。"""
    if len(sys.argv) < 2:
        return 20
    try:
        limit = int(sys.argv[1])
    except ValueError:
        print(f"invalid limit: {sys.argv[1]}")
        raise SystemExit(1)
    if limit <= 0:
        print("limit must be greater than 0")
        raise SystemExit(1)
    return limit


def main() -> None:
    """列出当前项目最近的 Claude 会话，并附上可直接恢复的命令。"""
    history_file = Path.home() / ".claude" / "history.jsonl"
    project = str(Path.cwd())
    limit = parse_limit()

    if not history_file.exists():
        print(f"history file not found: {history_file}")
        return

    rows: list[tuple[int, str, str]] = []
    with history_file.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except Exception:
                continue

            if obj.get("project") == project:
                rows.append(
                    (
                        obj.get("timestamp", 0),
                        obj.get("sessionId", ""),
                        obj.get("display", ""),
                    )
                )

    seen: set[str] = set()
    out: list[tuple[int, str, str]] = []
    for ts, sid, display in reversed(rows):
        if sid and sid not in seen:
            seen.add(sid)
            out.append((ts, sid, display))

    if not out:
        print(f"no sessions found for project: {project}")
        return

    for index, (ts, sid, display) in enumerate(out[:limit], start=1):
        print(f"[{index}] {format_timestamp(ts)} | {sid} | {display}")
        print(f"    claude --resume {sid}")


if __name__ == "__main__":
    main()
