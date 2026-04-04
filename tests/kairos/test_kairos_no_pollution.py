"""
TDD 测试：验证 KAIROS tick 不污染 session.history

Bug 背景：
- KAIROS 每 15 秒执行一次 tick
- 每次 tick 调用 runner.run_async() 会向 session.events 添加消息
- 导致 session.events 无限膨胀（5208 events 案例）

修复目标：
- KAIROS tick 执行后回滚 session.events
- 不污染用户的对话历史
- 结果只记录到 recent_events 和 activity log
"""
import asyncio
from datetime import UTC, datetime

import pytest

from src.adk_agent.kairos.models import KairosMode, KairosState
from src.adk_agent.kairos.runtime import KairosRuntime


class FakeDexBridge:
    def get_tasks(self, task_ids):
        return []


class FakeSessionService:
    """模拟 SessionService，跟踪 session.events 的变化"""

    def __init__(self, initial_events=None):
        self.events = initial_events or []
        self.save_count = 0

    async def get_session(self, app_name, user_id, session_id):
        """返回模拟的 session 对象"""
        class FakeSession:
            def __init__(self, events):
                self.events = events
                self.app_name = app_name
                self.user_id = user_id
                self.session_id = session_id
                self.state = {}

        return FakeSession(self.events.copy())

    async def save_session(self, session):
        """保存 session，记录调用次数"""
        self.events = session.events.copy()
        self.save_count += 1


def _make_kairos_callbacks():
    """创建 KAIROS 测试用的回调函数"""
    saved = []
    emitted = []
    logged = []

    async def save_state(state):
        saved.append(state)

    async def emit_event(event):
        emitted.append((event.kind, event.message))

    async def append_log(event):
        logged.append(event.message)

    return saved, emitted, logged, save_state, emit_event, append_log


# === 测试用例 ===


@pytest.mark.asyncio
async def test_kairos_tick_does_not_pollute_session_events():
    """
    [核心测试] KAIROS tick 不应该污染 session.events

    场景：
    1. session 初始有 5 条历史消息
    2. 执行 KAIROS tick
    3. 验证 session.events 仍然是 5 条（没有增加）
    """
    # 准备：创建初始 session history（模拟用户对话）
    initial_events = [
        {"role": "user", "content": "hello"},
        {"role": "model", "content": "hi"},
        {"role": "user", "content": "how are you?"},
        {"role": "model", "content": "I'm fine"},
        {"role": "user", "content": "good"},
    ]

    session_service = FakeSessionService(initial_events=initial_events)
    saved, emitted, logged, save_state, emit_event, append_log = _make_kairos_callbacks()

    # 记录执行前的 events 数量
    session_before = await session_service.get_session("test_app", "test_user", "test_session")
    events_count_before = len(session_before.events)
    assert events_count_before == 5, "初始应该有 5 条消息"

    # 模拟 run_turn 函数（KAIROS 调用）
    async def mock_run_turn(reason):
        """
        模拟 run_kairos_turn 内部调用的 _run_agent_turn
        它会向 session.events 添加 2 条消息（用户提问 + 模型回答）
        """
        # 模拟 Runner 的行为：向 session.events 添加消息
        session = await session_service.get_session("test_app", "test_user", "test_session")
        session.events.append({"role": "user", "content": f"[KAIROS_TICK] reason={reason}"})
        session.events.append({"role": "model", "content": "Status: idle, continuing sleep."})
        await session_service.save_session(session)
        return "ok"

    # 创建 KAIROS runtime
    runtime = KairosRuntime(
        state=KairosState(),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=mock_run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=15.0,
        is_worker_busy=lambda: False,
    )

    # 执行：手动触发一次 tick
    await runtime.wake("manual_test")

    # 验证：session.events 应该回滚到 5 条
    session_after = await session_service.get_session("test_app", "test_user", "test_session")
    events_count_after = len(session_after.events)

    # 关键断言：events 数量不应该增加
    assert events_count_after == events_count_before, (
        f"KAIROS tick 不应该污染 session.events！"
        f"执行前: {events_count_before} 条，执行后: {events_count_after} 条"
    )


