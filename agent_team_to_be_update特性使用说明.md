# agent_team_to_be_update 特性使用说明

基于 `skills/agent_team_to_be_update` 的分布式 Worker 协作模式完整指南。

---

## 一、核心概念

### 两个独立目录

| 目录 | 环境变量 | 作用 |
|------|---------|------|
| 协调目录 | `ADK_COORDINATION_DIR` | 任务队列、邮箱、成员注册表（节点间通信） |
| 开发目录 | 无（在任务描述中指定） | Worker 实际写代码的工作目录 |

两者完全独立，互不干扰。换端口、换任务都**不需要改协调目录**。

### 协调目录结构

```
D:/test123/
└── swarm_team/
    ├── coordination/
    │   └── config.json         ← 团队成员注册表（重启时自动清理）
    ├── mailbox/
    │   └── *_inbox.jsonl       ← 节点间消息（按 agent_id 命名）
    └── tasks/
        ├── locks/
        └── task-xxxxxxxx.json  ← 任务进度 JSON（可跨重启保留）
```

---

## 二、集群启动

### start_demo_swarm.bat 配置

```bat
:: ==========================================
:: 演示配置区域（只需改这里）
:: ==========================================
set LEADER_PORT=9000
set WORKER_COUNT=4
set START_PORT=9001
set MODULE_PATH=src.adk_agent.main_web_start_steering
set ADK_COORDINATION_DIR=D:\test123
```

启动时自动完成：
1. 删除 `sqlite_db/swarm_registry.db`（ADK HTTP 会话注册表）
2. 删除 `coordination/config.json`（团队成员注册表，防止向死端口广播）
3. 依次启动 Leader + 4 个 Worker

### 换端口

只改 `LEADER_PORT` 和 `START_PORT`，其余全部自动适配：

| 自动适配项 | 示例（端口 9000） |
|-----------|------------------|
| agent_id | `leader_9000@adk_swarm` |
| SQLite 数据库 | `adk_sessions_port_9000.db` |
| Mailbox 收件箱 | `leader_9000@adk_swarm_inbox.jsonl` |
| 协调目录 | **不变**，无需修改 |

---

## 三、协调目录清理时机

### 不需要清空

- 相同端口重启集群：历史 `tasks/` JSON 不影响新任务认领
- 多次发送不同任务：每次 `dag_create` 生成唯一 task ID，互不干扰

### 只清 config.json（推荐，bat 已自动处理）

```bat
set COORD_CONFIG=%ADK_COORDINATION_DIR%\swarm_team\coordination\config.json
if exist "%COORD_CONFIG%" del "%COORD_CONFIG%"
```

**原因**：`config.json` 记录上次集群各节点端口。不清理会导致 Leader 向死端口发 mailbox 消息，任务分配挂起。

**注意**：`sqlite_db/swarm_registry.db` 是 ADK 框架的 HTTP 会话注册表，与文件协调系统是两套独立机制，清了 db **不等于**清了 `config.json`。

### 完全清空（彻底重置）

适用于：端口变化、任务卡在 `in_progress` 无法自愈、调试需要干净环境。

```bash
rm -rf D:/test123/*
```

---

## 四、团队成员注册机制

| 函数 | 调用方 | 作用 |
|------|--------|------|
| `team_create(team_id)` | Leader | 创建团队 + 注册自己为 orchestrator |
| `team_join(team_id)` | Worker | 注册自己到已有团队（可选） |

**完整流程**：

```
用户发消息给 Leader (port 9000)
  → Leader 调用 skill_load("agent_team_to_be_update")
  → Leader 调用 team_create("swarm_team")
      写入 config.json: {agent_id: "leader_9000@adk_swarm", port: 9000}
  → Leader 调用 dag_create(tasks=[...])  ← 创建任务 + 广播通知 Workers
  → Workers 的 SelfClaimLoop 抢占认领任务
  → Worker 执行时可调用 team_join        ← 注册自己（可选）
```

Worker 不调用 `team_join` 也能认领执行任务，只是在 `team_status` 查询中不可见。

---

## 五、发送任务脚本（send_chat.py）

