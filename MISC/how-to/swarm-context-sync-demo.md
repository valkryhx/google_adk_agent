# Swarm 上下文同步演示指南

## 准备工作

### 1. 清理旧数据（已完成）
```cmd
cd d:\git_codes\google_adk_helloworld_git
del /Q sqlite_db\adk_sessions_port_*.db sqlite_db\swarm_registry.db
```

### 2. 启动 Swarm 集群
```cmd
cd d:\git_codes\google_adk_helloworld_git
start_demo_swarm.bat
```

**等待所有节点启动完成**（大约 10-15 秒），直到看到：
```
[Node-8000] 🚀 服务已完全启动 (已加入 Swarm)
[Node-8001] 🚀 服务已完全启动 (已加入 Swarm)
[Node-8002] 🚀 服务已完全启动 (已加入 Swarm)
[Node-8003] 🚀 服务已完全启动 (已加入 Swarm)
```

---

## 演示场景：跨节点上下文同步

### 场景 1：在 Leader 节点发起并行任务

**步骤**：

1. **打开浏览器** → `http://localhost:8000`

2. **选择用户** → `userA`（在右上角用户选择器）

3. **发送任务**：
   ```
   请并行搜索以下 3 个公司的 2024 年财报：
   1. Apple
   2. Microsoft  
   3. Google
   
   要求每个公司都返回：收入、利润、主要业务亮点
   ```

4. **观察执行过程**：
   - 8000 会调用 `dispatch_batch_tasks`
   - 任务被分配给 8001, 8002, 8003
   - 每个 Worker 并行搜索
   - 8000 汇总结果并返回

5. **关键观察点**（后端控制台）：
   ```
   [Swarm Dispatch] 📡 正在连接 Worker 8001...
   [Swarm Dispatch] 📡 正在连接 Worker 8002...
   [Swarm Dispatch] 📡 正在连接 Worker 8003...
   
   [Swarm] 📝 已注入任务血缘元数据到 Worker 8001
   [Swarm] 📝 已注入任务血缘元数据到 Worker 8002
   [Swarm] 📝 已注入任务血缘元数据到 Worker 8003
   ```

### 场景 2：验证命名空间分离

**步骤**：

1. **打开数据库查看器**（推荐 DB Browser for SQLite）

2. **打开数据库**：
   - `sqlite_db/adk_sessions_port_8000.db`
   - `sqlite_db/adk_sessions_port_8001.db` (或 8002, 8003)

3. **查询 8000 的会话**：
   ```sql
   SELECT app_name, user_id, session_id 
   FROM sessions 
   WHERE user_id = 'userA';
   ```
   
   **预期结果**：
   ```
   | app_name       | user_id | session_id  |
   | -------------- | ------- | ----------- |
   | dynamic_expert | userA   | session_xxx |
   ```

4. **查询 8001 的会话**：
   ```sql
   SELECT app_name, user_id, session_id, state
   FROM sessions 
   WHERE user_id = 'userA';
   ```
   
   **预期结果**：
   ```
   | app_name        | user_id | session_id | state                      |
   | --------------- | ------- | ---------- | -------------------------- |
   | swarm_from_8000 | userA   | sub_abc123 | {"leader_port": 8000, ...} |
   ```

✅ **验证通过**：命名空间完全分离！

### 场景 3：切换到 Worker 节点继续对话（核心演示）

**步骤**：

1. **新开浏览器标签页** → `http://localhost:8003`（选择之前执行过任务的 Worker）

2. **保持用户为 userA**（不要更改）

3. **观察会话列表**：
   - 应该能看到之前的 Swarm 任务会话
   - 标题可能是 "搜索 Google 公司财报" 或类似

4. **点击该会话**，查看历史消息

5. **发送新消息**（这是关键！）：
   ```
   把刚才搜索的 3 个公司财报做成对比表格，包含：
   - 公司名称
   - 2024 年收入
   - 2024 年利润
   - 主要业务亮点
   ```

6. **观察 Agent 的行为**：

   **控制台日志（8003）**：
   ```
   [Swarm Sync] 🔄 开始同步 Leader 8000 的上下文,原因: 需要获取其他公司财报以生成对比表格
   [Swarm Sync] ✅ 同步成功,获得 8 条消息
   ```

   **Agent 的思考过程（在对话中可能看到）**：
   ```
   <think>
   用户要求对比 3 个公司的财报，但我当前只有 Google 的结果。
   检测到当前会话的 state 中有 leader_port=8000，说明这是一个 Worker 任务。
   我应该调用 sync_leader_context 获取完整的任务背景。
   </think>
   
   调用工具: sync_leader_context(reason="需要获取其他公司财报数据")
   
   工具返回:
   【Leader 上下文同步成功】
   🖥️ Leader 节点: http://localhost:8000
   👤 用户: userA
   📋 任务标题: 搜索多个公司财报
   最近对话摘要:
   用户: 请并行搜索以下 3 个公司的 2024 年财报...
   助手: 已完成搜索任务，结果如下...
   
   <think>
   现在我知道完整任务背景了，需要从其他 Worker 获取数据。
   我应该调用 dispatch_task 从 8001 和 8002 获取 Apple 和 Microsoft 的数据。
   </think>
   
   调用工具: dispatch_task(
       task_instruction="请提供你之前搜索到的 Apple 公司 2024 年财报数据",
       target_port=8001
   )
   
   调用工具: dispatch_task(
       task_instruction="请提供你之前搜索到的 Microsoft 公司 2024 年财报数据",
       target_port=8002
   )
   ```

