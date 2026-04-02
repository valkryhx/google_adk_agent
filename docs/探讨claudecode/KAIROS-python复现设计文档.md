# KAIROS Python 复现设计文档

## 1. 文档目的

本文不是重复解释 KAIROS 的源码逻辑，而是把现有三份分析材料进一步落到 Python 复现层面，直接回答下面几个问题：

- Python 版应该拆成哪些模块
- 每个模块的职责边界是什么
- 哪些能力应先做最小原型，哪些应后置
- 哪些地方可以按 Python 工程习惯改写，哪些必须保留和源码一致的语义
- 如何在“源码不完整”的情况下，做一个**证据驱动、可逐步演进**的 KAIROS 复现方案

本文综合以下材料：

- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\docs\KAIROS-特性源码分析报告.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\docs\claudecode-best-KAIROS-相关文件清单.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\docs\KAIROS-社区资料筛选.md`
- `D:\git_codes\google_adk_helloworld_git\claude-reviews-claude\docs\ULTRAPLAN-Python复现设计文档.md`

本文默认读者已经知道 KAIROS 的大致目标：

> 它不是普通的前台聊天 REPL，而是一个长期存活、可定时唤醒、可被远程附着、可主动汇报状态，并能沉淀长期记忆的 assistant runtime。

---

## 2. 设计前提：这份复现文档如何处理“源码不完整”

在开始 Python 设计之前，必须先明确一个边界：

### 2.1 哪些是相对确定的直接证据

从现有源码和分析可较确定地得到：

- KAIROS 对应 `assistant mode`
- KAIROS 会影响命令注册、系统提示、工具池、状态位、bridge、memory、cron、brief
- KAIROS 强绑定 `brief`
- KAIROS 倾向长时自治、tick/sleep、异步子任务、阻塞命令自动后台化
- KAIROS 与 cron / scheduled tasks、bridge continuity、daily log memory、nightly dream 路径有关

可以直接支撑这些判断的关键文件包括：

- `src/main.tsx`
  - 负责 `kairosEnabled` 计算、`setKairosActive(true)`、assistant team 初始化接线、assistant prompt addendum 注入
- `src/commands.ts`
  - 负责 `/assistant`、`/brief`、`/proactive`、`/subscribe-pr` 注册
- `src/tools.ts`
  - 负责 `SleepTool`、`SendUserFileTool`、`PushNotificationTool`、`SubscribePRTool` 工具接线
- `src/constants/prompts.ts`
  - 负责 autonomous / tick / sleep 的主提示语义
- `src/memdir/memdir.ts` 与 `src/memdir/paths.ts`
  - 负责 assistant-mode daily log memory 路径和写入策略
- `src/bridge/initReplBridge.ts` 与 `src/bridge/bridgeMain.ts`
  - 负责 assistant session continuity / worker type / resume / attach 相关边界
- `src/tools/BashTool/BashTool.tsx`、`src/tools/PowerShellTool/PowerShellTool.tsx`
  - 负责 assistant mode 下阻塞命令自动后台化
- `src/tools/AgentTool/AgentTool.tsx`
  - 负责 assistant mode 下子代理强制 async
- `src/tools/BriefTool/BriefTool.ts`
  - 负责 brief entitlement / activation / assistant-mode bypass 逻辑
- `src/hooks/useScheduledTasks.ts` 与 `src/tools/ScheduleCronTool/prompt.ts`
  - 负责 cron / scheduled wake-up 相关基础能力

### 2.2 哪些是高可信推断，但不是完整源码实证

当前仍属于“高可信推断”的有：

- daemon supervisor 的完整生命周期
- `src/assistant/daemonBridge.ts` 内部细节
- 完整 bridge protocol
- 完整 session continuity 恢复流程
- assistant install / gate / discovery 真正实现

同时还要注意，`claudecode-best` 中 assistant 核心模块存在明确缺口：

- `src/assistant/index.ts`：stub
- `src/assistant/gate.ts`：stub
- `src/assistant/sessionDiscovery.ts`：stub
- `src/commands/assistant/assistant.ts`：stub

因此我们不能把这部分缺失逻辑当成已经完整恢复的源码事实。

### 2.3 这对 Python 复现意味着什么

因此，Python 版不应该一开始就假装自己能 100% 复刻 Claude Code 内部版本。

更合理的策略是：

1. **先复现已被证据支撑的行为语义**
2. **把缺失部分设计成可替换适配层**
3. **把高保真但未完全确认的部分放到后续 phase**

也就是说，Python 版应采用：

> **C：分阶段方案** —— 先做可运行最小原型，再做高保真增强，最后补足待源码确认的部分。

---

## 3. 设计目标

Python 版本建议优先满足下面几个目标：

1. 行为语义尽量贴近现有 KAIROS 证据
2. 模块边界清晰，便于后续补齐缺失能力
3. 主循环、调度、通知、记忆、远程附着解耦
4. 先做本地可运行 assistant runtime，再逐步外接 webhook / GitHub / push
5. 设计时把“证据确定”和“推断补位”分开

这意味着不建议一上来就做：

- 完整网页端远程 UI
- 真正 OS 级 daemon 安装器
- 复杂多进程 supervisor
- 所有外部渠道集成

更合理的做法是：

> 先做一个**可在本地 Python 进程中长期运行的 assistant service**，它具备 tick loop、cron、brief、memory、后台任务和基础状态机；再逐步把它包成 daemon，并补 bridge / remote attach / webhook 等能力。

---

## 4. Python 复现架构候选方案

在真正落模块设计之前，先比较 3 种 Python 复现路线。这样可以避免一开始就把实现形态写死。

### 4.1 方案 A：单进程 asyncio assistant service

定义：

- 一个 Python 进程同时承担：
  - session state
  - tick loop
  - cron 调度
  - brief 输出
  - memory 写入
  - background task 跟踪
  - 未来 bridge 接口

优点：

- 最容易做出 MVP
- 调试简单
- 对本地开发最友好
- 代码路径短，早期验证快

缺点：

- 隔离性最弱
- 长时间任务和主循环仍然容易相互影响
- 很难高保真模拟 “main coordinator 保持响应、worker 独立运行” 的语义
- 后续做 viewer attach / session resume 时，需要额外重构

适用阶段：

- 适合超早期 PoC
- 不适合作为最终推荐架构

---

### 4.2 方案 B：Supervisor + Worker Session 架构（推荐）

定义：

- 一个轻量 supervisor 管：
  - durable session metadata
  - start/stop/restart
  - future bridge attach
  - session discovery
- 每个 KAIROS session 由独立 worker 运行：
  - tick loop
  - task queue
  - background task policy
  - brief / memory / trigger handling

优点：

- 与现有源码证据最贴近
- 容易表达 perpetual session / resume / attach 语义
- 主协调者与实际执行者可以分离
- 未来扩展到 teammate fan-out 更自然
- 更容易模拟 assistant runtime 的长期存活与隔离

缺点：

- 比单进程 MVP 更复杂
- 需要先定义 supervisor / worker 的通信边界
- Phase 1 的工作量会稍高

适用阶段：

- 最适合作为本设计文档的默认目标架构
- Phase 1 可以先做“弱 supervisor + 单 worker”版本
- Phase 2 再补齐更完整的 session 管理

---

### 4.3 方案 C：事件溯源 / 队列优先架构

定义：

- 把 tick、cron fire、webhook、用户输入、后台任务完成都建模成 durable event
- worker 从事件流消费并产出新事件
- 更接近事件总线/任务编排系统

优点：

- 最强的可观察性
- 最容易做 replay / audit / resume
- 将来扩展多 assistant / 多 workspace 时非常强

缺点：

- 对当前目标来说过重
- 会显著增加初始复杂度
- 超出了现有 KAIROS 证据所要求的最低实现复杂度

适用阶段：

- 不建议作为第一版 Python 复现路线
- 只适合未来系统规模明显扩大后再考虑

---

### 4.4 推荐结论

推荐采用：

> **方案 B：Supervisor + Worker Session 架构**

理由：

1. 它是“复杂度”和“保真度”之间最好的平衡
2. 它最符合现有证据里反复出现的这些特征：
   - assistant mode
   - perpetual / resumable session
   - bridge attach
   - main loop responsiveness
   - forced async / backgrounded work
3. 它允许 Phase 1 用较轻实现先跑通，Phase 2 再逐步逼近真实形态

因此，下面的目录结构和模块设计，都以 **方案 B** 为默认前提。

---

## 5. 复现范围总览：三阶段方案

## 4.1 Phase 1：最小可运行原型（MVP）

目标：

> 在单机 Python 环境里，做出一个能“长期运行 + 定时唤醒 + 调度任务 + brief 汇报 + 记录状态”的最小 KAIROS 原型。

Phase 1 必做能力：

- async tick loop
- 本地 task queue
- blocking budget + background handoff
- cron trigger
- brief notifier
- JSONL state log
- append-only daily activity log
- 可测试的状态机

Phase 1 暂不做：

- 真正 GitHub webhook
- 真正 push notification
- 浏览器 viewer attach
- 多进程 daemon supervisor
- 完整 session continuity

这是最重要的一步，因为它先把 KAIROS 的“核心运行时语义”跑起来。

---

## 4.2 Phase 2：高保真增强

目标：

> 在 MVP 已稳定的前提下，把系统逐步向现有源码形态靠拢。

Phase 2 增强能力：

- daily log + distilled memory
- remote attach 骨架
- richer lifecycle state machine
- teammate/task fan-out
- webhook adapter 抽象
- GitHub 事件源抽象
- 更细粒度通知策略
- basic session continuity

这阶段的重点是：

- 把“本地长期服务”升级成“接近 assistant runtime 的系统”
- 但仍然不要求所有 Claude Code 内部实现细节都一模一样

---

## 4.3 Phase 3：待源码进一步确认后补齐

目标：

> 只在证据更充足时，补那些当前缺少完整实现细节的模块。

Phase 3 可能补的能力：

- daemon supervisor + child worker 精确分离
- 更真实的 remote bridge protocol
- 完整 viewer attach 模式
- 完整 session continuity / bridge pointer 机制
- push/file-send 外设化集成
- trust gate / entitlement / feature gate 的高保真模拟

这部分必须在文档里明确标注为：

> **待进一步源码确认，不在第一版 Python 复现中承诺完全一致。**

---

## 5. Python 版建议目录结构

建议采用如下目录结构：

```text
kairos/
  __init__.py
  constants.py
  models.py
  errors.py
  mode.py
  state_store.py
  scheduler.py
  queue.py
  service.py
  memory.py
  notifier.py
  background.py
  daemon_runner.py
  bridge_adapter.py
  triggers/
    __init__.py
    base.py
    cron_trigger.py
    manual_trigger.py
    webhook_trigger.py
  adapters/
    __init__.py
    cli_adapter.py
    jsonl_state_store.py
    markdown_memory_store.py
    noop_notifier.py
  tests/
    test_mode.py
    test_scheduler.py
    test_service.py
    test_background.py
    test_memory.py
    test_notifier.py
