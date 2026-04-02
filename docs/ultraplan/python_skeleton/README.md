# ULTRAPLAN Python 原型骨架

这个目录保存了一套用于复现 ULTRAPLAN 核心架构的 Python 原型骨架。它不是生产代码，但已经具备较完整的模块边界、transport/runtime 行为、测试覆盖和最小 demo 入口。

## 当前已经实现的能力

- 常量、数据模型、错误模型
- trigger / prompt builder / scanner / phase resolver 这几类纯逻辑模块
- precondition checker 接口与默认 allow-all 实现
- 拆分后的远端 API 层：`RemoteSessionApi` + `HttpxRemoteSessionTransport`
- transport builders：headers、create/events/archive URL、title、create-session payload
- 在未注入 client 时构建运行时 `httpx.AsyncClient`
- HTTP 状态码映射：auth / not-found / rate-limit / server / transport error
- create / poll 响应结构校验
- backend 返回的 `url` 与 `branch` 元数据解析
- service 层：launch / stop / poll_once / poll_until_terminal / task 状态流转 / pending local handoff
- 最小 demo 入口：`run_demo(...)`
- pytest 覆盖：纯逻辑、transport 组合、runtime 行为、fake-server 风格 round trip、CLI/demo

## 当前有意不做的部分

- 真实 Claude Web 后端联通
- 完整 CLI 产品化交互
- UI 层
- 持久化 state store
- 生产级 retry/backoff/telemetry
- 真正的端到端外部服务集成测试

## 依赖

- 运行时依赖：`httpx>=0.27`
- 开发依赖：`pytest>=8.0`

安装方式：

```bash
pip install -e .[dev]
```

## 运行测试

```bash
PYTHONIOENCODING=utf-8 pytest tests -q
```

## CLI / Demo 用法

当前可用的最小入口有两个：

- `ultraplan/cli.py` 里的 `run_demo(...)`
- `python -m ultraplan ...` 模块入口

### 方式 1：在代码里直接调用 `run_demo(...)`

它的职责是：

1. 调用 `service.launch_request(...)`
2. 从 `session_url` 自动提取 `session_id`
3. 调用 `service.poll_until_terminal(...)`
4. 返回一个统一的结果字典

返回状态可能是：

- `rejected`
- `launch_only`
- `completed`
- `phase`

示例：
```python
import asyncio

from ultraplan.cli import run_demo
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


async def main():
    service = UltraplanService(
        state_store=InMemoryUltraplanStateStore(),
        remote_api=RemoteSessionApi(),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await run_demo(
        service=service,
        blurb="please plan this task",
    )
    print(result)


asyncio.run(main())
```

### 示例 2：使用更接近真实 transport 的配置

```python
import asyncio

from ultraplan.cli import run_demo
from ultraplan.notifier import StdoutNotifier
from ultraplan.phase import UltraplanPhaseResolver
from ultraplan.preconditions import AllowAllPreconditionChecker
from ultraplan.prompt_builder import UltraplanPromptBuilder
from ultraplan.remote_api import HttpxRemoteSessionTransport, RemoteSessionApi
from ultraplan.service import UltraplanService
from ultraplan.state_store import InMemoryUltraplanStateStore


async def main():
    transport = HttpxRemoteSessionTransport(
        base_url="https://example.invalid",
        access_token="token",
        organization_uuid="org",
        allow_stub_responses=False,
        timeout_seconds=30.0,
    )
    service = UltraplanService(
        state_store=InMemoryUltraplanStateStore(),
        remote_api=RemoteSessionApi(base_url="https://example.invalid", transport=transport),
        prompt_builder=UltraplanPromptBuilder("INSTRUCTIONS"),
        phase_resolver=UltraplanPhaseResolver(),
        notifier=StdoutNotifier(),
        precondition_checker=AllowAllPreconditionChecker(),
    )

    result = await run_demo(
        service=service,
        blurb="please plan this task",
    )
    print(result)


asyncio.run(main())
```

说明：
- `allow_stub_responses=False` 时，transport 会尝试构建真实 `httpx.AsyncClient`
- 如果你没有接真实后端，这种写法更适合测试 transport wiring，而不是得到真实业务结果

### 方式 2：直接命令行运行

在包目录下执行：

```bash
PYTHONIOENCODING=utf-8 python -m ultraplan "please plan this task"
```

预期行为：
- 会打印一个 JSON 结果
- 如果 launch 被拒绝，进程退出码为 `1`
- 如果返回 `completed` 或 `phase`，进程退出码为 `0`

返回 JSON 的典型字段包括：

- `status`
- `message`
- `session_url`
- `plan`
- `execution_target`
- `phase`

当前这个 `python -m ultraplan` 入口仍然是最小原型入口，默认使用：

- `InMemoryUltraplanStateStore`
- `RemoteSessionApi()`
- `UltraplanPromptBuilder("INSTRUCTIONS")`
- `UltraplanPhaseResolver()`
- `StdoutNotifier()`
- `AllowAllPreconditionChecker()`

如果你要做真实联调，通常还是会自己显式构造 service，再调用 `run_demo(...)`。

## 目录结构

- `ultraplan/` — 包代码
- `tests/` — pytest 测试

## 当前包内主要模块

- `ultraplan/trigger.py` — 判断输入是否应该触发 ULTRAPLAN
- `ultraplan/prompt_builder.py` — 构造初始远端规划 prompt
- `ultraplan/scanner.py` — 从远端事件中提取 approve / reject / teleport 信号
- `ultraplan/phase.py` — 把非终态 poll 结果映射为 UI 侧 phase
- `ultraplan/remote_api.py` — payload 构造、runtime transport、响应校验、HTTP 错误映射
- `ultraplan/service.py` — launch / stop / poll_once / poll_until_terminal / 状态流转
- `ultraplan/state_store.py` — 当前默认的内存态 state store
- `ultraplan/cli.py` — 最小 demo 入口

## 下一步最值得继续做的方向

- 增加真正的 `python -m ...` 入口
- 把 fake server 抽成独立测试 helper
- 增加持久化 state store
- 增加更高层的 service + transport 集成测试
