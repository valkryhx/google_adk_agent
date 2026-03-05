import sqlite3
import json

db_path = r'd:\git_codes\google_adk_helloworld_git\sqlite_db\adk_sessions_port_8000.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, session_id FROM adk_sessions ORDER BY updated_at DESC LIMIT 1")
    res = cursor.fetchone()
    if res:
        internal_id, session_uuid = res
        print(f"--- Session: {session_uuid} (Internal ID: {internal_id}) ---")
        
        cursor.execute("SELECT id, role, event_json FROM adk_events WHERE session_internal_id = ? ORDER BY id", (internal_id,))
        rows = cursor.fetchall()
        
        for r_id, role, event_json in rows:
            event_data = json.loads(event_json)
            parts_desc = []
            
            # 1. 提取 content.parts 逻辑
            content = event_data.get('content')
            if content and isinstance(content, dict):
                parts = content.get('parts', [])
                if parts:
                    for p in parts:
                        if not isinstance(p, dict): continue
                        if p.get('text'): parts_desc.append(f"Text: {p['text'][:30]}...")
                        elif p.get('inline_data') or p.get('file_data'): parts_desc.append("Media: [IMAGE]")
                        elif p.get('function_call'): parts_desc.append(f"FC: {p['function_call'].get('name')}")
                        elif p.get('function_response'): parts_desc.append(f"FR: {p['function_response'].get('name')}")
            
            # 2. 提取 actions 逻辑 (增加鲁棒性)
            if not parts_desc:
                actions = event_data.get('actions', [])
                if actions:
                    formatted_actions = []
                    for a in actions:
                        if isinstance(a, dict):
                            formatted_actions.append(a.get('type', 'UnknownAction'))
                        else:
                            # 处理 a 是字符串的情况，例如 ['observation', 'thought']
                            formatted_actions.append(str(a))
                    parts_desc.append(f"Actions: {formatted_actions}")
            
            # 3. 兜底提取：如果没有 parts 也没有 actions，可能在 metadata 或其他字段
            if not parts_desc:
                if event_data.get('observation'): parts_desc.append(f"Obs: {str(event_data['observation'])[:30]}...")
                elif event_data.get('thought'): parts_desc.append(f"Thought: {str(event_data['thought'])[:30]}...")

            print(f"DB_ID[{r_id}] Role: {role:10} | Parts: {parts_desc}")

except Exception as e:
    import traceback
    print(f"Error: {e}")
    traceback.print_exc()

conn.close()
