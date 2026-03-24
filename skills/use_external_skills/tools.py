"""
Use External Skills - 外部 Skill 库查找与加载工具

从 C:\\Users\\drago\\.agents\\skills 目录动态发现、搜索、加载外部 skill 的 Instructions。
外部 skill 可包含：SKILL.md（必须）、附加 .md 文档、scripts/ 可执行脚本、references/ 参考资料、
以及其他代码文件（.js/.ts/.sh/.py 等）。
"""

import os
import re
from typing import Optional

# 外部 skill 库根目录
_EXTERNAL_SKILLS_ROOT = os.path.expanduser(r"C:\Users\drago\.agents\skills")


def _read_skill_md(skill_dir: str) -> Optional[str]:
    """读取 SKILL.md 内容，失败返回 None"""
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def _parse_frontmatter(content: str) -> dict:
    """
    解析 SKILL.md 头部 YAML frontmatter，提取 name / description。
    格式:
        ---
        name: xxx
        description: "..."
        ---
    """
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"\'')
            meta[key] = val
    return meta


def _iter_skills():
    """
    遍历外部 skill 根目录，yield (skill_id, meta, content)。
    跳过不含 SKILL.md 的目录。
    """
    if not os.path.isdir(_EXTERNAL_SKILLS_ROOT):
        return
    for entry in sorted(os.listdir(_EXTERNAL_SKILLS_ROOT)):
        skill_dir = os.path.join(_EXTERNAL_SKILLS_ROOT, entry)
        if not os.path.isdir(skill_dir):
            continue
        content = _read_skill_md(skill_dir)
        if content is None:
            continue
        meta = _parse_frontmatter(content)
        yield entry, meta, content


def list_external_skills() -> str:
    """
    列出 C:\\Users\\drago\\.agents\\skills 中所有可用的外部 skill。

    Returns:
        格式化的 skill 列表，包含 skill_id 和 description。
    """
    rows = []
    for skill_id, meta, _ in _iter_skills():
        name = meta.get("name", skill_id)
        desc = meta.get("description", "（无描述）")
        # description 可能较长，截断到 80 字符
        if len(desc) > 80:
            desc = desc[:77] + "..."
        rows.append(f"  [{skill_id}] {name}\n    {desc}")

    if not rows:
        return f"[WARN] 未找到任何外部 skill，请检查路径: {_EXTERNAL_SKILLS_ROOT}"

    header = f"外部 skill 库: {_EXTERNAL_SKILLS_ROOT}\n共 {len(rows)} 个 skill:\n"
    return header + "\n".join(rows)


