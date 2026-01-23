"""
Data Analyst Skill - 数据分析专家工具集

提供 CSV 数据分析、统计计算和图表生成功能。
"""

import io
import sys
from typing import Optional, List, Dict, Any


def analyze_csv(file_path: str) -> str:
    """
    分析 CSV 文件，返回数据预览和统计摘要
    
    Args:
        file_path: CSV 文件路径
        
    Returns:
        分析结果字符串
    """
    try:
        import pandas as pd
    except ImportError:
        return "[ERROR] pandas 未安装，请运行 pip install pandas"
    
    try:
        df = pd.read_csv(file_path)
        
        result = []
        result.append(f"[文件] {file_path}")
        result.append(f"[形状] {df.shape[0]} 行 × {df.shape[1]} 列")
        result.append(f"\n[列名] {df.columns.tolist()}")
        result.append(f"\n[数据类型]\n{df.dtypes.to_string()}")
        result.append(f"\n[预览] 前5行:\n{df.head().to_string()}")
        result.append(f"\n[统计摘要]\n{df.describe().to_string()}")
        
        # 检查缺失值
        missing = df.isnull().sum()
        if missing.any():
            result.append(f"\n[WARN] 缺失值:\n{missing[missing > 0].to_string()}")
        
        return "\n".join(result)
    except FileNotFoundError:
        return f"[ERROR] 文件 '{file_path}' 不存在"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {str(e)}"


def calculate_statistics(file_path: str, column: str) -> str:
    """
    计算指定列的统计信息
    
    Args:
        file_path: CSV 文件路径
        column: 要分析的列名
        
    Returns:
        统计结果字符串
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        return "[ERROR] pandas/numpy 未安装"
    
    try:
        df = pd.read_csv(file_path)
        
        if column not in df.columns:
            return f"[ERROR] 列 '{column}' 不存在\n可用列: {df.columns.tolist()}"
        
        col_data = df[column]
        
        result = [f"[统计] 列 '{column}' 的统计分析:"]
        
        if pd.api.types.is_numeric_dtype(col_data):
            result.append(f"   类型: 数值型")
            result.append(f"   计数: {col_data.count()}")
            result.append(f"   均值: {col_data.mean():.4f}")
            result.append(f"   中位数: {col_data.median():.4f}")
            result.append(f"   标准差: {col_data.std():.4f}")
            result.append(f"   最小值: {col_data.min()}")
            result.append(f"   最大值: {col_data.max()}")
            result.append(f"   25%分位: {col_data.quantile(0.25):.4f}")
            result.append(f"   75%分位: {col_data.quantile(0.75):.4f}")
        else:
            result.append(f"   类型: 非数值型")
            result.append(f"   计数: {col_data.count()}")
            result.append(f"   唯一值数: {col_data.nunique()}")
            result.append(f"   最常见值: {col_data.mode().iloc[0] if not col_data.mode().empty else 'N/A'}")
            result.append(f"\n   值分布:\n{col_data.value_counts().head(10).to_string()}")
        
        return "\n".join(result)
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {str(e)}"


def generate_chart(
    file_path: str, 
    x_column: str, 
    y_column: str, 
    chart_type: str = "line",
    output_path: str = "output.png"
) -> str:
    """
    生成图表并保存为图片
    
    Args:
        file_path: CSV 文件路径
        x_column: X 轴列名
        y_column: Y 轴列名
        chart_type: 图表类型 (line, bar, scatter, hist)
        output_path: 输出图片路径
        
    Returns:
        操作结果字符串
    """
    try:
        import pandas as pd
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        return "[ERROR] pandas/matplotlib 未安装"
    
    try:
        df = pd.read_csv(file_path)
        
        # 验证列名
        for col in [x_column, y_column]:
            if col not in df.columns:
                return f"[ERROR] 列 '{col}' 不存在\n可用列: {df.columns.tolist()}"
        
        plt.figure(figsize=(10, 6))
        plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'ggplot')
        
        if chart_type == "line":
            plt.plot(df[x_column], df[y_column], marker='o', linewidth=2)
        elif chart_type == "bar":
            plt.bar(df[x_column], df[y_column])
        elif chart_type == "scatter":
            plt.scatter(df[x_column], df[y_column], alpha=0.7)
        elif chart_type == "hist":
            plt.hist(df[y_column], bins=20, edgecolor='black')
            x_column = y_column  # 直方图的 x 轴标签
        else:
            return f"[ERROR] 不支持的图表类型 '{chart_type}'\n支持: line, bar, scatter, hist"
        
        plt.xlabel(x_column, fontsize=12)
        plt.ylabel(y_column, fontsize=12)
        plt.title(f"{y_column} vs {x_column}", fontsize=14)
        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        plt.close()
        
        return f"[OK] 图表已保存到: {output_path}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {str(e)}"


def query_data(file_path: str, query: str) -> str:
    """
    使用 pandas query 语法查询数据
    
    Args:
        file_path: CSV 文件路径
        query: 查询条件 (如 "age > 30 and salary > 50000")
        
    Returns:
        查询结果字符串
    """
    try:
        import pandas as pd
    except ImportError:
        return "[ERROR] pandas 未安装"
    
    try:
        df = pd.read_csv(file_path)
        result_df = df.query(query)
        
        return f"[查询结果] ({len(result_df)} 行):\n{result_df.to_string()}"
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {str(e)}"


# 工具函数字典，用于动态挂载
DATA_ANALYST_TOOLS = {
    "analyze_csv": analyze_csv,
    "calculate_statistics": calculate_statistics,
    "generate_chart": generate_chart,
    "query_data": query_data,
}


def get_tools() -> List:
    """返回所有数据分析工具函数列表"""
    return list(DATA_ANALYST_TOOLS.values())
