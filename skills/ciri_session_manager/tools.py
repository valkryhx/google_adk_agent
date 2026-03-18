"""
Ciri Session Manager - 查询和导出 ADK Session 内容工具集

提供查询 Session 内容、导出 Session 为 JSON 等功能。
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

# Windows 平台下强制 sys.stdout 为 utf-8 编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def get_default_db_path() -> str:
    """
    获取默认数据库路径。
    从脚本所在目录向上推导到项目根目录，然后找到 sqlite_db/adk_sessions_port_8000.db
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(curr_dir))
    
    db_path = os.path.join(project_root, "sqlite_db", "adk_sessions_port_8000.db")
    
    if not os.path.exists(db_path):
        fallback_path = os.path.join(os.getcwd(), "sqlite_db", "adk_sessions_port_8000.db")
        if os.path.exists(fallback_path):
            return os.path.abspath(fallback_path)
    
    return db_path


def get_all_available_dbs() -> list:
    """
    获取所有可用的数据库文件列表。
    自动扫描 sqlite_db 目录下的所有 adk_sessions_*.db 文件。
    
    Returns:
        数据库路径列表
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(curr_dir))
    
    sqlite_dir = os.path.join(project_root, "sqlite_db")
    available_dbs = []
    
    if os.path.exists(sqlite_dir) and os.path.isdir(sqlite_dir):
        for filename in os.listdir(sqlite_dir):
            if filename.startswith("adk_sessions_") and filename.endswith(".db"):
                db_path = os.path.join(sqlite_dir, filename)
                if os.path.exists(db_path):
                    available_dbs.append(db_path)
    
    # 如果没找到，尝试当前工作目录
    if not available_dbs:
        cwd_sqlite_dir = os.path.join(os.getcwd(), "sqlite_db")
        if os.path.exists(cwd_sqlite_dir) and os.path.isdir(cwd_sqlite_dir):
            for filename in os.listdir(cwd_sqlite_dir):
                if filename.startswith("adk_sessions_") and filename.endswith(".db"):
                    db_path = os.path.join(cwd_sqlite_dir, filename)
                    if os.path.exists(db_path):
                        available_dbs.append(db_path)
    
    return available_dbs


def parse_event_json(event_json_str: str, with_response: bool = False) -> str:
    """
    解析 event_json，提取可读的对话内容。
    
    Args:
        event_json_str: JSON 字符串
        with_response: 是否显示工具响应内容
        
    Returns:
        格式化后的文本
    """
    try:
        data = json.loads(event_json_str)
        content = data.get("content", {})
        parts = content.get("parts", [])
        result_lines = []
        
        for part in parts:
            if "text" in part and part["text"]:
                result_lines.append(f"[Text]: {part['text'].strip()}")
            elif "function_call" in part and part["function_call"]:
                fc = part["function_call"]
                name = fc.get('name', fc.get('function_name', '未知'))
                args = fc.get('args', fc.get('arguments', {}))
                result_lines.append(f"[FunctionCall]: {name}(args={args})")
            elif "function_response" in part and part["function_response"]:
                if with_response:
                    fr = part["function_response"]
                    resp = fr.get('response', fr.get('content', ''))
                    result_lines.append(f"[FunctionResp]: {str(resp)[:400]}...")
                else:
                    result_lines.append(f"[FunctionResp]: (已隐藏响应)")
            elif "executable_code" in part and part["executable_code"]:
                ec = part["executable_code"]
                result_lines.append(f"[Code]: {ec.get('code')}")
        
        if not result_lines:
            if "text" in data:
                result_lines.append(f"[Text]: {data['text']}")
        
        return "\n".join(result_lines)
    except Exception as e:
        return f"[解析 JSON 出错：{e}]"


def list_sessions(
    limit: int = 10, 
    db_paths: Optional[list] = None,
    show_db_name: bool = True
) -> Dict[str, Any]:
    """
    列出最近的 Session 列表。
    支持单数据库或多数据库联合查询。
    
    Args:
        limit: 每个数据库返回的 Session 数量
        db_paths: 数据库路径列表（可选，默认自动扫描所有可用数据库）
                 如果为 None，自动扫描所有 adk_sessions_*.db
                 如果为字符串列表，使用指定的数据库
        show_db_name: 是否在结果中包含数据库名称
        
    Returns:
        包含 Session 列表的字典
    """
    # 确定数据库列表
    if db_paths is None:
        db_paths = get_all_available_dbs()
        if not db_paths:
            # 如果没找到任何数据库，尝试默认路径
            default_db = get_default_db_path()
            if os.path.exists(default_db):
                db_paths = [default_db]
            else:
                return {"error": "找不到任何数据库文件，请确保 sqlite_db 目录下有 adk_sessions_*.db 文件"}
    elif isinstance(db_paths, str):
        db_paths = [db_paths]
    
    # 过滤存在的数据库
    valid_dbs = [db for db in db_paths if os.path.exists(db)]
    if not valid_dbs:
        return {"error": "指定的数据库文件不存在"}
    
    all_sessions = []
    db_results = {}
    
    for db_path in valid_dbs:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            query = """
            SELECT id, app_name, user_id, session_id, session_metadata, created_at 
            FROM adk_sessions 
            ORDER BY id DESC 
            LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            
            db_name = os.path.basename(db_path)
            db_results[db_name] = []
            
            for id_val, app, user, sid, metadata, ts in rows:
                session_info = {
                    "id": id_val,
                    "app_name": app,
                    "user_id": user,
                    "session_id": sid,
                    "session_metadata": metadata,
                    "created_at": str(ts)
                }
                if show_db_name:
                    session_info["source_db"] = db_name
                db_results[db_name].append(session_info)
                all_sessions.append(session_info)
            
            conn.close()
        except Exception as e:
            db_name = os.path.basename(db_path)
            db_results[db_name] = {"error": str(e)}
    
    # 按创建时间排序所有会话
    all_sessions.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "success": True,
        "total_count": len(all_sessions),
        "databases_queried": len(valid_dbs),
        "sessions": all_sessions[:limit * len(valid_dbs)],  # 限制总数
        "db_results": db_results
    }


