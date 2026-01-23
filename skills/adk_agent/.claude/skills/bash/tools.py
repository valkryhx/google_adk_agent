"""
Shell Executor Skill - 系统命令执行工具集

提供系统命令执行、进程管理、网络诊断等功能。
无需外部 API，直接使用系统原生命令。
"""

import subprocess
import platform
import os
import psutil
from typing import Optional, List


def validate_command(command: str) -> tuple[bool, str]:
    """
    验证命令安全性
    
    Args:
        command: 要执行的命令
        
    Returns:
        (是否安全, 拒绝原因)
    """
    dangerous_patterns = [
        'rm -rf', 'rm -fr', 'rm -r -f', 'rm -f -r', # 递归强制删除
        'mkfs', 'fdisk', 'dd if=',                   # 格式化/磁盘操作
        ':(){:|:&};:',                               # Fork炸弹
        '> /dev/sda', '> /dev/hda',                  # 直接写设备
        'mv /', 'chmod -R 777 /',                    # 系统级破坏
        
        # Windows Specific
        'del /s /q', 'rd /s /q', 'rmdir /s /q',      # Windows 递归删除
        'format c:', 'format d:',                    # 格式化
        'diskpart',                                  # 磁盘分区工具
        'shutdown', 'restart-computer',              # 关机/重启
        'reg delete',                                # 注册表删除
        'net user', 'net localgroup',                # 用户/组修改
        'takeown', 'icacls /grant',                  # 权限修改
        'powershell -enc',                           # 混淆执行
    ]
    
    for pattern in dangerous_patterns:
        if pattern in command:
            return False, f"Command contains dangerous pattern: {pattern}"
            
    return True, ""


def bash(
    command: str,
    restart: bool = False,
    timeout: int = 60,
    shell: bool = True,
    cwd: Optional[str] = None
) -> str:
    """
    执行系统 Shell 命令 (Bash Tool)
    
    Args:
        command: 要执行的命令
        restart: 重启会话 (当前无状态模式下仅作为兼容参数)
        timeout: 超时时间（秒）
        shell: 是否使用 shell 执行
        cwd: 工作目录（可选）
        
    Returns:
        命令输出结果
    """
    if restart:
        return "Bash session restarted (Stateless mode - no actual session reset needed)"
        
    if not command:
        return "[ERROR] Command content is empty"

    # 安全检查
    is_safe, reason = validate_command(command)
    if not is_safe:
        return f"[ERROR] Security Alert: {reason}"

    try:
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            # text=True 会自动解码，导致我们没机会处理编码错误。改为 False 获取 bytes
            text=False, 
            timeout=timeout,
            cwd=cwd,
            # Windows 默认编码通常是 gbk/cp936，强制 utf-8 可能会导致解码错误从而丢弃输出
            # 移除 encoding 参数，获取 bytes 后手动解码
            # encoding='utf-8', 
            # errors='replace'
        )
        
        output_parts = []
        
        # 手动解码策略
        def decode_bytes(b: bytes) -> str:
            if not b: return ""
            try:
                # 优先尝试 utf-8
                return b.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    # 尝试系统默认编码 (如 gbk)
                    return b.decode(platform.system() == 'Windows' and 'mbcs' or 'utf-8')
                except:
                    # 最后兜底
                    return b.decode('utf-8', errors='replace')

        stdout_str = decode_bytes(result.stdout)
        stderr_str = decode_bytes(result.stderr)
        
        if stdout_str:
            output_parts.append(f"[标准输出]\n{stdout_str}")
        
        if stderr_str:
            output_parts.append(f"[错误输出]\n{stderr_str}")
        
        if result.returncode != 0:
            output_parts.append(f"[返回码] {result.returncode}")
        
        if not output_parts:
            # 兼容 Claude Bash tool 的静默成功
            # return "[OK] 命令执行成功，无输出" 
            return "" 
        
        return "\n".join(output_parts)
        
    except subprocess.TimeoutExpired:
        return f"[ERROR] 命令执行超时（超过 {timeout} 秒）"
    except FileNotFoundError:
        return f"[ERROR] 命令未找到: {command.split()[0]}"
    except Exception as e:
        return f"[ERROR] 执行失败: {type(e).__name__}: {str(e)}"


def get_system_info() -> str:
    """
    获取系统基本信息
    
    Returns:
        系统信息字符串
    """
    try:
        info = []
        
        # 操作系统信息
        info.append("[操作系统]")
        info.append(f"  系统: {platform.system()} {platform.release()}")
        info.append(f"  版本: {platform.version()}")
        info.append(f"  架构: {platform.machine()}")
        info.append(f"  主机名: {platform.node()}")
        
        # CPU 信息
        info.append("\n[CPU]")
        info.append(f"  处理器: {platform.processor()}")
        info.append(f"  核心数: {psutil.cpu_count(logical=False)} 物理核 / {psutil.cpu_count()} 逻辑核")
        info.append(f"  使用率: {psutil.cpu_percent(interval=1)}%")
        
        # 内存信息
        mem = psutil.virtual_memory()
        info.append("\n[内存]")
        info.append(f"  总量: {mem.total / (1024**3):.2f} GB")
        info.append(f"  已用: {mem.used / (1024**3):.2f} GB ({mem.percent}%)")
        info.append(f"  可用: {mem.available / (1024**3):.2f} GB")
        
        # 磁盘信息
        info.append("\n[磁盘]")
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                info.append(f"  {partition.device}: {usage.total / (1024**3):.1f} GB, 已用 {usage.percent}%")
            except:
                pass
        
        return "\n".join(info)
        
    except Exception as e:
        return f"[ERROR] 获取系统信息失败: {str(e)}"