```python
# -*- coding: utf-8 -*-
import urllib.request, json, uuid

session_id = str(uuid.uuid4())[:8]

# ============================================================
# 简单用例：TodoList CLI（无前端/数据库）[当前激活]
# ============================================================
msg = (
    'skill_load("agent_team_to_be_update")\n'
    '请帮我开发一个 Python TodoList CLI 工具。要求：\n'
    '1. 支持 add/list/done/delete 命令\n'
    '2. 数据持久化到 todo.json\n'
    '3. 每个任务有 id、内容、完成状态\n'
    '4. 必须包含 pytest 测试，验收命令：pytest tests/test_todo.py -v\n'
    '5. 工作目录：D:/test9000/todo_cli\n'
    '请用分布式 Worker 协作完成。'
)

# ============================================================
# 复杂用例：任务管理 Web 应用（FastAPI + SQLite + 前端）
# 取消注释下方 msg 并注释上方 msg 即可切换
# ============================================================
# msg = (
#     'skill_load("agent_team_to_be_update")\n'
#     '请帮我开发一个带前端的任务管理 Web 应用。要求：\n'
#     '1. 后端：Python FastAPI，SQLite 数据库持久化\n'
#     '2. 前端：纯 HTML+CSS+JS（单页面，不需要构建工具），支持增删改查\n'
#     '3. 支持任务标题、描述、优先级（高/中/低）、状态（待办/进行中/完成）\n'
#     '4. 前端通过 REST API 与后端交互，界面美观\n'
#     '5. 必须包含 pytest 测试，验收命令：pytest tests/ -v\n'
#     '6. 工作目录：D:/do123/task_manager\n'
#     '请用分布式 Worker 协作完成。'
# )

data = json.dumps({
    "message": msg,
    "session_id": session_id,
    "user_id": "user_001"   # 与前端默认 user_id 一致，会话在前端可见
}).encode('utf-8')

print(f'session_id: {session_id}')

req = urllib.request.Request(
    'http://localhost:9000/api/chat',
    data=data,
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=600) as resp:
    for line in resp:
        line = line.decode('utf-8').strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            chunk = d.get('chunk', {})
            t = chunk.get('type', '')
            c = chunk.get('content', '')
            if t == 'text':
                print(c, end='', flush=True)
            elif t == 'tool_call':
                print(f'\n[tool] {str(c)[:120]}', flush=True)
            elif t == 'error':
                print(f'\n[error] {c}', flush=True)
        except Exception:
            pass
print()
```

运行：
```bash
cd D:/git_repos/google_adk_agent
PYTHONIOENCODING=utf-8 python send_chat.py
```

---

## 六、用例一：TodoList CLI（简单）

### 任务输入

```
skill_load("agent_team_to_be_update")
请帮我开发一个 Python TodoList CLI 工具。要求：
1. 支持 add/list/done/delete 命令
2. 数据持久化到 todo.json
3. 每个任务有 id、内容、完成状态
4. 必须包含 pytest 测试，验收命令：pytest tests/test_todo.py -v
5. 工作目录：D:/test9000/todo_cli
请用分布式 Worker 协作完成。
```

### 产出目录结构

```
D:/test9000/todo_cli/
├── todo.py            # 主程序模块
├── requirements.txt
├── todo.json          # 数据存储（运行后生成）
└── tests/
    └── test_todo.py   # 12 个测试用例
```

### 核心代码：todo.py

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, sys

if sys.platform == "win32":
    import codecs
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

TODO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "todo.json")

