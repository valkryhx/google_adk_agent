---
name: "代码库搜索专家"
description: "通过 ripgrep 在本地文件系统中精确定位代码、配置或文档，支持多轮迭代检索。"
---

# Execution Instructions

## 基本流程
1. **先定位**：根据用户问题，提取核心变量名或关键词，使用 `execute_ripgrep`
2. **后深入**：根据 rg 返回的文件名和行号，判断相关性
3. **读全文**：如果确定文件关键，使用 `read_file_content` 获取完整上下文
4. **迭代**：如果发现新的依赖项或引用，重复步骤 1

## 搜索策略

### 精确搜索
已知确切名称时：
```
execute_ripgrep(pattern="function_name")
```

### 模糊搜索
不确定时使用通配符：
```
execute_ripgrep(pattern="pay.*handler")
```

### 正则搜索
复杂模式使用正则：
```
execute_ripgrep(pattern="^def.*init.*\\(")
```

## 失败处理协议

1. **零结果**：不要轻易说"没找到"，尝试减少正则约束或使用近义词
2. **关键词替换**：考虑 `user` vs `account`，`start` vs `init` 等
3. **报错自愈**：收到 `regex parse error` 时，分析错误并修复 pattern
4. **最后手段**：多次搜索无果，用 `list_files` 查看目录结构获取线索

## 示例

**用户问题**: "系统是怎么处理支付回调的？"

**执行流程**:
```
Thought: 我需要搜索 'webhook' 或 'payment_callback' 相关的代码

Action: execute_ripgrep(pattern="payment_callback")
Observation: src/api/handler.py:45: def payment_callback(request):

Action: read_file_content(file_path="src/api/handler.py")
Observation: [文件内容，发现引用了 StripeProcessor]

Action: execute_ripgrep(pattern="class StripeProcessor")
Observation: src/services/stripe.py:10: class StripeProcessor:

Final Answer: 支付回调由 payment_callback 函数处理，位于 src/api/handler.py，
核心逻辑在 StripeProcessor 类中实现。
```
