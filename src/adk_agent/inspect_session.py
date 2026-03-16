#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os
import json
import argparse
import sys

## 用法
#
# 🔧 本脚本是一个综合辅助诊断工具，支持单离线库及跨离线库一键综合对账。
#
# 1. 基础用法 (使用默认数据库)
#    - 列出最近 10 个会话:
#      python src/adk_agent/inspect_session.py --list 10
#
#    - 全局检索对话关键字:
#      python src/adk_agent/inspect_session.py --search "你是谁"
#
#    - 打印特定 Session 完整对话流:
#      python src/adk_agent/inspect_session.py --session-id "<Session_ID>"
#
#    - 一键导出 Session 原始 Parts 历史:
#      python src/adk_agent/inspect_session.py --export "<Session_ID>"
#
# 2. 🔀 高阶用法：多数据库联调 (跨库连环对账)
#    通过 `--db` 指定一个或多个数据库路径，工具将按照顺序对其连续运行指定子命令：
#
#    - 在多个库中，同时列出最近 5 个 Session:
#      python src/adk_agent/inspect_session.py --db sqlite_db/adk_sessions_port_8000.db sqlite_db/adk_sessions_port_8001.db --list 5
#
#    - 在多个库中，一键全局通搜关键词（推荐排障姿势）:
#      python src/adk_agent/inspect_session.py --db sqlite_db/adk_sessions_port_8000.db sqlite_db/adk_sessions_port_8002.db --search "你是谁"
#
# 3. 说明
#    - 如果不指定 `--db`，工具会自动推导至 `sqlite_db/adk_sessions_port_8000.db` 兜底。
#    - 工具内部已注入 `sys.stdout.reconfigure(encoding='utf-8')`，确保 Windows CMD 输出宽字符安全。

# Windows 平台下强制 sys.stdout 为 utf-8 编码，防止 print 宽字符/Emoji 爆 GBK 错误
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def get_default_db_path():
    """
    假设该脚本放置在 src/adk_agent 目录下。
    自动向外退两层找 sqlite_db/adk_sessions_port_8000.db。
    """
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(curr_dir))
    db_path = os.path.join(project_root, "sqlite_db", "adk_sessions_port_8000.db")
    if not os.path.exists(db_path):
        # 兜底：看当前工作目录
        if os.path.exists("./sqlite_db/adk_sessions_port_8000.db"):
             return os.path.abspath("./sqlite_db/adk_sessions_port_8000.db")
    return db_path

def parse_event_json(event_json_str, with_resp=False):
    """
    解析 event_json，美化提取 Text, FunctionCall 和 Response。
    """
    try:
        data = json.loads(event_json_str)
        content = data.get("content", {})
        parts = content.get("parts", [])
        result_lines = []
        for part in parts:
            if "text" in part and part["text"]:
                result_lines.append(f"  [Text]: {part['text'].strip()}")
            elif "function_call" in part and part["function_call"]:
                fc = part["function_call"]
                name = fc.get('name', fc.get('function_name', '未知'))
                args = fc.get('args', fc.get('arguments', {}))
                result_lines.append(f"  [FunctionCall]: {name}(args={args})")
            elif "function_response" in part and part["function_response"]:
                if with_resp:
                     fr = part["function_response"]
                     resp = fr.get('response', fr.get('content', ''))
                     result_lines.append(f"  [FunctionResp]: {str(resp)[:400]} ...")
                else:
                     result_lines.append(f"  [FunctionResp]: (已隐藏响应，使用 --with-response 展开)")
            elif "executable_code" in part and part["executable_code"]:
                ec = part["executable_code"]
                result_lines.append(f"  [Code]: {ec.get('code')}")

        if not result_lines:
             if "text" in data: result_lines.append(f"  [Text]: {data['text']}")
        return "\n".join(result_lines)
    except:
        return "  [解析 JSON 对话出错]"

def list_sessions(cursor, limit=10):
    print(f"\n📋 --- 正在查看最近的 {limit} 个会话 ---")
    query = """
    SELECT id, app_name, user_id, session_id, session_metadata, created_at 
    FROM adk_sessions 
    ORDER BY id DESC 
    LIMIT ?
    """
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    for id_val, app, user, sid, metadata, ts in rows:
        print(f"\n📌 Session ID: {sid}")
        print(f"   - App: {app} | User: {user}")
        print(f"   - 标题/元数据: {metadata}")
        print(f"   - 创立时间: {ts}")

def inspect_single_session(cursor, session_id, with_resp=False):
    print(f"\n📌 --- 正在加载完整对话流: {session_id} ---")
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
        print("   (该 Session 暂无任何对话或消息记录)")
        return

    print(f"   共发现 {len(rows)} 条消息线索：")
    for role, event_json, ts, eid in rows:
        print(f"\n--- [ID: {eid} | {ts}] 角色: {role} ---")
        print(parse_event_json(event_json, with_resp=with_resp))

