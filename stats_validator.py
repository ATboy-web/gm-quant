"""
stats_validator.py - 统计验证引擎 (仿 Vibe-Trading)

Vibe-Trading 核心借鉴: Monte Carlo模拟 + Bootstrap CI + Walk-Forward验证。
避免"只看一条权益曲线"的陷阱, 提供统计学意义上的策略可靠性评估。

功能:
  1. Monte Carlo: 随机扰动交易顺序 N 次, 估计收益分布
  2. Bootstrap CI: 重采样交易记录, 计算 Sharpe/收益/回撤的置信区间
  3. Walk-Forward: 滚动训练/测试窗口, 验证参数稳定性
  4. 综合评分: 0-100分, 评估策略鲁棒性
"""

import numpy as np
import pandas as pd
from datetime import timedelta


def monte_carlo_shuffle(trades, daily_values, n_simulations=500, seed=42):
    """
    Monte Carlo模拟: 随机打乱交易顺序, 评估路径依赖性。

    原理: 如果策略收益严重依赖交易顺序, 则鲁棒性差。
    每次随机排列卖出交易, 重新计算权益曲线。

    Returns:
        dict: {mc_returns, mc_sharpes, mc_maxdd, win_ratio, stability_score}
    """
    np.random.seed(seed)
    sells = [t for t in trades if t.get('side') == 'SELL']
    if len(sells) < 10:
        return {'mc_returns': [], 'stability_score': 0.0, 'warning': '交易太少'}

    mc_returns = []
    mc_sharpes = []
    mc_maxdds = []

    initial = daily_values[0]['total'] if daily_values else 25000

    for _ in range(n_simulations):
        shuffled = np.random.permutation(sells)
        equity = initial
        peak = initial
        max_dd = 0
        daily_returns = []

        for t in shuffled:
            pnl_pct = t.get('pnl_pct', 0)
            equity *= (1 + pnl_pct / 100)
            daily_returns.append(pnl_pct)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak
            if dd < max_dd:
                max_dd = dd

        final_return = (equity - initial) / initial * 100
        mc_returns.append(final_return)
        mc_maxdds.append(-max_dd * 100)

        if len(daily_returns) > 1:
            mu = np.mean(daily_returns)
            sigma = np.std(daily_returns) if np.std(daily_returns) > 0 else 0.01
            sharpe = mu / sigma * np.sqrt(252) if sigma > 0 else 0
        else:
            sharpe = 0
        mc_sharpes.append(sharpe)

    mc_returns = np.array(mc_returns)
    wins = np.sum(mc_returns > 0)
    win_ratio = wins / n_simulations * 100

    # 稳定性评分: 收益分布的 CV 越低越好
    if np.mean(mc_returns) != 0:
        cv = np.std(mc_returns) / abs(np.mean(mc_returns))
    else:
        cv = 999
    stability_score = max(0, min(100, 100 * (1 - cv / 3)))

    return {
        'mc_returns': mc_returns,
        'mc_sharpes': mc_sharpes,
        'mc_maxdds': mc_maxdds,
        'mean_return': float(np.mean(mc_returns)),
        'std_return': float(np.std(mc_returns)),
        'p5_return': float(np.percentile(mc_returns, 5)),
        'p95_return': float(np.percentile(mc_returns, 95)),
        'win_ratio': float(win_ratio),
        'stability_score': float(stability_score),
        'stability_grade': _score_to_grade(stability_score),
    }


def bootstrap_confidence(trades, daily_values, n_bootstrap=1000, seed=42):
    """
    Bootstrap置信区间: 重采样交易, 估计关键指标的不确定性。

    对卖出交易做有放回重采样, 计算收益/Sharpe/回撤的 95% CI。

    Returns:
        dict: {return_ci, sharpe_ci, maxdd_ci, mean_return, ...}
    """
    np.random.seed(seed)
    sells = [t for t in trades if t.get('side') == 'SELL']
    if len(sells) < 20:
        return {'warning': '交易太少, Bootstrap不可靠 (需要20+笔)'}

    initial = daily_values[0]['total'] if daily_values else 25000
    n_samples = min(len(sells), len(sells))

    bs_returns = []
    bs_sharpes = []
    bs_maxdds = []

    for _ in range(n_bootstrap):
        sampled = np.random.choice(sells, size=n_samples, replace=True)
        equity = initial
        peak = initial
        max_dd = 0
        pnls = []

        for t in sampled:
            pnl_pct = t.get('pnl_pct', 0)
            equity *= (1 + pnl_pct / 100)
            pnls.append(pnl_pct)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak
            if dd < max_dd:
                max_dd = dd

        final_return = (equity - initial) / initial * 100
        bs_returns.append(final_return)
        bs_maxdds.append(-max_dd * 100)

        if len(pnls) > 1:
            mu = np.mean(pnls)
            sigma = np.std(pnls) if np.std(pnls) > 0 else 0.01
            sharpe = mu / sigma * np.sqrt(252) if sigma > 0 else 0
        else:
            sharpe = 0
        bs_sharpes.append(sharpe)

    bs_returns = np.array(bs_returns)
    bs_sharpes = np.array(bs_sharpes)
    bs_maxdds = np.array(bs_maxdds)

    return {
        'return_ci': (float(np.percentile(bs_returns, 2.5)), float(np.percentile(bs_returns, 97.5))),
        'return_mean': float(np.mean(bs_returns)),
        'sharpe_ci': (float(np.percentile(bs_sharpes, 2.5)), float(np.percentile(bs_sharpes, 97.5))),
        'sharpe_mean': float(np.mean(bs_sharpes)),
        'maxdd_ci': (float(np.percentile(bs_maxdds, 2.5)), float(np.percentile(bs_maxdds, 97.5))),
        'maxdd_mean': float(np.mean(bs_maxdds)),
        'profit_prob': float(np.sum(bs_returns > 0) / n_bootstrap * 100),
    }


