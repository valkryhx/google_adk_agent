---
name: ciri_session_manager
description: 查询和导出 Ciri ADK Session 内容的工具。支持查询指定 Session 或最新 Session 的完整对话记录，导出为 JSON 格式，列出最近 Session 列表，以及全局搜索关键词。使用场景：(1) 需要查看某个 Session 的对话历史，(2) 需要将 Session 内容导出为 JSON 分享给他人，(3) 需要列出最近的 Session 列表，(4) 需要在所有 Session 中搜索特定关键词。
---

# Ciri Session Manager

## 概述

Ciri Session Manager 是一个用于查询和导出 ADK Session 内容的工具。它可以：

1. **查询 Session 内容**：查看指定 Session ID 或最新 Session 的完整对话记录
2. **导出为 JSON**：将 Session 内容导出为结构化的 JSON 文件，便于分享和存档
3. **列出 Session**：显示最近的 Session 列表
4. **全局搜索**：在所有 Session 的历史消息中搜索特定关键词

该工具基于 `src/adk_agent/inspect_session.py` 的核心逻辑，专为 Session 查询和导出场景优化。

## 工具函数

本技能通过 `tools.py` 提供了以下可直接调用的工具函数：

### 1. `list_sessions(limit=10, db_path=None)`
列出最近的 Session 列表。

**参数：**
- `limit`: 返回的 Session 数量（默认 10）
- `db_path`: 数据库路径（可选，默认自动推导）

**返回：**
```python
{
    "success": True,
    "count": 5,
    "sessions": [
        {
            "id": 311,
            "app_name": "dynamic_expert",
            "user_id": "user_001",
            "session_id": "session_xxx",
            "session_metadata": "...",
            "created_at": "2026-03-18 03:05:21.702067"
        }
    ]
}
```

### 2. `get_latest_session(db_path=None)`
获取最新的 Session ID。

**返回：**
```python
{"success": True, "session_id": "session_xxx"}
```

### 3. `query_session(session_id, with_response=False, db_path=None)`
查询指定 Session 的完整对话内容。

**参数：**
- `session_id`: Session ID
- `with_response`: 是否显示工具响应内容
- `db_path`: 数据库路径（可选）

**返回：**
```python
{
    "success": True,
    "session_id": "session_xxx",
    "message_count": 62,
    "messages": [
        {
            "id": 94699,
            "role": "user",
            "timestamp": "2026-03-18 03:10:45.375782",
            "text": "[Text]: ...",
            "content": {...}
        }
    ]
}
```

### 4. `export_session_to_json(session_id, output_path, include_raw=True, db_path=None)`
将指定 Session 导出为 JSON 文件。

**参数：**
- `session_id`: Session ID
- `output_path`: 输出文件路径
- `include_raw`: 是否包含原始 event_json 数据
- `db_path`: 数据库路径（可选）

**返回：**
```python
{
    "success": True,
    "message": "成功导出 62 条消息",
    "output_path": "/path/to/output.json",
    "message_count": 62
}
```

### 5. `export_latest_session_to_json(output_path, include_raw=True, db_path=None)`
导出最新 Session 为 JSON 文件。

**参数：**
- `output_path`: 输出文件路径
- `include_raw`: 是否包含原始 event_json 数据
- `db_path`: 数据库路径（可选）

**返回：**
同上

## 命令行工具

除了工具函数外，本技能还提供命令行工具 `scripts/query_and_export_session.py`：

### 1. 查询最新 Session

默认情况下，查询最新的 Session 内容：

```bash
python scripts/query_and_export_session.py
```

### 2. 查询指定 Session

通过 `--session-id` 参数指定要查询的 Session ID：

```bash
python scripts/query_and_export_session.py --session-id <SESSION_ID>
```

### 3. 导出 Session 为 JSON

将 Session 内容导出为 JSON 文件：

```bash
# 导出最新 Session
python scripts/query_and_export_session.py --output session_export.json

# 导出指定 Session
python scripts/query_and_export_session.py --session-id <SESSION_ID> --output session_export.json

# 导出时不包含原始 event_json（仅保留结构化内容）
python scripts/query_and_export_session.py --session-id <SESSION_ID> --output session_export.json --no-raw
```

