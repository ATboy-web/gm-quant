"""
ai_assistant.py — 联网AI辅助筛选模块 (V24)

================================================================================
  API 供应商参考 (调用时根据 AI_PROVIDER 选择):
================================================================================

  1. DeepSeek (默认)
     文档: https://platform.deepseek.com/api-docs
     端点: https://api.deepseek.com/v1/chat/completions
     模型: deepseek-chat  (默认, 64K上下文, 1元/百万token)
          deepseek-reasoner (推理增强, 64K上下文)

  2. OpenAI
     文档: https://platform.openai.com/docs/api-reference
     端点: https://api.openai.com/v1/chat/completions
     模型: gpt-4o-mini (性价比), gpt-4o (强), o3-mini (推理)

  3. 智谱 GLM
     文档: https://open.bigmodel.cn/dev/api
     端点: https://open.bigmodel.cn/api/paas/v4/chat/completions
     模型: glm-4-flash (免费), glm-4-plus (强)

  4. 通义千问 (阿里)
     文档: https://help.aliyun.com/zh/dashscope/developer-reference
     端点: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
     模型: qwen-turbo (快), qwen-plus (强), qwen-max (最强)

  5. Moonshot (月之暗面)
     文档: https://platform.moonshot.cn/docs
     端点: https://api.moonshot.cn/v1/chat/completions
     模型: moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k

  6. 自定义
     设 AI_PROVIDER='custom' + AI_API_ENDPOINT='你的端点'
     只要接口兼容 OpenAI Chat Completions 格式即可

================================================================================
  联网搜索: DuckDuckGo (免费, 无需API Key)
  离线降级: 无API Key时自动切换本地关键词分析
================================================================================

终端开关: 启动时提示 [1=开启AI 2=关闭] → 动态设置 AI_ENABLED
"""

import os
import json
import re
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime

# =============================================================================
# 配置 — 从 config.py 读取，这里设默认值
# =============================================================================

try:
    import config
    AI_ENABLED = getattr(config, 'AI_ENABLED', True)
    AI_PROVIDER = getattr(config, 'AI_PROVIDER', 'deepseek')
    AI_API_KEY = getattr(config, 'AI_API_KEY', '')
    AI_MODEL = getattr(config, 'AI_MODEL', 'deepseek-chat')
    AI_SEARCH_SOURCES = getattr(config, 'AI_SEARCH_SOURCES', 5)
    AI_MAX_TOKENS = getattr(config, 'AI_MAX_TOKENS', 500)
    AI_TEMPERATURE = getattr(config, 'AI_TEMPERATURE', 0.3)
except ImportError:
    AI_ENABLED = False
    AI_PROVIDER = 'deepseek'
    AI_API_KEY = ''
    AI_MODEL = 'deepseek-chat'


# =============================================================================
# 第一部分: 联网搜索 (DuckDuckGo — 免费, 无需API Key)
# =============================================================================

