"""
sentiment_engine.py — 市场情绪引擎 (V23 final)

合并: crawler.py + market_sentiment.py
功能:
  1. 抓取财经新闻 (新浪/财联社/东方财富)
  2. 板块情绪分析 (关键词+极性)
  3. 情绪过滤/冻结/加权 (供 executor 调用)
  4. 本地缓存 (data/news/板块_日期.txt)

用法:
    import sentiment_engine

    # 完整抓取
    sentiment = sentiment_engine.run_full_crawl()

    # 或只用情绪分析 (不用爬虫)
    scores = sentiment_engine.get_sector_sentiment(news_texts)

    # executor 集成
    sentiment_engine.get_sector_bias(sector, scores)
    sentiment_engine.get_sector_freeze(sector, scores)
"""
import os
import re
import json
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict

# ===== 配置 =====
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'news')
if not os.path.isabs(DATA_DIR):
    DATA_DIR = os.path.join(os.getcwd(), 'data', 'news')

# ===== 板块关键词 (共享) =====
SECTOR_KEYWORDS = {
    '金融':     ['银行', '保险', '券商', '金融', '利率', '降息', '加息', '央行', '存款'],
    '消费':     ['消费', '白酒', '食品', '饮料', '零售', '家电', '茅台', '五粮液'],
    '医药':     ['医药', '医疗', '疫苗', '创新药', '中药', '医院', '恒瑞'],
    '科技':     ['AI', '人工智能', '芯片', '半导体', '算力', '5G', '通信', '软件', '华为', '大模型', '信创'],
    '新能源':   ['光伏', '风电', '储能', '锂电', '新能源', '碳中和', '电池', '隆基', '通威'],
    '制造':     ['工程机械', '制造', '基建', '建材', '水泥', '钢铁', '重工', '挖掘机'],
    '有色':     ['黄金', '铜', '铝', '稀土', '矿产', '有色', '紫金', '洛阳钼业'],
    '汽车':     ['汽车', '新能源车', '整车', '零部件', '比亚迪', '特斯拉', '智能驾驶'],
    '化工':     ['化工', '石化', '化肥', '农药', '新材料', '万华'],
    '公用事业': ['电力', '核电', '水电', '电网', '公用', '长江电力', '华能'],
    '军工':     ['军工', '航天', '航空', '船舶', '导弹', '国防', '沈飞', '西飞'],
    '煤炭':     ['煤炭', '煤', '矿山', '神华', '陕煤'],
}

POSITIVE_WORDS = [
    '大涨', '涨停', '暴涨', '飙升', '利好', '突破', '反弹', '走强', '领涨',
    '政策支持', '资金流入', '业绩增长', '订单', '中标', '创新高', '放量',
    '回购', '增持', '分红', '超预期', '复苏', '景气', '回暖',
]
NEGATIVE_WORDS = [
    '大跌', '跌停', '暴跌', '下挫', '利空', '破位', '走弱', '领跌',
    '监管', '处罚', '亏损', '减持', '暴雷', '退市', '违约', '风险',
    '贸易战', '制裁', '衰退', '通缩',
]

# ===== 第一部分: 爬虫 =====

def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _classify_sector(text):
    sectors = []
    for sec, kws in SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                sectors.append(sec)
                break
    return sectors if sectors else ['综合']


def _sentiment_score(text):
    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)
    if pos + neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 2)


def crawl_sina_roll():
    """新浪财经滚动新闻"""
    news = []
    try:
        url = 'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num=50'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('result', {}).get('data', []):
            title = item.get('title', '')
            if title and len(title) > 10:
                news.append((title, '新浪'))
    except Exception:
        pass
    return news


