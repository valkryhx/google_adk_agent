# Kairos Panel Visual Design Brief (Phase 4A)

## Design Direction

**Theme:** 夜间值班台 / Autonomous Ops Console  
**Tone:** 深色、克制、精密、高密度，但不是“黑底 JSON 调试面板”。  
**Rememberable detail:** 右侧时间线不是普通日志列表，而是像“任务推进轨迹带”——每条事件有明确等级、事件类型标签、微弱发光边界与纵向时间轴，让人第一眼就知道 Kairos 不是静态状态机，而是在持续推进工作。

这个方向适合当前 4A 目标，因为用户真正的痛点不是缺少更多字段，而是**看不清 Kairos 何时做了什么、为什么停、为什么继续**。所以视觉重点不该只是“更多卡片”，而应该是：

1. 左侧像驾驶舱：看现在
2. 右侧像飞行记录仪：看过程
3. 两边同时存在，形成“可解释 autonomy”的感觉

---

## Layout Recommendation

### Overall modal
- 宽度从当前 `max-width: 640px` 提升到 **1180px ~ 1280px** 桌面上限
- modal body 改为 **左右双栏 grid**
- 左栏约 `58%`，右栏约 `42%`
- modal 高度建议限制在 `80vh ~ 86vh`
- 两栏都各自内部滚动，避免整个 modal 变成长页面

### Left column: Live Snapshot
分成 4 个视觉层级更强的卡片组：

1. **Runtime Overview**
   - mode / running / busy / trigger / sleep_until
   - 以状态 pill + 小型指标行展示，而不是整段 monospace 文本

2. **Workflow & Planned Actions**
   - workflow 当前阶段
   - planned actions 列表
   - blocked reason / guardrail / decision explanation

3. **Execution Evidence**
   - tracked dex tasks
   - result summaries
   - unfinished work / proactive candidates

4. **Controls Dock**
   - start / stop / wake / refresh / schedules / dex handoff
   - 控件区独立成一个更轻的操作卡，不与状态区混在一起

### Right column: History Timeline
- 顶部固定一个小 header：
  - `Session History`
  - session scope 提示（session/app/user）
  - optional sort toggle / refresh hint
- 下方是纵向 timeline rail
- timeline item 用卡片而不是纯文本
- 每条 item 显示：
  - kind badge
  - title
  - timestamp
  - message
  - optional workflow/stage/task linkage metadata

---

## Visual System

### Color palette
避免常见 AI 紫渐变。推荐偏 **石墨黑 + 冷青绿 + 琥珀告警**：

- `--kairos-bg: #0a0f14`
- `--kairos-panel: #101923`
- `--kairos-panel-2: #13202c`
- `--kairos-border: rgba(148, 163, 184, 0.14)`
- `--kairos-text: #e6edf5`
- `--kairos-muted: #8aa0b6`
- `--kairos-accent: #53e0c1`
- `--kairos-accent-soft: rgba(83, 224, 193, 0.14)`
- `--kairos-warn: #f4b860`
- `--kairos-danger: #ef6b73`
- `--kairos-info: #6ec1ff`

### Typography
在现有项目里不强行引入复杂字体加载链时，建议：
- 标题：`"Google Sans", "Segoe UI", sans-serif`
- 数据/时间轴标签：`"Consolas", "SFMono-Regular", monospace`
- 正文：继续现有 sans，但通过字重/间距区分层级

重点不是换花哨字体，而是**建立明显层级**：
- Modal title：18-20px / 600
- Section label：11-12px / uppercase / letter spacing
- Card title：13-14px / 600
- Body text：12-13px
- Metadata：11px monospace

### Surface treatment
- modal 背景不再纯白，改为深色面板
- 卡片边缘用 1px 低对比边框 + 柔和内发光
- timeline rail 用一条垂直渐变线
- state pills 用低饱和填充，不搞彩虹标签
- 让“running / blocked / handoff / waiting_input”这类状态一眼可扫

---

## Component Styling Guidance

### Runtime status card
把当前 `formatKairosStatus()` 输出的纯文本块，逐步视觉转成：
- 一行状态 pills
- 下方 2 列 key-value metrics
- 重要字段优先：mode / trigger / last_tick_at / sleep_until

### Planned actions / workflow cards
- 每个 action 做成小 list-row
- action kind 左侧带微图标感圆点/色条
- workflow stage 用步骤高亮或 stage marker

### History timeline item
每条 timeline item 建议结构：
- 左：时间轴节点（圆点 + 连接线）
- 右：事件卡片
  - badge（follow_up / task_completion / brief / guardrail）
  - title
  - timestamp
  - message
  - meta row（workflow/stage/task_id）

颜色建议：
- `follow_up` → accent cyan-green
- `task_completion` → cool blue/green
- `guardrail` → amber / red
- `brief` → neutral steel
- `status` → subdued gray-blue

### Controls area
按钮仍然保留现有功能，但视觉改成：
- primary action：实心 accent
- destructive/stop：低饱和 danger outline
- 次级动作：深底细边框
- 控件区统一在底部或左栏顶部次级区，不要散在整个面板里

---

## Motion
保守但精致：
- modal 打开：轻微上浮 + fade in
- timeline items：staggered fade-in（只在首次渲染）
- cards hover：微小亮度提升 + 边框 accent 化
- buttons hover：背景/边框 120ms 过渡
- 不要做夸张玻璃漂浮动画，避免影响运维工具感

---

## Practical Implementation Notes

在当前代码结构下，推荐这样落地：

### HTML
在 `src/adk_agent/static/index.html` 中新增这些结构 id/class：
- `kairosConsole`
- `kairosLiveColumn`
- `kairosHistoryColumn`
- `kairosHistoryHeader`
- `kairosHistoryTimeline`
- `kairosOverviewCard`
- `kairosControlsCard`

### CSS
在 `src/adk_agent/static/style.css` 中新增一组专属类，而不是继续所有内容都写 inline style：
- `.kairos-modal`
- `.kairos-console`
- `.kairos-column`
- `.kairos-card`
- `.kairos-card-title`
- `.kairos-pill`
- `.kairos-metric-grid`
- `.kairos-timeline`
- `.kairos-timeline-item`
- `.kairos-timeline-dot`
- `.kairos-timeline-content`

### JS
在 `src/adk_agent/static/script.js` 中保留现有 formatter 架构，但新增：
- `formatKairosOverview(kairos)`
- `formatKairosHistoryTimeline(entries)`
- `renderKairosTimelineCards(entries)`

如果想先低风险推进：
- 第一版 timeline 仍可输出格式化文本，但挂在卡片容器里
- 第二版再升级为真正 DOM cards

---

## Recommended Aesthetic Choice

我建议这次**不要走极简白板风，也不要走赛博霓虹过度风**。  
最合适的是：

> **“Dark operator console with calm confidence”**

理由：
- 它和 Kairos 的“长期自治、可观测、可解释”定位一致
- 比当前表单式 modal 更像真正的 autonomy cockpit
- 比夸张 sci-fi 更容易长期使用
- 对现有 vanilla HTML/CSS/JS 改造成本适中

---

## How to Fold This Into 4A Plan

把它纳入 4A Task 3 / Task 4 即可：
- Task 3 负责双栏结构 + visual system + responsive layout
- Task 4 负责 timeline render + current snapshot cards 的前端映射

如果你要继续，我下一步可以直接用工具把这份视觉 brief **写回 4A plan / 或直接开始按这个风格改 `index.html + style.css + script.js` 的实现任务**。