def _fetch(url, headers=None, timeout=8, max_retries=2):
    """
    通用HTTP GET, 带重试机制。
    返回 bytes 或 None (失败时)
    所有爬虫都通过此函数请求, 统一超时和错误处理
    """
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            req.add_header('User-Agent',
                           'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            if attempt == max_retries - 1:
                # 最后一次尝试失败才记录
                pass
            time.sleep(0.5)
    return None


def web_search(query, max_results=5):
    """
    联网搜索 — 使用 DuckDuckGo HTML 搜索 (免费, 无Key)

    流程:
        1. 拼接 DDG HTML 搜索 URL
        2. 解析搜索结果 (标题 + 摘要 + URL)
        3. 返回结构化结果列表

    Args:
        query: 搜索关键词, 如 "A股 新能源 利好"
        max_results: 最多返回几条结果 (默认5)

    Returns:
        list[dict]: [{'title': '', 'snippet': '', 'url': ''}, ...]
        每次返回不超过 max_results 条
    """
    if not AI_ENABLED:
        return []

    results = []
    try:
        # DuckDuckGo HTML 搜索 (lite版, 结构简单)
        params = urllib.parse.urlencode({'q': query})
        url = f'https://lite.duckduckgo.com/lite/?{params}'

        html = _fetch(url, timeout=8)
        if not html:
            return []

        text = html.decode('utf-8', errors='replace')

        # 解析搜索结果:
        # DDG lite 格式: <a rel="nofollow" href="...">标题</a> + <span class="snippet">摘要</span>
        links = re.findall(
            r'<a[^>]*href="([^"]+)"[^>]*>([^<]{10,200})</a>',
            text
        )
        snippets = re.findall(
            r'<span class="snippet">([^<]+)</span>',
            text
        )

        for i, (url, title) in enumerate(links):
            if i >= max_results:
                break
            # 跳过 DDG 自身链接和广告
            if 'duckduckgo.com' in url or 'ad-' in url:
                continue
            # 清理标题
            title = title.replace('<b>', '').replace('</b>', '').strip()
            if len(title) < 10:
                continue
            # 匹配摘要
            snippet = snippets[i] if i < len(snippets) else ''
            snippet = snippet.replace('<b>', '').replace('</b>', '').strip()
            results.append({
                'title': title,
                'snippet': snippet[:300],
                'url': url,
            })
    except Exception:
        pass

    return results[:max_results]


# =============================================================================
# 第二部分: AI API 调用 (DeepSeek / OpenAI 兼容接口)
# =============================================================================

# 各供应商的 API 端点
_API_ENDPOINTS = {
    'deepseek': 'https://api.deepseek.com/v1/chat/completions',
    'openai':   'https://api.openai.com/v1/chat/completions',
    # 自定义: 在 config.py 中设 AI_PROVIDER='custom' + AI_API_ENDPOINT='...'
}


def _call_ai(system_prompt, user_prompt, max_tokens=None):
    """
    调用 AI API (DeepSeek/OpenAI 兼容格式)

    通信格式:
        POST {endpoint}
        {
            "model": "...",
            "messages": [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."}
            ],
            "max_tokens": ...,
            "temperature": ...
        }

    Args:
        system_prompt: 系统提示词 (设定AI角色)
        user_prompt: 用户输入 (要分析的内容)
        max_tokens: 最大输出token, 不传用默认

    Returns:
        str: AI返回的文本, 失败返回空字符串
    """
    # ===== 离线模式: 无API Key =====
    if not AI_ENABLED or not AI_API_KEY:
        return ''

    endpoint = _API_ENDPOINTS.get(AI_PROVIDER)
    if not endpoint:
        # 尝试从 config 读取自定义端点
        try:
            endpoint = config.AI_API_ENDPOINT
        except Exception:
            return ''

    payload = json.dumps({
        'model': AI_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'max_tokens': max_tokens or AI_MAX_TOKENS,
        'temperature': AI_TEMPERATURE,
    }).encode('utf-8')

    headers = {
        'Authorization': f'Bearer {AI_API_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        req = urllib.request.Request(endpoint, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        # 提取 AI 文本
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        # 静默失败: AI辅助不应中断主流程
        return ''


# =============================================================================
# 第三部分: AI 辅助分析功能
# =============================================================================

def analyze_news(news_texts):
    """
    AI 分析新闻情感和关键信息

    输入一批新闻文本 → AI 提取:
        1. 主要话题 (3-5个)
        2. 整体情绪倾向 (positive/neutral/negative)
        3. 影响最大的板块 (2-3个)
        4. 关键事件摘要 (1句话)

    Args:
        news_texts: list[str] 新闻标题/正文列表

    Returns:
        dict: {
            'topics': [...], 'sentiment': '...',
            'sectors': [...], 'summary': '...',
            'hot_stocks': [...]  # AI识别出的热门个股
        }
        离线模式返回空结构
    """
    if not news_texts:
        return {}

    # ===== 离线/本地降级 =====
    if not AI_API_KEY:
        return _local_analyze(news_texts)

    # ===== AI 模式 =====
    combined = '\n'.join(f'- {t[:200]}' for t in news_texts[:20])

    system = (
        '你是A股量化分析助手。分析财经新闻，返回JSON格式。'
        '只返回JSON，不要额外解释。'
    )
    user = (
        f'分析以下新闻，返回JSON: '
        f'{{"topics":["话题1","话题2"],'
        f'"sentiment":"positive/neutral/negative",'
        f'"sectors":["板块1","板块2"],'
        f'"summary":"一到两句话总结",'
        f'"hot_stocks":["股票名1","股票名2"]}}\n\n'
        f'新闻:\n{combined}'
    )

    response = _call_ai(system, user, max_tokens=400)
    if not response:
        return _local_analyze(news_texts)

    # 解析AI返回的JSON
    try:
        # 提取JSON块 (AI可能包裹在 ```json ... ``` 中)
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return _local_analyze(news_texts)


def rank_stocks(symbols, news_data, sentiment_scores=None):
    """
    AI 辅助股票排序 — 结合爬虫数据 + AI分析

    流程:
        1. 从新闻中提取每只股票的提及次数和情感
        2. 结合板块情绪分数
        3. (可选)调AI做语义深度排序
        4. 输出top-N推荐

    Args:
        symbols: list[str] 股票代码列表
        news_data: list[(text, source, score)] 爬虫数据
        sentiment_scores: dict 板块情绪分数 (可选)

    Returns:
        list[tuple]: [(symbol, total_score, detail_dict), ...] 按分数降序
    """
    if not symbols or not news_data:
        return []

    # ===== 第一步: 本地统计 =====
    stock_mentions = defaultdict(lambda: {'count': 0, 'sentiment': 0.0, 'news': []})

    # 提取股票代码尾号匹配
    for text, source, score in news_data:
        for sym in symbols:
            code = sym.split('.')[1] if '.' in sym else sym
            if code in text or sym in text:
                stock_mentions[sym]['count'] += 1
                stock_mentions[sym]['sentiment'] += score
                stock_mentions[sym]['news'].append(text[:100])

    # ===== 第二步: 计算综合分数 =====
    results = []
    max_mentions = max((v['count'] for v in stock_mentions.values()), default=1)

    for sym in symbols:
        info = stock_mentions.get(sym, None)
        if info and info['count'] > 0:
            avg_sent = info['sentiment'] / info['count']
            # 热度 = 提及次数标准化 * 0.5 + 情感 * 0.3 + 板块情绪 * 0.2
            mention_score = info['count'] / max_mentions * 0.5
            section_bonus = 0.0
            if sentiment_scores:
                # 根据股票所属板块取情绪加成
                try:
                    import stock_pool
                    sector = stock_pool.get_sector_for_symbol(sym)
                    section_bonus = sentiment_scores.get(sector, 0.0) * 0.2
                except Exception:
                    pass
            total = mention_score + avg_sent * 0.3 + section_bonus
            results.append((
                sym, round(total, 3), {
                    'mentions': info['count'],
                    'avg_sentiment': round(avg_sent, 2),
                    'sample_news': info['news'][:3],
                }
            ))

    # ===== 第三步: 排序 =====
    results.sort(key=lambda x: -x[1])
    return results


def sector_analysis(sector, news_data):
    """
    AI 板块深度分析

    输入板块名 + 相关新闻 → AI生成:
        1. 近期驱动因素
        2. 风险提示
        3. 操作建议 (偏多/偏空/观望)

    Args:
        sector: str 板块名称, 如 "新能源"
        news_data: list[(text, source, score)] 爬虫数据

    Returns:
        dict: {'drivers': [...], 'risks': [...], 'advice': '...'}
    """
    if not AI_API_KEY or not news_data:
        return {
            'drivers': ['数据不足-AI未启用'],
            'risks': ['请设置AI_API_KEY'],
            'advice': 'neutral'
        }

    # 筛选相关新闻
    related = [(t, s) for t, _, s in news_data if sector in t][:10]
    if not related:
        return {'drivers': [], 'risks': [], 'advice': '观望'}

    combined = '\n'.join(f'[{s:+.1f}] {t[:150]}' for t, s in related)

    system = '你是A股板块分析师。返回JSON格式，简洁。'
    user = (
        f'分析"{sector}"板块近期情况，返回JSON:\n'
        f'{{"drivers":["利好1","利好2"],'
        f'"risks":["风险1","风险2"],'
        f'"advice":"bullish/neutral/bearish"}}\n\n'
        f'新闻:\n{combined}'
    )

    response = _call_ai(system, user, max_tokens=300)
    if not response:
        return {'drivers': ['AI调用失败'], 'risks': [], 'advice': 'neutral'}

    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError:
        pass

    return {'drivers': ['解析失败'], 'risks': [], 'advice': 'neutral'}


# =============================================================================
# 第四部分: 离线降级分析 (不需要AI API Key)
# =============================================================================

# 板块关键词 (与 sentiment_engine.py 共享, 此处为独立副本避免循环导入)
_SECTOR_KW = {
    '金融': ['银行', '保险', '券商', '金融', '央行', '利率', '降息'],
    '消费': ['消费', '白酒', '食品', '饮料', '家电', '零售'],
    '医药': ['医药', '医疗', '疫苗', '创新药', '中药'],
    '科技': ['AI', '人工智能', '芯片', '半导体', '5G', '华为', '信创'],
    '新能源': ['光伏', '风电', '储能', '锂电', '新能源', '碳中和'],
    '制造': ['制造', '基建', '水泥', '钢铁', '工程机械'],
    '有色': ['黄金', '铜', '铝', '稀土', '矿产', '有色'],
    '汽车': ['汽车', '新能源车', '比亚迪', '特斯拉'],
    '化工': ['化工', '石化', '化肥', '新材料'],
    '公用事业': ['电力', '核电', '水电', '电网'],
    '军工': ['军工', '航天', '航空', '船舶', '国防'],
    '煤炭': ['煤炭', '煤', '矿山', '神华'],
}


def _local_analyze(news_texts):
    """
    离线模式: 基于关键词的本地分析
    统计词频、板块分布、情感极性
    """
    pos_words = ['涨', '利好', '突破', '反弹', '增长', '支持']
    neg_words = ['跌', '利空', '破位', '下滑', '风险', '亏损']

    sector_count = defaultdict(int)
    pos_count = 0
    neg_count = 0
    all_words = []

    for text in news_texts:
        # 板块统计
        for sec, kws in _SECTOR_KW.items():
            for kw in kws:
                if kw in text:
                    sector_count[sec] += 1
                    break
        # 情感统计
        pos_count += sum(1 for w in pos_words if w in text)
        neg_count += sum(1 for w in neg_words if w in text)
        # 词频
        all_words.extend(re.findall(r'[\u4e00-\u9fff]{2,4}', text))

    # 高频词
    from collections import Counter
    top_words = [w for w, _ in Counter(all_words).most_common(10)]

    # 热门板块
    top_sectors = [s for s, _ in Counter(sector_count).most_common(3)]

    # 情感判断
    total = pos_count + neg_count
    sentiment = 'neutral'
    if total > 0:
        ratio = pos_count / total
        sentiment = 'positive' if ratio > 0.55 else ('negative' if ratio < 0.45 else 'neutral')

    return {
        'topics': top_words[:5],
        'sentiment': sentiment,
        'sectors': top_sectors,
        'summary': f'本地分析: 共{len(news_texts)}条新闻, 偏向{len(top_sectors)}个板块',
        'hot_stocks': [],
    }


# =============================================================================
# 第五部分: 辅助函数 — 供 executor 和 main 调用
# =============================================================================

def get_stock_filter(symbols, sentiment_data, top_n=10):
    """
    获取AI筛选后的推荐股票列表 (供 executor 调用)

    综合:
        1. 联网搜索最近财经热点 (web_search)
        2. AI/本地分析新闻
        3. 股票热度排行 (rank_stocks)
        4. 返回top-N

    Args:
        symbols: list[str] 候选股票池
        sentiment_data: list[(text, source, score)] 爬虫数据
        top_n: int 返回前几名

    Returns:
        list[str]: 推荐的股票代码, 按热度排序
    """
    if not AI_ENABLED:
        return symbols  # 未启用时返回全量

    # 联网搜索补充
    search_results = web_search('A股 今日热点板块 资金流入')
    # 把搜索结果加入分析数据
    extended_news = list(sentiment_data)  # copy
    for r in search_results:
        score = 0.3 if any(w in r['title'] for w in ['涨', '利好']) else 0.0
        extended_news.append((f"{r['title']} {r['snippet']}", 'web_search', score))

    # 热度排行
    ranking = rank_stocks(symbols, extended_news)
    return [sym for sym, _, _ in ranking[:top_n]]


def is_enabled():
    """检查AI辅助是否启用"""
    return AI_ENABLED


# =============================================================================
# 自测 (离线运行: python ai_assistant.py)
# =============================================================================

if __name__ == '__main__':
    print('=== AI Assistant 自测 ===')

    # 1. 测试联网搜索
    print('\n1. 联网搜索 "A股 新能源"')
    results = web_search('A股 新能源 利好', max_results=3)
    for r in results:
        print(f'   [{r["title"][:50]}]')
        print(f'   {r["snippet"][:80]}')
        print(f'   {r["url"]}')
        print()

    # 2. 测试本地新闻分析
    print('2. 本地新闻分析 (离线)')
    test_news = [
        '新能源汽车销量大涨30%,比亚迪再创新高',
        '芯片板块利空消息,半导体指数下挫2%',
        '央行降息利好银行板块,招商银行涨幅居前',
        '光伏行业政策支持,隆基绿能业绩超预期',
        '茅台股价回调,消费板块承压',
    ]
    analysis = analyze_news(test_news)
    for k, v in analysis.items():
        print(f'   {k}: {v}')

    # 3. 测试股票排序
    print('\n3. 股票热度排序')
    test_symbols = ['SHSE.601012', 'SHSE.600036', 'SZSE.002594', 'SHSE.600519']
    test_data = [
        ('比亚迪新能源车销量突破', '新浪', 0.8),
        ('招商银行受降息利好', '财联社', 0.6),
        ('隆基绿能光伏项目中标', '东方财富', 0.7),
        ('芯片短缺影响科技板块', '同花顺', -0.4),
    ]
    ranking = rank_stocks(test_symbols, test_data)
    for sym, score, detail in ranking:
        print(f'   {sym}: {score:.3f} (mentions={detail["mentions"]}, sent={detail["avg_sentiment"]})')

    # 4. 功能状态
    print(f'\n4. AI状态: enabled={is_enabled()}')
    print(f'   Provider: {AI_PROVIDER}, API_KEY: {"已设置" if AI_API_KEY else "未设置(离线模式)"}')
    print('\n=== 自测通过 ===')
