"""
knn_matcher.py - KNN 历史匹配引擎 (V18)

核心思想: 不预判市场是趋势还是震荡，而是拿当前特征去历史库里
找最相似的 K 个时刻，看当时哪种策略赚了钱，就用哪种。

工作流程:
  1. 特征提取: 从日线数据提取 8 维特征向量
  2. 历史库构建: 为所有股票的所有历史时刻构建特征 → 未来收益标签
  3. KNN 搜索: 欧氏距离找最近邻居
  4. 策略推荐: 统计邻居中哪种策略表现最好

特征维度:
  [RSI(14), MA20偏差, MA60偏差, 量比, 波动率, 5日收益, 20日收益, 20日回撤]
"""

import numpy as np
import config
import indicators

KNN_K = 5          # 邻居数量
KNN_MIN_DIST = 0.01  # 最小距离阈值（太近忽略）
FEATURE_NAMES = [
    'rsi', 'ma20_dev', 'ma60_dev', 'vol_ratio',
    'volatility', 'ret_5d', 'ret_20d', 'drawdown_20d',
]


class KNNMatcher:
    """KNN 历史匹配器。"""

    def __init__(self):
        self.feature_db = []       # [{symbol, date, features, forward_ret, ...}]
        self._ready = False

    def build_from_data(self, all_data, bar_dates):
        """
        从预加载的历史数据构建特征库。

        Args:
            all_data: {symbol: DataFrame}  所有股票的历史数据
            bar_dates: [str]  交易日列表
        """
        print('[KNN] 构建历史特征库...')
        self.feature_db = []
        total = 0
        skipped = 0

        for sym, df in all_data.items():
            if sym == config.MARKET_INDEX:
                continue
            if df is None or len(df) < 80:
                skipped += 1
                continue

            closes = df['close'].values
            highs  = df['high'].values
            lows   = df['low'].values
            vols   = df['volume'].values

            # 滑动窗口: 对每个 bar 提取特征
            for i in range(60, len(closes) - 15):
                features = _extract_features(
                    closes[:i+1], highs[:i+1], lows[:i+1], vols[:i+1]
                )
                if features is None:
                    continue

                # 计算未来 15 日收益（标签）
                cur_price = closes[i]
                fwd_price = closes[min(i + 15, len(closes) - 1)]
                fwd_ret = (fwd_price / cur_price - 1) if cur_price > 0 else 0

                date_str = ''
                if 'bob' in df.columns:
                    date_str = str(df['bob'].iloc[i])[:10]

                self.feature_db.append({
                    'symbol': sym,
                    'date': date_str,
                    'features': features,
                    'forward_ret': fwd_ret,
                    'price': cur_price,
                })
                total += 1

        self._ready = True
        print('[KNN] 特征库: %d 条记录 (跳过 %d 只股票数据不足)'
              % (total, skipped))

    def query(self, df, top_k=KNN_K):
        """
        查询与当前特征最相似的 K 个历史时刻。

        Args:
            df: 当前股票的日线 DataFrame
            top_k: 返回的邻居数量

        Returns:
            list of dict: 最相似的 K 个记录，按距离升序
        """
        if not self._ready or len(self.feature_db) == 0:
            return []

        closes = df['close'].values
        highs  = df['high'].values
        lows   = df['low'].values
        vols   = df['volume'].values

        features = _extract_features(closes, highs, lows, vols)
        if features is None:
            return []

        # 计算所有距离
        distances = []
        cur_arr = np.array(features)

        for record in self.feature_db:
            rec_arr = np.array(record['features'])
            # 欧氏距离，但各维度先做归一化（除以最大可能值）
            diff = cur_arr - rec_arr
            # 加权距离: RSI 和波动率更重要
            weights = np.array([2.0, 1.0, 1.0, 1.0, 1.5, 1.0, 1.0, 1.0])
            weighted_diff = diff * weights
            dist = np.sqrt(np.sum(weighted_diff ** 2))
            distances.append((dist, record))

        # 排序取 top-K
        distances.sort(key=lambda x: x[0])
        top = distances[:top_k]

        neighbors = []
        for dist, record in top:
            if dist < KNN_MIN_DIST:
                continue
            neighbors.append({
                **record,
                'distance': round(dist, 4),
            })

        return neighbors

    def recommend_strategy(self, df):
        """
        基于 KNN 推荐最优策略。

        统计最近的 K 个邻居中:
          - 均值回归策略在类似场景下的表现（假设 RSI 信号方向）
          - 动量策略的表现（假设趋势信号方向）
          - 量价背离策略的表现

        返回推荐结果。
        """
        neighbors = self.query(df, top_k=KNN_K)

        if len(neighbors) == 0:
            return {
                'recommend': 'voting',  # 回退到投票
                'confidence': 0.0,
                'reason': 'KNN_无相似邻居，回退投票',
                'neighbors': 0,
            }

        # 统计各策略在邻居中的表现
        # 简化版: 用邻居的未来收益方向来判断
        mr_wins = 0
        mom_wins = 0
        vp_wins = 0
        total_ret = 0.0

        for n in neighbors:
            fwd_ret = n['forward_ret']
            total_ret += fwd_ret

            # 均值回归: RSI低时买入 → 反弹 = 胜利
            rsi_val = n['features'][0]
            if rsi_val < 35 and fwd_ret > 0:
                mr_wins += 1
            elif rsi_val < 35 and fwd_ret <= 0:
                mr_wins -= 0.5

            # 动量: MA20 > MA60 时买入 → 继续涨 = 胜利
            ma20_dev = n['features'][1]
            if ma20_dev > 0 and fwd_ret > 0:
                mom_wins += 1
            elif ma20_dev > 0 and fwd_ret <= 0:
                mom_wins -= 0.5

            # 量价背离: 量比 < 0.7 时买入 → 反弹 = 胜利
            vol_ratio = n['features'][3]
            if vol_ratio < 0.7 and fwd_ret > 0:
                vp_wins += 1
            elif vol_ratio < 0.7 and fwd_ret <= 0:
                vp_wins -= 0.5

        # 选最优
        scores = {'MR': mr_wins, 'MOM': mom_wins, 'VP': vp_wins}
        best = max(scores, key=scores.get)
        best_score = scores[best]

        # 如果最优得分太低，回退投票
        if best_score < 1.0 and len(neighbors) < 3:
            return {
                'recommend': 'voting',
                'confidence': 0.0,
                'reason': 'KNN_证据不足(邻居%d,最高分%.1f)，回退投票'
                          % (len(neighbors), best_score),
                'neighbors': len(neighbors),
            }

        avg_ret = total_ret / len(neighbors) if neighbors else 0

        return {
            'recommend': best,
            'confidence': min(0.9, max(0.3, best_score / len(neighbors))),
            'reason': 'KNN_%d邻居推荐%s策略(得分%.1f, 均收益%+.2f%%)'
                      % (len(neighbors), best, best_score, avg_ret * 100),
            'neighbors': len(neighbors),
            'scores': scores,
            'avg_forward_ret': round(avg_ret * 100, 2),
        }


