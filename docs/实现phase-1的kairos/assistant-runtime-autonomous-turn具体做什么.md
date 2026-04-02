# assistant runtime autonomous turn 具体做什么

## 一句话定义

在本项目的 KAIROS Phase 1 里，**assistant runtime autonomous turn** 指的是：

> 由 runtime 在 `wake` / `tick` 时主动触发的一次内部 assistant 回合。它先检查运行时状态和后台任务，再在必要时调用真实 agent 执行一轮 synthetic prompt，最后把结果沉淀为 `brief / status / recent_events / activity log`，并决定是否继续 `sleep`。

它不是普通的 `/api/chat` 用户问答，也不是“自己无限思考”，而是一次**面向后台自治状态管理的内部回合**。

---

## 1. 这轮回合的目标是什么

按 `KAIROS多方案选择.md` 与 `KAIROS-python复现设计文档.md` 的语义，Phase 1 的 autonomous turn 目标应聚焦在以下几点：

1. **检查当前 runtime 是否需要做事**
2. **处理已知后台状态变化**（尤其是 Dex 任务）
3. **必要时生成一条简洁的 brief/status**
4. **决定是否继续 sleep**
5. **把这轮决策结果写入持久化状态与活动日志**

所以它更像一个“后台 assistant 的自治检查回合”，而不是一个“面向用户长篇输出的聊天回合”。

---

## 2. 一次 autonomous turn 的推荐执行步骤

### Step 1：被唤醒

触发源可能包括：

- `POST /kairos/start`
- `POST /kairos/wake`
- 内部 tick
- Dex tracked task 状态变化
- 未来的 cron / webhook / 外部 trigger

Phase 1 里，主要先支持：

- start
- wake
- runtime tick

---

### Step 2：先做不依赖模型的运行时检查

这一层应该先用代码做 cheap checks，而不是立刻跑 LLM：

- runtime 是否 `enabled/running`
- 当前 `mode` 是什么
- 是否有 `pending_wake_reason`
- 当前 worker 是否被 `/api/chat` 占用
- 是否有 tracked Dex tasks
- 最近是否已有待汇报事件

这一层的目的，是避免把所有事情都变成一次模型调用。

---

### Step 3：处理无需模型即可判断的事项

这一步是 runtime 语义本身，典型动作包括：

#### 3.1 Dex 状态轮询

- 读取 `tracked_dex_task_ids`
- 查询 Dex task 当前状态
- 如果任务 `completed` / `failed`：
  - 生成一条状态事件
  - 写入 `recent_events`
  - 写入 activity log
  - 从 tracked 列表移除

#### 3.2 前台忙碌避让

如果当前 `WORKER_LOCK.locked()`：

- 不抢占 `/api/chat`
- 不跑真实 agent turn
- 记录：`worker busy, skip kairos tick`
- 保留 `pending_wake_reason`
- 直接返回

#### 3.3 无事可做时继续 sleep

如果没有任何新任务、没有 Dex 完成、没有需要汇报的状态：

- 可以不跑模型
- 直接进入 / 保持 `sleeping`
- 按需写一条轻量 status，或静默返回

---

### Step 4：只有“确实需要 assistant 判断”时，才触发真实 agent 回合

这一轮才是真正意义上的 autonomous assistant turn。

此时应由 runtime 构造一条 **synthetic prompt**，例如：

```text
[KAIROS_TICK]
reason=manual_smoke

你现在处于 assistant runtime 模式。
请基于当前 runtime 状态做一次自治检查：
- 是否有值得 brief 给用户的状态变化
- 是否有 Dex 已完成任务需要摘要
- 如果没有实质工作，直接进入 sleep
- 输出应简洁，不要像普通聊天那样展开
```

它本质上不是“用户消息”，而是 system/runtime 发给 agent 的内部工作指令。

---

### Step 5：复用真实 ADK Runner 主链路执行这一轮

按当前仓库设计，正确做法不是重新抄一份执行逻辑，而是：

- 从 `SteeringSession.run_task()` 抽出共享执行骨架
- `/api/chat` 走这条骨架
- `run_kairos_turn()` 也走这条骨架

