"""
sync_task_context 三模式重设计 验证脚本
==========================================
验证内容:
1. _get_all_nodes() 辅助函数
2. sync_task_context 参数解析 (三种模式判定)
3. /api/context/user_sessions API (如果节点在线)
4. /api/context/leader_summary?session_id=xxx (如果节点在线)

执行方式:
  cmd /c set PYTHONIOENCODING=utf-8 && python MISC/how-to/优化sync_task_context/test_sync_redesign.py
"""

import sys
import os
import json
import asyncio
import traceback

# 设置项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

# 测试计数器
passed = 0
failed = 0
skipped = 0

def test_pass(name):
    global passed
    passed += 1
    print(f"  [PASS] {name}")

def test_fail(name, detail=""):
    global failed
    failed += 1
    print(f"  [FAIL] {name}")
    if detail:
        print(f"         {detail}")

def test_skip(name, reason=""):
    global skipped
    skipped += 1
    print(f"  [SKIP] {name} ({reason})")


# ==============================================
# Test 1: _get_all_nodes() 辅助函数
# ==============================================
def test_get_all_nodes():
    print("\n== Test 1: _get_all_nodes() ==")
    
    from skills.agent_team.tools import _get_all_nodes, _get_active_workers, REGISTRY_DB
    
    # 1a. 函数存在且可调用
    if callable(_get_all_nodes):
        test_pass("_get_all_nodes is callable")
    else:
        test_fail("_get_all_nodes is NOT callable")
        return
    
    # 1b. 检查 REGISTRY_DB 路径
    if os.path.exists(REGISTRY_DB):
        test_pass(f"REGISTRY_DB exists: {REGISTRY_DB}")
    else:
        test_skip("REGISTRY_DB not found", "集群未启动，无法测试实际节点发现")
        return
    
    # 1c. 调用 include_self=True (应该包含所有节点)
    all_nodes = _get_all_nodes(include_self=True)
    print(f"         _get_all_nodes(include_self=True) => {len(all_nodes)} nodes: {all_nodes}")
    
    if isinstance(all_nodes, list):
        test_pass(f"Returns list with {len(all_nodes)} nodes")
    else:
        test_fail("Should return list")
    
    # 1d. 对比 _get_active_workers (排除自身)
    workers_only = _get_active_workers()
    all_nodes_no_self = _get_all_nodes(include_self=False)
    
    # include_self=False 和 _get_active_workers 应该长度相同
    if len(all_nodes_no_self) == len(workers_only):
        test_pass(f"_get_all_nodes(include_self=False) == _get_active_workers() ({len(workers_only)} nodes)")
    else:
        test_fail(f"Mismatch: _get_all_nodes(False)={len(all_nodes_no_self)} vs workers={len(workers_only)}")
    
    # 1e. 每个节点应有 port 和 url 字段
    if all_nodes:
        node = all_nodes[0]
        if 'port' in node and 'url' in node:
            test_pass(f"Node has port={node['port']} and url={node['url']}")
        else:
            test_fail(f"Node missing fields: {node}")


# ==============================================
# Test 2: sync_task_context 参数解析逻辑
# ==============================================
def test_parameter_parsing():
    print("\n== Test 2: sync_task_context 参数解析 ==")
    
    from skills.agent_team.tools import sync_task_context
    import inspect
    
    # 2a. 函数签名应包含 session_id 参数
    sig = inspect.signature(sync_task_context)
    params = list(sig.parameters.keys())
    
    if 'session_id' in params:
        test_pass("session_id parameter exists")
    else:
        test_fail(f"session_id NOT in params: {params}")
    
    if 'target_ports' in params:
        test_pass("target_ports parameter exists")
    else:
        test_fail(f"target_ports NOT in params: {params}")
    
    if 'reason' in params:
        test_pass("reason parameter exists")
    else:
        test_fail(f"reason NOT in params: {params}")
    
    # 2b. session_id 默认值应为 None
    default = sig.parameters['session_id'].default
    if default is None:
        test_pass("session_id default is None")
    else:
        test_fail(f"session_id default is {default}, expected None")
    
    # 2c. target_ports 默认值应为 None (广播模式)
    default_tp = sig.parameters['target_ports'].default
    if default_tp is None:
        test_pass("target_ports default is None (broadcast mode)")
    else:
        test_fail(f"target_ports default is {default_tp}, expected None")

    # 2d. docstring 应包含三种模式描述
    doc = sync_task_context.__doc__ or ""
    for keyword in ["broadcast", "targeted", "precise", "session_id"]:
        # 不区分大小写
        if keyword.lower() in doc.lower():
            test_pass(f"Docstring contains '{keyword}'")
        else:
            test_fail(f"Docstring missing '{keyword}'")


