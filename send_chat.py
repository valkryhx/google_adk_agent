# -*- coding: utf-8 -*-
import urllib.request, json, sys

msg = ('skill_load("agent_team_to_be_update")\n'
       '然后帮我开发一个简单的 Python TodoList CLI 工具。'
       '要求：1. 支持 add/list/done/delete 命令；'
       '2. 数据持久化到 todo.json；'
       '3. 每个任务有 id、内容、完成状态；'
       '4. 必须包含 pytest 测试，验收命令: pytest tests/test_todo.py -v；'
       '工作目录: D:/test123/todo_project')

data = json.dumps({"message": msg}).encode('utf-8')
req = urllib.request.Request(
    'http://localhost:8000/api/chat',
    data=data,
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req, timeout=300) as resp:
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
