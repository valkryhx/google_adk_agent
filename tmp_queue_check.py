import sys, os, json
sys.path.append(os.path.join('d:\\git_codes\\google_adk_helloworld_git', 'src'))
sys.path.append(os.path.join('d:\\git_codes\\google_adk_helloworld_git', 'skills', 'agent_team_to_be_update'))
try:
    from task_queue import TaskQueue
except Exception as e:
    print('Error importing TaskQueue:', e)
    sys.exit(1)

# try adk directory first
base_dir = os.path.join(os.path.expanduser('~'), '.gemini', 'antigravity', 'coordination', 'swarm_team')
if not os.path.exists(base_dir):
    # fallback or custom location, possibly near app data
    base_dir = os.path.join('d:\\git_codes\\google_adk_helloworld_git', 'coordination', 'swarm_team')

q = TaskQueue('swarm_team', base_dir)
tasks = q.list_tasks()
print(f'Total tasks: {len(tasks)} found at {q.tasks_dir}')
for t in tasks:
    if t.status == 'pending':
        print(f'- [PENDING] {t.name} (id: {t.id}, blocked_by: {t.blocked_by})')
    elif t.status == 'in_progress':
        print(f'- [RUNNING] {t.name} (id: {t.id}, blocked_by: {t.blocked_by})')
