# ULTRAPLAN Python 复现设计文档

## 1. 文档目的

本文不是重复解释 ULTRAPLAN 的源码逻辑，而是把前一份源码分析进一步落到 Python 实现层面，直接回答下面几个问题：

- Python 版本应该拆成哪些类
- 每个类的职责边界是什么
- 数据结构应该如何定义
- 各个接口如何设计
- 异步流程应该怎么串起来
- 哪些地方必须和源码保持一致，哪些地方可以按 Python 习惯调整

本文默认读者已经看过上一份源码分析报告，或者至少知道 ULTRAPLAN 的基本目标：

> 在远程会话中完成长时间规划，本地只负责触发、状态跟踪、审批承接和结果接收。

---

## 2. 设计目标

Python 版本建议优先满足下面几个目标：

1. 行为与源码一致
2. 模块边界清晰，便于测试
3. 网络层与状态机分离
4. UI 层可替换
5. 先做最小可用版本，再逐步扩展

这意味着不建议一开始就把终端 UI、Web UI、数据库、消息队列全部做进去。更合适的做法是先实现一个“可在命令行下运行的本地编排器”，把关键链路打通。

---

## 3. Python 版建议目录结构

建议采用如下目录结构：

```text
ultraplan/
  __init__.py
  constants.py
  models.py
  errors.py
  trigger.py
  prompt_builder.py
  scanner.py
  phase.py
  state_store.py
  remote_api.py
  service.py
  orchestrator.py
  adapters/
    __init__.py
    cli_adapter.py
    memory_state_store.py
  tests/
    test_trigger.py
    test_scanner.py
    test_phase.py
    test_prompt_builder.py
    test_service.py
```

### 各文件职责

- `constants.py`
  - 放常量、标记串、默认轮询参数、marker 字符串
- `models.py`
  - 放 dataclass、枚举、TypedDict、协议对象
- `errors.py`
  - 放自定义异常
- `trigger.py`
  - 关键字检测与输入改写
- `prompt_builder.py`
  - 构造远程 prompt
- `scanner.py`
  - 事件流扫描器，纯逻辑，不做网络
- `phase.py`
  - 由 scanner 状态和 session metadata 计算 UI phase
- `state_store.py`
  - 本地 ULTRAPLAN 状态存储接口和默认实现
- `remote_api.py`
  - 远程会话 API 客户端
- `service.py`
  - ULTRAPLAN 核心业务服务，编排完整生命周期
- `orchestrator.py`
  - 应用层入口，把 trigger、service、UI 适配器串起来
- `adapters/cli_adapter.py`
  - 终端输出、用户交互、通知适配
- `adapters/memory_state_store.py`
  - 基于内存的状态存储实现，便于先跑通

---

## 4. 核心数据结构设计

这一部分最重要。建议先把数据结构定清楚，再写业务逻辑。

## 4.1 常量设计

文件建议：`constants.py`

```python
ULTRAPLAN_KEYWORD = "ultraplan"
ULTRAPLAN_TELEPORT_SENTINEL = "__ULTRAPLAN_TELEPORT_LOCAL__"
APPROVED_PLAN_MARKERS = [
    "## Approved Plan (edited by user):\n",
    "## Approved Plan:\n",
]
DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_MAX_CONSECUTIVE_FAILURES = 5
DEFAULT_ULTRAPLAN_TIMEOUT_SECONDS = 30 * 60
DEFAULT_REMOTE_PERMISSION_MODE = "plan"
```

这里建议常量和源码保持一致，尤其是：

- `ULTRAPLAN_TELEPORT_SENTINEL`
- `APPROVED_PLAN_MARKERS`
- 轮询间隔
- 连续失败阈值

这些值不只是配置，而是协议的一部分。

---

## 4.2 枚举设计

文件建议：`models.py`

