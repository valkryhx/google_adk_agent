# Agent Team Swarm 使用说明

基于 `skills/agent_team_to_be_update` 的分布式 Worker 协作模式。

---

## 核心概念

### 两个独立目录

| 目录 | 环境变量 | 作用 |
|------|---------|------|
| 协调目录 | `ADK_COORDINATION_DIR` | 任务队列、邮箱、成员注册表（节点间通信） |
| 开发目录 | 无（在任务描述中指定） | Worker 实际写代码的工作目录 |

两者完全独立，互不干扰。

---

## 集群启动

### 使用 start_demo_swarm.bat

```bat
:: 配置区域（只需改这里）
set LEADER_PORT=9000          :: Leader 端口
set WORKER_COUNT=4            :: Worker 数量
set START_PORT=9001           :: Worker 起始端口
set ADK_COORDINATION_DIR=D:\test123   :: 协调目录
```

启动后自动完成：
1. 清理 `sqlite_db/swarm_registry.db`（ADK 会话注册表）
2. 清理 `coordination/config.json`（团队成员注册表）
3. 依次启动 Leader + Workers

### 换端口

只改 `LEADER_PORT` 和 `START_PORT`，其余全部自动适配：
- `agent_id` 自动生成（如 `leader_9000@adk_swarm`）
- SQLite 数据库自动隔离（`adk_sessions_port_9000.db`）
- Mailbox 收件箱自动对应（`leader_9000@adk_swarm_inbox.jsonl`）
- **协调目录不需要改**

---

## 协调目录清理时机

### 不需要清空

- 相同端口重启集群 → 直接启动，历史任务 JSON 不影响新任务
- 多次发送任务 → 每次 `dag_create` 生成唯一 task ID，互不干扰

### 需要清理 config.json（成员注册表）

每次重启集群时必须清理，`start_demo_swarm.bat` 已自动处理：

```bat
set COORD_CONFIG=%ADK_COORDINATION_DIR%\swarm_team\coordination\config.json
if exist "%COORD_CONFIG%" del "%COORD_CONFIG%"
```

**原因**：`config.json` 记录了上次集群的节点端口。不清理会导致 Leader 向死端口广播任务，任务分配挂起。

**注意**：`sqlite_db/swarm_registry.db` 是 ADK 框架的 HTTP 会话注册表，与文件协调系统是两套独立机制，清了 db 不等于清了 `config.json`。

### 需要完全清空（彻底重置）

- 端口发生变化
- 出现异常中断导致任务卡在 `in_progress`
- 调试测试需要干净环境

```bash
rm -rf D:/test123/*
```

---

## 团队成员注册机制

注册通过两个工具函数完成，写入 `coordination/config.json`：

| 函数 | 调用方 | 作用 |
|------|--------|------|
| `team_create(team_id)` | Leader | 创建团队 + 注册自己为 orchestrator |
| `team_join(team_id)` | Worker | 注册自己到已有团队 |

**注册流程**：
```
用户发消息给 Leader
  → Leader 调用 skill_load("agent_team_to_be_update")
  → Leader 调用 team_create(team_id)   ← 自己注册
  → Leader 调用 dag_create(tasks)      ← 广播任务给 Workers
  → Workers 的 SelfClaimLoop 收到通知，认领任务
  → Worker 执行任务时可选调用 team_join ← 注册自己（可选）
```

Worker 不注册也能认领和执行任务，只是在 `team_status` 里不可见。

---

## 协调目录结构

修复后的正确结构（`ADK_COORDINATION_DIR=D:/test123`，`team_id=swarm_team`）：

```
D:/test123/
└── swarm_team/
    ├── coordination/
    │   └── config.json     ← 团队成员注册表（重启时清理）
    ├── mailbox/
    │   └── *_inbox.jsonl   ← 节点间消息（按 agent_id 命名）
    └── tasks/
        ├── locks/
        └── task-xxxxxxxx.json  ← 任务进度（可保留）
```

**注意**：如果看到 `swarm_team/swarm_team/` 双重嵌套目录，说明使用了旧版代码。已在 `task_queue.py` 和 `team_config.py` 中修复——构造函数不再内部拼接 `team_id`，调用方统一传 `coord_dir`。

---

## 发送任务（send_chat.py）

```python
# 简单用例（当前激活）
msg = (
    'skill_load("agent_team_to_be_update")\n'
    '请帮我开发一个 Python TodoList CLI 工具...\n'
    '工作目录：D:/test9000/todo_cli'
)

# 复杂用例（取消注释切换）
# msg = (
#     'skill_load("agent_team_to_be_update")\n'
#     '请帮我开发一个带前端的任务管理 Web 应用...\n'
#     '工作目录：D:/do123/task_manager'
# )

# 明确传入默认用户 ID，确保前端会话可见
data = json.dumps({
    "message": msg,
    "session_id": session_id,
    "user_id": "user_001"      ← 必须与前端默认一致
}).encode('utf-8')
```

运行：
```bash
cd D:/git_repos/google_adk_agent
python send_chat.py
```

---

## 典型测试用例对比

| 项目 | 简单用例 | 复杂用例 |
|------|---------|----------|
| 工作目录 | `D:/test9000/todo_cli` | `D:/do123/task_manager` |
| 技术栈 | Python CLI + JSON | FastAPI + SQLite + HTML/JS |
| 测试命令 | `pytest tests/test_todo.py -v` | `pytest tests/ -v` |
| 测试数量 | 12 个 | 14 个 |
| Worker 数 | 3 个协作 | 4 个协作 |