```

这个结构是参考 `ULTRAPLAN` 的 Python 复现文档思路做的，但它更偏“长期运行 runtime”，所以多了：

- `scheduler.py`
- `background.py`
- `daemon_runner.py`
- `bridge_adapter.py`
- `triggers/`
- `notifier.py`
- `memory.py`

---

## 6. 各模块职责设计

### 6.1 `constants.py`

负责：

- 默认 tick 间隔
- blocking budget
- cron 默认参数
- state log 文件名
- daily log 路径模板
- phase 名称常量

建议常量：

```python
DEFAULT_TICK_INTERVAL_SECONDS = 15.0
DEFAULT_BLOCKING_BUDGET_SECONDS = 15.0
DEFAULT_CRON_POLL_SECONDS = 1.0
DEFAULT_DAILY_LOG_DIRNAME = "logs"
DEFAULT_STATE_LOG_FILENAME = "kairos_state.jsonl"
DEFAULT_TASK_LOG_FILENAME = "kairos_tasks.jsonl"
```

说明：

- `15s` 这里可以作为默认 blocking budget，原因是社区资料和分析笔记都指向短阻塞预算语义
- 但文档里要注明：**这个值是设计选择，不是当前已恢复源码逐行实证得出的唯一权威值**

---

### 6.2 `models.py`

负责：

- dataclass
- 枚举
- TypedDict / 协议对象

建议核心枚举：

```python
from enum import Enum