7. **最终结果**：
   
   Agent 会生成完整的对比表格：
   ```markdown
   | 公司      | 2024 年收入  | 2024 年利润 | 主要业务亮点                   |
   | --------- | ------------ | ----------- | ------------------------------ |
   | Apple     | $XXX billion | $YYY        | iPhone 销售增长... (来自 8001) |
   | Microsoft | $AAA billion | $BBB        | Azure 云服务... (来自 8002)    |
   | Google    | $CCC billion | $DDD        | 广告业务... (本地数据)         |
   ```

✅ **核心功能验证成功**：
- ✅ 自动检测到 Leader 信息
- ✅ 主动同步上下文
- ✅ 跨节点获取数据
- ✅ 生成完整结果

---

## 关键验证点

### 验证 1：命名空间隔离

**数据库查询**：
```sql
-- 在各个节点的数据库中执行
SELECT 
    app_name, 
    user_id, 
    session_id,
    json_extract(state, '$.leader_port') as leader_port,
    json_extract(state, '$.task_type') as task_type
FROM sessions 
WHERE user_id = 'userA'
ORDER BY created_at DESC;
```

**预期结果**：
- 8000：`app_name="dynamic_expert"`, `leader_port=NULL`
- 8001/8002/8003：`app_name="swarm_from_8000"`, `leader_port=8000`, `task_type="swarm_worker"`

### 验证 2：元数据完整性

**查看 Worker 节点的 state 字段**：
```sql
SELECT state FROM sessions 
WHERE app_name = 'swarm_from_8000' 
LIMIT 1;
```

**预期包含**：
```json
{
  "task_type": "swarm_worker",
  "leader_port": 8000,
  "original_user_id": "userA",
  "task_instruction": "搜索 Apple 公司..."
}
```

### 验证 3：API 端点测试

**手动测试跨节点 API**：

1. 访问 Leader 的上下文 API：
   ```
   http://localhost:8000/api/context/leader_summary?user_id=userA&app_name=dynamic_expert
   ```

2. **预期返回**：
   ```json
   {
     "title": "搜索多个公司财报",
     "session_id": "session_xxx",
     "recent_summary": "用户: 请并行搜索...\n助手: 已完成...",
     "total_messages": 8
   }
   ```

---

## 故障排查

### 问题 1：Worker 没有调用 sync_leader_context

**可能原因**：
- session.state 中没有 leader_port 信息
- Agent 没有识别到需要同步上下文

**解决方案**：
1. 检查控制台是否有元数据注入日志
2. 查询数据库确认 state 字段
3. 尝试更明确的指令："请先同步一下 Leader 的任务信息，然后..."

### 问题 2：无法连接到 Leader 节点

**错误信息**：`❌ 无法连接到 Leader 节点 (Port 8000)`

**检查**：
1. 8000 端口是否在运行
2. 防火墙是否阻止本地连接

### 问题 3：数据库文件未创建

**可能原因**：节点尚未收到任何消息

**解决方案**：从 Leader 发起任务后，Worker 会自动创建数据库

---

## 演示脚本（完整版）

### 开场白
```
今天演示 Swarm 架构的自动上下文同步功能。这个功能解决了分布式 Agent 对话中的上下文连续性问题。
```

### 演示步骤

**1. 启动集群**（1 分钟）
- 运行 `start_demo_swarm.bat`
- 等待所有节点启动

**2. 发起并行任务**（2 分钟）
- 在 8000 发送搜索 3 个公司财报的请求
- 展示并行执行的日志
- 展示元数据注入日志

**3. 验证命名空间**（1 分钟）
- 打开数据库查看器
- 展示 8000 和 8001 的 app_name 不同
- 强调 user_id 保持一致

**4. 跨节点继续对话**（3 分钟）
- 切换到 8003
- 发送对比表格请求
- **重点展示**：Agent 自动调用 sync_leader_context
- 展示最终生成的完整表格

**5. 总结**（1 分钟）
- 用户无需记忆端口
- 无需手动切换 user_id
- Agent 智能识别并同步上下文
- 真正的分布式连续对话

---

## 快速演示版（3 分钟）

如果时间有限，只演示**场景 3**即可：

1. ✅ 启动集群
2. ✅ 8000 发起任务
3. ✅ 切换到 8003 继续对话
4. ✅ 观察 Agent 自动同步上下文
5. ✅ 展示最终结果

**核心卖点**：用户无需任何手动操作，Agent 自动发现并同步上下文！

---

祝演示成功！🎉