```python
from enum import Enum


class UltraplanPhase(str, Enum):
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    PLAN_READY = "plan_ready"


class ExecutionTarget(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"


class ScanKind(str, Enum):
    APPROVED = "approved"
    TELEPORT = "teleport"
    REJECTED = "rejected"
    PENDING = "pending"
    TERMINATED = "terminated"
    UNCHANGED = "unchanged"


class PollFailReason(str, Enum):
    TERMINATED = "terminated"
    TIMEOUT_PENDING = "timeout_pending"
    TIMEOUT_NO_PLAN = "timeout_no_plan"
    EXTRACT_MARKER_MISSING = "extract_marker_missing"
    NETWORK_OR_UNKNOWN = "network_or_unknown"
    STOPPED = "stopped"
```

这些枚举基本可以直接对应源码。

---

## 4.3 会话状态对象

文件建议：`models.py`

```python
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PendingChoice:
    plan: str
    session_id: str
    task_id: str


@dataclass
class LaunchPending:
    blurb: str


@dataclass
class UltraplanTaskState:
    task_id: str
    session_id: str
    session_url: str
    status: str = "running"
    phase: Optional[UltraplanPhase] = None
    command: str = ""
    notified: bool = False
    start_time: float = 0.0
    end_time: Optional[float] = None


@dataclass
class UltraplanAppState:
    launching: bool = False
    session_url: Optional[str] = None
    pending_choice: Optional[PendingChoice] = None
    launch_pending: Optional[LaunchPending] = None
    is_ultraplan_mode: Optional[bool] = None
    tasks: dict[str, UltraplanTaskState] = field(default_factory=dict)
```

### 设计说明

- `launching`
  - 对应源码里的 `ultraplanLaunching`
  - 用于远程 URL 还没拿到之前的防重入
- `session_url`
  - 对应源码里的 `ultraplanSessionUrl`
  - 代表当前存在活跃的远程 ULTRAPLAN 会话
- `pending_choice`
  - 对应源码里的 `ultraplanPendingChoice`
  - 代表 plan 已拿到，但执行地点还未定
- `launch_pending`
  - 对应源码里的 `ultraplanLaunchPending`
  - 代表启动前待确认的请求
- `is_ultraplan_mode`
  - 对应远程 metadata 同步值
- `tasks`
  - 复用任务视角来跟踪每个远程会话

---

## 4.4 远程事件模型

如果你不想一开始引入 pydantic，可以先用 dataclass + 原始 dict 混合方式。

建议定义最小模型：

```python
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class PollRemoteSessionResponse:
    new_events: list[dict[str, Any]]
    last_event_id: Optional[str]
    branch: Optional[str] = None
    session_status: Optional[str] = None


@dataclass
class PollResult:
    plan: str
    reject_count: int
    execution_target: ExecutionTarget
```

这里没有强行把全部 SDKMessage 建模成复杂 dataclass，是因为：

- 源码里的事件结构本身嵌套较深
- Python 原型阶段先使用 dict 更灵活
- 真正需要强类型的，只有最终业务结果

当行为稳定后，再逐步把 event block 建模。

---

## 4.5 扫描结果模型

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class ScanResult:
    kind: ScanKind
    plan: Optional[str] = None
    rejected_id: Optional[str] = None
    terminated_subtype: Optional[str] = None
```

这和源码的 union type 对应。

---

## 4.6 自定义异常

文件建议：`errors.py`

```python
class UltraplanError(Exception):
    pass


class UltraplanPollError(UltraplanError):
    def __init__(self, message: str, reason: str, reject_count: int, cause: Exception | None = None):
        super().__init__(message)
        self.reason = reason
        self.reject_count = reject_count
        self.cause = cause


class UltraplanPreconditionError(UltraplanError):
    pass


class UltraplanAlreadyActiveError(UltraplanError):
    pass
```

`UltraplanPollError` 应保留：

- `reason`
- `reject_count`

因为源码会把它们上报到日志和通知。

---

## 5. 类设计

下面给出推荐的 Python 类设计。

## 5.1 `UltraplanTrigger`

职责：

- 判断一段输入是否触发 ULTRAPLAN
- 返回触发位置
- 做关键字替换

建议接口：

```python
class UltraplanTrigger:
    def find_positions(self, text: str) -> list[tuple[int, int]]:
        ...

    def has_keyword(self, text: str) -> bool:
        ...

    def replace_keyword(self, text: str) -> str:
        ...