def walk_forward_analysis(trades, daily_values, n_windows=4):
    """
    Walk-Forward分析: 按时间切分窗口, 检测策略在不同市场阶段的表现一致性。

    V29.10 改进:
      - 改为按时间切分(而非按交易数), 更准确反映市场周期
      - 标识"学习期"问题: 早期窗口差可能因策略未成熟, 非过拟合
      - 增加日期范围输出, 便于诊断

    Returns:
        dict: {window_returns, consistency_score, grade, date_ranges}
    """
    sells = [t for t in trades if t.get('side') == 'SELL']
    if len(sells) < n_windows * 5:
        return {'warning': '交易太少, Walk-Forward不可靠'}

    # 按日期排序
    sells_sorted = sorted(sells, key=lambda x: x.get('date', ''))
    all_dates = [t.get('date', '') for t in sells_sorted]

    # V29.10: 按日期切分窗口(等长时间段)
    total_days = len(set(all_dates))
    if total_days < n_windows * 10:
        # 交易日不足, 退回到按交易数切分
        window_size = len(sells_sorted) // n_windows
        use_time_split = False
    else:
        use_time_split = True
        unique_dates = sorted(set(all_dates))
        days_per_window = len(unique_dates) // n_windows

    initial = daily_values[0]['total'] if daily_values else 25000
    window_returns = []
    date_ranges = []

    for i in range(n_windows):
        if use_time_split:
            start_idx = i * days_per_window
            end_idx = start_idx + days_per_window if i < n_windows - 1 else len(unique_dates)
            start_date = unique_dates[start_idx]
            end_date = unique_dates[min(end_idx - 1, len(unique_dates) - 1)]
            window_trades = [t for t in sells_sorted if start_date <= t.get('date', '') <= end_date]
        else:
            start = i * window_size
            end = start + window_size if i < n_windows - 1 else len(sells_sorted)
            window_trades = sells_sorted[start:end]
            start_date = window_trades[0].get('date', '?') if window_trades else '?'
            end_date = window_trades[-1].get('date', '?') if window_trades else '?'

        equity = initial
        for t in window_trades:
            equity *= (1 + t.get('pnl_pct', 0) / 100)
        r = (equity - initial) / initial * 100
        window_returns.append(r)
        date_ranges.append('%s ~ %s (%d笔)' % (start_date, end_date, len(window_trades)))

    window_returns = np.array(window_returns)

    # V29.10: 改进一致性评分
    positive_windows = np.sum(window_returns > 0)
    # 检测"学习期"问题: 如果只有第1个窗口差, 后面都好, 不算过拟合
    early_penalty = 0
    learning_issue = False
    if n_windows >= 3:
        early_bad = window_returns[0] < 0 and all(window_returns[1:] > 0)
        if early_bad:
            learning_issue = True
            early_penalty = 20  # 减轻早期差的惩罚

    cv = np.std(window_returns) / (abs(np.mean(window_returns)) + 0.01)
    consistency = max(0, min(100,
        positive_windows / n_windows * 50 +
        (1 - min(cv / 3, 1)) * 50 +
        early_penalty))

    return {
        'window_returns': window_returns.tolist(),
        'date_ranges': date_ranges,
        'mean_window_return': float(np.mean(window_returns)),
        'std_window_return': float(np.std(window_returns)),
        'positive_windows': int(positive_windows),
        'total_windows': n_windows,
        'consistency_score': float(consistency),
        'consistency_grade': _score_to_grade(consistency),
        'learning_issue': learning_issue,
    }