def _extract_features(closes, highs, lows, vols):
    """
    从日线数据提取 8 维特征向量。

    所有特征归一化到大致 [0, 1] 或 [-1, 1] 范围。
    """
    n = len(closes)
    if n < 60:
        return None

    cur_price = float(closes[-1])

    # 1. RSI(14) → [0, 100] → 归一化到 [0, 1]
    rsi = indicators.calc_rsi(closes, period=14)
    if rsi is None:
        return None
    rsi_norm = rsi / 100.0

    # 2. MA20 偏差: (price - MA20) / MA20 → ~[-0.3, 0.3]
    ma20 = indicators.calc_sma(closes, 20)
    if ma20 is None or ma20 <= 0:
        return None
    ma20_dev = (cur_price - ma20) / ma20

    # 3. MA60 偏差
    ma60 = indicators.calc_sma(closes, 60)
    if ma60 is None or ma60 <= 0:
        return None
    ma60_dev = (cur_price - ma60) / ma60

    # 4. 量比: 当日量 / 20日均量 → ~[0, 5] → clip 到 [0, 3]
    vol_ratio = indicators.calc_volume_ratio(vols, 20)
    if vol_ratio is None:
        vol_ratio = 1.0
    vol_ratio_norm = min(3.0, vol_ratio) / 3.0

    # 5. 波动率: 20日标准差 / 价格 → ~[0.01, 0.08]
    if n >= 20:
        rets = np.diff(closes[-21:]) / closes[-21:-1]
        volatility = np.std(rets) if len(rets) > 0 else 0.02
    else:
        volatility = 0.02
    vol_norm = min(0.08, volatility) / 0.08

    # 6. 5日收益率 → ~[-0.3, 0.3]
    if n >= 6:
        ret_5d = (closes[-1] / closes[-6] - 1)
    else:
        ret_5d = 0
    ret_5d_norm = max(-0.3, min(0.3, ret_5d)) / 0.3 + 0.5  # 映射到 [0, 1]

    # 7. 20日收益率
    if n >= 21:
        ret_20d = (closes[-1] / closes[-21] - 1)
    else:
        ret_20d = 0
    ret_20d_norm = max(-0.5, min(0.5, ret_20d)) / 0.5 + 0.5

    # 8. 20日回撤 → [0, 1]
    dd = indicators.calc_drawdown(closes, 20)
    if dd is None:
        dd = 0
    dd_norm = min(0.5, dd) / 0.5

    return [
        rsi_norm, ma20_dev, ma60_dev, vol_ratio_norm,
        vol_norm, ret_5d_norm, ret_20d_norm, dd_norm,
    ]
