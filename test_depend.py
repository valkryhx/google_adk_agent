import sys, os
sys.path.append(os.path.join(os.path.abspath('.'), 'src'))
sys.path.append(os.path.join(os.path.abspath('.'), 'skills', 'agent_team_to_be_update'))

from task_queue import TaskQueue

coord_dir = os.path.join(os.path.abspath('.'), 'test_coord_dag')
queue = TaskQueue('test_team', base_dir=coord_dir)

# Clear old tasks
for tid in [t.id for t in queue.list_tasks()]:
    queue.delete_task(tid)

# Create task 1
t1 = queue.create_task('Task 1', 'Desc 1')
print('Created', t1.id, 'blocked_by:', t1.blocked_by)

# Create task 2 with dependency
t2 = queue.create_task('Task 2', 'Desc 2', blocked_by=[t1.id])
print('Created', t2.id, 'blocked_by:', t2.blocked_by)

# Check available tasks
avail = [t.id for t in queue.get_available_tasks()]
print('Available Tasks:', avail)

# Claim task 1
print('Claim T1?', queue.claim_task(t1.id, 'agent1'))
print('Claim T2?', queue.claim_task(t2.id, 'agent2'))

# Complete task 1
queue.complete_task(t1.id)
print('T1 completed.')

# Check again
avail2 = [t.id for t in queue.get_available_tasks()]
print('Available Tasks After T1 Complete:', avail2)
print('Claim T2 Again?', queue.claim_task(t2.id, 'agent2'))