即：

```text
run_kairos_turn(reason)
-> _run_agent_turn(synthetic_prompt, yield_chunks=False)
-> ADK Runner
-> 收集输出
```

这样 KAIROS autonomous turn 与普通前台聊天共享同一条核心执行通道，只在输入来源和输出消费方式上不同。

---

### Step 6：将结果归一为 runtime 可消费的产物

这轮 agent 执行完成后，不应只停留在文本输出，而应归一为 KAIROS runtime 状态：

- `report_swarm_event()`
- `session.state["kairos"]["recent_events"]`
- append-only `_kairos.md` activity log

也就是说，**brief/status/event/log 才是 autonomous turn 的最终产物**。

---

### Step 7：结束时更新状态机并重新 sleep

一轮结束后，应更新：

- `mode`
- `busy`
- `sleep_until`
- `pending_wake_reason`
- `tracked_dex_task_ids`
- `recent_events`

典型收尾状态：

- `mode = sleeping`
- `busy = false`
- `pending_wake_reason = null`
- 设置下次 `sleep_until`

这样一次 autonomous turn 才算真正闭环。

---

## 3. 在本项目里，这一轮“实际应该处理什么”

结合当前仓库和 Phase 1 边界，一次正确的 autonomous turn 最适合处理下面 4 类事情。

### 3.1 状态汇报

例如：

- `kairos runtime started`
- `wake requested: manual_smoke`
- `worker busy, skip kairos tick`
- `no substantive updates, returning to sleep`

### 3.2 Dex 后台任务结果处理

例如：

- `Dex task abc12345 completed`
- `Dex task abc12345 failed`
- 生成简洁 summary/brief
- 从 tracked 列表删除已完成项

### 3.3 sleep / wake 决策

例如：

- 有事情 -> 运行一轮 assistant turn
- 没事情 -> 直接 sleep
- 前台忙 -> 跳过本轮

### 3.4 持久化 runtime 痕迹

例如：

- 更新 `session.state["kairos"]`
- 写 `recent_events`
- 写 `_kairos.md`

---

## 4. Phase 1 不应该让它做什么

按当前 Phase 1 边界，autonomous turn **不应扩张成完整 daemon assistant 系统**。因此本阶段不应要求它：

- 完整 attach/view 体验
- cron 表达式调度全套能力
- GitHub webhook / 外部触发器
- nightly distill / dream
- 完整 supervisor 多进程架构
- 自动把所有工具调用都改造成后台化

也就是说，Phase 1 的目标是：

> 先跑通“自治检查 + brief/status + Dex tracking + sleep/wake”的最小运行时语义。

---

## 5. 当前代码已经做到什么、还没做到什么

### 已做到

当前已经落好的能力包括：

- KAIROS 状态模型
- activity log
- Dex bridge
- runtime 基本状态机壳子
- start/stop/wake/status API
- busy 避让探针
- 单元测试与 smoke test

### 还没真正打通的核心点

当前真正缺的，是这一条链：

```text
wake/tick
-> runtime 判断是否值得跑 agent
-> run_kairos_turn()
-> 复用 run_task 的真实 Runner 主骨架
-> 输出 brief/status
-> 写 recent_events / activity log / stream_queue
-> sleep
```

也就是说，当前代码已经有：

- 状态层
- API 层
- runtime 壳子
- 持久化与日志

但还没有完全实现：

- **真实 autonomous turn 驱动真实 ADK Runner**
- **后台 tick loop 自动触发这轮 turn**
- **`run_kairos_turn()` 复用 `run_task()` 主执行链路**

---

## 6. 对本项目最准确的定义

如果要用一句更贴近本仓库的话来定义：

> assistant runtime autonomous turn = 由 `KairosRuntime` 在 wake/tick 时触发的一次内部 `SteeringSession` agent 回合；它先处理 Dex/忙碌等硬状态，再在必要时通过 synthetic prompt 调用共享 ADK Runner 主链路，生成简洁 brief/status，并最终回到 `sleeping` 状态。

这就是 KAIROS 文档语义在当前项目里的最小、正确落点。