def list_processes(top_n: int = 20, sort_by: str = "memory") -> str:
    """
    列出当前运行的进程
    
    Args:
        top_n: 显示前 N 个进程
        sort_by: 排序方式 (memory, cpu, name)
        
    Returns:
        进程列表
    """
    try:
        processes = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                pinfo = proc.info
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'cpu': pinfo['cpu_percent'] or 0,
                    'memory': pinfo['memory_percent'] or 0,
                    'status': pinfo['status']
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # 排序
        if sort_by == "memory":
            processes.sort(key=lambda x: x['memory'], reverse=True)
        elif sort_by == "cpu":
            processes.sort(key=lambda x: x['cpu'], reverse=True)
        else:
            processes.sort(key=lambda x: x['name'].lower())
        
        # 格式化输出
        result = [f"[进程列表] (按 {sort_by} 排序，显示前 {top_n} 个)"]
        result.append("-" * 60)
        result.append(f"{'PID':>8}  {'CPU%':>6}  {'MEM%':>6}  {'状态':>10}  名称")
        result.append("-" * 60)
        
        for p in processes[:top_n]:
            result.append(f"{p['pid']:>8}  {p['cpu']:>6.1f}  {p['memory']:>6.1f}  {p['status']:>10}  {p['name']}")
        
        return "\n".join(result)
        
    except Exception as e:
        return f"[ERROR] 获取进程列表失败: {str(e)}"


def get_network_info() -> str:
    """
    获取网络配置信息
    
    Returns:
        网络信息字符串
    """
    try:
        info = []
        
        # 网络接口信息
        info.append("[网络接口]")
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        
        for iface, addr_list in addrs.items():
            if iface in stats:
                is_up = "UP" if stats[iface].isup else "DOWN"
                speed = stats[iface].speed
                info.append(f"\n  {iface} ({is_up}, {speed}Mbps)")
            else:
                info.append(f"\n  {iface}")
            
            for addr in addr_list:
                if addr.family.name == 'AF_INET':
                    info.append(f"    IPv4: {addr.address}")
                    if addr.netmask:
                        info.append(f"    掩码: {addr.netmask}")
                elif addr.family.name == 'AF_INET6':
                    info.append(f"    IPv6: {addr.address}")
        
        # 网络连接统计
        info.append("\n[网络连接统计]")
        conns = psutil.net_connections(kind='inet')
        
        status_count = {}
        for conn in conns:
            status = conn.status
            status_count[status] = status_count.get(status, 0) + 1
        
        for status, count in sorted(status_count.items()):
            info.append(f"  {status}: {count}")
        
        # 网络 IO 统计
        io = psutil.net_io_counters()
        info.append("\n[网络流量]")
        info.append(f"  发送: {io.bytes_sent / (1024**2):.2f} MB ({io.packets_sent} 包)")
        info.append(f"  接收: {io.bytes_recv / (1024**2):.2f} MB ({io.packets_recv} 包)")
        
        return "\n".join(info)
        
    except Exception as e:
        return f"[ERROR] 获取网络信息失败: {str(e)}"


def ping_host(host: str, count: int = 4) -> str:
    """
    Ping 指定主机
    
    Args:
        host: 目标主机名或 IP
        count: Ping 次数
        
    Returns:
        Ping 结果
    """
    system = platform.system().lower()
    
    if system == "windows":
        cmd = f"ping -n {count} {host}"
    else:
        cmd = f"ping -c {count} {host}"
    
    return bash(cmd, timeout=count * 5 + 10)


def check_port(host: str, port: int, timeout: int = 5) -> str:
    """
    检查端口是否开放
    
    Args:
        host: 目标主机
        port: 端口号
        timeout: 超时秒数
        
    Returns:
        检查结果
    """
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            return f"[OK] {host}:{port} 端口开放"
        else:
            return f"[WARN] {host}:{port} 端口关闭或无法连接"
            
    except socket.gaierror:
        return f"[ERROR] 无法解析主机名: {host}"
    except socket.timeout:
        return f"[ERROR] 连接超时"
    except Exception as e:
        return f"[ERROR] 检查失败: {str(e)}"


def get_environment_variables(filter_key: Optional[str] = None) -> str:
    """
    获取环境变量
    
    Args:
        filter_key: 过滤关键字（可选）
        
    Returns:
        环境变量列表
    """
    result = ["[环境变量]"]
    
    env_vars = dict(os.environ)
    
    if filter_key:
        env_vars = {k: v for k, v in env_vars.items() if filter_key.lower() in k.lower()}
        result[0] = f"[环境变量] (包含 '{filter_key}')"
    
    for key in sorted(env_vars.keys()):
        value = env_vars[key]
        # 对于 PATH 类变量，换行显示
        if 'PATH' in key.upper() and ';' in value:
            result.append(f"\n{key}:")
            for path in value.split(';'):
                if path:
                    result.append(f"  {path}")
        else:
            result.append(f"{key}={value}")
    
    return "\n".join(result)


# 工具函数字典
bash_TOOLS = {
    "bash": bash,  # Renamed from bash
    "get_system_info": get_system_info,
    "list_processes": list_processes,
    "get_network_info": get_network_info,
    "ping_host": ping_host,
    "check_port": check_port,
    "get_environment_variables": get_environment_variables,
}


def get_tools() -> List:
    """返回所有 Bash 工具函数列表"""
    return list(bash_TOOLS.values())