def get_latest_session(db_paths: Optional[list] = None) -> Dict[str, Any]:
    """
    获取最新的 Session ID。
    支持多数据库联合查询，返回所有数据库中最新的 Session。
    
    Args:
        db_paths: 数据库路径列表（可选，默认自动扫描所有可用数据库）
        
    Returns:
        包含最新 Session ID 的字典
    """
    # 确定数据库列表
    if db_paths is None:
        db_paths = get_all_available_dbs()
        if not db_paths:
            default_db = get_default_db_path()
            if os.path.exists(default_db):
                db_paths = [default_db]
            else:
                return {"error": "找不到任何数据库文件"}
    elif isinstance(db_paths, str):
        db_paths = [db_paths]
    
    valid_dbs = [db for db in db_paths if os.path.exists(db)]
    if not valid_dbs:
        return {"error": "指定的数据库文件不存在"}
    
    latest_session = None
    latest_time = None
    latest_db = None
    
    for db_path in valid_dbs:
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            query = """
            SELECT id, session_id, created_at
            FROM adk_sessions 
            ORDER BY id DESC 
            LIMIT 1
            """
            cursor.execute(query)
            row = cursor.fetchone()
            conn.close()
            
            if row:
                sid, created_at = row[1], row[2]
                if latest_time is None or str(created_at) > str(latest_time):
                    latest_time = created_at
                    latest_session = sid
                    latest_db = os.path.basename(db_path)
        except Exception as e:
            continue
    
    if latest_session:
        return {
            "success": True, 
            "session_id": latest_session,
            "source_db": latest_db,
            "created_at": str(latest_time)
        }
    else:
        return {"error": "找不到任何 Session 记录"}