def search_anywhere(cursor, keyword, with_resp=False):
    print(f"\n🎯 --- 对话内容全局检索: '{keyword}' ---")
    query = """
    SELECT s.session_id, e.role, e.event_json, e.id, e.timestamp 
    FROM adk_events e
    JOIN adk_sessions s ON e.session_internal_id = s.id
    WHERE e.event_json LIKE ?
    ORDER BY e.id DESC
    LIMIT 15
    """
    cursor.execute(query, ('%' + keyword + '%',))
    rows = cursor.fetchall()
    if not rows:
        print("   (在任何历史消息流中未找到该匹配项)")
        return

    print(f"   展示最近 {len(rows)} 条命中点：")
    for sid, role, event_json, eid, ts in rows:
        print(f"\n🎯 [Session: {sid}] | 角色: {role} | ID: {eid} | {ts}")
        print(parse_event_json(event_json, with_resp=with_resp))

def export_session_parts(cursor, session_id):
    print(f"\n📂 --- 正在导出原始 Event JSON 到文件... ---")
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
        print("   (该 Session 暂无消息记录，无法导出)")
        return

    full_data = []      # 包含所有元数据的完整列表
    history_data = []   # 纯净的 LlmMessage (role + parts) 历史流列表

    for eid, role, event_json_str, ts in rows:
        try:
             event_obj = json.loads(event_json_str)
             
             # 1. 组装 Full Data
             full_data.append({
                 "id": eid,
                 "role": role,
                 "timestamp": str(ts),
                 "event_json": event_obj
             })
             
             # 2. 组装 History Parts Data (剥离外部元数据，取 content)
             if "content" in event_obj:
                 content_obj = event_obj["content"]
                 # 确保包含了 parts 且非空
                 if "parts" in content_obj:
                     history_data.append({
                         "role": content_obj.get("role", role.lower()),
                         "parts": content_obj["parts"]
                     })
        except:
             pass

    curr_dir = os.path.dirname(os.path.abspath(__file__))

    # 导出文件 1: Full
    full_file = f"session_{session_id}_full.json"
    full_path = os.path.join(curr_dir, full_file)
    with open(full_path, "w", encoding="utf-8") as f:
         json.dump(full_data, f, ensure_ascii=False, indent=2)

    # 导出文件 2: Pure Parts History
    history_file = f"session_{session_id}_parts_history.json"
    history_path = os.path.join(curr_dir, history_file)
    with open(history_path, "w", encoding="utf-8") as f:
         json.dump(history_data, f, ensure_ascii=False, indent=2)
         
    print(f"✅ 成功导出 {len(full_data)} 条完整记录至: {full_path}")
    print(f"✅ 成功提取 {len(history_data)} 条纯净 parts_history 至: {history_path}")

def main():
    parser = argparse.ArgumentParser(description="🔧 Ciri ADK Sessions 综合诊断工具")
    # 修改为 nargs="+" 以支持列表
    parser.add_argument("--db", type=str, nargs="+", help="指定一个或多个数据库文件路径 (默认自动推导)")
    parser.add_argument("--list", type=int, metavar="N", help="列出最近 N 个 Session 的元数据标题")
    parser.add_argument("--session-id", type=str, metavar="ID", help="打印特定 Session ID 的完整上下游对话")
    parser.add_argument("--search", type=str, metavar="KEYWORD", help="在全历史消息流中全局检索并美化展示")
    parser.add_argument("--export", type=str, metavar="ID", help="导出指定 Session 的原始 parts 结构到 JSON 文件")
    parser.add_argument("--with-response", action="store_true", help="打印工具(如bash/sql)产生的巨量响应内容")

    args = parser.parse_args()
    
    # 自动推导默认：如果没传，使用 List[get_default_db_path()]
    db_paths = args.db if args.db else [get_default_db_path()]

    # 如果什么参数都没传，打印 help
    if not any([args.list, args.session_id, args.search, args.export]):
         parser.print_help()
         return

    for db_path in db_paths:
        if not os.path.exists(db_path):
            print(f"\n⚠️ 找不到数据库文件: {db_path}，跳过该库")
            continue

        print(f"\n# ========================================================")
        print(f"# [加载数据库]: {os.path.basename(db_path)}")
        print(f"# ========================================================")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            if args.list:
                list_sessions(cursor, limit=args.list)
            elif args.session_id:
                inspect_single_session(cursor, args.session_id, with_resp=args.with_response)
            elif args.search:
                search_anywhere(cursor, args.search, with_resp=args.with_response)
            elif args.export:
                export_session_parts(cursor, args.export)

        except Exception as e:
            print(f"❌ 运行报错 ({os.path.basename(db_path)}): {e}")
        finally:
            conn.close()

if __name__ == "__main__":
    main()