@pytest.mark.asyncio
async def test_kairos_tick_records_to_recent_events():
    """
    [验证] KAIROS tick 结果应该记录到 recent_events，而不是 session.events

    区分：
    - session.events: 用户的对话历史（应该保持干净）
    - recent_events: KAIROS 的运行时事件（用于状态监控）
    """
    session_service = FakeSessionService(initial_events=[{"role": "user", "content": "test"}])
    saved, emitted, logged, save_state, emit_event, append_log = _make_kairos_callbacks()

    async def mock_run_turn(reason):
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=mock_run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=15.0,
        is_worker_busy=lambda: False,
    )

    # 执行 wake
    await runtime.wake("test_reason")

    # 验证：session.events 不变
    session = await session_service.get_session("test_app", "test_user", "test_session")
    assert len(session.events) == 1, "session.events 应该保持初始状态"

    # 验证：recent_events 有记录
    status = runtime.get_status()
    assert len(status["recent_events"]) > 0, "recent_events 应该记录事件"

    # 验证：emit_event 被调用（记录到 recent_events）
    assert len(emitted) > 0, "应该通过 emit_event 记录事件"


@pytest.mark.asyncio
async def test_multiple_kairos_ticks_no_accumulation():
    """
    [压力测试] 多次 KAIROS tick 不应该累积 session.events

    模拟真实场景：
    - 1 小时 = 240 次 tick
    - session.events 应该保持初始大小
    """
    session_service = FakeSessionService(initial_events=[{"role": "user", "content": "start"}])
    saved, emitted, logged, save_state, emit_event, append_log = _make_kairos_callbacks()

    tick_count = 0

    async def mock_run_turn(reason):
        nonlocal tick_count
        tick_count += 1

        # 模拟每次 tick 添加消息（如果没有回滚机制）
        session = await session_service.get_session("test_app", "test_user", "test_session")
        session.events.append({"role": "user", "content": f"tick {tick_count}"})
        session.events.append({"role": "model", "content": f"response {tick_count}"})
        await session_service.save_session(session)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=mock_run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=15.0,
        is_worker_busy=lambda: False,
    )

    # 执行 10 次 tick（模拟短时间内的多次触发）
    for i in range(10):
        await runtime.wake(f"tick_{i}")
        # 清空 emitted 以便下一次检查
        emitted.clear()

    # 验证：session.events 仍然是初始大小
    session = await session_service.get_session("test_app", "test_user", "test_session")
    assert len(session.events) == 1, (
        f"10 次 tick 后，session.events 应该仍然是 1 条，但实际是 {len(session.events)} 条"
    )


@pytest.mark.asyncio
async def test_kairos_does_not_break_user_chat():
    """
    [集成测试] KAIROS 不应该干扰用户的正常对话

    场景：
    1. 用户发起对话（添加到 session.events）
    2. KAIROS tick 执行
    3. 用户再次对话
    4. 验证只有用户消息在 session.events 中
    """
    session_service = FakeSessionService(initial_events=[])
    saved, emitted, logged, save_state, emit_event, append_log = _make_kairos_callbacks()

    async def mock_run_turn(reason):
        # 模拟添加 KAIROS 消息
        session = await session_service.get_session("test_app", "test_user", "test_session")
        session.events.append({"role": "user", "content": f"[KAIROS] {reason}"})
        session.events.append({"role": "model", "content": "idle"})
        await session_service.save_session(session)
        return "ok"

    runtime = KairosRuntime(
        state=KairosState(),
        save_state=save_state,
        emit_event=emit_event,
        append_log=append_log,
        run_turn=mock_run_turn,
        dex_bridge=FakeDexBridge(),
        tick_interval_seconds=15.0,
        is_worker_busy=lambda: False,
    )

    # 用户第一次对话
    session = await session_service.get_session("test_app", "test_user", "test_session")
    session.events.append({"role": "user", "content": "你好"})
    session.events.append({"role": "model", "content": "你好！"})
    await session_service.save_session(session)
    assert len(session.events) == 2

    # KAIROS tick
    await runtime.wake("background_check")

    # 验证：session.events 仍然是 2 条
    session = await session_service.get_session("test_app", "test_user", "test_session")
    assert len(session.events) == 2, "KAIROS tick 不应该增加 session.events"

    # 用户第二次对话
    session.events.append({"role": "user", "content": "今天天气如何？"})
    session.events.append({"role": "model", "content": "天气晴朗"})
    await session_service.save_session(session)

    # 最终验证：只有用户消息
    session = await session_service.get_session("test_app", "test_user", "test_session")
    assert len(session.events) == 4, "应该有 4 条用户对话消息"
    assert all("[KAIROS]" not in str(e) for e in session.events), "session.events 中不应该有 KAIROS 消息"