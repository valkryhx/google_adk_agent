# -*- coding: utf-8 -*-
import urllib.request, json, sys, uuid

session_id = str(uuid.uuid4())[:8]

msg = (
    'skill_load("agent_team_to_be_update")\n'
    '请帮我开发一个带前端的任务管理 Web 应用。要求：\n'
    '1. 后端：Python FastAPI，SQLite 数据库持久化\n'
    '2. 前端：纯 HTML+CSS+JS（单页面，不需要构建工具），支持增删改查\n'
    '3. 支持任务标题、描述、优先级（高/中/低）、状态（待办/进行中/完成）\n'
    '4. 前端通过 REST API 与后端交互，界面美观\n'
    '5. 必须包含 pytest 测试，验收命令：pytest tests/ -v\n'
    '6. 工作目录：D:/do123/task_manager\n'
    '请用分布式 Worker 协作完成。'
)

data = json.dumps({
    "message": msg,
    "session_id": session_id
}).encode('utf-8')

print(f'Using session_id: {session_id}')

req = urllib.request.Request(
    'http://localhost:8000/api/chat',
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
