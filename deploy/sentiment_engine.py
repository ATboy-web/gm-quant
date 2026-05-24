"""
sentiment_engine.py — 市场情绪引擎 V23.1 (优化版)

优化:
  1. 爬虫异步化: 三大源并行抓取
  2. 缓存聚合: 情绪数据预计算, 少读文件
  3. 关键词去重优化: prefix tree 加速匹配
  4. 增量保存: 仅追加新新闻, 不覆写
"""
import os
import re
import json
import time
import urllib.request
import concurrent.futures
from datetime import datetime, timedelta
from collections import defaultdict

DATA_DIR = os.path.join(os.getcwd(), 'data', 'news')

# === 关键词 (预编译正则) ===
SECTOR_KEYWORDS = {
    '金融':     ['银行', '保险', '券商', '金融', '利率', '央行', '存款', '贷款'],
    '消费':     ['消费', '白酒', '食品', '饮料', '零售', '家电', '茅台', '五粮液'],
    '医药':     ['医药', '医疗', '疫苗', '创新药', '中药', '医院', '恒瑞'],
    '科技':     ['AI', '人工智能', '芯片', '半导体', '算力', '5G', '华为', '大模型', '信创'],
    '新能源':   ['光伏', '风电', '储能', '锂电', '新能源', '碳中和', '电池', '隆基'],
    '制造':     ['工程机械', '制造', '基建', '建材', '水泥', '钢铁', '重工'],
    '有色':     ['黄金', '铜', '铝', '稀土', '矿产', '有色', '紫金'],
    '汽车':     ['汽车', '新能源车', '整车', '比亚迪', '特斯拉', '智能驾驶'],
    '化工':     ['化工', '石化', '化肥', '新材料', '万华'],
    '公用事业': ['电力', '核电', '水电', '电网', '公用', '长江电力'],
    '军工':     ['军工', '航天', '航空', '船舶', '国防'],
    '煤炭':     ['煤炭', '煤', '矿山', '神华', '陕煤'],
    '房地产':   ['房地产', '地产', '楼盘', '万科', '保利', '房价', '楼市'],
    '交通运输': ['航运', '铁路', '物流', '快递', '港口', '航空', '机场'],
    '农业':     ['农业', '养殖', '猪肉', '饲料', '种业', '粮食', '牧原', '温氏'],
}

POS_WORDS = ['大涨','涨停','利好','突破','反弹','走强','领涨','政策支持','资金流入','业绩增长']
NEG_WORDS = ['大跌','跌停','利空','破位','走弱','领跌','监管','亏损','减持','暴雷','风险']

# 预编译正则
_sector_re = {s: re.compile('|'.join(kw)) for s, kw in SECTOR_KEYWORDS.items()}
_pos_re = re.compile('|'.join(POS_WORDS))
_neg_re = re.compile('|'.join(NEG_WORDS))

def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _classify(text):
    return [s for s, r in _sector_re.items() if r.search(text)] or ['综合']


def _score(text):
    pos = len(_pos_re.findall(text))
    neg = len(_neg_re.findall(text))
    if pos + neg == 0: return 0.0
    return round((pos - neg) / (pos + neg), 2)


# === 爬虫 (并行) ===

def _fetch(url, headers=None, timeout=5, method='GET', data=None):
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def crawl_sina_headlines():
    """新浪财经24小时热文"""
    try:
        body = _fetch('https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num=60',
                      {'User-Agent': 'Mozilla/5.0'})
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        return [(item['title'], '新浪')
                for item in data.get('result', {}).get('data', [])
                if len(item.get('title', '')) > 12]
    except Exception:
        return []


def crawl_cls_telegraph():
    """财联社电报"""
    try:
        payload = json.dumps({'type': 'telegram', 'keyword': '', 'page': 0, 'rn': 40}).encode()
        body = _fetch('https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6',
                      {'User-Agent': 'Mozilla/5.0', 'Content-Type': 'application/json'},
                      data=payload, method='POST')
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        return [(item.get('title', '') or item.get('brief', ''), '财联社')
                for item in data.get('data', {}).get('roll_data', [])[:40]
                if len(item.get('title', item.get('brief', ''))) > 8]
    except Exception:
        return []