def crawl_cls_telegraph():
    """财联社电报"""
    news = []
    try:
        url = 'https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6'
        payload = json.dumps({'type': 'telegram', 'keyword': '', 'page': 0, 'rn': 30}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={
            'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('data', {}).get('roll_data', [])[:30]:
            title = item.get('title', '') or item.get('brief', '')
            if title and len(title) > 8:
                news.append((title, '财联社'))
    except Exception:
        pass
    return news


def crawl_eastmoney_sector():
    """东方财富板块行情"""
    results = []
    try:
        url = ('https://push2.eastmoney.com/api/qt/clist/get?'
               'pn=1&pz=50&po=1&np=1&fltt=2&invt=2'
               '&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14')
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('data', {}).get('diff', [])[:30]:
            name = item.get('f14', '')
            pct = item.get('f3', 0)
            if name:
                results.append((name, pct))
    except Exception:
        pass
    return results


def save_news(date_str, sector_news):
    """保存新闻到本地文件"""
    ensure_dir()
    for sector, items in sector_news.items():
        if not items:
            continue
        filename = os.path.join(DATA_DIR, f'{sector}_{date_str}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f'# {sector} {date_str} | {len(items)}条\n\n')
            for t, src, score in items:
                emoji = '🟢' if score > 0.2 else ('🔴' if score < -0.2 else '⚪')
                f.write(f'[{emoji} {score:+.1f}] {t} | {src}\n')


def cleanup_old_news(days=7):
    """清理过期文件"""
    cutoff = datetime.now() - timedelta(days=days)
    if not os.path.exists(DATA_DIR):
        return
    for fn in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, fn)
        if os.path.isfile(path):
            if datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
                os.remove(path)


def load_today_sentiment_from_cache():
    """从本地缓存加载今日情绪"""
    today = datetime.now().strftime('%Y-%m-%d')
    scores = defaultdict(float)
    if not os.path.exists(DATA_DIR):
        return dict(scores)
    for fn in os.listdir(DATA_DIR):
        if fn.endswith(f'_{today}.txt'):
            sec = fn.split('_')[0]
            path = os.path.join(DATA_DIR, fn)
            with open(path, encoding='utf-8') as f:
                for line in f:
                    m = re.search(r'\[.*?([+-]\d+\.\d+)\]', line)
                    if m:
                        scores[sec] += float(m.group(1))
    return dict(scores) if scores else {}


def run_full_crawl():
    """执行完整抓取流程"""
    date_str = datetime.now().strftime('%Y-%m-%d')

    sina = crawl_sina_roll()
    cls_news = crawl_cls_telegraph()
    em = crawl_eastmoney_sector()

    all_news = [(t, src, _sentiment_score(t)) for t, src in sina]
    all_news += [(t, src, _sentiment_score(t)) for t, src in cls_news]
    for name, pct in em:
        score = 0.5 if pct > 2 else (-0.5 if pct < -2 else 0)
        all_news.append((f'{name}板块 {"涨" if pct>0 else "跌"}{abs(pct):.1f}%', '东方财富', score))

    sector_news = defaultdict(list)
    for title, src, score in all_news:
        for sec in _classify_sector(title):
            sector_news[sec].append((title, src, score))

    save_news(date_str, sector_news)
    cleanup_old_news(7)
    return load_today_sentiment_from_cache()


# ===== 第二部分: 情绪分析 =====

def get_sector_sentiment(news_texts=None):
    """
    计算板块情绪分数 (不需要爬虫时直接调用)
    返回: {sector: score}  score ∈ [-1, 1]
    """
    if news_texts is None:
        return load_today_sentiment_from_cache()

    sentiment = defaultdict(float)
    for text in news_texts:
        related = set()
        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    related.add(sector)
                    break
        if not related:
            continue

        pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
        neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)
        if pos_count + neg_count == 0:
            score = 0.0
        else:
            score = (pos_count - neg_count) / (pos_count + neg_count + 1)

        for sector in related:
            sentiment[sector] += score * 0.3

    return {s: max(-1.0, min(1.0, v)) for s, v in sentiment.items()}


def get_sector_bias(sector, sentiment_scores):
    """
    板块情绪偏向 → 权重乘数 [0.3, 2.0]
    """
    score = sentiment_scores.get(sector, 0.0)
    if score < 0:
        return 1.0 + score * 0.7
    else:
        return 1.0 + score * 1.0


def get_sector_freeze(sector, sentiment_scores, threshold=-0.8):
    """
    是否冻结板块 (情绪极度悲观)
    """
    score = sentiment_scores.get(sector, 0.0)
    return score <= threshold