class KairosMode(str, Enum):
    IDLE = "idle"
    SLEEPING = "sleeping"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    HANDOFF = "handoff"
    STOPPED = "stopped"


class TriggerKind(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    INTERNAL = "internal"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BACKGROUNDED = "backgrounded"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotifyLevel(str, Enum):
    NORMAL = "normal"
    PROACTIVE = "proactive"
```

建议核心 dataclass：

```python
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class KairosTask:
    task_id: str
    title: str
    payload: dict[str, Any]
    trigger_kind: TriggerKind
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = 0.0
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    background_job_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class KairosState:
    mode: KairosMode = KairosMode.IDLE
    active_task_id: Optional[str] = None
    last_tick_at: Optional[float] = None
    sleep_until: Optional[float] = None
    trust_accepted: bool = False
    brief_enabled: bool = True
    daemon_enabled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 设计说明

- `KairosMode` 对应的是运行时 phase，不是 UI display state
- `KairosTask` 负责统一表示手动任务、cron 触发任务、未来的 webhook 触发任务
- `KairosState` 只保留主循环真正需要的状态，不把所有 UI 状态混进去

---

### 6.3 `errors.py`

负责：

- 自定义异常

建议：

```python
class KairosError(Exception):
    pass


class KairosTriggerError(KairosError):
    pass


class KairosSchedulingError(KairosError):
    pass


class KairosBackgroundError(KairosError):
    pass


class KairosBridgeError(KairosError):
    pass
```

说明：

- 不要一开始就把异常体系做得太复杂
- 先保证每个子系统至少有一个边界异常即可

---

### 6.4 `mode.py`

负责：

- 根据当前状态推导运行 phase
- 决定是否进入 sleeping / running / handoff

这个文件应该尽量做成纯逻辑模块，避免网络和磁盘依赖。

建议提供：

```python
def compute_next_mode(state: KairosState, has_ready_task: bool, waiting_input: bool) -> KairosMode:
    ...
```

这样单元测试会很容易写。

---

### 6.5 `queue.py`

负责：

- task enqueue / dequeue
- 根据优先级挑选下一个任务
- 支持 trigger 统一落入队列

这层要和 scheduler 分开。原因是：

- scheduler 决定“什么时候触发”
- queue 决定“触发后怎么排队和执行”

---

### 6.6 `scheduler.py`

负责：

- tick loop
- cron 触发检查
- sleep_until 逻辑
- idle / wait / wake 决策

建议职责保持纯粹：

- 不直接执行任务
- 只负责产生“现在该唤醒 / 现在该 enqueue 什么”的结论

建议接口：

```python
class KairosScheduler:
    async def tick(self, now: float) -> list[KairosTask]:
        ...

    def should_wake(self, now: float) -> bool:
        ...

    def set_sleep_until(self, ts: float | None) -> None:
        ...
```

---

### 6.7 `background.py`

负责：

- 把超过 blocking budget 的任务转为后台执行
- 跟踪 background job 生命周期
- 提供“前台任务 -> 后台任务”的统一抽象

这个模块很关键，因为它对应 KAIROS 源码分析里很重要的一点：

> 主 agent 要保持响应，慢任务不能一直阻塞主循环。

建议接口：

```python
class BackgroundExecutor:
    async def start(self, task: KairosTask) -> str:
        ...

    async def poll(self, job_id: str) -> TaskStatus:
        ...

    async def result(self, job_id: str) -> dict:
        ...
```

Phase 1 可以先做成：

- `asyncio.create_task()` 的本地后台任务
- 不需要一开始就起子进程

---

### 6.8 `notifier.py`

负责：

- brief 输出
- 未来 push 通知
- 未来 file-send

建议 Phase 1 只定义统一接口：

```python
class Notifier:
    async def send(self, message: str, level: NotifyLevel = NotifyLevel.NORMAL) -> None:
        ...
```

然后先提供：

- `CliNotifier`
- `NoopNotifier`

未来再加：

- `WebhookNotifier`
- `PushNotifier`
- `AttachmentNotifier`

这样就能把“给用户输出”从主 service 中独立出去。

---

### 6.9 `memory.py`

负责：

- append-only daily activity log
- durable memory note 提取
- 为未来 dream/distill 预留接口

建议拆成两层：

1. `DailyLogWriter`
   - 只负责追加写日志
2. `MemoryDistiller`
   - 负责把日志压缩成 durable notes

Phase 1 只实现 `DailyLogWriter` 即可。

Phase 2 再补：

- 按天扫描
- 提取 durable notes
- 产出 Markdown memory index

---

### 6.10 `state_store.py`

负责：

- 保存/恢复 `KairosState`
- 保存/恢复 task 状态
- 提供抽象接口

建议定义协议：

```python
class StateStore(Protocol):
    async def load_state(self) -> KairosState: ...
    async def save_state(self, state: KairosState) -> None: ...
    async def append_task_event(self, event: dict[str, Any]) -> None: ...
```

Phase 1 实现：

- `JsonlStateStore`

Phase 2 可以再加：

- `SQLiteStateStore`（如果以后确实需要）

但默认仍建议 JSONL，因为它更接近现有分析里的存储思路。

---

### 6.11 `service.py`

这是 KAIROS Python 版的核心业务层。

负责：

- 挂接 scheduler / queue / notifier / memory / background executor
- 执行 tick loop
- 决定任务什么时候前台执行、什么时候转后台
- 在重要状态变化时发 brief
- 在合适时点写 state / log

建议它成为全系统的“协调器”。

建议接口：

```python
class KairosService:
    async def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    async def submit_task(self, title: str, payload: dict[str, Any], trigger_kind: TriggerKind) -> str:
        ...

    async def tick(self) -> None:
        ...
```

### 设计原则

- `service.py` 负责 orchestration
- 真正的“怎么记日志 / 怎么通知 / 怎么转后台 / 怎么判断唤醒”都下沉到专门模块
- 避免把所有逻辑都塞进一个超大文件

---

### 6.12 `daemon_runner.py`

负责：

- 把 `KairosService` 包装成长期驻留进程入口
- 提供 `start_forever()` / `shutdown()`
- 为未来 supervisor 化保留位置

但注意：

Phase 1 不要求它真的实现成 OS 级 system service。更适合先做成：

- 一个标准 Python async main loop
- 能持续运行
- 能优雅关闭

如果采用本文推荐的 Supervisor + Worker Session 架构，那么这里的更稳妥设计是：

- `daemon_runner.py` 只负责 supervisor 入口
- 真正的 worker loop 放到 `service.py` 或 `worker_runtime.py`（如果后续需要再拆）
- supervisor 负责 session 注册、查找、恢复和关闭
- worker 负责 tick、task、background job、brief、memory

这样可以避免把“进程管理”和“任务执行”混在一个文件里。

---

### 6.13 `bridge_adapter.py`

负责：

- 未来 remote attach / viewer client 接口的边界抽象

Phase 1 可以只定义接口、不实现真正网络桥接：

```python
class BridgeAdapter:
    async def publish_event(self, event: dict[str, Any]) -> None:
        ...

    async def next_inbound_prompt(self) -> dict[str, Any] | None:
        ...
```

Phase 2 再决定是否做：

- websocket adapter
- local viewer adapter
- file-based bridge mock

如果按推荐架构推进，bridge adapter 的职责更适合收敛为：

- supervisor 向 viewer 暴露 session 列表 / attach 点
- worker 向 bridge 发布状态事件、brief 消息、任务更新
- bridge 向 worker 注入外部 prompt / wake 事件

这能避免过早把未确认的 Claude 内部 bridge 细节写死。

---

### 6.14 `triggers/`

建议拆成单独目录，而不是把所有 trigger 写死在 scheduler 里。

建议文件：

- `base.py`：Trigger 协议
- `cron_trigger.py`：cron 调度源
- `manual_trigger.py`：手动触发
- `webhook_trigger.py`：保留接口，Phase 2 再实现

这样后续想加：

- GitHub PR activity
- file watcher
- API callback

都不会污染主循环。

---

## 7. 核心运行流程设计

下面给出推荐的 KAIROS Python 主循环流程。

### 7.1 启动流程

1. `daemon_runner.py` 创建 `KairosService`
2. `StateStore.load_state()` 恢复上次状态
3. 初始化 scheduler / queue / notifier / memory / background executor
4. 注册 triggers（至少 manual + cron）
5. 进入长期 tick loop

### 7.2 每次 tick 执行顺序

建议固定为：

1. 更新时间戳、写运行心跳
2. 检查是否有 trigger 产生活动
3. 将新 trigger 转为 task 入队
4. 检查后台任务状态更新
5. 选取可执行 task
6. 若无 task：进入 sleeping / idle
7. 若有 task：
   - 尝试前台执行
   - 若超过 blocking budget，则转 background
8. 若状态变化重要，则发送 brief
9. 写 state log / task log / daily log

### 7.3 为什么要这样排

原因是：

- trigger 先入队，才能和后台状态一起统一仲裁
- 先检查后台状态，避免重复执行已经完成的工作
- 通知要在状态稳定后发送，而不是边执行边乱发
- 日志最后落盘，避免中间状态不一致

---

## 8. 数据与持久化设计

## 8.1 短期状态

建议使用 JSONL：

- `kairos_state.jsonl`
- `kairos_tasks.jsonl`

原因：

- append-only 容易调试
- 对 daemon / 长活进程友好
- 符合现有分析里对 KAIROS / Claude Code 文本存储风格的理解

### 建议事件模型

```python
{
  "ts": 1712040000.0,
  "kind": "task_started",
  "task_id": "...",
  "title": "...",
  "trigger_kind": "cron"
}
```

```python
{
  "ts": 1712040015.0,
  "kind": "task_backgrounded",
  "task_id": "...",
  "job_id": "..."
}
```

```python
{
  "ts": 1712040030.0,
  "kind": "task_completed",
  "task_id": "..."
}
```

---

## 8.2 长期记忆

建议目录结构直接借鉴分析中 daily log 的思路：

```text
.memory/
  MEMORY.md
  logs/
    2026/
      04/
        2026-04-02.md
```

### 写入规则

- Phase 1：只追加到 daily log
- Phase 2：增加 distill 过程，把 daily log 压缩成 durable memory

### 为什么不一开始就维护 MEMORY.md

因为长期运行 agent 的记忆问题最怕两件事：

1. 每轮都重写结构化索引，容易损坏
2. 持续改写 MEMORY.md 会放大状态竞争和格式漂移

因此更合理的做法是：

- 在线阶段只 append
- 离线或低频阶段再 distill

---

## 9. 通知与输出设计

KAIROS 最关键的设计点之一，就是它不是普通终端打印，而是更接近“后台 agent 对用户做摘要式回传”。

因此 Python 版的输出建议也分层：

### 9.1 Phase 1

- 只做 `CliNotifier`
- 将重要状态变化输出为 brief 风格消息

例如：

- 任务开始
- 任务转后台
- 任务完成
- 任务失败
- 无任务，进入 sleep

### 9.2 Phase 2

再扩展：

- webhook notifier
- push notifier
- attachment notifier

### 9.3 设计原则

- 不是每次 tick 都输出
- 不是每次循环都打扰用户
- 只在“用户应知道的状态转折点”发送 brief

这点必须保留，因为它是 KAIROS 用户体验和普通 REPL 最大的差别之一。

---

## 10. 远程附着设计

### 10.1 Phase 1 不做真实远程附着

理由很简单：

- 现有源码对 bridge protocol 的细节并不完整
- assistant 内核也缺失
- 若过早实现，很容易写出与真实语义偏差很大的“假桥接”

### 10.2 Phase 2 只做“抽象先行”

建议先实现一个最小 bridge adapter 抽象：

- 发布本地状态变化事件
- 接收外部唤醒/输入 prompt

最早可以先用：

- 本地 websocket
- 或文件队列 mock

模拟 viewer/attach 的基本体验。

### 10.3 Phase 3 再考虑高保真

例如：

- viewer client
- persistent bridge session
- reconnect / continuity
- parent/child split

---

## 11. Python 版与源码一致、但可按 Python 习惯调整的地方

### 11.1 应尽量保持一致的地方

这些是语义层面，不建议轻易改：

- assistant mode 的长期运行定位
- brief 作为主要用户可见输出通道
- tick / sleep 思路
- blocking budget + background handoff
- cron / scheduled wake-up
- append-only daily log memory
- remote attach 作为后续能力而非首版必做

### 11.2 可按 Python 工程习惯调整的地方

这些可以改：

- TypeScript 模块拆法 -> Python package 拆法
- React/Ink UI -> CLI notifier + adapter
- GrowthBook gate -> 配置文件或 feature flag service
- 多层 app state -> dataclass + JSONL state store
- Bun/Node runtime -> asyncio runtime

核心原则是：

> **保留行为语义，不必机械复制实现语法。**

---

## 12. 风险与已知开放问题

### 12.1 assistant 内核缺失

当前恢复源码中 assistant 关键模块不完整，所以 Python 版不能声称“完整复刻 Claude 内部 KAIROS”。

### 12.2 bridge 细节不完整

因此远程附着必须后置，不应抢在 MVP 前面。

### 12.3 blocking budget 数值是否精确一致

当前我们可以合理采用短预算（例如 15 秒）作为设计值，但文档中应明确它是“设计选择 + 现有分析支持”，不是已完全确证的硬编码事实。

### 12.4 push / webhook / file-send 是否必须内建

这些能力在社区和分析文档里都被提到，但在 Python MVP 中应先抽象、后实现，不应一开始硬编码外部平台。

---

## 13. 推荐实现顺序

如果后续真要把这个设计落代码，推荐顺序如下：

### Step 1

先实现：

- `models.py`
- `state_store.py`
- `mode.py`
- `queue.py`

先把数据结构和状态机固定下来。

### Step 2

再实现：

- `scheduler.py`
- `background.py`
- `service.py`

把 tick loop + blocking budget + background handoff 打通。

### Step 3

再实现：

- `notifier.py`
- `memory.py`
- `triggers/cron_trigger.py`

让系统具备“长期运行 + 定时唤醒 + 向用户汇报 + 记忆落盘”的完整闭环。

### Step 4

最后再实现：

- `daemon_runner.py`
- `bridge_adapter.py`
- `webhook_trigger.py`

也就是把 MVP 提升到更接近真实 KAIROS runtime 的形态。

---

## 14. 推荐 MVP 架构落点

虽然本文前面比较了 3 种架构路线，但如果要真正开始写 Python 原型，建议把 MVP 具体落在下面这个中间形态上：

### 14.1 一个轻量 supervisor + 单 worker 的本地实现

也就是：

- 逻辑上采用 Supervisor + Worker Session 架构
- 实现上先只支持单 session
- 进程上允许先跑在一个 Python 进程里，但代码边界按 supervisor/worker 分开

这样做的好处是：

- Phase 1 不会因为多进程通信而过度复杂
- 但代码边界已经为后续拆分成真正 supervisor / worker 做好了准备
- 不会像纯单体 service 那样，后期一加 attach / session resume 就必须大改

### 14.2 MVP 的最小边界

推荐 MVP 最小边界如下：

- supervisor 只负责：
  - 启动 worker
  - 持有 session metadata
  - 暴露 session id / 状态
- worker 只负责：
  - tick loop
  - task queue
  - cron wake-up
  - background handoff
  - brief notifier
  - memory append-only 日志

### 14.3 为什么这比纯单进程 service 更稳妥

原因是它更符合现有证据里反复出现的这些特征：

- `claude assistant [sessionId]` viewer 语义
- perpetual / resumable session
- main coordinator responsiveness
- backgrounded work
- daemon / worker 分层倾向

因此它虽然比单进程 service 多一层抽象，但从长期演进看更省重构成本。

---

## 15. 最终结论

如果只用一句话总结这份设计文档，我会这样定义：

> KAIROS 的 Python 复现不应该一开始就追求“完整复刻 Anthropic 内部 daemon assistant”，而应该先落成一个证据驱动、可长期运行、支持 tick/sleep、cron 唤醒、brief 汇报、JSONL 状态、daily-log memory 的本地 assistant runtime，再按阶段补齐 remote attach、memory distill、daemon supervisor 和更高保真的桥接能力。

也就是说，这份设计的核心思想不是：

- 一口气把所有神秘功能都做完

而是：

- 先复刻最确定的运行语义
- 再逐步逼近高保真架构
- 对尚未确认的细节保留明确边界

这才是当前证据条件下，最稳妥也最工程化的 KAIROS Python 复现路线。
