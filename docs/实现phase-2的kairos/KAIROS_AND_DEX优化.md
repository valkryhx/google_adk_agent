# KAIROS_AND_DEX 优化点

> 记录时间: 2026-04-04
> 背景: 在真实接口演示中，KAIROS 已经能够自主跟踪 Dex 后台任务，但当前展示与结果质量仍然不够强，必须尽快补强。

---

## 一、当前已验证具备的能力

通过真实接口联调，已经确认：

- agent 可以加载 Dex skill 并创建后台任务
- KAIROS 可以接手 Dex task 的跟踪责任
- KAIROS 会在 tick 中轮询 Dex 任务状态
- 当任务完成时，KAIROS 会自动记录完成事件

这说明 KAIROS + Dex 的主链路已经打通。

但同时，这次演示也暴露出几个必须马上增强的点。

---

## 二、必须马上增强的点

### 1. KAIROS 面板对 Dex 跟踪信息的展示太弱

### 现状
当前 KAIROS 面板主要展示：
- `mode`
- `tracked_dex_task_ids`
- `recent_events`

例如只会看到：

```text
mode: handoff
tracked_dex_task_ids: ["048c9869"]
```

这对开发者还能看懂，但对演示和实际使用都不够直观。

### 问题
用户真正关心的不是：
- “有一个 task_id 正在跟踪”

而是：
- 这个任务是什么
- 当前状态是什么
- 是成功还是失败
- 有没有结果摘要
- 日志里有什么关键信息

### 应立即增强成什么样
KAIROS 面板应该增加一个 **Tracked Dex Tasks** 区域，对每个 task 直接展示：

- `task_id`
- `status`
- `description`
- `created_at`
- `completed_at`
- `result_summary`
- `log_path`（如可用）

### 预期价值
这样用户一打开面板就能直接看懂：
- KAIROS 正在跟踪什么
- 跟踪结果是什么
- 有没有值得关注的问题

---

### 2. KAIROS 只记录了“完成事件”，但没有自动展开任务结果

### 现状
当前 `_poll_dex()` 发现任务完成时，只记录类似：

```text
Dex task 048c9869 completed: 演示 kairos 自动跟踪任务进度
```

### 问题
这条事件只告诉我们：
- 任务结束了

但没有告诉我们：
- 它实际做成了什么
- 输出里有没有关键结果
- 日志里有没有异常
- 这个 completed 是否真的是“高质量完成”

### 应立即增强成什么样
在任务状态变成 `completed` 或 `failed` 时，KAIROS 应自动：

1. 读取 Dex task 的 `result`
2. 读取日志尾部（如有）
3. 生成一份简洁摘要写入 `recent_events`

例如从：

```text
Dex task 048c9869 completed: 演示 kairos 自动跟踪任务进度
```

增强成：

```text
Dex task 048c9869 completed: 演示 kairos 自动跟踪任务进度
Result: task done
```

或失败时：

```text
Dex task 048c9869 failed: 演示 kairos 自动跟踪任务进度
Error summary: command exited with code 1
```

### 预期价值
这会让 KAIROS 从：
- “知道任务结束了”

升级到：
- “知道任务结束了，而且能告诉你它到底做成了什么”

---

### 3. Dex 任务命令构造质量不稳定，影响 KAIROS 跟踪价值

### 这次真实演示暴露的问题
在 task `048c9869` 中，Dex 记录下来的命令是：

```text
python -c "\"import time; print('task start'); time.sleep(10); print('task done')\""
```

明显多包了一层引号。

任务虽然被标记成了 `completed`，但结果内容并不理想，KAIROS 只能拿到一份很薄的完成信息。

### 问题本质
如果 Dex 启动的任务本身命令构造不稳定，那么：
- KAIROS 就算能自主跟踪
- 也只能跟踪一个“结果质量不高”的任务

最终表现就是：
- 看起来完成了
- 但没有真正有价值的结果摘要

### 应立即增强成什么样
需要优先排查并加固：
- agent 通过 `dex_start_task` 传入 `python -c` 时的引号处理
- Windows 场景下 `shlex.split(..., posix=False)` 的参数拆分是否符合预期
- Dex 执行器是否应对 `python -c` 场景做更明确的命令规范约束

### 预期价值
这一步不是只为了 Dex，本质上也是为了让 KAIROS 的“自主跟踪”真正有意义。

因为：
- KAIROS 的价值 = 跟踪能力 × 被跟踪任务的结果质量

---

## 三、建议的优先级

### P0：必须先做
1. **KAIROS 完成任务后自动展开 Dex 结果摘要**
2. **KAIROS 面板增加 Dex tracked task 明细展示**
3. **修 Dex 命令构造不稳定问题（尤其是 `python -c` 引号问题）**

这三项是下一步最应该马上做的优化。

---

## 四、为什么这是“马上要增强”的点

因为当前状态下，KAIROS 已经证明了：
- 它能自主跟踪后台任务

但用户体验上还停留在：
- “我得自己去猜 tracked task 是什么”
- “我得自己去 Dex JSON 里翻结果”
- “完成事件很薄，不够有解释力”

如果不补强这三点，KAIROS 虽然 technically 已经有 autonomous tracking 能力，但在实际演示和实际使用中，用户感受到的价值会明显不足。

---

## 五、一句话结论

下一步必须立即增强的不是“再多加几个状态字段”，而是：

> **让 KAIROS 把 Dex 跟踪结果真正展示出来、解释出来，并建立在稳定可靠的 Dex 执行结果之上。**
