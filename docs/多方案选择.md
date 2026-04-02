# KAIROS 接入多方案选择

## 文档目的

本文汇总当前对本项目接入 KAIROS feat 的几个可行方案，并给出建议路线，方便在真正进入实现计划前先做架构取舍。

当前讨论范围聚焦 **Phase 1**，目标是先做一个 KAIROS-lite，而不是一次性复刻完整的 Claude Code KAIROS。

Phase 1 默认目标包括：

- 单 session assistant runtime
- tick / sleep / wake
- brief / status 事件输出
- Dex 后台任务接管
- append-only activity log

暂不优先纳入：

- 完整前端 attach/view 体验
- cron 表达式调度
- GitHub webhook / 外部触发器
- nightly memory distill / dream
- 完整 supervisor 多进程拆分

---

## 已确认的现有基础能力

本项目并不是从零开始，已经具备不少适合承接 KAIROS 的底座：

1. **会话宿主与运行时容器**
   - `src/adk_agent/main_web_start_steering.py`
   - 已有 `SteeringSession`、`SessionManager`

2. **持久化 Session / Event 能力**
   - `src/shared/db/custom_table_db_service.py`
   - 已支持 session state + events 的 SQLite 持久化

3. **流式 side-channel 输出**
   - `SteeringSession.stream_queue`
   - 适合承接 brief / status event

4. **后台任务执行能力**
   - `skills/dex/tools.py`
   - 已有 detached process + task state 管理

5. **append-only 记忆归档能力**
   - `memory_archive/...`
   - 已有 per-turn markdown 落盘逻辑

6. **节点注册 / 心跳 / 弱 supervisor-worker 倾向**
   - swarm registry
   - heartbeat daemon
   - self-claim task loop
   - wake / mailbox 原语

这些能力决定了：

> 本项目更适合做一个“独立的 assistant runtime 子系统”，而不是在普通 chat flow 上堆几个定时功能。

---

## 方案 A：将 KAIROS 实现为 `SteeringSession` 的内嵌 runtime

### 核心思路

- 新增 `src/adk_agent/kairos/` 模块
- 每个 `SteeringSession` 可选挂一个 `KairosService`
- `KairosService` 负责：
  - tick / sleep / wake
  - runtime state machine
  - brief/status 输出
  - Dex 后台任务接管
  - activity log 写入
- 复用当前：
  - session store
  - stream_queue
  - Dex
  - memory archive

### 优点

- 与现有项目结构最贴近
- 对现有主链路侵入最小
- Phase 1 落地成本最低
- 可以最大程度复用现有会话模型与持久化模型
- 后续还能平滑升级到 supervisor 模式

### 缺点

- 后续如果要做更强的多 session 生命周期控制，可能还要再抽一层 supervisor
- 第一版 runtime 容器仍然与 `SteeringSession` 绑定较深

### 适用结论

这是当前最适合本项目的方案，也是最适合作为 **Phase 1 推荐方案** 的路线。

---

## 方案 B：先抽一个轻量 supervisor，再挂单 worker runtime

### 核心思路

- 先新增一个 `KairosSupervisor`
- supervisor 管：
  - session registry
  - runtime metadata
  - wake 调度
  - attach/resume 路由
- 每个 assistant session 再对应一个 worker loop
- `SteeringSession` 更像 worker 内部执行宿主，而不是唯一入口

### 优点

- 架构更清晰
- 更接近长期理想形态
- 更适合未来做：
  - 多 session 管理
  - attach/resume
  - 独立 lifecycle
  - 多 worker 扩展

### 缺点

- 第一版明显更重
- 需要更早定义 supervisor/worker 边界
- 实现成本比 Phase 1 需要的最小能力更高
- 如果当前目标只是尽快落一个可运行 KAIROS-lite，会偏慢

### 适用结论

这是一个更强的中长期架构方向，但不适合作为当前仓库的最小第一步。

---

## 方案 C：直接在现有 `/api/chat` 主链路上继续打补丁

### 核心思路

- 在 `main_web_start_steering.py` 内直接增加：
  - assistant_mode
  - sleep / wake
  - 定时检查
  - brief
  - Dex 转后台
- 不额外抽出清晰的 runtime 子系统

### 优点

- 表面上看最快
- 文件最少、接线最少

### 缺点

- 容易进一步加重 `main_web_start_steering.py`
- 极易和 `WORKER_LOCK`、前台请求驱动模型冲突
- 会把 assistant runtime 和普通聊天路径搅在一起
- 后续大概率返工
- 风险最大

### 适用结论

不推荐。

---

## 推荐方案

当前建议采用：

> **方案 A：先做 `SteeringSession` 内嵌 runtime 的 KAIROS Phase 1，实现一个 KAIROS-lite；未来如果需要，再平滑升级到 supervisor 模式。**

推荐理由：

1. **最契合当前代码结构**
2. **复用率最高**
3. **能避免主链路大范围破坏**
4. **足够支持 Phase 1 的核心能力落地**
5. **后续仍保留架构演进空间**

---

## 建议的 Phase 1 实现边界

如果采用推荐方案，Phase 1 应明确控制范围，只做以下能力：

### 要做

- 单 session assistant runtime
- tick / sleep / wake
- minimal runtime state machine
- brief / status event 输出
- Dex 长任务后台接管
- append-only activity log
- 基础 KAIROS 管理 API（如 start / stop / wake / status）

### 后置

- cron 表达式
- webhook / GitHub trigger
- 完整 attach/view bridge
- nightly distill / dream
- 完整 supervisor 多进程架构

---

## 当前建议

如果没有额外约束，下一步建议沿着本文件的推荐路线继续推进：

1. 先确认采用 **方案 A**
2. 再写 **Phase 1 实施方案**
3. 再进入详细 implementation plan

这样能保证：

- 先把架构边界定住
- 再拆实施阶段
- 最后再写具体开发计划
