#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ciri Session Manager - 查询和导出 ADK Session 内容

功能:
1. 查询指定 Session ID 的完整对话内容
2. 将 Session 内容导出为 JSON 格式便于分享
3. 支持默认当前 Session (最近一个)
4. 全局搜索关键词 (新增)

用法:
 python query_and_export_session.py --session-id <SESSION_ID> --output <OUTPUT_FILE>
 python query_and_export_session.py --latest --output <OUTPUT_FILE>
 python query_and_export_session.py --list 10
 python query_and_export_session.py --search "关键词"
"""

import sqlite3
import os
import json
import argparse
import sys
from datetime import datetime

# Windows 平台下强制 sys.stdout 为 utf-8 编码
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def get_default_db_path():
    """
    获取默认数据库路径。
    从脚本所在目录向上推导到项目根目录，然后找到 sqlite_db/adk_sessions_port_8000.db
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(curr_dir)))
    db_path = os.path.join(project_root, "sqlite_db", "adk_sessions_port_8000.db")
    
    if not os.path.exists(db_path):
        fallback_path = os.path.join(os.getcwd(), "sqlite_db", "adk_sessions_port_8000.db")
        if os.path.exists(fallback_path):
            return os.path.abspath(fallback_path)
    
    return db_path


def parse_event_json(event_json_str, with_response=False):
    """
    解析 event_json，提取可读的对话内容。
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


def list_sessions(cursor, limit=10):
    """
    列出最近的 Session 列表。
    """
    query = """
    SELECT id, app_name, user_id, session_id, session_metadata, created_at 
    FROM adk_sessions 
    ORDER BY id DESC 
    LIMIT ?
    """
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    
    sessions = []
    for id_val, app, user, sid, metadata, ts in rows:
        session_info = {
            "id": id_val,
            "app_name": app,
            "user_id": user,
            "session_id": sid,
            "session_metadata": metadata,
            "created_at": str(ts)
        }
        sessions.append(session_info)
        print(f"\n📌 Session ID: {sid}")
        print(f" - App: {app} | User: {user}")
        print(f" - 元数据：{metadata}")
        print(f" - 创建时间：{ts}")
        
    return sessions


def search_sessions(cursor, keyword, with_response=False, limit=15):
    """
    在全历史消息流中全局检索关键词。
    基于 inspect_session.py 的 search_anywhere 函数优化。
    """
    print(f"\n🎯 --- 对话内容全局检索: '{keyword}' ---")
    query = """
    SELECT s.session_id, e.role, e.event_json, e.id, e.timestamp 
    FROM adk_events e
    JOIN adk_sessions s ON e.session_internal_id = s.id
    WHERE e.event_json LIKE ?
    ORDER BY e.id DESC
    LIMIT ?
    """
    cursor.execute(query, ('%' + keyword + '%', limit))
    rows = cursor.fetchall()
    
    if not rows:
        print(" (在任何历史消息流中未找到该匹配项)")
        return []
    
    print(f" 展示最近 {len(rows)} 条命中点：")
    hits = []
    for sid, role, event_json_str, eid, ts in rows:
        readable_text = parse_event_json(event_json_str, with_response)
        hit_info = {
            "session_id": sid,
            "role": role,
            "message_id": eid,
            "timestamp": str(ts),
            "content": readable_text
        }
        hits.append(hit_info)
        
        print(f"\n🎯 [Session: {sid}] | 角色: {role} | ID: {eid} | {ts}")
        print(readable_text)
    
    return hits


def get_latest_session(cursor):
    """
    获取最新的 Session。
    """
    query = """
    SELECT id, session_id 
    FROM adk_sessions 
    ORDER BY id DESC 
    LIMIT 1
    """
    cursor.execute(query)
    row = cursor.fetchone()
    
    if row:
        return row[1]
    return None


def inspect_session(cursor, session_id, with_response=False):
    """
    获取指定 Session 的完整对话内容。
    """
    query = """
    SELECT e.role, e.event_json, e.timestamp, e.id
    FROM adk_events e
    JOIN adk_sessions s ON e.session_internal_id = s.id
    WHERE s.session_id = ?
    ORDER BY e.id ASC
    """
    cursor.execute(query, (session_id,))
    rows = cursor.fetchall()
    
    if not rows:
        return None, []
    
    conversation_text = []
    conversation_data = []
    
    for eid, role, event_json_str, ts in rows:
        try:
            event_obj = json.loads(event_json_str)
            
            readable_text = parse_event_json(event_json_str, with_response)
            conversation_text.append({
                "id": eid,
                "role": role,
                "timestamp": str(ts),
                "text": readable_text
            })
            
            conversation_data.append({
                "id": eid,
                "role": role,
                "timestamp": str(ts),
                "event_json": event_obj
            })
        except Exception as e:
            print(f"⚠️ 解析消息 ID {eid} 时出错：{e}")
            continue
    
    return "\n".join([f"[{item['role']} @ {item['timestamp']}]\n{item['text']}\n" for item in conversation_text]), conversation_data


def export_session_to_json(cursor, session_id, output_path, include_raw=True):
    """
    将 Session 导出为 JSON 文件。
    """
    query = """
    SELECT e.id, e.role, e.event_json, e.timestamp
    FROM adk_events e
    JOIN adk_sessions s ON e.session_internal_id = s.id
    WHERE s.session_id = ?
    ORDER BY e.id ASC
    """
    cursor.execute(query, (session_id,))
    rows = cursor.fetchall()
    
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
            print(f"⚠️ 处理消息 ID {eid} 时出错：{e}")
            continue
    
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


def main():
    parser = argparse.ArgumentParser(
        description="🔧 Ciri Session Manager - 查询和导出 ADK Session 内容"
    )
    
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="数据库文件路径 (默认自动推导至 sqlite_db/adk_sessions_port_8000.db)"
    )
    
    parser.add_argument(
        "--session-id",
        type=str,
        metavar="ID",
        help="指定要查询/导出的 Session ID"
    )
    
    parser.add_argument(
        "--latest",
        action="store_true",
        help="使用最新的 Session (默认行为)"
    )
    
    parser.add_argument(
        "--list",
        type=int,
        metavar="N",
        help="列出最近 N 个 Session"
    )
    
    parser.add_argument(
        "--search",
        type=str,
        metavar="KEYWORD",
        help="在全历史消息流中全局检索关键词"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        metavar="FILE",
        help="导出 JSON 文件的路径"
    )
    
    parser.add_argument(
        "--with-response",
        action="store_true",
        help="显示工具调用的响应内容"
    )
    
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="导出时不包含原始 event_json 数据，仅保留结构化内容"
    )
    
    args = parser.parse_args()
    
    db_path = args.db if args.db else get_default_db_path()
    
    if not os.path.exists(db_path):
        print(f"❌ 错误：找不到数据库文件：{db_path}")
        sys.exit(1)
    
    print(f"📂 使用数据库：{db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        if args.list:
            sessions = list_sessions(cursor, limit=args.list)
            print(f"\nOK 共找到 {len(sessions)} 个 Session")
            return
        
        if args.search:
            hits = search_sessions(cursor, args.search, args.with_response)
            print(f"\nOK 共找到 {len(hits)} 条匹配记录")
            return
        
        if args.latest or (not args.session_id and not args.list and not args.search):
            session_id = get_latest_session(cursor)
            if not session_id:
                print("❌ 找不到任何 Session 记录")
                sys.exit(1)
            print(f"📌 使用最新 Session: {session_id}")
        else:
            session_id = args.session_id
        
        if not args.output:
            print(f"\n🔍 正在查询 Session: {session_id}")
            conversation_text, _ = inspect_session(cursor, session_id, args.with_response)
            
            if conversation_text:
                print("\n" + "=" * 60)
                print(conversation_text)
                print("=" * 60)
            else:
                print("该 Session 暂无消息记录")
            return
        
        print(f"\n💾 正在导出 Session: {session_id}")
        result = export_session_to_json(
            cursor, 
            session_id, 
            args.output,
            include_raw=not args.no_raw
        )
        
        if result["success"]:
            print(f"OK {result['message']}")
            print(f"📁 输出文件：{result['output_path']}")
        else:
            print(f"❌ {result['message']}")
            sys.exit(1)
        
    except Exception as e:
        print(f"❌ 执行出错：{e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