def load_todos():
    if not os.path.exists(TODO_FILE):
        return []
    try:
        with open(TODO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_todos(todos):
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        json.dump(todos, f, ensure_ascii=False, indent=2)

def add_todo(content):
    todos = load_todos()
    new_todo = {"id": max((t["id"] for t in todos), default=0) + 1,
                "content": content, "completed": False}
    todos.append(new_todo)
    save_todos(todos)
    print(f"已添加任务 [ID: {new_todo['id']}]: {content}")
    return new_todo

def list_todos():
    todos = load_todos()
    if not todos:
        print("暂无任务")
        return
    print(f"{'ID':<6} {'状态':<8} {'内容'}")
    for t in todos:
        status = "完成" if t["completed"] else "未完成"
        print(f"{t['id']:<6} {status:<10} {t['content']}")
    print(f"总计: {len(todos)} 个任务")

def mark_done(todo_id):
    todos = load_todos()
    for todo in todos:
        if todo["id"] == todo_id:
            if todo["completed"]:
                print(f"任务 [ID: {todo_id}] 已经是完成状态")
            else:
                todo["completed"] = True
                save_todos(todos)
                print(f"已标记完成 [ID: {todo_id}]: {todo['content']}")
            return True
    print(f"错误: 未找到 ID 为 {todo_id} 的任务")
    return False

def delete_todo(todo_id):
    todos = load_todos()
    for i, todo in enumerate(todos):
        if todo["id"] == todo_id:
            todos.pop(i)
            save_todos(todos)
            print(f"已删除任务 [ID: {todo_id}]: {todo['content']}")
            return True
    print(f"错误: 未找到 ID 为 {todo_id} 的任务")
    return False

def main():
    parser = argparse.ArgumentParser(description="TodoList CLI", prog="todo.py")
    subparsers = parser.add_subparsers(dest="command")
    add_p = subparsers.add_parser("add")
    add_p.add_argument("content", nargs="+")
    subparsers.add_parser("list")
    done_p = subparsers.add_parser("done")
    done_p.add_argument("todo_id", type=int)
    del_p = subparsers.add_parser("delete")
    del_p.add_argument("todo_id", type=int)
    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
    elif args.command == "add":
        add_todo(" ".join(args.content))
    elif args.command == "list":
        list_todos()
    elif args.command == "done":
        mark_done(args.todo_id)
    elif args.command == "delete":
        delete_todo(args.todo_id)

if __name__ == "__main__":
    main()
```

### 测试代码：tests/test_todo.py

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, pytest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import todo

@pytest.fixture
def temp_todo_file(tmp_path):
    temp_file = tmp_path / "test_todo.json"
    original_file = todo.TODO_FILE
    todo.TODO_FILE = str(temp_file)
    yield str(temp_file)
    todo.TODO_FILE = original_file

@pytest.fixture
def clean_todos(temp_todo_file):
    if os.path.exists(temp_todo_file):
        os.remove(temp_todo_file)
    yield []

class TestAddTodo:
    def test_add_todo_creates_file(self, temp_todo_file, clean_todos):
        result = todo.add_todo("测试任务1")
        assert os.path.exists(temp_todo_file)
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved) == 1
        assert saved[0]["id"] == 1
        assert saved[0]["content"] == "测试任务1"
        assert saved[0]["completed"] is False

    def test_add_multiple_todos_increment_id(self, temp_todo_file, clean_todos):
        todo.add_todo("任务1")
        todo.add_todo("任务2")
        todo.add_todo("任务3")
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved) == 3
        assert saved[0]["id"] == 1
        assert saved[1]["id"] == 2
        assert saved[2]["id"] == 3

class TestListTodos:
    def test_list_empty_todos(self, temp_todo_file, clean_todos, capsys):
        todo.list_todos()
        captured = capsys.readouterr()
        assert "暂无任务" in captured.out

    def test_list_multiple_todos(self, temp_todo_file, clean_todos, capsys):
        todo.add_todo("任务A")
        todo.add_todo("任务B")
        todo.list_todos()
        captured = capsys.readouterr()
        assert "待办事项列表" in captured.out
        assert "任务A" in captured.out
        assert "任务B" in captured.out
        assert "总计: 2 个任务" in captured.out

    def test_list_shows_completion_status(self, temp_todo_file, clean_todos, capsys):
        todo.add_todo("测试任务")
        todo.mark_done(1)
        todo.list_todos()
        captured = capsys.readouterr()
        assert "完成" in captured.out

class TestMarkDone:
    def test_mark_done_success(self, temp_todo_file, clean_todos):
        todo.add_todo("待完成任务")
        result = todo.mark_done(1)
        assert result is True
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved[0]["completed"] is True

    def test_mark_done_already_completed(self, temp_todo_file, clean_todos, capsys):
        todo.add_todo("已完成任务")
        todo.mark_done(1)
        result = todo.mark_done(1)
        captured = capsys.readouterr()
        assert result is True
        assert "已经是完成状态" in captured.out

    def test_mark_done_nonexistent(self, temp_todo_file, clean_todos, capsys):
        result = todo.mark_done(999)
        captured = capsys.readouterr()
        assert result is False
        assert "未找到" in captured.out

class TestDeleteTodo:
    def test_delete_todo_success(self, temp_todo_file, clean_todos):
        todo.add_todo("待删除任务")
        result = todo.delete_todo(1)
        assert result is True
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved) == 0

    def test_delete_specific_todo(self, temp_todo_file, clean_todos):
        todo.add_todo("任务1")
        todo.add_todo("任务2")
        todo.add_todo("任务3")
        result = todo.delete_todo(2)
        assert result is True
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved) == 2
        ids = [t["id"] for t in saved]
        assert 1 in ids and 2 not in ids and 3 in ids

    def test_delete_nonexistent(self, temp_todo_file, clean_todos, capsys):
        result = todo.delete_todo(999)
        captured = capsys.readouterr()
        assert result is False
        assert "未找到" in captured.out

class TestIntegration:
    def test_full_workflow(self, temp_todo_file, clean_todos):
        todo.add_todo("任务1")
        todo.add_todo("任务2")
        todo.add_todo("任务3")
        todo.mark_done(1)
        todo.delete_todo(2)
        with open(temp_todo_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert len(saved) == 2
        ids = [t["id"] for t in saved]
        assert 1 in ids and 2 not in ids and 3 in ids
        task1 = next(t for t in saved if t["id"] == 1)
        assert task1["completed"] is True

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

### 验收

```bash
cd D:/test9000/todo_cli
pytest tests/test_todo.py -v
```

预期：**12 passed**

---

## 七、用例二：任务管理 Web 应用（复杂）

### 任务输入

```
skill_load("agent_team_to_be_update")
请帮我开发一个带前端的任务管理 Web 应用。要求：
1. 后端：Python FastAPI，SQLite 数据库持久化
2. 前端：纯 HTML+CSS+JS（单页面，不需要构建工具），支持增删改查
3. 支持任务标题、描述、优先级（高/中/低）、状态（待办/进行中/完成）
4. 前端通过 REST API 与后端交互，界面美观
5. 必须包含 pytest 测试，验收命令：pytest tests/ -v
6. 工作目录：D:/do123/task_manager
请用分布式 Worker 协作完成。
```

### 产出目录结构

```
D:/do123/task_manager/
├── main.py              # FastAPI 应用入口
├── database.py          # SQLAlchemy 数据库配置
├── models.py            # 数据模型
├── schemas.py           # Pydantic 序列化模式
├── crud.py              # 数据库操作函数
├── requirements.txt
├── tasks.db             # SQLite 数据库（运行后生成）
├── static/
│   └── index.html       # 单页面前端
└── tests/
    ├── test_api.py       # API 测试
    └── test_crud.py      # CRUD 测试
```

### 启动方式

```bash
cd D:/do123/task_manager
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
# 访问 http://localhost:8080/static/index.html
```

### 验收

```bash
cd D:/do123/task_manager
pytest tests/ -v
```

---

## 八、常见问题排查

### 任务卡在 in_progress

原因：Worker 进程崩溃，任务锁未释放。

```bash
# 彻底重置协调目录
rm -rf D:/test123/*
# 重启集群
start_demo_swarm.bat
```

### 端口已占用

```bash
# 查找占用端口的进程
netstat -ano | grep 9000
# 杀掉进程
taskkill /PID <pid> /F
```

或使用项目内的 `kill_ports.ps1`：

```powershell
powershell -ExecutionPolicy Bypass -File kill_ports.ps1
```

### Worker 收不到任务

1. 检查 `config.json` 是否已清理（重启前 bat 自动处理）
2. 检查 `ADK_COORDINATION_DIR` 是否与 bat 配置一致
3. 查看 Worker 日志：`logs/worker_900X.log`

### 模块导入走旧缓存（路径异常）

重启后如果路径仍然双重嵌套（如 `swarm_team/swarm_team/tasks`）：

```bash
# 清除所有 __pycache__
find D:/git_repos/google_adk_agent/skills -name '__pycache__' -type d -exec rm -rf {} +
# 重启集群
start_demo_swarm.bat
```

---

## 九、路径规范（快速参考）

| 组件 | 初始化参数 | 实际路径 |
|------|-----------|----------|
| `TaskQueue` | `base_dir=coord_dir` | `coord_dir/tasks/` |
| `TeamConfig` | `base_dir=coord_dir` | `coord_dir/coordination/` |
| `Mailbox` | `base_dir=coord_dir` | `coord_dir/mailbox/` |

其中 `coord_dir = ADK_COORDINATION_DIR/team_id`，例如 `D:/test123/swarm_team`。

**规则**：所有组件都传 `coord_dir`，由组件内部追加子目录名，不在外部拼接。
