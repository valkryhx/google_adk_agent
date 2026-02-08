
import asyncio
import os
import sys
import json
from datetime import datetime

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

try:
    from src.shared.db.custom_table_db_service import FullyCustomDbService
    from google.adk.events import Event as AdkEvent
    from google.adk.sessions import Session
except ImportError as e:
    print(f"Import Error: {e}")
    # Fallback/Mocking if google.adk is not found for strict testing of just the DB service class structure
    # But we really want to test integration.
    print("Ensure google-adk is installed or in path.")
    sys.exit(1)

# Mock Event if needed (but we imported it)
# We will use the real class.

async def main():
    print("--- Starting DB Service Test ---")
    
    import time
    db_file = f"test_adk_sessions_{int(time.time())}.db"
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except:
            pass
        
    db_url = f"sqlite+aiosqlite:///{db_file}"
    print(f"DB URL: {db_url}")
    
    service = FullyCustomDbService(db_url=db_url)
    
    print("1. Initializing DB...")
    await service.init_db()
    print("   DB Initialized.")
    
    app_name = "test_app"
    user_id = "test_user"
    session_id = "session_001"
    
    print("\n2. Creating Session...")
    session = await service.create_session(app_name, user_id, session_id)
    print(f"   Session Created: {session.id}")
    
    # Verify properties
    assert session.app_name == app_name
    assert session.user_id == user_id
    
    print("\n3. Creating Event...")
    # Create a dummy event
    # Assuming AdkEvent structure based on usage in service: .model_dump(), .role, .content
    # We might need to construct it correctly.
    # Let's check signature if possible, or try generic construction.
    # Usually pydantic model.
    try:
        # Try to use correct fields based on error message
        # author is required. type/source/text are strict extra forbidden.
        # It likely accepts content.
        event = AdkEvent(
            author="user",
            content={
                "role": "user",
                "parts": [{"text": "Hello World"}]
            }
        )
        print("   (Used AdkEvent)")
    except Exception as e:
        print(f"   [Debug] AdkEvent init failed: {e}")
        # Fallback to loose construction if specific fields required
        class MockContent:
            role = "user"
            parts = ["Hello"]
        
        class MockEvent:
            role = "user"
            type = "message"
            source = "user"
            partial = False
            actions = None
            content = MockContent()
            def model_dump(self, mode='json'):
                return {
                    "role": self.role, 
                    "type": self.type, 
                    "source": self.source, 
                    "partial": self.partial,
                    "content": {"role": "user", "parts": ["Hello"]}
                }
        
        event = MockEvent()
        print("   (Used MockEvent)")

    # Real AdkEvent usage:
    # We will try to use the imported class first. If it requires specific args, we might fail.
    # Let's try to inspect it or just run and see.
    
    # 3. Append Event
    print("\n4. Appending Event...")
    
    # We used MockEvent or real AdkEvent. 
    # If MockEvent, we need to ensure it has model_dump method as expected by service.
    # The MockEvent class I defined earlier has model_dump.
    
    # Actually call append_event
    try:
        await service.append_event(session, event)
        print("   Event Appended.")
    except Exception as e:
        print(f"   Error appending event: {e}")
        import traceback
        traceback.print_exc()

    print(f"   [Debug] session.events count before save: {len(session.events)}")
    if len(session.events) > 0:
        print(f"   [Debug] First event type: {type(session.events[0])}")

    # SAVE SESSION (Full Sync)
    print("\n4b. Saving Session (Full Sync)...")
    await service.save_session(session)
    print("   Session Saved.")
    
    # For now, let's just test get_session on empty
    print("\n5. Retrieving Session...")
    loaded_session = await service.get_session(app_name, user_id, session_id)
    
    if loaded_session:
        print(f"   Loaded Session: {loaded_session.id}")
        print(f"   Events count: {len(loaded_session.events)}")
        if len(loaded_session.events) > 0:
            print("   SUCCESS: Event persisted!")
        else:
            print("   FAILURE: No events found!")
    else:
        print("   ERROR: Session not found!")
    
    # Clean up
    await service.engine.dispose()
    
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            print("\nCleaned up test db.")
        except Exception as e:
            print(f"Cleanup warning: {e}")

if __name__ == "__main__":
    asyncio.run(main())
