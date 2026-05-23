"""
market_sentiment.py - 市场情绪策略模块 (V23)

散户跟市场情绪走: 读热点新闻 → 判断板块情绪 → 指导选股方向
顺序: 情绪先行 → 定方向 → 选股

数据源: 东方财富板块异动、新浪财经热点
"""
import re
import urllib.request
import json
from collections import defaultdict

# === 板块关键词映射 ===
SECTOR_KEYWORDS = {
    '金融':     ['银行', '保险', '券商', '金融', '利率', '降息', '加息', '央行', '存款', '贷款'],
    '消费':     ['消费', '白酒', '食品', '饮料', '零售', '家电', '茅台', '五粮液', '伊利'],
    '医药':     ['医药', '医疗', '疫苗', '创新药', '中药', '医院', '药明', '恒瑞'],
    '科技':     ['AI', '人工智能', '芯片', '半导体', '算力', '5G', '通信', '软件', '数据', '信创', '华为', '大模型'],
    '新能源':   ['光伏', '风电', '储能', '锂电', '新能源', '碳中和', '电池', '隆基', '通威', '宁德'],
    '制造':     ['工程机械', '挖掘机', '工业', '制造', '基建', '建材', '水泥', '钢铁', '重工'],
    '有色':     ['黄金', '铜', '铝', '稀土', '矿产', '有色', '紫金', '洛阳钼业'],
    '汽车':     ['汽车', '新能源车', '整车', '零部件', '比亚迪', '特斯拉', '智能驾驶'],
    '化工':     ['化工', '石化', '化肥', '农药', '新材料', '万华'],
    '公用事业': ['电力', '核电', '水电', '风电', '电网', '公用', '长江电力', '华能'],
    '军工':     ['军工', '航天', '航空', '船舶', '导弹', '国防', '沈飞', '西飞'],
    '煤炭':     ['煤炭', '煤', '矿山', '神华', '陕煤'],
}

# === 情绪关键词 ===
POSITIVE_WORDS = [
    '大涨', '涨停', '暴涨', '飙升', '利好', '突破', '反弹', '走强', '领涨',
    '政策支持', '资金流入', '业绩增长', '订单', '中标', '创新高', '放量',
    '回购', '增持', '分红', '超预期', '复苏', '景气', '回暖',
]
NEGATIVE_WORDS = [
    '大跌', '跌停', '暴跌', '下挫', '利空', '破位', '走弱', '领跌',
    '监管', '处罚', '亏损', '减持', '暴雷', '退市', '违约', '风险',
    '贸易战', '制裁', '疫情', '衰退', '通缩',
]


def _fetch_eastmoney_news():
    """抓取东方财富24小时热门新闻"""
    try:
        url = 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f12,f14,f3,f2,f15&secids=1.000001,0.399001,0.399006,0.399005,0.399004,0.399003,0.399002,0.399001,0.399000'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return str(data)  # Return raw for keyword scanning
    except Exception as e:
        return ''


def _fetch_sina_headlines():
    """抓取新浪财经头条"""
    headlines = []
    try:
        url = 'https://finance.sina.com.cn/'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            html = resp.read().decode('gbk', errors='replace')
        # 提取标题
        titles = re.findall(r'<a[^>]*>([^<]{8,}?[涨跌利好突破板块].*?)</a>', html)
        headlines.extend(titles[:30])
    except Exception:
        pass
    return headlines


def get_sector_sentiment(news_texts=None):
    """
    计算各板块的市场情绪分数。

    返回: {sector: score}  score ∈ [-1, 1]
    正数=看多, 负数=看空, 0=中性
    """
    if news_texts is None:
        news_texts = _fetch_sina_headlines()
        if not news_texts:
            raw = _fetch_eastmoney_news()
            if raw:
                news_texts = [raw]

    sentiment = defaultdict(float)

    for text in news_texts:
        text_lower = text.lower()

        # 确定相关板块
        related_sectors = set()
        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    related_sectors.add(sector)
                    break

        if not related_sectors:
            continue

        # 计算情绪极性
        pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)

        if pos_count + neg_count == 0:
            score = 0.0
        else:
            score = (pos_count - neg_count) / (pos_count + neg_count + 1)

        # 分配给相关板块
        for sector in related_sectors:
            # 避免单条新闻过度影响
            sentiment[sector] += score * 0.3

    # 裁剪到 [-1, 1]
    result = {}
    for sector, s in sentiment.items():
        result[sector] = max(-1.0, min(1.0, s))

    return result


def get_sector_bias(sector, sentiment_scores):
    """
    获取某板块的情绪偏向，用于策略权重调整。
    返回: multiplier ∈ [0.3, 2.0]
      < 0.5: 情绪偏空, 降低该板块权重
      = 1.0: 中性
      > 1.5: 情绪偏多, 提高该板块权重
    """
    score = sentiment_scores.get(sector, 0.0)
    # Sigmoid-like mapping: score=-1 → 0.3, score=0 → 1.0, score=+1 → 2.0
    if score < 0:
        return 1.0 + score * 0.7  # 0.3 ~ 1.0
    else:
        return 1.0 + score * 1.0  # 1.0 ~ 2.0


def get_sector_freeze(sector, sentiment_scores, threshold=-0.8):
    """
    判断是否应该冻结某板块（情绪极度悲观）。
    返回: True = 冻结, 不交易该板块
    """
    score = sentiment_scores.get(sector, 0.0)
    return score <= threshold


if __name__ == '__main__':
    # 测试
    test_news = [
        'AI芯片概念大涨，华为发布新芯片利好科技板块',
        '新能源车销量超预期，比亚迪股价创新高',
        '煤炭价格走低，神华陕煤承压',
        '政策利好消费，白酒板块反弹',
        '银行利空，央行收紧政策导致金融股大跌',
    ]
    sentiment = get_sector_sentiment(test_news)
    print('板块情绪:')
    for s, v in sorted(sentiment.items(), key=lambda x: -x[1]):
        bias = get_sector_bias(s, sentiment)
        freeze = get_sector_freeze(s, sentiment)
        bar = '🟢' if v > 0.2 else ('🔴' if v < -0.2 else '⚪')
        print(f'  {bar} {s}: {v:+.2f} (乘数:{bias:.2f}{" 冻结!" if freeze else ""})')
