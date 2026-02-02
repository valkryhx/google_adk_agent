
import sys
import os
import json
import argparse

# DexManager logic is now in tools.py to support better dynamic loading
# Add current directory to sys.path to ensure we can import tools.py
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from tools import DexManager
except ImportError:
    print("Error: Could not import DexManager from tools.py")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Dex: Task tracking for async work")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: create
    create_parser = subparsers.add_parser("create", help="Create a new task")
    create_parser.add_argument("-d", "--description", required=True, help="One-line summary")
    create_parser.add_argument("--context", default="", help="Background, goal, done-when")

    # Command: list
    list_parser = subparsers.add_parser("list", help="List tasks")
    list_parser.add_argument("--all", action="store_true", help="Include completed tasks")

    # Command: show
    show_parser = subparsers.add_parser("show", help="View task details")
    show_parser.add_argument("id", help="Task ID")
    show_parser.add_argument("--full", action="store_true", help="Show raw JSON")

    # Command: start (CLI 专用)
    start_parser = subparsers.add_parser("start", help="Start a task in background")
    start_parser.add_argument("id", help="Task ID")
    start_parser.add_argument("cmd_args", nargs=argparse.REMAINDER, help="The command to execute")

    # Command: complete
    comp_parser = subparsers.add_parser("complete", help="Complete a task")
    comp_parser.add_argument("id", help="Task ID")
    comp_parser.add_argument("--result", required=True, help="What was done")

    # Command: edit
    edit_parser = subparsers.add_parser("edit", help="Update task context")
    edit_parser.add_argument("id", help="Task ID")
    edit_parser.add_argument("--context", required=True, help="Updated context")

    # Command: delete
    del_parser = subparsers.add_parser("delete", help="Delete a task")
    del_parser.add_argument("id", help="Task ID")

    args = parser.parse_args()
    
    # 实例化 Manager (CLI 默认无 user_id，使用全局空间)
    dex = DexManager()

    try:
        if args.command == "create":
            task = dex.create_task(args.description, args.context)
            print(f"Task created: {task['id']}")

        elif args.command == "list":
            tasks = dex.list_tasks(args.all)
            if not tasks:
                print("(No tasks via Dex)")
            else:
                print(f"{'ID':<10} {'STATUS':<12} {'DESCRIPTION'}")
                print("-" * 60)
                for t in tasks:
                    print(f"{t['id']:<10} {t.get('status', 'pending'):<12} {t['description']}")

        elif args.command == "show":
            task = dex.load_task(args.id)
            if args.full:
                print(json.dumps(task, indent=2, ensure_ascii=False))
            else:
                print(f"ID:          {task['id']}")
                print(f"Status:      {task.get('status', 'unknown')}")
                print(f"Created:     {task['created_at']}")
                print(f"Description: {task['description']}")
                print(f"Context:     {task['context']}")
                if task.get('result'):
                    print(f"Result:      {task['result']}")

        elif args.command == "start":
            if not args.cmd_args:
                print("Error: No command provided to start.")
                return
            
            cmd_parts = args.cmd_args
            dex.start_background_process(args.id, cmd_parts)
            print(f"Task {args.id} started in background.")

        elif args.command == "complete":
            dex.complete_task(args.id, args.result)
            print(f"Task {args.id} marked as completed.")

        elif args.command == "edit":
            dex.update_context(args.id, args.context)
            print(f"Task {args.id} updated.")

        elif args.command == "delete":
            dex.delete_task(args.id)
            print(f"Task {args.id} deleted.")
        
        else:
            parser.print_help()
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
