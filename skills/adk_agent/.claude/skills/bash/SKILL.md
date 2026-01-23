---
name: "Bash Tool"
description: "执行系统 Shell 命令 (bash)，用于系统诊断、网络排查、文件操作等任务。"
---

# Execution Instructions

## 基本流程
1. **理解需求**：分析用户需要什么系统操作
2. **构建命令**：选择合适的命令和参数
3. **执行命令**：调用 `bash` 执行。**注意：这是执行任何外部脚本或系统命令的唯一授权方式。**
4. **分析结果**：解读输出，如需进一步操作则继续

## 可用工具

### bash
执行系统 Shell 命令，返回标准输出和错误输出。支持无状态执行。

```python
bash(
    command="ping -n 4 8.8.8.8",  # 要执行的命令
    timeout=30,                   # 超时秒数
    shell=True,                   # 是否使用 shell (默认: True)
    restart=False                 # 重启会话 (当前版本仅做兼容，无状态)
)
```

### get_system_info
获取系统基本信息（操作系统、CPU、内存等）。

### list_processes
列出当前运行的进程。

### get_network_info
获取网络配置信息。

## 常用命令参考

### Windows
- `ipconfig /all` - 网络配置
- `netstat -an` - 网络连接状态
- `ping -n 4 <host>` - 网络连通性
- `tracert <host>` - 路由追踪
- `tasklist` - 进程列表
- `systeminfo` - 系统信息
- `dir /s /b <path>` - 文件列表

### Linux/macOS
- `ifconfig` 或 `ip addr` - 网络配置
- `netstat -tulpn` - 网络连接
- `ping -c 4 <host>` - 网络连通性
- `traceroute <host>` - 路由追踪
- `ps aux` - 进程列表
- `uname -a` - 系统信息
- `find <path> -name <pattern>` - 查找文件

## 安全注意事项
1. **禁止执行高危命令**（如 `rm -rf`, `mkfs` 等），工具会自动拦截。
2. 对于耗时命令，设置合理的超时时间。
3. 敏感信息（密码、密钥）不要在命令中明文传递。

## 示例

**用户问题**: "检查一下到 Google DNS 的网络连通性"

**执行流程**:
```
Action: bash(command="ping -n 4 8.8.8.8", timeout=30)
Observation: 
正在 Ping 8.8.8.8 具有 32 字节的数据:
来自 8.8.8.8 的回复: 字节=32 时间=35ms TTL=117
...
数据包: 已发送 = 4，已接收 = 4，丢失 = 0 (0% 丢失)

Final Answer: 网络连通正常，到 8.8.8.8 的平均延迟约 35ms，无丢包。
```
