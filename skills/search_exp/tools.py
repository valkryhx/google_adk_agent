import os
import json
import re
from typing import List

# ==========================================
# 1. 路径配置
# 当前文件位于: skills/search_exp/tools.py
# 从 skills_path 向上 1 层找到 Project Root
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))

# 经验池根目录 (与 main_web_start_steering.py 中的 SHARED_GENE_POOL 保持一致)
SHARED_GENE_POOL = os.path.join(PROJECT_ROOT, "agent_experiences")
# 全局索引文件 (L0 Index，只有这个会被每次调用读取)
EXPERIENCE_INDEX_PATH = os.path.join(SHARED_GENE_POOL, "index_manifest.json")


def search_experience(query: str) -> str:
    """
    本地经验库智能检索工具 (OpenViking-Lite 分层索引)

    【使用时机】:
    1. 代码执行报错时 (Traceback/Error/Exception)，必须第一时间调用。
    2. 不确定内网工具正确命令/配置时。
    3. 多次尝试失败，想知道历史上是否有人解决过同类问题时。

    【检索原理 (分两层)】:
    - L0 层（极速）: 读取极小的 index_manifest.json，在内存中用
      报错特征正则 + 关键词交集做加权评分，耗时 < 1ms。
    - L2 层（懒加载）: 只有 L0 命中且置信度足够时，才读取硬盘上
      对应的完整 JSON 经验文件，避免无效 IO。

    Args:
        query: 完整的报错信息 (如 "SSL certificate problem: unable to get
               local issuer certificate") 或问题描述 (如 "git proxy 配置方法")。
               越精确，匹配到历史报错特征的概率越高，得分越高。

    Returns:
        命中时返回【历史问题 + 已验证的解决方案 + 原理分析】；
        未命中或置信度不足时返回友好提示。
    """
    # ==========================================
    # 0. 基础检查
    # ==========================================
    if not os.path.exists(EXPERIENCE_INDEX_PATH):
        return "[search_exp] 本地经验库尚未建立索引，暂无可用经验。"

    print(f"[search_exp] L0 检索中, Query: {query[:60]}...")

    # ==========================================
    # 1. 加载 L0 索引 (全量读入内存，文件通常极小)
    # ==========================================
    try:
        with open(EXPERIENCE_INDEX_PATH, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    except Exception as e:
        return f"[search_exp] 索引文件损坏或无法读取: {e}"

    if not manifest:
        return "[search_exp] 经验库目前为空，没有任何记录。"

    # ==========================================
    # 2. BM25 (Okapi) 评分机制
    # ==========================================
    import math

    # 简易分词：保留中英文和数字
    def tokenize(text: str) -> List[str]:
        return [w for w in re.findall(r'[a-z0-9\u4e00-\u9fa5]+', text.lower()) if len(w) > 1]

    query_words = tokenize(query)

    # 准备语料库
    corpus = []
    doc_ids = []
    doc_metas = []
    
    for gene_id, meta in manifest.items():
        doc_ids.append(gene_id)
        doc_metas.append(meta)
        
        # 将历史特征混合成一个长文档进行 BM25 计算，加大 error_regex 的权重可以重复拼接
        error_regex = meta.get('error_regex', '')
        title = meta.get('title', '')
        keywords = " ".join(meta.get('keywords', []))
        
        text_doc = f"{error_regex} {error_regex} {title} {keywords}"
        corpus.append(tokenize(text_doc))

    N = len(corpus)
    if N == 0:
        return "[search_exp] 经验库目前为空，没有任何记录。"

    # 计算 BM25 需要的参数
    avgdl = sum(len(doc) for doc in corpus) / N
    k1 = 1.5
    b = 0.75

    # 计算 IDF
    idf = {}
    for word in query_words:
        # 包含该词的文档数
        nq = sum(1 for doc in corpus if word in doc)
        # BM25 IDF 公式，+0.5 平滑处理
        idf[word] = math.log((N - nq + 0.5) / (nq + 0.5) + 1.0)

    scored_items = []
    for i, doc in enumerate(corpus):
        doc_len = len(doc)
        score = 0
        freqs = {w: doc.count(w) for w in query_words}
        
        for word in query_words:
            if freqs[word] > 0:
                tf = freqs[word]
                # BM25 核心公式
                score += idf[word] * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avgdl))

        # 额外：如果要保留原来的"完整精确命中"致命一击，可以在 BM25 基础上附加
        error_regex = doc_metas[i].get('error_regex', '').lower()
        if error_regex and (error_regex in query.lower() or query.lower() in error_regex):
            score += 10.0  # 视 BM25 分数范围而定，10分通常很高了

        if score > 0:
            scored_items.append((score, doc_ids[i], doc_metas[i]))

    # ==========================================
    # 3. 排序与阈值决策
    # ==========================================
    if not scored_items:
        return (
            f"[search_exp] 未找到与该问题相关的历史经验。\n"
            f"查询摘要: '{query[:60]}...'\n"
            f"建议自行分析，或使用更精确的报错关键词重新检索。"
        )

    scored_items.sort(key=lambda x: x[0], reverse=True)
    best_score, best_gene_id, best_meta = scored_items[0]

    print(f"[search_exp] L0 命中(BM25): {best_meta.get('title')} | 得分={best_score:.2f} | 路径={best_meta.get('path')}")

    # BM25 分数依赖于文档总数。如果只有不到 1.0 的分，极大概率是无意义匹配
    if best_score < 1.0:
        candidates = ", ".join([f"'{m.get('title')}'(得分:{s:.1f})" for s, _, m in scored_items[:3]])
        return (
            f"[search_exp] 置信度不足 (最高仅 {best_score:.2f})，未自动加载。\n"
            f"也许相关: {candidates}\n"
            f"请带上更完整的报错片段重新搜索。"
        )

    # ==========================================
    # 4. 懒加载 L2 正文 (只读这一条)
    # ==========================================
    rel_path = best_meta.get('path', '')
    if not rel_path:
        return "[search_exp] 索引命中，但文件路径字段丢失，数据异常。"

    full_path = os.path.join(SHARED_GENE_POOL, rel_path)

    try:
        if not os.path.exists(full_path):
            return f"[search_exp] 索引指向的文件不存在: {rel_path}"

        with open(full_path, 'r', encoding='utf-8') as f:
            full_data = json.load(f)

        content = full_data.get('content', {})
        problem = content.get('problem_context', '无描述')
        solution = content.get('solution_action', {}).get('commands', [])
        reasoning = content.get('reasoning', '无')
        category = full_data.get('category', 'general')
        timestamp = full_data.get('timestamp', 'unknown')

        solution_text = json.dumps(solution, indent=2, ensure_ascii=False) if solution else "（无命令记录）"

        return (
            f"[search_exp] 已匹配到历史经验 (置信度: {best_score})\n"
            f"分类: {category}  |  时间: {timestamp[:10]}  |  ID: {best_gene_id}\n"
            f"{'=' * 50}\n"
            f"【历史问题】: {problem}\n"
            f"【报错特征】: {best_meta.get('error_regex', 'N/A')}\n\n"
            f"【已验证的解决方案】:\n{solution_text}\n\n"
            f"【原理分析】: {reasoning}\n"
            f"{'=' * 50}\n"
            f"建议：优先参考上述方案，理解原理后结合当前路径/环境适当调整。"
        )

    except json.JSONDecodeError:
        return f"[search_exp] 经验文件损坏 (JSON 解析失败): {rel_path}"
    except Exception as e:
        return f"[search_exp] 读取经验文件失败: {e}"


def get_tools(*args, **kwargs) -> List:
    """ADK 标准工具导出接口"""
    return [search_experience]
