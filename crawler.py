"""
crawler.py — 财经新闻爬虫 (V23)

抓取数据源:
  1. 东方财富板块异动
  2. 新浪财经24小时热文
  3. 财联社电报

保存格式: data/news/{板块}_{YYYY-MM-DD}.txt
每条: [时间] 标题 | 来源 | 情绪分
"""
import os
import re
import json
import time
import urllib.request
from datetime import datetime, timedelta
from collections import defaultdict

# 保存目录
DATA_DIR = r'C:\Users\Administrator\WorkBuddy\Claw\data\news'

# 板块关键词 (从 market_sentiment 复制)
SECTOR_KW = {
    '金融': ['银行', '保险', '券商', '金融', '利率', '降息', '加息', '央行'],
    '消费': ['消费', '白酒', '食品', '饮料', '零售', '家电'],
    '医药': ['医药', '医疗', '疫苗', '创新药', '中药'],
    '科技': ['AI', '人工智能', '芯片', '半导体', '算力', '5G', '华为', '大模型'],
    '新能源': ['光伏', '风电', '储能', '锂电', '新能源', '碳中和'],
    '制造': ['工程机械', '工业', '制造', '基建', '建材', '水泥', '钢铁'],
    '有色': ['黄金', '铜', '铝', '稀土', '矿产', '有色'],
    '汽车': ['汽车', '新能源车', '整车', '比亚迪', '特斯拉'],
    '化工': ['化工', '石化', '化肥', '新材料'],
    '公用事业': ['电力', '核电', '水电', '电网', '公用'],
    '军工': ['军工', '航天', '航空', '船舶', '国防'],
    '煤炭': ['煤炭', '煤', '矿山'],
}

POS_WORDS = ['大涨', '涨停', '利好', '突破', '反弹', '走强', '领涨', '政策支持', '资金流入']
NEG_WORDS = ['大跌', '跌停', '利空', '破位', '走弱', '领跌', '监管', '处罚', '亏损']


def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def classify_sector(text):
    """识别文本属于哪些板块"""
    sectors = []
    for sec, kws in SECTOR_KW.items():
        for kw in kws:
            if kw in text:
                sectors.append(sec)
                break
    return sectors if sectors else ['综合']


def sentiment_score(text):
    """简单情绪评分"""
    pos = sum(1 for w in POS_WORDS if w in text)
    neg = sum(1 for w in NEG_WORDS if w in text)
    if pos + neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 2)


def crawl_eastmoney_sector():
    """
    抓取东方财富板块行情 (实时)
    返回: [(板块名, 涨跌幅, 领涨股)]
    """
    results = []
    try:
        url = ('https://push2.eastmoney.com/api/qt/clist/get?'
               'pn=1&pz=50&po=1&np=1&fltt=2&invt=2'
               '&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14')
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://quote.eastmoney.com/'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('data', {}).get('diff', [])[:30]:
            name = item.get('f14', '')
            pct = item.get('f3', 0)
            if name:
                results.append((name, pct))
    except Exception as e:
        print(f'[东方财富] 抓取失败: {e}')
    return results


def crawl_sina_roll():
    """
    抓取新浪财经滚动新闻
    返回: [(标题, 时间)]
    """
    news = []
    try:
        url = 'https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&num=50'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('result', {}).get('data', []):
            title = item.get('title', '')
            ctime = item.get('ctime', '')
            if title:
                news.append((title, ctime))
    except Exception as e:
        print(f'[新浪] 抓取失败: {e}')
    return news


def crawl_cls_telegraph():
    """
    抓取财联社电报 (快讯)
    返回: [(标题, 时间)]
    """
    news = []
    try:
        url = 'https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6'
        payload = json.dumps({
            'type': 'telegram', 'keyword': '', 'page': 0, 'rn': 30
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        for item in data.get('data', {}).get('roll_data', [])[:30]:
            title = item.get('title', '') or item.get('brief', '')
            ctime = item.get('ctime', '')
            if title:
                news.append((title, ctime))
    except Exception as e:
        print(f'[财联社] 抓取失败: {e}')
    return news


def save_news(date_str, sector_news):
    """保存新闻到文件"""
    ensure_dir()
    for sector, items in sector_news.items():
        if not items:
            continue
        filename = os.path.join(DATA_DIR, f'{sector}_{date_str}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f'# {sector} 板块新闻 {date_str}\n')
            f.write(f'# 共 {len(items)} 条\n\n')
            for t, src, score in items:
                emoji = '🟢' if score > 0.2 else ('🔴' if score < -0.2 else '⚪')
                f.write(f'[{emoji} {score:+.1f}] {t} | 来源:{src}\n')
        print(f'  保存: {filename} ({len(items)}条)')


def cleanup_old_news(days=7):
    """清理N天前的新闻文件"""
    cutoff = datetime.now() - timedelta(days=days)
    if not os.path.exists(DATA_DIR):
        return
    deleted = 0
    for fn in os.listdir(DATA_DIR):
        path = os.path.join(DATA_DIR, fn)
        if os.path.isfile(path):
            mtime = datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)
                deleted += 1
    if deleted:
        print(f'清理了 {deleted} 个过期文件')


def load_today_sentiment():
    """加载今天的板块情绪数据 (配合 market_sentiment 使用)"""
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
    # 归一化
    if scores:
        max_abs = max(abs(v) for v in scores.values())
        if max_abs > 0:
            return {k: round(v / max_abs, 2) for k, v in scores.items()}
    return dict(scores)


def run_full_crawl():
    """执行完整抓取流程"""
    date_str = datetime.now().strftime('%Y-%m-%d')
    print(f'=== 财经爬虫 {date_str} ===')

    # 1. 新浪滚动
    print('[1/3] 新浪财经...')
    sina = crawl_sina_roll()
    print(f'  获取 {len(sina)} 条')

    # 2. 财联社
    print('[2/3] 财联社电报...')
    cls = crawl_cls_telegraph()
    print(f'  获取 {len(cls)} 条')

    # 3. 东方财富板块
    print('[3/3] 东方财富板块...')
    em = crawl_eastmoney_sector()
    print(f'  获取 {len(em)} 个板块')

    # 汇总 & 分类
    all_news = [(t, '新浪', sentiment_score(t)) for t, _ in sina if len(t) > 10]
    all_news += [(t, '财联社', sentiment_score(t)) for t, _ in cls if len(t) > 10]
    # 板块数据也加入
    for name, pct in em:
        score = 0.5 if pct > 2 else (-0.5 if pct < -2 else 0)
        all_news.append((f'{name}板块 {"涨" if pct>0 else "跌"}{abs(pct):.1f}%', '东方财富', score))

    # 按板块分组
    sector_news = defaultdict(list)
    for title, src, score in all_news:
        for sec in classify_sector(title):
            sector_news[sec].append((title, src, score))

    # 保存
    print(f'\n保存新闻 ({sum(len(v) for v in sector_news.values())} 条 → {len(sector_news)} 个板块)')
    save_news(date_str, sector_news)

    # 清理7天前的
    cleanup_old_news(7)

    # 返回今日情绪
    return load_today_sentiment()


if __name__ == '__main__':
    sentiment = run_full_crawl()
    print('\n今日板块情绪:')
    for sec, score in sorted(sentiment.items(), key=lambda x: -x[1]):
        bar = '🟢' if score > 0.1 else ('🔴' if score < -0.1 else '⚪')
        print(f'  {bar} {sec}: {score:+.2f}')
