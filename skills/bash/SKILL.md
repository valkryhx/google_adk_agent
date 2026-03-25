---
name: "Bash Tool"
description: "【系统级后备工具】仅用于网络诊断、进程管理等基础任务。代码搜索/数据分析等应使用专用 skill。"
---

# Execution Instructions

## 基本流程
1. **理解需求**:分析用户需要什么系统操作
2. **构建命令**:选择合适的命令和参数
3. **执行命令**:调用 `bash` 执行
4. **分析结果**:解读输出,如需进一步操作则继续

## ⚠️ 何时不应使用 Bash
Bash 是**系统级操作的通用工具**,但以下场景**必须使用专用 skill**:

**禁用场景清单**:
- ❌ 代码搜索/文件查找 → 使用 `codebase_search` skill
- ❌ 数据分析/CSV处理 → 使用 `data_analyst` skill
- ❌ PDF 文件操作 → 使用 `pdf` skill
- ❌ MCP 服务连接 → 使用 `dynamic-mcp` skill
- ❌ 项目代码理解/函数查找 → 使用 `codebase_search` skill

## 适用场景
仅当没有专用 skill 时,bash 才适用于:
- 网络诊断 (ping, traceroute, netstat)
- 进程管理 (kill, ps, tasklist)
- 系统信息查询 (systeminfo, uname, df)
- 简单文件操作 (cp, mv) - 不涉及搜索或分析

## 可用工具

### bash
执行系统 Shell 命令，返回标准输出和错误输出。支持无状态执行。

**Windows 多行命令支持**：命令字符串中包含字面换行符（`\n`）时，会自动写入临时脚本文件再执行，支持 `python -c "...多行脚本..."` 写法。

```python
# 执行 Python 脚本片段
bash(command='python -c "import sys; print(sys.version)"')

# 执行多行 Python 脚本（含换行符，Windows 自动转为临时 .py 文件）
bash(command='python -c "import os\nfor f in os.listdir(\".\"):\n    print(f)"')

# 执行 CMD 命令
bash(command='cmd /c dir /b /s *.py')

# 执行 PowerShell 命令
bash(command='powershell -Command "Get-ChildItem -Recurse -Filter *.log | Select-Object Name, Length"')

# 执行 PowerShell 多行脚本
bash(command='powershell -Command "$files = Get-ChildItem .\\logs; $files | ForEach-Object { Write-Output $_.Name }"')

# 设置超时（默认 60 秒）
bash(command='python -c "import time; time.sleep(5); print(done)"', timeout=10)
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

## Windows 后台启动服务（重要）

在 Windows 上启动 Flask/uvicorn 等服务时，**必须使用后台方式**，否则会阻塞对话。

### 方式一：`subprocess.Popen` + `DETACHED_PROCESS`（推荐，可获取 PID）

```python
# 启动 Flask 服务到后台，不阻塞，返回 PID 方便后续 kill
bash(command='python -c "
import subprocess
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
proc = subprocess.Popen(
    [\"python\", \"app.py\"],
    creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
    stdout=open(\"flask.log\", \"w\"),
    stderr=subprocess.STDOUT
)
print(\"PID:\", proc.pid)
"')
```

### 方式二：`START /B`（快捷，日志重定向到文件）

```python
# 用 CMD 的 START /B 在后台启动，输出写入 flask.log
bash(command='cmd /c start /b python app.py > flask.log 2>&1')
```

### 验证服务已启动

```python
import time, urllib.request
time.sleep(3)  # 等待服务就绪
try:
    r = urllib.request.urlopen('http://localhost:5000/', timeout=3)
    print('服务正常:', r.status)
except Exception as e:
    print('服务未就绪:', e)
    # 查看日志排查原因
    bash(command='type flask.log')
```

### 停止后台服务

```python
# 按端口 kill（推荐）
bash(command='powershell -Command "Get-NetTCPConnection -LocalPort 5000 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"')

# 按 PID kill（已知 PID 时）
bash(command='taskkill /PID 12345 /F')
```

> ❌ **禁止**直接 `bash(command='python app.py')` 启动服务，这会前台阻塞，导致对话挂起。


## 安全注意事项
1. **禁止执行高危命令**（如 `rm -rf`, `mkfs`, `del /f /s /q` 等），工具会自动拦截。
2. 对于耗时命令，设置合理的超时时间。
3. 敏感信息（密码、密钥）不要在命令中明文传递。

## 示例

**用户问题**:"检查一下到 Google DNS 的网络连通性"

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

---

## Windows 实用命令示例

### 进程与端口管理

```python
# 查看占用某端口的进程
bash(command='powershell -Command "Get-NetTCPConnection -LocalPort 5000 | Select-Object LocalPort, State, OwningProcess"')

# 按端口强制 kill 进程
bash(command='powershell -Command "Get-NetTCPConnection -LocalPort 5000 | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }"')

# 查看所有 Python 进程
bash(command='tasklist /fi "imagename eq python.exe"')

# 按 PID kill
bash(command='taskkill /PID 12345 /F')
```

### 文件与目录操作

```python
# 查看目录内容（含大小）
bash(command='powershell -Command "Get-ChildItem D:\\myproject | Select-Object Name, Length, LastWriteTime"')

# 递归查找特定文件
bash(command='cmd /c dir /s /b D:\\myproject\\*.py')

# 查看文件末尾 N 行（tail 等价）
bash(command='powershell -Command "Get-Content D:\\myproject\\app.log -Tail 20"')

# 实时监控日志文件（tail -f 等价，超时后停止）
bash(command='powershell -Command "Get-Content D:\\myproject\\flask.log -Wait -Tail 10"', timeout=10)

# 创建多级目录
bash(command='cmd /c mkdir D:\\myproject\\static\\css')

# 复制文件
bash(command='cmd /c copy D:\\src\\file.py D:\\dst\\file.py')
```

### Python 环境

```python
# 检查已安装的包
bash(command='pip list')

# 安装依赖
bash(command='pip install flask requests -q')

# 从 requirements.txt 安装
bash(command='pip install -r D:\\myproject\\requirements.txt -q')

# 检查 Python 版本和路径
bash(command='python --version && where python')

# 运行 Python 脚本（前台，适合短命令）
bash(command='python D:\\myproject\\init_db.py', timeout=30)
```

### 网络诊断

```python
# 检查端口是否监听
bash(command='netstat -an | findstr :5000')

# HTTP 请求测试（curl 等价）
bash(command='powershell -Command "Invoke-WebRequest -Uri http://localhost:5000/api/test -Method GET | Select-Object StatusCode, Content"')

# 发送 POST 请求
bash(command='powershell -Command "Invoke-WebRequest -Uri http://localhost:5000/api/items -Method POST -Body \'{\'\"title\'\":\'\"test\'\'\"}\'\' -ContentType application/json | Select-Object StatusCode"')
```

### 系统信息

```python
# 查看磁盘空间
bash(command='powershell -Command "Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{N=\'Used(GB)\';E={[math]::Round($_.Used/1GB,1)}}, @{N=\'Free(GB)\';E={[math]::Round($_.Free/1GB,1)}}"')

# 查看内存使用
bash(command='powershell -Command "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 Name, @{N=\'Mem(MB)\';E={[math]::Round($_.WorkingSet/1MB,1)}}"')

# 查看环境变量
bash(command='cmd /c set PATH')
bash(command='powershell -Command "$env:PYTHONPATH"')
```