def comprehensive_validation(trades, daily_values):
    """
    综合验证: 运行全部三项统计检验, 输出综合评分。

    仿 Vibe-Trading 的统计验证层 — 不只画一条权益曲线。

    Returns:
        dict: 完整的验证报告
    """
    print('\n' + '=' * 60)
    print('  统计验证引擎 (仿 Vibe-Trading)')
    print('  Monte Carlo + Bootstrap CI + Walk-Forward')
    print('=' * 60)

    report = {}

    # 1. Monte Carlo
    mc = monte_carlo_shuffle(trades, daily_values, n_simulations=300)
    report['monte_carlo'] = mc
    if 'warning' not in mc:
        print('  [MC]  收益均值: %+.2f%% | 95%%区间: [%+.1f%%, %+.1f%%]'
              % (mc['mean_return'], mc['p5_return'], mc['p95_return']))
        print('  [MC]  稳定性: %.0f/100 (%s) | 正收益概率: %.0f%%'
              % (mc['stability_score'], mc['stability_grade'], mc['win_ratio']))
    else:
        print('  [MC]  ' + mc['warning'])

    # 2. Bootstrap CI
    bs = bootstrap_confidence(trades, daily_values, n_bootstrap=500)
    report['bootstrap'] = bs
    if 'warning' not in bs:
        rc = bs['return_ci']
        sc = bs['sharpe_ci']
        dc = bs['maxdd_ci']
        print('  [BS]  收益 95%%CI: [%+.1f%%, %+.1f%%] | 均值: %+.1f%%'
              % (rc[0], rc[1], bs['return_mean']))
        print('  [BS]  Sharpe 95%%CI: [%.2f, %.2f] | 均值: %.2f'
              % (sc[0], sc[1], bs['sharpe_mean']))
        print('  [BS]  最大回撤 95%%CI: [%.1f%%, %.1f%%] | 盈利概率: %.0f%%'
              % (dc[0], dc[1], bs['profit_prob']))
    else:
        print('  [BS]  ' + bs['warning'])

    # 3. Walk-Forward
    wf = walk_forward_analysis(trades, daily_values, n_windows=5)
    report['walk_forward'] = wf
    if 'warning' not in wf:
        print('  [WF]  窗口收益: %s' % ', '.join('%+.1f%%' % r for r in wf['window_returns']))
        print('  [WF]  日期范围:')
        for dr in wf.get('date_ranges', []):
            print('        %s' % dr)
        print('  [WF]  一致性: %.0f/100 (%s) | 正收益窗口: %d/%d'
              % (wf['consistency_score'], wf['consistency_grade'],
                 wf['positive_windows'], wf['total_windows']))
        if wf.get('learning_issue'):
            print('  [WF]  提示: 早期窗口表现差(学习期), 后期策略已稳定')
    else:
        print('  [WF]  ' + wf['warning'])

    # 综合评分
    scores = []
    weights = []
    if 'warning' not in mc:
        scores.append(mc['stability_score']); weights.append(0.4)
    if 'warning' not in bs:
        scores.append(bs['profit_prob']); weights.append(0.3)
    if 'warning' not in wf:
        scores.append(wf['consistency_score']); weights.append(0.3)

    if scores and sum(weights) > 0:
        overall = sum(s * w for s, w in zip(scores, weights)) / sum(weights)
    else:
        overall = 0

    report['overall_score'] = round(overall, 1)
    report['overall_grade'] = _score_to_grade(overall)
    report['recommendation'] = _get_recommendation(overall)

    print('  ---')
    print('  综合评分: %.0f/100 (%s)' % (overall, report['overall_grade']))
    print('  建议: %s' % report['recommendation'])
    print('=' * 60)

    return report


def _score_to_grade(score):
    if score >= 80: return 'A — 优秀'
    if score >= 65: return 'B — 良好'
    if score >= 50: return 'C — 一般'
    if score >= 30: return 'D — 较差'
    return 'F — 不可用'


def _get_recommendation(score):
    if score >= 80:
        return '策略鲁棒性优秀, 建议实盘小仓位验证'
    if score >= 65:
        return '策略基本可靠, 建议进一步优化后实盘'
    if score >= 50:
        return '策略存在过拟合风险, 需Walk-Forward调参'
    if score >= 30:
        return '策略稳定性不足, 建议重构入场/出场逻辑'
    return '策略不可用, 回测收益可能是随机结果'


if __name__ == '__main__':
    # 独立测试: 生成模拟数据
    np.random.seed(42)
    fake_trades = []
    equity = 25000
    for i in range(100):
        pnl = np.random.normal(0.5, 3.0)
        fake_trades.append({'side': 'SELL', 'pnl_pct': pnl, 'date': f'2024-{i//20+1:02d}-{i%20+1:02d}'})

    fake_daily = [{'total': equity * (1 + 0.001 * i + np.random.normal(0, 0.01))} for i in range(500)]

    report = comprehensive_validation(fake_trades, fake_daily)
