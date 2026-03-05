# Analyze Image Skill Bug 修复技术总结

## 1. 背景与问题描述
在优化 `analyze_local_image` 技能时，我们遇到了 Agent 无法正确分析图片内容的问题。初期现象是 Agent 即使成功调用了工具并提示注入了图片，但后续的分析内容完全是错误或凭空捏造的。

经过深度调试，我们发现了四个层面的 Bug：**持久化失效**、**协议校验违规**、**模型定义约束**以及**边界判空缺失**。

---

## 2. 核心 Bug 分析与修复方案

### Bug A: 事件注入未持久化（导致图片“消失”）
*   **现象**：Agent 在当前 Turn 提示注入成功，但在下一步分析时表现得像没看见图片。
*   **原因**：原代码直接使用 `tool_context.session.events.insert(...)` 修改内存中的列表。ADK 的 `DatabaseSessionService`  在处理完 Tool 响应后，往往会从数据库重新加载 Session 以同步状态。由于内存修改未触发 SQL `COMMIT` 或 API 调用，新注入的图片事件在刷新后丢失。
*   **修复**：改用官方持久化方法：
    ```python
    await tool_context._invocation_context.session_service.append_event(
        tool_context.session, image_event
    )
    ```

### Bug B: 对话流协议违规（导致历史解析失败）
*   **现象**：Agent 频繁 hang 住、报错 "missing tool result" 或 LiteLLM 校验失败。
*   **原因**：LiteLLM 规定，如果模型发出了 `function_call`，那么下一条消息必须是该调用的 `function_response`。原代码将图片（user 角色）注入在两者之间，破坏了 `Assistant -> Tool` 的原子序列。
*   **修复**：在持久化后，手动调整内存列表顺序，将图片事件移动到 `model` 事件（当前 tool 调用）之前：
    ```python
    tool_context.session.events.insert(tool_call_idx, image_event)
    ```
    最终序列：`User(Show me this) -> User(Image Data) -> Assistant(Call Tool) -> Tool(Response: Success)`。

### Bug C: Pydantic 字段约束报错
*   **现象**：工具执行报错 `Extra inputs are not permitted`。
*   **原因**：ADK 的 `Event` 类开启了 `extra='forbid'` 约束。原代码尝试在构造函数中传入 `user_id` 和 `app_name`，但这些字段并不直接属于 `Event` 模型（它们属于 `Session`）。
*   **修复**：根据 `google/adk/events/event.py` 定义，仅传入受领字段，确保校验通过。

### Bug D: 空内容导致的 AttributeError
*   **现象**：报错 `'NoneType' object has no attribute 'parts'`。
*   **原因**：遍历历史记录进行“重复注入检查”时，未考虑到某些系统事件或占位事件的 `content` 可能为 `None`。
*   **修复**：增加了安全性判空：`if event.author == "user" and event.content and event.content.parts:`。

### Bug E: SDK 方法参数名错误
*   **现象**：传入 URL 时报错 `TypeError: Part.from_uri() got an unexpected keyword argument 'uri'`。
*   **原因**：对 `google-genai` SDK 的 `Part.from_uri` 方法误用了 `uri` 参数名。
*   **修复**：将参数名更正为 `file_uri`。

---

## 3. 修复后的执行流程总结
1.  **用户发起请求**：指令包含图片路径。
2.  **工具拦截并读取**：读取路径对应的二进制数据。
3.  **双重操作**：
    *   **数据库侧**：通过 `session_service` 确保图片入库。
    *   **内存侧**：调整顺序以满足协议校验。
4.  **模型反馈**：ADK 刷新上下文后，模型在当前上下文上方看到一个包含真实图片数据的 User Message。
5.  **视觉分析**：模型利用多模态能力准确描述图片内容。

---

## 4. 总结与启示
Agent 开发中，**上下文注入**不能简单视作内存操作。必须尊重以下三大支柱：
1.  **持久化层**：必须通过 Service 接口操作。
2.  **协议栈**：必须遵守 LLM 厂商的 Message Role 顺序规约。
3.  **数据模型**：必须严格遵循 Pydantic 定义。

修复后的 `analyze_local_image` 不仅能“看”到本地图片，还具备了极高的鲁棒性。