### 4. 列出最近 Session

列出最近的 N 个 Session：

```bash
python scripts/query_and_export_session.py --list 10
```

### 5. 全局搜索关键词

在所有 Session 的历史消息中搜索特定关键词：

```bash
python scripts/query_and_export_session.py --search "关键词"
```

**示例**：
```bash
# 搜索包含"小伙计"的所有消息
python scripts/query_and_export_session.py --search "小伙计"

# 搜索包含"601919"的所有消息
python scripts/query_and_export_session.py --search "601919"
```

### 6. 显示工具响应内容

如果需要查看工具调用（如 bash/sql）的完整响应：

```bash
python scripts/query_and_export_session.py --session-id <SESSION_ID> --with-response
```

### 7. 指定数据库路径

如果数据库不在默认位置，可以指定：

```bash
python scripts/query_and_export_session.py --db /path/to/adk_sessions_port_8000.db
```

## 使用场景

### 场景 1: 分享 Session 对话

用户想要将某个 Session 的对话内容分享给他人：

**方式一：使用工具函数**
```python
from tools import export_session_to_json
result = export_session_to_json("session_xxx", "session_export.json")
```

**方式二：使用命令行**
```bash
python scripts/query_and_export_session.py --session-id session_xxx --output session_export.json
```

### 场景 2: 排查问题

需要查看某个 Session 的完整对话历史以排查问题：

**方式一：使用工具函数**
```python
from tools import list_sessions, query_session
sessions = list_sessions(10)  # 列出最近 10 个 Session
session_data = query_session("session_xxx", with_response=True)  # 查询详细内容
```

**方式二：使用命令行**
```bash
python scripts/query_and_export_session.py --list 10
python scripts/query_and_export_session.py --session-id session_xxx --with-response
```

### 场景 3: 存档 Session

需要将 Session 内容存档：

**方式一：使用工具函数**
```python
from tools import export_latest_session_to_json
result = export_latest_session_to_json("archive/session_20260318.json")
```

**方式二：使用命令行**
```bash
python scripts/query_and_export_session.py --output archive/session_20260318.json
```

### 场景 4: 全局搜索关键词

需要在所有历史对话中查找特定内容：

**方式一：使用命令行**
```bash
# 搜索所有包含"小伙计"的消息
python scripts/query_and_export_session.py --search "小伙计"

# 搜索所有包含"601919"的消息
python scripts/query_and_export_session.py --search "601919"
```

**说明**：
- 搜索会遍历所有 Session 的 `event_json` 字段
- 默认返回最近 15 条匹配记录
- 支持使用 `--with-response` 显示工具响应的详细内容


## 输出格式

导出的 JSON 文件包含以下结构：

```json
{
  "session_id": "xxx-xxx-xxx",
  "exported_at": "2026-03-18 11:10:45",
  "message_count": 10,
  "messages": [
    {
      "id": 1,
      "role": "user",
      "timestamp": "2026-03-18 11:00:00",
      "content": {
        "parts": [...]
      },
      "raw_event_json": {...}  // 仅在未使用 --no-raw 时包含
    }
  ]
}
```

## 数据库位置

默认数据库路径：
- 项目根目录下的 `sqlite_db/adk_sessions_port_8000.db`

如果自动推导失败，可以手动指定 `--db` 参数。

## 依赖

- Python 3.7+
- sqlite3（Python 内置）
- json（Python 内置）
- argparse（Python 内置）

## 注意事项

1. **当前 Session**：如果不指定 `--session-id`，默认使用最新的 Session
2. **输出目录**：如果输出路径包含不存在的目录，会自动创建
3. **编码**：所有输出文件使用 UTF-8 编码
4. **权限**：确保对数据库文件和输出目录有读写权限

## 文件结构

```
ciri_session_manager/
├── SKILL.md              # 技能说明文档
├── tools.py              # 工具函数定义（包含 get_tools 入口）
└── scripts/
    └── query_and_export_session.py  # 命令行工具
```

## 依赖

- Python 3.7+
- sqlite3（Python 内置）
- json（Python 内置）
- argparse（Python 内置）