# ==============================================
# Test 3: 格式化函数
# ==============================================
def test_format_functions():
    print("\n== Test 3: 格式化函数 ==")
    
    from skills.agent_team.tools import _format_discovery_results, _format_detail_results
    
    # 3a. _format_discovery_results
    mock_results = [
        {"port": 8000, "success": True, "sessions": [
            {"session_id": "abc123456789", "title": "Test Task", "task_type": "swarm_leader", "updated_at": "2026-02-12T22:00:00"}
        ], "count": 1},
        {"port": 8001, "error": "Connection refused"},
    ]
    output = _format_discovery_results("test_user", [8000, 8001], mock_results, "broadcast")
    
    if "Broadcast" in output:
        test_pass("Discovery report contains 'Broadcast' mode")
    else:
        test_fail("Discovery report missing 'Broadcast'")
    
    if "abc123456789" in output:
        test_pass("Discovery report shows full session_id")
    else:
        test_fail(f"Discovery report missing session_id prefix")
    
    if "Test Task" in output:
        test_pass("Discovery report shows task title")
    else:
        test_fail("Discovery report missing title")
    
    if "Connection refused" in output:
        test_pass("Discovery report shows error for offline node")
    else:
        test_fail("Discovery report missing error info")
    
    if "swarm_leader" in output:
        test_pass("Discovery report shows task_type tag")
    else:
        test_fail("Discovery report missing task_type tag")
    
    if "sync_task_context" in output:
        test_pass("Discovery report includes 'Tip' with follow-up command")
    else:
        test_fail("Discovery report missing follow-up tip")
    
    # 3b. _format_detail_results
    mock_detail = [
        {"port": 8000, "success": True, "data": {
            "title": "Deep Task",
            "app_name": "adk_swarm",
            "total_messages": 42,
            "recent_summary": "User: hello Assistant: hi there"
        }}
    ]
    detail_output = _format_detail_results("test_user", [8000], mock_detail, "session_abc")
    
    if "Deep Task" in detail_output:
        test_pass("Detail report shows title")
    else:
        test_fail("Detail report missing title")
    
    if "42" in detail_output:
        test_pass("Detail report shows message count")
    else:
        test_fail("Detail report missing message count")
    
    if "session_abc" in detail_output:
        test_pass("Detail report shows session_id")
    else:
        test_fail("Detail report missing session_id")
    
    print(f"\n--- Discovery Report Sample ---")
    print(output[:500])
    print("...")


# ==============================================
# Test 4: API 端点测试 (需要在线节点)
# ==============================================
def test_api_endpoints():
    print("\n== Test 4: API Endpoints (Live) ==")
    
    import httpx
    
    test_ports = [8000, 8001, 8002]
    live_port = None
    
    # 找一个在线的节点
    for port in test_ports:
        try:
            resp = httpx.get(f"http://localhost:{port}/health", timeout=3.0)
            if resp.status_code == 200:
                live_port = port
                test_pass(f"Found live node at port {port}")
                break
        except Exception:
            continue
    
    if not live_port:
        test_skip("No live nodes found", "Start swarm to test API endpoints")
        return
    
    base_url = f"http://localhost:{live_port}"
    
    # 4a. GET /api/context/user_sessions
    try:
        resp = httpx.get(f"{base_url}/api/context/user_sessions", params={"user_id": "dwh"}, timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            if "sessions" in data and "count" in data:
                test_pass(f"/api/context/user_sessions returns correct schema: count={data['count']}")
            else:
                test_fail(f"/api/context/user_sessions bad schema: {data}")
        else:
            test_fail(f"/api/context/user_sessions HTTP {resp.status_code}")
    except Exception as e:
        test_fail(f"/api/context/user_sessions exception: {e}")
    
    # 4b. GET /api/context/leader_summary with session_id (不存在的)
    try:
        resp = httpx.get(
            f"{base_url}/api/context/leader_summary",
            params={"user_id": "dwh", "session_id": "non_existent_session"},
            timeout=5.0
        )
        if resp.status_code == 200:
            data = resp.json()
            if "error" in data:
                test_pass(f"leader_summary with bad session_id returns error: '{data['error'][:60]}'")
            else:
                test_fail(f"leader_summary should return error for non-existent session, got: {data}")
        else:
            test_fail(f"leader_summary HTTP {resp.status_code}")
    except Exception as e:
        test_fail(f"leader_summary exception: {e}")
    
    # 4c. GET /api/context/user_sessions for real user
    try:
        resp = httpx.get(f"{base_url}/api/context/user_sessions", params={"user_id": "dwh"}, timeout=5.0)
        data = resp.json()
        if data.get("count", 0) > 0:
            first_session = data["sessions"][0]
            required_fields = ["session_id", "app_name", "title"]
            missing = [f for f in required_fields if f not in first_session]
            if not missing:
                test_pass(f"user_sessions(user_001) returned {data['count']} sessions, schema OK")
                print(f"         First session: {first_session.get('title')} [{first_session.get('session_id', '?')[:8]}...]")
                
                # 4d. 用真实的 session_id 测试精准查询
                real_sid = first_session["session_id"]
                resp2 = httpx.get(
                    f"{base_url}/api/context/leader_summary",
                    params={"app_name": "*", "user_id": "dwh", "session_id": real_sid},
                    timeout=10.0
                )
                if resp2.status_code == 200:
                    detail = resp2.json()
                    if "error" not in detail and "title" in detail:
                        test_pass(f"leader_summary(session_id={real_sid[:8]}...) precise query works: '{detail['title']}'")
                    else:
                        test_fail(f"leader_summary precise query returned: {detail}")
                else:
                    test_fail(f"leader_summary precise query HTTP {resp2.status_code}")
            else:
                test_fail(f"Missing fields in session: {missing}")
        else:
            test_skip("No sessions for user_001", "Create sessions first")
    except Exception as e:
        test_fail(f"user_sessions(user_001) exception: {e}")


# ==============================================
# Main
# ==============================================
if __name__ == "__main__":
    print("=" * 50)
    print("sync_task_context Redesign Verification")
    print("=" * 50)
    
    os.chdir(PROJECT_ROOT)
    
    try:
        test_get_all_nodes()
    except Exception as e:
        test_fail(f"test_get_all_nodes crashed: {e}")
        traceback.print_exc()
    
    try:
        test_parameter_parsing()
    except Exception as e:
        test_fail(f"test_parameter_parsing crashed: {e}")
        traceback.print_exc()
    
    try:
        test_format_functions()
    except Exception as e:
        test_fail(f"test_format_functions crashed: {e}")
        traceback.print_exc()
    
    try:
        test_api_endpoints()
    except Exception as e:
        test_fail(f"test_api_endpoints crashed: {e}")
        traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print("=" * 50)
    
    sys.exit(1 if failed > 0 else 0)