```

### 设计说明

这个类应该保持纯函数风格，不依赖全局状态，不访问网络。

### 最小实现建议

- 先复刻源码中的边界规则
- 再补单元测试
- 不要偷懒写成 `"ultraplan" in text.lower()`

---

## 5.2 `UltraplanPromptBuilder`

职责：

- 按源码顺序组装 prompt
- 注入 seed plan
- 避免在 instructions 中误带 `ultraplan` 关键字

建议接口：

```python
class UltraplanPromptBuilder:
    def __init__(self, instructions: str):
        self.instructions = instructions

    def build(self, blurb: str, seed_plan: str | None = None) -> str:
        ...
```

建议实现：

```python
class UltraplanPromptBuilder:
    def __init__(self, instructions: str):
        self.instructions = instructions.rstrip()

    def build(self, blurb: str, seed_plan: str | None = None) -> str:
        parts: list[str] = []
        if seed_plan:
            parts.extend([
                "Here is a draft plan to refine:",
                "",
                seed_plan,
                "",
            ])
        parts.append(self.instructions)
        if blurb:
            parts.extend(["", blurb])
        return "\n".join(parts)
```

### 设计说明

保持 builder 独立，方便以后针对不同远程后端替换 instructions。

---

## 5.3 `RemoteSessionApi`

职责：

- 创建远程 session
- 轮询远程事件
- 归档远程 session

建议接口：

```python
class RemoteSessionApi:
    async def create_ultraplan_session(
        self,
        *,
        initial_message: str,
        description: str,
        model: str,
        permission_mode: str = "plan",
        ultraplan: bool = True,
    ) -> dict:
        ...

    async def poll_remote_session_events(
        self,
        session_id: str,
        after_id: str | None = None,
        skip_metadata: bool = False,
    ) -> PollRemoteSessionResponse:
        ...

    async def archive_remote_session(self, session_id: str) -> None:
        ...
```

### 设计要求

这个类只负责远程 API 交互，不负责业务状态流转。

### 关键点：创建会话时写入初始 control_request

建议内部实现类似：

```python
def _build_initial_events(self, initial_message: str, permission_mode: str, ultraplan: bool) -> list[dict]:
    events: list[dict] = [
        {
            "type": "event",
            "data": {
                "type": "control_request",
                "request_id": f"set-mode-{uuid4()}",
                "request": {
                    "subtype": "set_permission_mode",
                    "mode": permission_mode,
                    "ultraplan": ultraplan,
                },
            },
        }
    ]
    if initial_message:
        events.append(
            {
                "type": "event",
                "data": {
                    "uuid": str(uuid4()),
                    "session_id": "",
                    "type": "user",
                    "parent_tool_use_id": None,
                    "message": {
                        "role": "user",
                        "content": initial_message,
                    },
                },
            }
        )
    return events
```

### 关键点：create 接口建议返回最小结果

```python
@dataclass
class RemoteSessionRef:
    session_id: str
    title: str
    url: str
```

不要把整个服务端返回体裸暴露给上层，尽量收窄接口。

---

## 5.4 `ExitPlanModeScanner`

这是最核心的业务逻辑类。

职责：

- 消费一批新的远程事件
- 记录见过的 `ExitPlanMode` 调用
- 记录对应 `tool_result`
- 判断当前状态

建议接口：

```python
class ExitPlanModeScanner:
    def __init__(self):
        self.exit_plan_calls: list[str] = []
        self.results: dict[str, dict] = {}
        self.rejected_ids: set[str] = set()
        self.terminated_subtype: str | None = None
        self.rescan_after_rejection: bool = False
        self.ever_seen_pending: bool = False

    @property
    def reject_count(self) -> int:
        return len(self.rejected_ids)

    @property
    def has_pending_plan(self) -> bool:
        ...

    def ingest(self, new_events: list[dict]) -> ScanResult:
        ...
