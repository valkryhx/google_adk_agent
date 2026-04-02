# KAIROS 社区资料筛选

## 1. 说明

本文只整理目前公开社区资料里，和 **Claude Code / KAIROS / assistant mode** 相关、且相对有信息量的来源。

目标不是把所有搜索结果都堆出来，而是回答两个问题：

1. 目前社区里到底哪里有值得看的 KAIROS 讨论
2. 哪些来源其实信息价值不高，不值得投入时间

---

## 2. 总体结论

当前公开社区资料的结论很明确：

> **KAIROS 的主要信息源不是 Reddit，而是 GitHub 上的源码分析、镜像仓库和少量 issue / design proposal。**

换句话说：

- **高价值来源**：GitHub issue、源码镜像、分析仓库
- **中低价值来源**：Reddit、HN、Lobsters 的泛讨论搜索结果
- **缺失来源**：官方 Anthropic / Claude Code 正式公开文档

所以如果要高效查 KAIROS，优先级应该是：

1. GitHub 分析资料
2. 本地还原源码
3. 其他社区讨论

而不是反过来。

---

## 3. 最值得看的社区来源

### 3.1 `forkwright/aletheia#2260`

链接：`https://github.com/forkwright/aletheia/issues/2260`

标题：`feat(nous): KAIROS-style autonomous daemon mode`

> 重要说明：**这个页面目前是一个 Open 状态的 GitHub issue / proposal，不是已完成实现，也不是已经合并的 KAIROS 复现功能。**

这是当前最值得看的公开社区页面，因为它不是泛泛而谈，而是把 KAIROS 提炼成了一组很具体的工程能力：

- 持久后台 daemon
- cron-scheduled tasks
- teammate coordination
- Brief mode output
- trust gate
- GrowthBook gate
- `.claude/scheduled_tasks.json`
- event-driven activation

它的价值不在于“已经实现了 KAIROS”，而在于：

> 它把社区对 KAIROS 的工程共识，压缩成了一份可执行的设计 proposal。

### 3.1.1 为什么它有价值

因为它和本地源码分析出来的结论高度一致：

- assistant mode
- daemon
- cron
- brief
- teammate agent
- trust-gated
- feature flag

说明这个 issue 不是拍脑袋想象，而是基于源码痕迹做的合理提炼。

### 3.1.2 它的局限

也要明确：

- 它不是 Anthropic 官方说明
- 它不是 KAIROS 完整复现仓库
- 它本质上是“借鉴 KAIROS 思路”的社区设计提案
- **它目前仍处于 Open 状态，因此最多只能证明“有人计划实现”，不能证明“功能已经做完”**

所以适合拿来：

- 理解社区如何概括 KAIROS
- 看别人打算如何把 KAIROS 思路迁移到自己的 agent 系统里

不适合拿来：

- 证明 KAIROS 已公开发布
- 证明已有完整成熟复现版

---

## 4. 目前信息价值一般的来源

### 4.1 Reddit

我筛了这些关键词：

- `Claude Code KAIROS`
- `tengu_kairos`
- `Claude Code assistant daemon`

当前结论是：

> **Reddit 不是 KAIROS 的主要信息源。**

至少在这轮检索里，没有看到：

- 系统性拆解 KAIROS 的高质量帖子
- 权威一手爆料
- 工程实现级的深入讨论

Reddit 的问题在于：

- 噪声大
- 命中少
- 即使命中，也往往不如 GitHub issue / 仓库分析具体

所以如果只是想高效获取信息，Reddit 当前优先级很低。

---

### 4.2 Hacker News

HN 这轮也没有筛出特别值得保留的结果。

原因和 Reddit 类似：

- 命中数量少
- 即使讨论到 KAIROS，也大概率只是“泄露源码里提到一个功能”这种级别
- 缺乏代码级细节

因此，HN 更适合看“有没有人讨论这件事”，不适合看“这个特性到底怎么实现”。

---

### 4.3 Lobsters

这轮检索同样没有筛出高价值结果。

结论可以直接定为：

- 目前不值得投入额外时间

---

## 5. 当前社区共识画像

虽然公开社区讨论不算多，但从 GitHub 资料和少量分析文字里，KAIROS 的社区画像是比较一致的：

### 5.1 社区通常如何理解 KAIROS

通常会把它概括为：

- Claude Code 的 assistant mode
- 长期运行的 autonomous agent runtime
- daemon-backed architecture
- 带 cron / proactive wake-up
- 带 brief / push / webhook / message 输出能力
- 可跨重启延续会话

### 5.2 哪些点是社区高频提到的

社区反复提到的关键词包括：

- `assistant mode`
- `daemon`
- `tengu_kairos`
- `brief`
- `cron`
- `scheduled_tasks.json`
- `webhook`
- `trust`
- `GrowthBook`

这些关键词和本地代码痕迹是能够互相印证的。

---

## 6. 当前社区资料缺什么

社区资料目前最明显的缺口有三个：

### 6.1 缺官方文档

没有看到 Anthropic 或 Claude Code 官方公开把 KAIROS 当作正式特性讲清楚。

### 6.2 缺成熟复现项目

虽然很多仓库提到了 KAIROS，但目前公开能看到的更多是：

- 分析
- 镜像
- 提案
- 局部还原

而不是“完整可跑的 KAIROS assistant 复刻版”。

### 6.3 缺高质量论坛讨论

Reddit / HN / Lobsters 这类论坛，没有成为 KAIROS 信息的主阵地。

---

## 7. 实用建议

如果你的目标是继续研究 KAIROS，我建议优先顺序这样排：

### 第一优先级

- 本地还原源码
- `claudecode-best`
- `claude-code-sourcemap`

### 第二优先级

- GitHub 上和 KAIROS 相关的 issue / 提案 / 分析仓库
- 尤其是 `forkwright/aletheia#2260` 这类工程化总结

### 第三优先级

- Reddit / HN / Lobsters

也就是说：

> **KAIROS 研究应该是“代码优先、GitHub 次之、论坛最后”。**

---

## 8. 最终结论

如果只从社区资料角度给一句总结：

> 当前 KAIROS 的公开社区信息主要集中在 GitHub 的源码分析和工程提案里，而不是 Reddit 这类论坛。最值得看的页面是 `forkwright/aletheia#2260`，因为它把社区对 KAIROS 的工程理解总结得最清楚；但它依然不是官方文档，也不是完整复现实现。
