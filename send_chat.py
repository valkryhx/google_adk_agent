# -*- coding: utf-8 -*-
import urllib.request, json, uuid

session_id = str(uuid.uuid4())[:8]

# ============================================================
# 简单用例：TodoList CLI（无前端/数据库）
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

data = json.dumps({"message": msg, "session_id": session_id, "user_id": "user_001"}).encode('utf-8')
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
