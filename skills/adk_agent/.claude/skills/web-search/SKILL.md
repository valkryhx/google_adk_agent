---
name: web-search
description: Perform web searches and extract content from URLs using the Tavily API. Use this skill to find real-time information, news, or deep-dive into specific web pages.
---

# Web Search

## Overview

This skill provides capabilities to search the web and extract content from specific URLs. It uses the Tavily API to ensure high-quality, LLM-ready results.

## Workflow

1.  **Search**: Use when you need to find information, answer questions, or discover resources.
2.  **Extract**: Use when you have a specific URL (e.g., from a search result or user input) and need to read its full content.

## Usage

### 1. Search the Web

To search for information, you **must** have the `bash` skill loaded and use the `bash` tool to run the `search.py` script.

```bash
python skills/adk_agent/.claude/skills/web-search/scripts/search.py --query "your search query"
```

**Optional Arguments:**
- `--depth`: "basic" (default, fast) or "advanced" (comprehensive).
- `--include-answer`: If set, returns a generated answer summary.
- `--include-raw-content`: If set, returns the full content of the search results.

### 2. Extract Content from URL

To read the content of a specific URL, run the `search.py` script with the `--url` argument.

```bash
python skills/adk_agent/.claude/skills/web-search/scripts/search.py --url "https://example.com/article"
```

## Examples

**User:** "What are the latest features in Python 3.13?"
**Action:**
1. `skill_load(skill_id="bash")` (if not already loaded)
2. `bash(command="python skills/adk_agent/.claude/skills/web-search/scripts/search.py --query \"Python 3.13 new features\" --include-answer")`

**User:** "Read this article for me: https://example.com/long-article"
**Action:**
```bash
python skills/adk_agent/.claude/skills/web-search/scripts/search.py --url "https://example.com/long-article"
```