```

### 建议拆出的小函数

```python
def content_to_text(content: object) -> str: ...
def extract_teleport_plan(content: object) -> str | None: ...
def extract_approved_plan(content: object) -> str: ...
def is_exit_plan_tool_use(block: dict) -> bool: ...
def is_tool_result_block(block: dict) -> bool: ...
```

### 为什么 scanner 必须独立

因为它是最适合做单元测试的部分。你可以直接把录制好的 event JSON 喂给它，验证：

- pending -> approved
- pending -> rejected -> pending -> approved
- approved 和 terminated 同时出现时，approved 优先
- teleport sentinel 正确分支

这部分一旦写成和网络轮询混在一起，就很难测试。

---

## 5.5 `UltraplanPhaseResolver`

职责：

- 根据 scanner 状态和 `session_status` 计算 `running / needs_input / plan_ready`

建议接口：

```python
class UltraplanPhaseResolver:
    def resolve(
        self,
        *,
        scanner: ExitPlanModeScanner,
        session_status: str | None,
        new_events: list[dict],
    ) -> UltraplanPhase:
        ...
```

建议实现：

```python
class UltraplanPhaseResolver:
    def resolve(self, *, scanner, session_status, new_events):
        quiet_idle = (
            session_status in {"idle", "requires_action"}
            and len(new_events) == 0
        )
        if scanner.has_pending_plan:
            return UltraplanPhase.PLAN_READY
        if quiet_idle:
            return UltraplanPhase.NEEDS_INPUT
        return UltraplanPhase.RUNNING
```

### 为什么单独拆这个类

因为 phase 判定是 UI 视角，而 scanner 是业务事件视角。拆开后更符合职责边界。

---

## 5.6 `UltraplanStateStore`

职责：

- 保存本地 ULTRAPLAN 状态
- 提供原子化更新接口

建议接口：

```python
from typing import Protocol, Callable


class UltraplanStateStore(Protocol):
    def get_state(self) -> UltraplanAppState:
        ...

    def update(self, updater: Callable[[UltraplanAppState], UltraplanAppState]) -> None:
        ...
```

### 简单内存实现

```python
class InMemoryUltraplanStateStore:
    def __init__(self):
        self._state = UltraplanAppState()

    def get_state(self) -> UltraplanAppState:
        return self._state

    def update(self, updater):
        self._state = updater(self._state)
```

### 为什么要加 store 抽象

因为这样之后你可以无痛替换成：

- 进程内 store
- Redis store
- SQLite store
- UI 框架内状态对象

而不改 service 层。

---

## 5.7 `UltraplanNotifier`

职责：

- 发送面向用户的通知
- 发送元通知
- 解耦 service 与具体 UI

建议接口：

```python
class UltraplanNotifier(Protocol):
    def info(self, message: str) -> None:
        ...

    def warning(self, message: str) -> None:
        ...

    def error(self, message: str) -> None:
        ...
```

如果是 CLI 实现，先用简单 stdout/stderr 即可。

---

## 5.8 `UltraplanService`

这是总编排类。

职责：

- 防重入检查
- 调用 precondition 检查
- 组装 prompt
- 创建远程会话
- 注册 task
- 启动后台轮询
- 处理成功、失败、停止

建议接口：

```python
class UltraplanService:
    async def launch(
        self,
        *,
        blurb: str,
        seed_plan: str | None = None,
        on_session_ready: callable | None = None,
    ) -> str:
        ...

    async def stop(self, task_id: str, session_id: str) -> None:
        ...
```

### 内部建议再拆几个私有方法

```python
async def _launch_detached(...): ...
async def _poll_until_approved(...): ...
def _build_launch_message(...): ...
def _build_session_ready_message(...): ...
def _build_already_active_message(...): ...
def _register_task(...): ...
def _complete_remote_execution(...): ...
def _prepare_local_choice(...): ...
```

这样 service 不会变成一个 500 行大类。

---

## 6. 接口设计建议

下面给出一套更具体的接口签名。

## 6.1 启动接口

```python
@dataclass
class LaunchUltraplanRequest:
    blurb: str
    seed_plan: str | None = None


@dataclass
class LaunchUltraplanResponse:
    accepted: bool
    message: str
    session_url: str | None = None
    task_id: str | None = None