def search_external_skill(query: str, top_k: int = 3) -> str:
    """
    根据自然语言意图搜索最相关的外部 skill。

    使用关键词匹配策略：
    - 优先匹配 skill_id 和 name
    - 其次匹配 description
    - 最后匹配 SKILL.md 正文内容

    Args:
        query: 用户意图描述，如 "调试 bug" "生成代码" "网页内容提取"
        top_k: 返回最多几个候选结果，默认 3

    Returns:
        相关 skill 的排名结果和简要说明。
    """
    query_lower = query.lower()
    keywords = re.findall(r"[\w\u4e00-\u9fff]+", query_lower)

    scored = []
    for skill_id, meta, content in _iter_skills():
        name = meta.get("name", skill_id).lower()
        desc = meta.get("description", "").lower()
        body = content.lower()

        score = 0
        for kw in keywords:
            if kw in skill_id.lower():
                score += 10
            if kw in name:
                score += 8
            if kw in desc:
                score += 5
            if kw in body:
                score += 1

        if score > 0:
            scored.append((score, skill_id, meta, content))

    if not scored:
        # 没有命中时，返回全部列表供人工挑选
        return (
            f"[未找到匹配 '{query}' 的 skill]\n"
            "以下是全部外部 skill，请手动指定 skill_id 再调用 load_external_skill():\n"
            + list_external_skills()
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for rank, (score, skill_id, meta, _) in enumerate(scored[:top_k], 1):
        name = meta.get("name", skill_id)
        desc = meta.get("description", "（无描述）")
        results.append(
            f"#{rank} [{skill_id}] {name} (相关度: {score})\n   {desc}"
        )

    best_id = scored[0][1]
    return (
        f"查询 '{query}' 的匹配结果（共 {len(scored)} 个命中，显示 top {min(top_k, len(scored))}）：\n\n"
        + "\n".join(results)
        + f"\n\n推荐使用: load_external_skill('{best_id}')"
    )


def load_external_skill(skill_id: str) -> str:
    """
    加载指定外部 skill 的完整 Instructions。

    加载成功后，agent 应严格按照返回的 Instructions 执行任务，
    就如同该 skill 被原生加载一样。
    如果 skill 包含附加文档（如 .md 文件），也会一并附上。

    Args:
        skill_id: 外部 skill 的目录名，如 "brainstorming" "systematic-debugging"

    Returns:
        该 skill 的完整 Instructions 文本。
    """
    skill_dir = os.path.join(_EXTERNAL_SKILLS_ROOT, skill_id)

    if not os.path.isdir(skill_dir):
        # 模糊匹配：找最接近的 skill_id
        candidates = [
            sid for sid, _, _ in _iter_skills()
            if skill_id.lower() in sid.lower() or sid.lower() in skill_id.lower()
        ]
        hint = f"\n相似 skill_id：{candidates}" if candidates else ""
        return f"[ERROR] 未找到外部 skill '{skill_id}'，路径不存在: {skill_dir}{hint}"

    content = _read_skill_md(skill_dir)
    if content is None:
        return f"[ERROR] skill '{skill_id}' 目录存在但缺少 SKILL.md"

    meta = _parse_frontmatter(content)
    name = meta.get("name", skill_id)

    # 收集同目录下的附加 .md 文件（排除 SKILL.md 本身）
    extra_docs = []
    for fname in sorted(os.listdir(skill_dir)):
        if fname.endswith(".md") and fname.upper() != "SKILL.MD":
            fpath = os.path.join(skill_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    extra_docs.append((fname, f.read()))
            except Exception:
                pass

    sections = [
        f"=== 外部 Skill 已加载: {name} ({skill_id}) ===",
        content,
    ]

    if extra_docs:
        sections.append("\n--- 附加文档 ---")
        for fname, doc in extra_docs:
            sections.append(f"\n### {fname}\n{doc}")

    sections.append(
        "\n=== 加载完成。请严格按照以上 Instructions 执行后续任务。 ==="
    )

    return "\n".join(sections)


_SCRIPT_EXTENSIONS = {".sh", ".js", ".ts", ".py", ".bash", ".zsh", ".ps1"}


def list_external_skill_assets(skill_id: str) -> str:
    """
    列出指定外部 skill（~/.agents/skills）目录下的所有资产文件（脚本、文档、引用等）。
    注意：这是外部 skill 的资产列表，不是本项目 skills/ 目录下的内容。

    Args:
        skill_id: 外部 skill 的 ID（目录名），如 "brainstorming"

    Returns:
        该 skill 目录下所有文件（含子目录）的结构列表，标注文件类型。
    """
    skill_dir = os.path.join(_EXTERNAL_SKILLS_ROOT, skill_id)
    if not os.path.isdir(skill_dir):
        return f"[ERROR] 未找到外部 skill: {skill_id}"

    lines = [f"=== {skill_id} 资产清单 ==="]
    for root, dirs, files in os.walk(skill_dir):
        dirs.sort()
        rel_root = os.path.relpath(root, skill_dir)
        prefix = "" if rel_root == "." else f"{rel_root}/"
        for fname in sorted(files):
            ext = os.path.splitext(fname)[1].lower()
            ftype = "[script]" if ext in _SCRIPT_EXTENSIONS else "[doc]" if ext == ".md" else "[asset]"
            fpath = os.path.join(root, fname)
            size = os.path.getsize(fpath)
            lines.append(f"  {ftype} {prefix}{fname}  ({size} bytes)")
    return "\n".join(lines)


def run_external_skill_script(
    skill_id: str,
    script_path: str,
    args: str = "",
    timeout: int = 60
) -> str:
    """
    执行指定外部 skill（~/.agents/skills）中的脚本文件。
    注意：这是运行外部 skill 的脚本，不是本项目 skills/ 目录下的工具。

    支持 .sh（bash）、.js（node）、.ts（npx ts-node）、.py（python）等。
    脚本路径相对于 skill 目录，例如 "scripts/start-server.sh"。

    Args:
        skill_id:    外部 skill 的 ID，如 "brainstorming"
        script_path: 相对于 skill 目录的脚本路径，如 "scripts/start-server.sh"
        args:        传给脚本的命令行参数（字符串），可为空
        timeout:     超时秒数，默认 60

    Returns:
        脚本的 stdout + stderr 输出，或错误信息。
    """
    import subprocess

    skill_dir = os.path.join(_EXTERNAL_SKILLS_ROOT, skill_id)
    if not os.path.isdir(skill_dir):
        return f"[ERROR] 未找到外部 skill: {skill_id}"

    full_path = os.path.join(skill_dir, script_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        return f"[ERROR] 脚本不存在: {full_path}"

    ext = os.path.splitext(full_path)[1].lower()
    runner_map = {
        ".sh":   ["bash"],
        ".bash": ["bash"],
        ".zsh":  ["zsh"],
        ".js":   ["node"],
        ".ts":   ["npx", "ts-node"],
        ".py":   ["python"],
        ".ps1":  ["powershell", "-ExecutionPolicy", "Bypass", "-File"],
    }
    runner = runner_map.get(ext)
    if runner is None:
        return f"[ERROR] 不支持的脚本类型: {ext}，支持: {list(runner_map)}"

    cmd = runner + [full_path] + (args.split() if args else [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=skill_dir,
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        parts = []
        if out:
            parts.append(f"[stdout]\n{out}")
        if err:
            parts.append(f"[stderr]\n{err}")
        parts.append(f"[returncode] {result.returncode}")
        return "\n".join(parts) or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[ERROR] 脚本执行超时（>{timeout}s）: {script_path}"
    except FileNotFoundError as e:
        return f"[ERROR] 找不到运行环境: {e}，请确认已安装对应工具"
    except Exception as e:
        return f"[ERROR] 执行失败: {e}"


def get_tools(agent=None, session_service=None, app_info=None,
              status_reporter=None, interruption_queue=None):
    """
    返回供 ADK agent 使用的工具函数列表。

    本 skill 提供五个工具（均以 external 开头，区别于本项目 skill_load 等本地工具）：
    - list_external_skills           : 列出全部外部 skill（含描述）
    - search_external_skill          : 按意图搜索最匹配的外部 skill
    - load_external_skill            : 加载指定外部 skill 的完整 Instructions + 附加文档
    - list_external_skill_assets     : 列出指定外部 skill 目录下的所有资产文件
    - run_external_skill_script      : 执行指定外部 skill 中的脚本（.sh/.js/.ts/.py 等）
    """
    return [
        list_external_skills,
        search_external_skill,
        load_external_skill,
        list_external_skill_assets,
        run_external_skill_script,
    ]