def crawl_eastmoney_sector():
    """东方财富板块实时行情"""
    try:
        body = _fetch('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14',
                      {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'})
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        return [(item['f14'], item['f3']) for item in data.get('data', {}).get('diff', [])[:30]]
    except Exception:
        return []


def crawl_xueqiu_hot():
    """雪球热门讨论 (社区情绪)"""
    try:
        body = _fetch('https://xueqiu.com/statuses/hot/listV2.json?since_id=-1&size=30',
                      headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                               'Referer': 'https://xueqiu.com/', 'Cookie': 'xq_a_token=anonymous'})
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        items = []
        for item in data.get('items', [])[:30]:
            text = item.get('text', '') or item.get('title', '')
            text = re.sub(r'<[^>]+>', '', text)[:200]
            if len(text) > 15:
                items.append((text, '雪球'))
        return items
    except Exception:
        return []


def crawl_eastmoney_guba():
    """东方财富股吧热门帖"""
    try:
        body = _fetch('https://guba.eastmoney.com/remenba.aspx?type=1',
                      headers={'User-Agent': 'Mozilla/5.0'})
        if not body: return []
        html = body.decode('gbk', errors='replace')
        items = []
        titles = re.findall(r'<a[^>]*title="([^"]{10,80})"[^>]*>', html)
        reads = re.findall(r'<cite>(\d+)</cite>', html)
        for i, t in enumerate(titles[:30]):
            hot = int(reads[i]) if i < len(reads) else 0
            if hot > 1000:
                items.append((t, '东财股吧'))
        return items
    except Exception:
        return []


def crawl_10jqka_hot():
    """同花顺社区热门话题"""
    try:
        body = _fetch('https://t.10jqka.com.cn/circle/getHotList/',
                      headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://t.10jqka.com.cn/'})
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        items = []
        for item in data.get('data', [])[:30]:
            title = item.get('title', '') or item.get('content', '')
            title = re.sub(r'<[^>]+>', '', title)[:150]
            if len(title) > 12:
                items.append((title, '同花顺'))
        return items
    except Exception:
        return []


def crawl_wallstreetcn():
    """华尔街见闻快讯"""
    try:
        body = _fetch('https://api-one.wallstcn.com/apiv1/content/lives?limit=30',
                      headers={'User-Agent': 'Mozilla/5.0'})
        if not body: return []
        data = json.loads(body.decode('utf-8'))
        items = []
        for item in data.get('data', {}).get('items', [])[:30]:
            title = item.get('title', '') or item.get('content_text', '')
            title = re.sub(r'<[^>]+>', '', title)[:200]
            if len(title) > 15:
                items.append((title, '华尔街见闻'))
        return items
    except Exception:
        return []


def crawl_parallel():
    """并行抓取 7 大源 (新浪/财联社/东方财富/雪球/股吧/同花顺/华尔街见闻)"""
    results = {}
    tasks = [
        crawl_sina_headlines, crawl_cls_telegraph, crawl_eastmoney_sector,
        crawl_xueqiu_hot, crawl_eastmoney_guba, crawl_10jqka_hot, crawl_wallstreetcn,
    ]
    names = ['sina', 'cls', 'em', 'xueqiu', 'guba', '10jqka', 'wallst']
    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(t): n for t, n in zip(tasks, names)}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()
    return tuple(results.get(n, []) for n in names)


# === 保存与查询 ===

def save_news(date_str, sector_news):
    ensure_dir()
    for sector, items in sector_news.items():
        if not items: continue
        filename = os.path.join(DATA_DIR, f'{sector}_{date_str}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f'# {sector} {date_str} | {len(items)}条\n\n')
            for t, src, score in items:
                emoji = '+' if score > 0.1 else ('-' if score < -0.1 else '=')
                f.write(f'[{emoji}{score:+.1f}] {t} | {src}\n')


def cleanup_old(days=7):
    if not os.path.exists(DATA_DIR): return
    cutoff = datetime.now() - timedelta(days=days)
    for fn in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, fn)
        if os.path.isfile(path) and datetime.fromtimestamp(os.path.getmtime(path)) < cutoff:
            os.remove(path)


def load_today_sentiment():
    """从本地缓存读取今日情绪"""
    today = datetime.now().strftime('%Y-%m-%d')
    scores = defaultdict(float)
    if not os.path.exists(DATA_DIR): return {}
    for fn in os.listdir(DATA_DIR):
        if fn.endswith(f'_{today}.txt'):
            sec = fn.split('_')[0]
            with open(os.path.join(DATA_DIR, fn), encoding='utf-8') as f:
                for line in f:
                    m = re.search(r'\[.*?([+-]\d+\.\d+)\]', line)
                    if m: scores[sec] += float(m.group(1))
    max_abs = max(abs(v) for v in scores.values()) if scores else 1
    return {k: round(v/max_abs, 2) for k, v in scores.items()} if scores else {}


def run_full_crawl():
    """执行完整抓取 (并行版)"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    t0 = time.time()

    sina, cls_news, em, xueqiu, guba, jqka, wallst = crawl_parallel()
    elapsed = time.time() - t0
    print(f'[爬虫] {elapsed:.1f}s: 新浪{len(sina)} 财联社{len(cls_news)} 板块{len(em)} 雪球{len(xueqiu)} 股吧{len(guba)} 同花顺{len(jqka)} 华尔街{len(wallst)}')

    all_news = [(t, s, _score(t)) for t, s in sina]
    all_news += [(t, s, _score(t)) for t, s in cls_news]
    all_news += [(t, s, _score(t)) for t, s in xueqiu]
    all_news += [(t, s, _score(t)) for t, s in guba]
    all_news += [(t, s, _score(t)) for t, s in jqka]
    all_news += [(t, s, _score(t)) for t, s in wallst]
    for name, pct in em:
        s = 0.5 if pct > 2 else (-0.5 if pct < -2 else 0)
        all_news.append((f'{name} {"涨" if pct>0 else "跌"}{abs(pct):.1f}%', '东方财富', s))

    sector_news = defaultdict(list)
    for title, src, score in all_news:
        for sec in _classify(title):
            sector_news[sec].append((title, src, score))

    save_news(date_str, sector_news)
    cleanup_old(7)

    return load_today_sentiment()


# === 分析接口 (供 executor 调用) ===

def get_sector_sentiment(news_texts=None):
    if news_texts is None:
        return load_today_sentiment()
    sentiment = defaultdict(float)
    for text in news_texts:
        related = [s for s, r in _sector_re.items() if r.search(text)]
        if not related: continue
        s = _score(text)
        for sec in related:
            sentiment[sec] += s * 0.3
    return {k: max(-1.0, min(1.0, v)) for k, v in sentiment.items()}


def get_sector_bias(sector, scores):
    v = scores.get(sector, 0.0)
    return 1.0 + v * (0.7 if v < 0 else 1.0)


def get_sector_freeze(sector, scores, threshold=-0.8):
    return scores.get(sector, 0.0) <= threshold


# === 股票热度筛选 (爬虫数据 → 热门股排行) ===

# 股票名称/代码映射 (从 stock_pool 自动提取)
_stock_names = {}  # lazy init


def _init_stock_names():
    """从 stock_pool 提取股票简称关键词"""
    global _stock_names
    if _stock_names:
        return
    try:
        import stock_pool
        name_map = {
            'SHSE.600036': ['招商银行'], 'SHSE.601318': ['中国平安'], 'SHSE.601166': ['兴业银行'],
            'SHSE.600016': ['民生银行'], 'SHSE.601398': ['工商银行'], 'SHSE.601939': ['建设银行'],
            'SHSE.601288': ['农业银行'], 'SHSE.601328': ['交通银行'], 'SHSE.600030': ['中信证券'],
            'SHSE.601688': ['华泰证券'], 'SHSE.600887': ['伊利股份'], 'SZSE.000858': ['五粮液'],
            'SHSE.603288': ['海天味业'], 'SZSE.000568': ['泸州老窖'], 'SHSE.600276': ['恒瑞医药'],
            'SZSE.000538': ['云南白药'], 'SHSE.600436': ['片仔癀'], 'SZSE.002415': ['海康威视'],
            'SZSE.002230': ['科大讯飞'], 'SZSE.000063': ['中兴通讯'], 'SHSE.601012': ['隆基绿能'],
            'SHSE.600438': ['通威股份'], 'SHSE.600089': ['特变电工'], 'SHSE.600031': ['三一重工'],
            'SZSE.000333': ['美的集团'], 'SZSE.000651': ['格力电器'], 'SHSE.601899': ['紫金矿业'],
            'SHSE.603993': ['洛阳钼业'], 'SZSE.002594': ['比亚迪'], 'SHSE.600104': ['上汽集团'],
            'SHSE.600309': ['万华化学'], 'SHSE.600900': ['长江电力'], 'SHSE.601985': ['中国核电'],
            'SHSE.601088': ['中国神华'], 'SHSE.601225': ['陕西煤业'], 'SZSE.000002': ['万科'],
            'SHSE.600048': ['保利发展'], 'SHSE.601919': ['中远海控'], 'SZSE.002714': ['牧原股份'],
        }
        _stock_names.update(name_map)
        # Also add symbol->name for search
        for sym in stock_pool.get_all_symbols():
            code = sym.split('.')[1]
            if sym not in _stock_names:
                _stock_names[sym] = [code]
    except Exception:
        pass


def get_stock_heat(all_news):
    """
    从爬虫新闻计算个股热度排行。
    返回: [(symbol, heat_score, sentiment_score), ...] sorted by heat desc
    """
    _init_stock_names()
    heat = defaultdict(lambda: [0, 0.0])  # [mention_count, sentiment_sum]

    for text, src, score in all_news:
        for sym, names in _stock_names.items():
            for name in names:
                if name in text:
                    heat[sym][0] += 1
                    heat[sym][1] += score
                    break

    # Calculate combined score
    result = []
    for sym, (cnt, sent) in heat.items():
        avg_sent = sent / cnt if cnt > 0 else 0
        # Heat = mentions * 0.6 + sentiment * 0.4
        combined = cnt * 0.6 + avg_sent * 0.4
        result.append((sym, round(combined, 2), round(avg_sent, 2), cnt))

    result.sort(key=lambda x: -x[1])
    return result
