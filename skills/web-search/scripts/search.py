#!/usr/bin/env python3
"""
Web Search & Extraction Script using Tavily API.
Reads API Key from private_key.yaml in the project root.
"""

import argparse
import json
import os
import sys
import yaml
from pathlib import Path

# Force UTF-8 encoding for stdout to handle non-ASCII characters on Windows
sys.stdout.reconfigure(encoding='utf-8')

# Try to import TavilyClient, handle missing dependency
try:
    from tavily import TavilyClient
except ImportError:
    print(json.dumps({
        "error": "Missing dependency 'tavily-python'. Please install it using: pip install tavily-python"
    }))
    sys.exit(1)

def load_api_key():
    """Load Tavily API Key from private_key.yaml."""
    # Find project root (assuming script is deep in skills/...)
    # Current script path: skills/adk_agent/.claude/skills/web-search/scripts/search.py
    # Project root is 6 levels up
    script_path = Path(__file__).resolve()
    project_root = script_path.parents[6] 
    
    # Fallback: try to find private_key.yaml by walking up
    current_dir = script_path.parent
    while current_dir != current_dir.parent:
        config_path = current_dir / "private_key.yaml"
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    return config.get("tavily_api_key")
            except Exception as e:
                return None
        current_dir = current_dir.parent
    
    return None

API_KEY = load_api_key() or os.environ.get("TAVILY_API_KEY")

def search(query, depth="basic", include_answer=False, include_raw_content=False):
    """Perform a web search."""
    if not API_KEY:
        return {"error": "TAVILY_API_KEY not found in private_key.yaml or environment variables."}

    client = TavilyClient(api_key=API_KEY)
    try:
        response = client.search(
            query=query,
            search_depth=depth,
            include_answer=include_answer,
            include_raw_content=include_raw_content
        )
        return response
    except Exception as e:
        return {"error": str(e)}

def extract(url):
    """Extract content from a URL."""
    if not API_KEY:
        return {"error": "TAVILY_API_KEY not found in private_key.yaml or environment variables."}

    client = TavilyClient(api_key=API_KEY)
    try:
        response = client.extract(urls=[url])
        return response
    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Web Search and Extraction Tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--query", help="Search query")
    group.add_argument("--url", help="URL to extract content from")

    parser.add_argument("--depth", choices=["basic", "advanced"], default="basic", help="Search depth")
    parser.add_argument("--include-answer", action="store_true", help="Include generated answer")
    parser.add_argument("--include-raw-content", action="store_true", help="Include raw content")

    args = parser.parse_args()

    if args.query:
        result = search(
            query=args.query,
            depth=args.depth,
            include_answer=args.include_answer,
            include_raw_content=args.include_raw_content
        )
    elif args.url:
        result = extract(url=args.url)
    
    # Print JSON output for the agent to parse
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