```

service 层：

```python
async def launch(self, request: LaunchUltraplanRequest) -> LaunchUltraplanResponse:
    ...
```

### 为什么建议显式 request / response 对象

原因有两个：

1. 未来字段会变多，例如 model override、environment、timeout
2. 这样上层接口更稳定，不会随着参数增加而频繁改签名

---

## 6.2 轮询接口

```python
@dataclass
class PollContext:
    task_id: str
    session_id: str
    session_url: str
    timeout_seconds: int = DEFAULT_ULTRAPLAN_TIMEOUT_SECONDS
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
```

service 内部接口：

```python
async def _poll_until_approved(self, ctx: PollContext) -> PollResult:
    ...
```

这样可以很容易在测试中调短 timeout 和 interval。

---

## 6.3 停止接口

```python
@dataclass
class StopUltraplanRequest:
    task_id: str
    session_id: str


async def stop(self, request: StopUltraplanRequest) -> None:
    ...
```

---

## 6.4 前置条件检查接口

源码里有 `checkRemoteAgentEligibility()`。Python 版本也建议显式抽象出来。

```python
@dataclass
class EligibilityError:
    type: str
    message: str


@dataclass
class EligibilityResult:
    eligible: bool
    errors: list[EligibilityError]


class EligibilityChecker(Protocol):
    async def check(self) -> EligibilityResult:
        ...
```

### 为什么要单独抽象

因为前置条件以后可能包括：

- 是否登录
- 是否有 access token
- 是否配置远程环境
- 是否允许远程执行
- 是否具备当前 repo 的同步能力

不建议把这些条件直接写进 `UltraplanService.launch()` 里。

---

## 7. 控制流设计

下面给出完整控制流。

## 7.1 启动控制流

```text
用户输入
  -> Trigger 检测
  -> 触发 /ultraplan
  -> UI 显示启动确认
  -> UltraplanService.launch()
       -> 检查 launching/session_url
       -> 标记 launching=True
       -> 检查 eligibility
       -> build prompt
       -> create remote session
       -> 写入 session_url
       -> 注册 task
       -> 启动后台 poller
       -> 立即返回用户提示
```

## 7.2 轮询控制流

```text
后台 poll loop
  -> poll_remote_session_events(after_id)
  -> scanner.ingest(new_events)
  -> 如果 approved
       -> executionTarget=remote
       -> task completed
       -> 清理 session_url
  -> 如果 teleport
       -> pending_choice = {plan, session_id, task_id}
  -> 如果 terminated
       -> 抛出 UltraplanPollError
  -> 否则
       -> phase_resolver.resolve(...)
       -> 更新 task.phase
       -> sleep(3)
```

## 7.3 停止控制流

```text
用户停止
  -> UltraplanService.stop()
       -> archive remote session
       -> task.status = killed
       -> 清理 launching/session_url/pending_choice
       -> 发送 stopped 通知
```

---

## 8. 参考实现骨架

下面给出一个更接近真实项目结构的 Python 骨架。

## 8.1 `scanner.py`

```python
from dataclasses import dataclass
from .constants import ULTRAPLAN_TELEPORT_SENTINEL, APPROVED_PLAN_MARKERS
from .models import ScanKind, ScanResult


class ExitPlanModeScanner:
    def __init__(self):
        self.exit_plan_calls: list[str] = []
        self.results: dict[str, dict] = {}
        self.rejected_ids: set[str] = set()
        self.terminated_subtype: str | None = None
        self.rescan_after_rejection = False
        self.ever_seen_pending = False

    @property
    def reject_count(self) -> int:
        return len(self.rejected_ids)

    @property
    def has_pending_plan(self) -> bool:
        for call_id in reversed(self.exit_plan_calls):
            if call_id in self.rejected_ids:
                continue
            return call_id not in self.results
        return False

    def ingest(self, new_events: list[dict]) -> ScanResult:
        for event in new_events:
            self._consume_event(event)

        should_scan = bool(new_events) or self.rescan_after_rejection
        self.rescan_after_rejection = False

        found: ScanResult | None = None
        if should_scan:
            found = self._scan_latest_result()
            if found and found.kind in {ScanKind.APPROVED, ScanKind.TELEPORT}:
                return found

        if found and found.kind == ScanKind.REJECTED:
            self.rejected_ids.add(found.rejected_id)
            self.rescan_after_rejection = True

        if self.terminated_subtype:
            return ScanResult(kind=ScanKind.TERMINATED, terminated_subtype=self.terminated_subtype)

        if found and found.kind == ScanKind.REJECTED:
            return found

        if found and found.kind == ScanKind.PENDING:
            self.ever_seen_pending = True
            return found

        return ScanResult(kind=ScanKind.UNCHANGED)
