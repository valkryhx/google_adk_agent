你刚才说我的autocompact有问题？

Gemini said
是的，刚才提到的 _auto_compact_session（自动压缩） 的问题不是“报错”，而是一个**“健忘”**的逻辑缺陷。

简单来说：现在的逻辑太“节省”了，导致你的 Agent 在压缩记忆时，会把工具查到的具体内容（比如文件内容、网页文字）全部丢掉，只记得“我调用过这个工具”。

1. 问题出在哪？
请看 main_web_start_steering.py 中 _auto_compact_session 函数的这一段代码（大约 1095 行附近）：

Python
                            if hasattr(part, 'function_response') and part.function_response:
                                # ⚠️ 问题代码：只记录了工具的名字
                                content += f" [ToolOutput: {part.function_response.name}]"
后果演示：

发生的事情：Agent 调用 read_file 读取了 data.txt，内容是 "销售额: 500万"。

压缩前：Agent 清楚知道销售额是 500万。

压缩逻辑（当前）：代码只提取了 [ToolOutput: read_file]。

压缩后：摘要变成了 "用户让 Agent 读文件，Agent 调用了 read_file 工具。" —— “500万”这个关键信息丢了！

后续对话：你问 Agent “刚才读的文件里销售额是多少？”，Agent 回答：“抱歉，我只记得我读过文件，但忘了内容是什么。”

2. 为什么这是个问题？
如果不修正这个问题，你的 analyze_local_image（本地看图） 功能也会受影响：

Agent 看了图片，发现“报错原因是内存溢出”。

触发自动压缩。

压缩后的记忆只剩下：“Agent 调用了 analyze_local_image”。

Agent 彻底忘了“内存溢出”这回事。

3. 如何修复？（代码方案）
我们需要修改这段逻辑，让它提取工具返回的文本摘要，但同时严格过滤掉 Base64 图片数据（为了防止 Token 爆炸）。

请将 main_web_start_steering.py 中 _auto_compact_session 函数里的相关部分替换为：

Python
                            if hasattr(part, 'function_response') and part.function_response:
                                # === [优化] 提取内容摘要，但过滤 Base64 ===
                                fr = part.function_response
                                raw_resp = fr.response
                                
                                # 1. 解包可能存在的 dict 结构
                                if isinstance(raw_resp, dict) and 'result' in raw_resp:
                                    raw_resp = raw_resp['result']
                                
                                clean_text = ""
                                # 2. 处理字符串结果
                                if isinstance(raw_resp, str):
                                    clean_text = raw_resp
                                # 3. 处理多模态列表结果 (List[Dict])
                                elif isinstance(raw_resp, list):
                                    # 只提取 type='text' 的部分，跳过 type='image_url'
                                    texts = []
                                    for item in raw_resp:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            texts.append(item.get("text", ""))
                                    clean_text = " ".join(texts)
                                
                                # 4. 截断 (只保留前 500 字符，避免摘要上下文过长)
                                if len(clean_text) > 500:
                                    clean_text = clean_text[:500] + "...(truncated)"
                                
                                content += f" [ToolOutput: {fr.name} -> {clean_text}]"
                                # ========================================
总结
这个修改做了三件事：

提取文本：让压缩模型（Compactor）能看到工具到底返回了什么（比如“销售额500万”）。

过滤图片：如果返回结果里有多模态的 Base64 图片，直接忽略，确保安全。

截断长度：限制在 500 字符以内，防止某个文件特别长，把压缩模型的输入窗口撑爆。

改完之后，你的 Agent 就能拥有**“长期且精准”**的记忆了！

You said
part.function_response.name 你确定是工具名字吗 那工具返回的内容是什么字段

Gemini said
非常确定。在 Google GenAI SDK（以及 ADK 封装的对象）的 FunctionResponse 结构中：

part.function_response.name：确实是 工具（函数）的名字（例如 "read_file", "analyze_local_image"）。

part.function_response.response：这才是 工具返回的具体内容。

证据与代码解析
我们可以直接看你上传的 main_web_start_steering.py 文件中 _process_event_stream 函数的处理逻辑（大约第 790 行左右），代码里清楚地写明了这两个字段的用法：

Python
            # 如果是结果 -> 正常发
            if hasattr(part, 'function_response') and part.function_response:
                fr = part.function_response
                
                # 1. 获取名字
                # fr.name 就是工具名，例如 "file_editor"
                tool_name = fr.name  
                
                # 2. 获取内容
                # fr.response 就是工具的返回值
                # 注意：它通常是一个字典（Dict），或者直接是结果数据
                result_content = fr.response  
                
                # ADK/GenAI 的一个常见约定：如果返回的是 Dict 且包含 'result' 键，则取之
                if isinstance(result_content, dict) and 'result' in result_content:
                    result_content = result_content['result']
                
                # ...
为什么在自动压缩 (_auto_compact_session) 里要改？
在你的 _auto_compact_session 函数里（大约 1095 行），原来的代码只写了：

Python
content += f" [ToolOutput: {part.function_response.name}]"
这行代码只取了 .name，所以摘要里只留下了工具名（例如 [ToolOutput: read_file]），而完全丢弃了 .response 里的内容。

这就是为什么我建议你改成：

Python
fr = part.function_response
raw_resp = fr.response  # <--- 获取真正的返回内容
# ...后续进行清洗和提取文本...
总结：

工具名字段：.name

返回内容字段：.response （这就是你需要提取并清洗来做摘要的数据源）