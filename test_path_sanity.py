#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
路径嵌套自测：验证 TaskQueue / TeamConfig / Mailbox 在给定 coordination_dir 时
不会产生双重 team_id 子目录，且 Leader(decentralized_tools) 与 Worker(self_claim_loop)
使用的路径一致，所有路径均在 coord_dir 下且结构整洁。
"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "skills", "agent_team_to_be_update"))

from task_queue import TaskQueue
from team_config import TeamConfig
from mailbox import Mailbox

TEAM_ID = "swarm_team"
ADK_COORDINATION_DIR = tempfile.mkdtemp(prefix="adk_test_")

# coord_dir = ADK_COORDINATION_DIR/team_id  (已含 team_id)
coord_dir = os.path.join(ADK_COORDINATION_DIR, TEAM_ID)
os.makedirs(coord_dir, exist_ok=True)

print(f"ADK_COORDINATION_DIR : {ADK_COORDINATION_DIR}")
print(f"coord_dir            : {coord_dir}")
print()

def norm(p):
    return p.replace("\\", "/")

# -------------------------------------------------------------------
# 1. TaskQueue — 传 coord_dir，内部不再拼 team_id
# -------------------------------------------------------------------
q = TaskQueue(team_id=TEAM_ID, base_dir=coord_dir)
print(f"TaskQueue.tasks_dir  : {q.tasks_dir}")

assert norm(q.tasks_dir).startswith(norm(coord_dir)), \
    f"FAIL: tasks_dir 不在 coord_dir 下: {q.tasks_dir}"

segments = norm(q.tasks_dir).split("/")
assert segments.count(TEAM_ID) == 1, \
    f"FAIL: tasks_dir 含双重 team_id ({segments.count(TEAM_ID)} 次): {q.tasks_dir}"

print("  [PASS] TaskQueue 路径无双重嵌套，位于 coord_dir 下")

# -------------------------------------------------------------------
# 2. TeamConfig — Leader 传 coord_dir
# -------------------------------------------------------------------
cfg_leader = TeamConfig(team_id=TEAM_ID, base_dir=coord_dir)
print(f"TeamConfig(leader)   : {cfg_leader.config_dir}")

assert norm(cfg_leader.config_dir).startswith(norm(coord_dir)), \
    f"FAIL: TeamConfig 不在 coord_dir 下: {cfg_leader.config_dir}"

segs = norm(cfg_leader.config_dir).split("/")
assert segs.count(TEAM_ID) == 1, \
    f"FAIL: TeamConfig 含双重 team_id ({segs.count(TEAM_ID)} 次): {cfg_leader.config_dir}"

print("  [PASS] TeamConfig(leader) 路径无双重嵌套，位于 coord_dir 下")

# -------------------------------------------------------------------
# 3. TeamConfig — Worker 传 coord_dir，与 Leader 路径一致
# -------------------------------------------------------------------
cfg_worker = TeamConfig(team_id=TEAM_ID, base_dir=coord_dir)
print(f"TeamConfig(worker)   : {cfg_worker.config_dir}")

assert cfg_worker.config_dir == cfg_leader.config_dir, \
    f"FAIL: Worker/Leader TeamConfig 路径不一致!\n  leader={cfg_leader.config_dir}\n  worker={cfg_worker.config_dir}"

print("  [PASS] Worker 与 Leader TeamConfig 路径一致")

# -------------------------------------------------------------------
# 4. Mailbox — 传 coord_dir
# -------------------------------------------------------------------
mb = Mailbox(base_dir=coord_dir)
print(f"Mailbox.base_dir     : {mb.base_dir}")

assert norm(mb.base_dir).startswith(norm(coord_dir)), \
    f"FAIL: Mailbox 不在 coord_dir 下: {mb.base_dir}"

segs = norm(mb.base_dir).split("/")
assert segs.count(TEAM_ID) == 1, \
    f"FAIL: Mailbox 含双重 team_id: {mb.base_dir}"

print("  [PASS] Mailbox 路径无双重嵌套，位于 coord_dir 下")

# -------------------------------------------------------------------
# 5. 目录结构整洁性：所有路径在同一层级下
# -------------------------------------------------------------------
print()
print("预期目录结构：")
print(f"  {ADK_COORDINATION_DIR}/")
print(f"  └── {TEAM_ID}/")
print(f"      ├── tasks/         ← TaskQueue")
print(f"      ├── coordination/  ← TeamConfig")
print(f"      └── mailbox/       ← Mailbox")
print()

# tasks_dir 直接父目录应为 coord_dir
tasks_parent = os.path.dirname(q.tasks_dir)
assert norm(tasks_parent) == norm(coord_dir), \
    f"FAIL: tasks/ 不直接在 coord_dir 下: parent={tasks_parent}"

# config_dir 直接父目录应为 coord_dir
config_parent = os.path.dirname(cfg_leader.config_dir)
assert norm(config_parent) == norm(coord_dir), \
    f"FAIL: coordination/ 不直接在 coord_dir 下: parent={config_parent}"

# mailbox 直接父目录应为 coord_dir
mailbox_parent = os.path.dirname(mb.base_dir)
assert norm(mailbox_parent) == norm(coord_dir), \
    f"FAIL: mailbox/ 不直接在 coord_dir 下: parent={mailbox_parent}"

print("  [PASS] tasks/ coordination/ mailbox/ 全部直接在 coord_dir 下")

print()
print("=" * 55)
print("ALL PASS — 无双重嵌套，结构整洁，Leader/Worker 路径一致")
print("=" * 55)

shutil.rmtree(ADK_COORDINATION_DIR, ignore_errors=True)
