import sqlite3
import pickle
import os
import sys
import json

# Add parent directory to path to find packages if needed, though we just need pickle class definitions if they are custom objects.
# Google ADK events are likely protobufs or structured objects. 
# If pickle fails due to missing classes, we might need to import them.
# Usually ADK uses 'google.ai.generativelanguage' classes regarding Content/Part.
# But let's try basic unpickle first.

DB_PATH = r"d:\git_repos\20260202\google_adk_agent\sqlite_db\adk_sessions_port_8000.db"

if not os.path.exists(DB_PATH):
    print(f"DB not found at {DB_PATH}")
    # Try finding any db
    files = [f for f in os.listdir('.') if f.endswith('.db')]
    if files:
        DB_PATH = files[0]
        print(f"Using {DB_PATH}")
    else:
        print("No .db files found in current directory.")
        exit()

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get latest session from adk_sessions table
    cursor.execute("SELECT id, session_id FROM adk_sessions ORDER BY updated_at DESC LIMIT 1")
    row = cursor.fetchone()

    if not row:
        print("No sessions found in adk_sessions")
        exit()

    internal_id, session_id = row
    print(f"Session: {session_id} (Internal ID: {internal_id})")

    # Get events for this session
    cursor.execute("SELECT event_json FROM adk_events WHERE session_internal_id = ? ORDER BY id ASC", (internal_id,))
    event_rows = cursor.fetchall()

    print(f"Events count: {len(event_rows)}")

    for i, (evt_json,) in enumerate(event_rows):
        try:
            event_dict = json.loads(evt_json)
            # Inspect content -> parts
            if 'content' in event_dict and 'parts' in event_dict['content']:
                parts = event_dict['content']['parts']
                for j, part in enumerate(parts):
                    # Check for function_call
                    if 'function_call' in part:
                        fc = part['function_call']
                        if fc:
                            print(f"[FOUND] Event {i} Part {j} FunctionCall Name: '{fc.get('name')}'")
                            print(f"  Args: {fc.get('args')}")
                    
                    if 'function_response' in part:
                         fr = part['function_response']
                         if fr:
                             print(f"[RESULT] Event {i} Part {j} FunctionResponse Name: '{fr.get('name')}'")
                             # Assuming 'response' is the content
                             import re
                             result_str = None
                             resp_content = fr.get('response', {})
                             if isinstance(resp_content, dict) and 'result' in resp_content:
                                 result_str = resp_content['result']
                                 print(f"  [EXTRACTED Clean Result] Length: {len(result_str)}")
                                 print(f"  [Preview] {result_str[:100]}...")
                                 
                                 # Test Regex
                                 regex_pattern = r"--- 任务 (\d+) 结果 ---\n([\s\S]*?)(?=\n--- 任务|\n$|$)"
                                 matches = re.finditer(regex_pattern, result_str)
                                 count = 0
                                 for m in matches:
                                     count += 1
                                     print(f"  [REGEX MATCH {count}] Task {m.group(1)} Success!")
                                 
                                 if count == 0:
                                     print("  [REGEX FAIL] No matches found.")
                             else:
                                 print(f"  [EXTRACT FAIL] 'result' key not found in response: {type(resp_content)}")
                                 print(f"  Response keys: {resp_content.keys() if isinstance(resp_content, dict) else 'Not dict'}")

                    # Check text for loose match
                    if 'text' in part and part['text']:
                        if "dispatch_task" in part['text']:
                            print(f"[TEXT MATCH] Event {i} Text contains 'dispatch_task': {part['text'][:50]}...")
                            
        except json.JSONDecodeError:
            print(f"Event {i} JSON Decode Error")

except Exception as e:
    print(f"Error: {str(e)}")