```

注意：上面只是骨架，`_consume_event()` 和 `_scan_latest_result()` 还需补全。

---

## 8.2 `remote_api.py`

```python
import httpx
from uuid import uuid4
from .models import PollRemoteSessionResponse, RemoteSessionRef


class RemoteSessionApi:
    def __init__(self, base_url: str, headers_factory):
        self.base_url = base_url.rstrip("/")
        self.headers_factory = headers_factory

    async def create_ultraplan_session(self, *, initial_message: str, description: str, model: str, permission_mode: str = "plan", ultraplan: bool = True) -> RemoteSessionRef:
        headers = await self.headers_factory()
        title = self._build_title(description, ultraplan)
        events = self._build_initial_events(initial_message, permission_mode, ultraplan)
        payload = {
            "title": title,
            "events": events,
            "session_context": {
                "model": model,
            },
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{self.base_url}/v1/sessions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        session_id = data["id"]
        return RemoteSessionRef(
            session_id=session_id,
            title=data.get("title", title),
            url=f"{self.base_url}/sessions/{session_id}",
        )
```

### 注意

实际服务端 payload 不一定和这里完全一致。这里给的是结构设计示意，重点在于：

- 初始 events 必须有 `set_permission_mode`
- 会话标题要能标记 `ultraplan`

---

## 8.3 `service.py`

```python
import asyncio
import time
from .models import (
    LaunchUltraplanRequest,
    LaunchUltraplanResponse,
    PendingChoice,
    UltraplanTaskState,
    ExecutionTarget,
)
from .errors import UltraplanAlreadyActiveError, UltraplanPollError


class UltraplanService:
    def __init__(
        self,
        *,
        state_store,
        remote_api,
        prompt_builder,
        scanner_factory,
        phase_resolver,
        notifier,
        eligibility_checker,
        model_provider,
    ):
        self.state_store = state_store
        self.remote_api = remote_api
        self.prompt_builder = prompt_builder
        self.scanner_factory = scanner_factory
        self.phase_resolver = phase_resolver
        self.notifier = notifier
        self.eligibility_checker = eligibility_checker
        self.model_provider = model_provider

    async def launch(self, request: LaunchUltraplanRequest) -> LaunchUltraplanResponse:
        state = self.state_store.get_state()
        if state.launching or state.session_url:
            return LaunchUltraplanResponse(
                accepted=False,
                message="ultraplan already active",
            )

        self.state_store.update(self._mark_launching)

        try:
            eligibility = await self.eligibility_checker.check()
            if not eligibility.eligible:
                self.state_store.update(self._clear_launching)
                message = "\n".join(err.message for err in eligibility.errors)
                self.notifier.error(message)
                return LaunchUltraplanResponse(accepted=False, message=message)

            prompt = self.prompt_builder.build(request.blurb, request.seed_plan)
            model = self.model_provider.get_ultraplan_model()
            session = await self.remote_api.create_ultraplan_session(
                initial_message=prompt,
                description=request.blurb or "Refine local plan",
                model=model,
                permission_mode="plan",
                ultraplan=True,
            )

            task_id = self._register_task(session.session_id, session.url, request.blurb)
            self.state_store.update(lambda s: self._set_session_ready(s, session.url))
            asyncio.create_task(self._poll_until_approved(task_id, session.session_id, session.url))

            return LaunchUltraplanResponse(
                accepted=True,
                message="ultraplan launching",
                session_url=session.url,
                task_id=task_id,
            )
        except Exception:
            self.state_store.update(self._clear_launching)
            raise
```

这个骨架足够表达 service 的主要职责。

---

## 9. 测试设计

Python 版本最值得优先写测试的模块有四个。

## 9.1 `test_trigger.py`

至少覆盖：

- 普通句子触发
- `/ultraplan` 不走关键字触发
- `src/ultraplan/foo.py` 不触发
- `ultraplan?` 不触发
- 引号中的 `ultraplan` 不触发
- `please ultraplan this` 会正确改写成 `please plan this`

## 9.2 `test_scanner.py`

至少覆盖：

- 收到 `tool_use(ExitPlanMode)` 但没 `tool_result` -> `pending`
- 收到普通 reject -> `rejected`
- 收到 reject 后再出现新 plan -> 能继续扫描
- 收到 approved marker -> `approved`
- 收到 sentinel -> `teleport`
- 同批 events 有 approved 和 terminated -> approved 优先

## 9.3 `test_phase.py`

至少覆盖：

- `has_pending_plan=True` -> `plan_ready`
- `idle + no new events` -> `needs_input`
- `idle + 有 new events` -> `running`
- `requires_action + no new events` -> `needs_input`

## 9.4 `test_service.py`

至少覆盖：

- 已有 active session 时 launch 被拒绝
- eligibility 不通过时 launch 被拒绝
- 远程创建成功时 task 与 session_url 正确写入
- poll 返回 `remote` 时 task completed
- poll 返回 `local` 时写入 `pending_choice`
- poll 报错时调用 archive

---

## 10. 哪些部分必须保持和源码一致

下面这些点建议尽量不要改。

### 10.1 sentinel 字符串

`__ULTRAPLAN_TELEPORT_LOCAL__`

这已经是协议的一部分。如果你远程端与本地端都自己控制，可以改；但如果你想和现有事件格式兼容，就不要改。

### 10.2 approved plan marker

```text
## Approved Plan:
## Approved Plan (edited by user):
```

这两个 marker 是 plan 提取的锚点，建议保留。

### 10.3 control_request 的注入方式

一定要在创建 session 的初始 `events` 数组里注入 `set_permission_mode`。这不是实现细节，而是行为正确性的基础。

### 10.4 phase 推导规则

尤其是 `idle + newEvents.length > 0` 仍然视为 `running`，这个规则非常重要。

---

## 11. 哪些部分可以按 Python 习惯调整

### 11.1 状态存储

源码使用前端 AppState。Python 可改成：

- dataclass + 内存 store
- Redis
- SQLite
- event bus

### 11.2 通知系统

源码里有 `enqueuePendingNotification()`。Python 可替换成：

- logger
- callback
- websocket 推送
- CLI stdout

### 11.3 远程模型配置

源码通过 feature gate 和 GrowthBook 动态读模型。Python 原型可先简化为：

```python
class ModelProvider:
    def get_ultraplan_model(self) -> str:
        return "claude-opus-4-6"
```

### 11.4 UI 层

源码里的 `UltraplanLaunchDialog` 和 `UltraplanChoiceDialog` 是 React/Ink 组件。Python 可以先用：

- 纯命令行问答
- FastAPI 页面
- 文本 UI

业务层不应依赖具体 UI。

---

## 12. 最小实现优先级建议

如果你要真正动手做，不建议一次写完。更合理的顺序如下：

### 第一阶段：纯后端原型

完成：

- `constants.py`
- `models.py`
- `errors.py`
- `prompt_builder.py`
- `scanner.py`
- `phase.py`
- `remote_api.py`
- `service.py`

目标：

- 能从 Python 脚本里调用 `launch()`
- 能拉起远程 session
- 能轮询到 approved / teleport 结果

### 第二阶段：CLI 接入

完成：

- `trigger.py`
- `cli_adapter.py`
- `orchestrator.py`

目标：

- 用户在终端输入时能自动触发 ULTRAPLAN
- 能显示运行状态
- 能停止会话

### 第三阶段：更完整的执行承接

完成：

- 本地 `pending_choice` 后续执行逻辑
- 远程继续执行与本地执行的分流
- session 历史与 plan 持久化

---

## 13. 一份更完整的伪代码样例

```python
async def main_loop(user_input: str, orchestrator: "UltraplanOrchestrator"):
    if orchestrator.trigger.has_keyword(user_input):
        rewritten = orchestrator.trigger.replace_keyword(user_input).strip()
        request = LaunchUltraplanRequest(blurb=rewritten)
        response = await orchestrator.service.launch(request)
        print(response.message)
        return

    print("normal flow")


class UltraplanOrchestrator:
    def __init__(self, service, trigger):
        self.service = service
        self.trigger = trigger


async def poll_loop(service: UltraplanService, task_id: str, session_id: str, session_url: str):
    scanner = ExitPlanModeScanner()
    after_id = None
    last_phase = UltraplanPhase.RUNNING
    failures = 0
    deadline = time.monotonic() + 1800

    while time.monotonic() < deadline:
        try:
            resp = await service.remote_api.poll_remote_session_events(session_id, after_id)
            after_id = resp.last_event_id
            failures = 0
        except Exception as exc:
            failures += 1
            if failures >= 5:
                raise UltraplanPollError(
                    "network failure",
                    reason=PollFailReason.NETWORK_OR_UNKNOWN,
                    reject_count=scanner.reject_count,
                    cause=exc,
                )
            await asyncio.sleep(3)
            continue

        result = scanner.ingest(resp.new_events)

        if result.kind == ScanKind.APPROVED:
            service.complete_remote(task_id, session_url)
            return PollResult(
                plan=result.plan,
                reject_count=scanner.reject_count,
                execution_target=ExecutionTarget.REMOTE,
            )

        if result.kind == ScanKind.TELEPORT:
            service.prepare_local_choice(task_id, session_id, result.plan)
            return PollResult(
                plan=result.plan,
                reject_count=scanner.reject_count,
                execution_target=ExecutionTarget.LOCAL,
            )

        if result.kind == ScanKind.TERMINATED:
            raise UltraplanPollError(
                f"remote session ended: {result.terminated_subtype}",
                reason=PollFailReason.TERMINATED,
                reject_count=scanner.reject_count,
            )

        phase = service.phase_resolver.resolve(
            scanner=scanner,
            session_status=resp.session_status,
            new_events=resp.new_events,
        )
        if phase != last_phase:
            service.update_phase(task_id, phase)
            last_phase = phase

        await asyncio.sleep(3)

    raise UltraplanPollError(
        "timeout",
        reason=PollFailReason.TIMEOUT_PENDING if scanner.ever_seen_pending else PollFailReason.TIMEOUT_NO_PLAN,
        reject_count=scanner.reject_count,
    )
```

这个结构已经足够指导实际编码。

---

## 14. 实施建议

如果你的目标是“先做出一个能工作的 Python 版本”，建议把范围控制在以下内容：

- 只支持 `/ultraplan <prompt>`，先不做自动关键字高亮
- 只做命令行输出，不做复杂 UI
- 只做内存状态，不做数据库
- 先实现 `approved` 和 `teleport` 两条主干路径
- 先用录制事件测试 scanner，再接远程 API

这样更容易在短时间内验证架构正确性。

等主链路稳定后，再把：

- trigger 高亮
- 状态持久化
- 更完整 UI
- 更细粒度日志
- 更复杂远程环境选择

逐步补上。

---

## 15. 最终建议

如果要复现 ULTRAPLAN，不要把重点放在“远程会话创建”本身。真正决定这个特性能不能稳定工作的，是以下四个部分：

1. 创建会话时把 `plan + ultraplan` 模式写入初始事件
2. 本地维护 `launching / active / pending_choice` 三类关键状态
3. 用独立 scanner 解析事件流
4. 用统一 poll loop 把事件状态转换成本地 phase 和最终结果

只要这四块设计正确，Python 版就能和源码思路保持一致。

反过来说，如果这四块混在一起写，往往会出现：

- 启动竞态
- 远程第一轮模式错误
- plan 状态误判
- idle 状态误判
- 结果落点混乱

因此，建议先把类边界和接口边界搭好，再开始写网络和 UI。
