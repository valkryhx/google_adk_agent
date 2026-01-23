---
name: "数据分析专家"
description: "使用 Python/Pandas 对 CSV 数据进行统计分析并生成图表。"
---

# Execution Instructions

## 前置条件
- 必须使用 `import pandas as pd`
- 如需绘图，使用 `import matplotlib.pyplot as plt`

## 执行步骤

### 1. 数据加载
```python
import pandas as pd
df = pd.read_csv('文件路径')
print(df.head())
print(df.columns.tolist())  # 检查列名
```

### 2. 数据分析
- 在分析前，先打印列名确认
- 如果用户指定的列名不存在，检查相似列名
- 使用 describe() 获取统计摘要

### 3. 绘图（如需要）
```python
import matplotlib.pyplot as plt
plt.figure(figsize=(10, 6))
# 绑图逻辑
plt.savefig('output.png')
plt.close()
```

### 4. 输出结果
- 将分析结果以清晰格式输出
- 如生成了图表，告知用户保存路径

## 错误处理
- 如果列名不匹配，先打印所有列名再重试
- 文件不存在时，提示用户确认路径

## 示例

**用户请求**: "分析 data.csv 里的销售数据"

**执行**:
```python
import pandas as pd
df = pd.read_csv('data.csv')
print("列名:", df.columns.tolist())
print("数据预览:")
print(df.head())
print("\n统计摘要:")
print(df.describe())
```