def query_session(
    session_id: str, 
    with_response: bool = False, 
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    查询指定 Session 的完整对话内容。
    
    Args:
        session_id: Session ID
        with_response: 是否显示工具响应内容
        db_path: 数据库路径（可选）
        
    Returns:
        包含对话内容的字典
    """
    if db_path is None:
        db_path = get_default_db_path()
    
    if not os.path.exists(db_path):
        return {"error": f"找不到数据库文件：{db_path}"}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT e.role, e.event_json, e.timestamp, e.id
        FROM adk_events e
        JOIN adk_sessions s ON e.session_internal_id = s.id
        WHERE s.session_id = ?
        ORDER BY e.id ASC
        """
        cursor.execute(query, (session_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {"success": True, "session_id": session_id, "messages": [], "message": "该 Session 暂无消息记录"}
        
        messages = []
        for role, event_json_str, ts, eid in rows:
            try:
                event_obj = json.loads(event_json_str)
                readable_text = parse_event_json(event_json_str, with_response)
                
                messages.append({
                    "id": eid,
                    "role": role,
                    "timestamp": str(ts),
                    "text": readable_text,
                    "content": event_obj.get("content", {})
                })
            except Exception as e:
                messages.append({
                    "id": eid,
                    "role": role,
                    "timestamp": str(ts),
                    "error": f"解析失败：{str(e)}"
                })
        
        return {
            "success": True,
            "session_id": session_id,
            "message_count": len(messages),
            "messages": messages
        }
    except Exception as e:
        return {"error": f"查询失败：{str(e)}"}


def export_session_to_json(
    session_id: str, 
    output_path: str, 
    include_raw: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    将 Session 导出为 JSON 文件。
    
    Args:
        session_id: Session ID
        output_path: 输出文件路径
        include_raw: 是否包含原始 event_json 数据
        db_path: 数据库路径（可选）
        
    Returns:
        导出结果信息
    """
    if db_path is None:
        db_path = get_default_db_path()
    
    if not os.path.exists(db_path):
        return {"error": f"找不到数据库文件：{db_path}"}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        query = """
        SELECT e.id, e.role, e.event_json, e.timestamp
        FROM adk_events e
        JOIN adk_sessions s ON e.session_internal_id = s.id
        WHERE s.session_id = ?
        ORDER BY e.id ASC
        """
        cursor.execute(query, (session_id,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return {"success": False, "message": "该 Session 暂无消息记录"}
        
        export_data = {
            "session_id": session_id,
            "exported_at": str(datetime.now()),
            "message_count": len(rows),
            "messages": []
        }
        
        for eid, role, event_json_str, ts in rows:
            try:
                event_obj = json.loads(event_json_str)
                
                message_entry = {
                    "id": eid,
                    "role": role,
                    "timestamp": str(ts),
                    "content": event_obj.get("content", {})
                }
                
                if include_raw:
                    message_entry["raw_event_json"] = event_obj
                
                export_data["messages"].append(message_entry)
            except Exception as e:
                continue
        
        # 确保输出目录存在
        output_dir = os.path.dirname(os.path.abspath(output_path))
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message": f"成功导出 {len(export_data['messages'])} 条消息",
            "output_path": output_path,
            "message_count": len(export_data['messages'])
        }
    except Exception as e:
        return {"error": f"导出失败：{str(e)}"}


def export_latest_session_to_json(
    output_path: str, 
    include_raw: bool = True,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    导出最新 Session 为 JSON 文件。
    
    Args:
        output_path: 输出文件路径
        include_raw: 是否包含原始 event_json 数据
        db_path: 数据库路径（可选）
        
    Returns:
        导出结果信息
    """
    if db_path is None:
        db_path = get_default_db_path()
    
    # 先获取最新 Session ID
    latest_result = get_latest_session(db_path)
    if "error" in latest_result:
        return latest_result
    
    session_id = latest_result["session_id"]
    return export_session_to_json(session_id, output_path, include_raw, db_path)


# 工具函数字典
CIRI_SESSION_TOOLS = {
    "list_sessions": list_sessions,
    "get_latest_session": get_latest_session,
    "query_session": query_session,
    "export_session_to_json": export_session_to_json,
    "export_latest_session_to_json": export_latest_session_to_json,
}


def get_tools(*args, **kwargs) -> List:
    """
    返回所有 Session 管理工具函数列表。
    
    Returns:
        工具函数列表
    """
    return list(CIRI_SESSION_TOOLS.values())
