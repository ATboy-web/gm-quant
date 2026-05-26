"""
optimizer.py - 策略参数优化器 (仿 Vibe-Trading 4 Optimizers)

Vibe-Trading 核心借鉴: Grid Search + Walk-Forward 交叉验证 + 参数稳定性测试。
自动搜索最优参数组合, 避免手动试错。

功能:
  1. Grid Search: 穷举参数空间, 找到最优组合
  2. Walk-Forward CV: 滚动窗口验证, 检测过拟合
  3. 参数稳定性: 最优参数邻域的表现衰减
  4. 综合评分: 权衡收益/回撤/稳定性
"""

import numpy as np
import config


class GridSearchOptimizer:
    """
    网格搜索优化器 — 仿 Vibe-Trading 参数寻优。

    为特定策略的参数做 Grid Search, 通过回测引擎评估每组参数。
    """

    def __init__(self, backtest_runner, param_space):
        """
        Args:
            backtest_runner: function(config_overrides) -> (return, maxdd, sharpe, trades)
            param_space:      {param_name: [values], ...}
        """
        self.runner = backtest_runner
        self.param_space = param_space

    def search(self, top_n=10, verbose=True):
        """
        穷举所有参数组合, 返回 top N。

        采用综合评分: 0.4*收益 + 0.3*(1-回撤/0.2) + 0.2*Sharpe + 0.1*(1-交易数/500)

        Returns:
            list of [(params, score, return, maxdd, sharpe, trades), ...]
        """
        # 生成所有参数组合
        from itertools import product
        keys = list(self.param_space.keys())
        values = list(self.param_space.values())
        combinations = list(product(*values))

        if verbose:
            print('[Optimizer] 参数空间: %d 组 × %d 维度' % (len(combinations), len(keys)))
            for k, v in self.param_space.items():
                print('  %s: %s' % (k, v))

        results = []
        for i, combo in enumerate(combinations):
            params = dict(zip(keys, combo))

            try:
                ret, maxdd, sharpe, trades = self.runner(params)
            except Exception as e:
                if verbose:
                    print('  [%d/%d] %s → ERROR: %s' % (i + 1, len(combinations), params, e))
                continue

            # 综合评分
            ret_score = max(-1.0, min(1.0, ret / 100.0))  # 收益映射到 [-1, 1]
            dd_score = max(0.0, min(1.0, 1.0 - abs(maxdd) / 0.20))  # 回撤映射
            sharpe_score = max(0.0, min(1.0, sharpe / 3.0))  # Sharpe映射
            trade_score = max(0.0, min(1.0, 1.0 - trades / 500.0))  # 过度交易惩罚

            score = (0.40 * ret_score + 0.30 * dd_score +
                     0.20 * sharpe_score + 0.10 * trade_score)

            results.append((params, score, ret, maxdd, sharpe, trades))

            if verbose and (i + 1) % max(1, len(combinations) // 5) == 0:
                print('  [%d/%d] %.1f%% done, best so far: score=%.3f'
                      % (i + 1, len(combinations), (i + 1) / len(combinations) * 100,
                         max(r[1] for r in results) if results else 0))

        results.sort(key=lambda x: x[1], reverse=True)

        if verbose:
            self._print_top(results, top_n)

        return results[:top_n]

    @staticmethod
    def _print_top(results, top_n):
        print('\n  排名 | 参数 | 评分 | 收益 | 回撤 | Sharpe | 交易')
        print('  ' + '-' * 70)
        for i, (params, score, ret, maxdd, sharpe, trades) in enumerate(results[:top_n]):
            param_str = ', '.join('%s=%s' % kv for kv in params.items())
            print('  #%d | %s | %.3f | %+.1f%% | %.1f%% | %.2f | %d'
                  % (i + 1, param_str[:40], score, ret, maxdd * 100, sharpe, trades))


class ParamStabilityTester:
    """
    参数稳定性测试 — 仿 Vibe-Trading Walk-Forward 验证。

    对最优参数做邻域扰动 (如 ±10%), 检查收益是否骤降。
    如果小幅改动导致收益暴跌, 说明参数过拟合。
    """

    def __init__(self, backtest_runner):
        self.runner = backtest_runner

    def test(self, best_params, perturbations=None, noise_level=0.10):
        """
        对最优参数做扰动测试。

        Args:
            best_params:   最优参数字典
            perturbations: 自定义扰动列表, None 则自动生成
            noise_level:   扰动幅度 (默认 ±10%)

        Returns:
            dict: {original_score, perturbed_scores, stability_ratio, grade}
        """
        if perturbations is None:
            perturbations = self._generate_perturbations(best_params, noise_level)

        # 原始分数
        orig_ret, orig_dd, orig_sharpe, orig_trades = self.runner(best_params)
        orig_score = self._compute_score(orig_ret, orig_dd, orig_sharpe, orig_trades)

        print('\n[Stability] 基准参数: %s → 评分: %.3f (%.1f%%, %.1f%%, %.2f)'
              % (best_params, orig_score, orig_ret, orig_dd * 100, orig_sharpe))

        perturbed_scores = []
        for i, p in enumerate(perturbations):
            try:
                ret, dd, sh, tr = self.runner(p)
                sc = self._compute_score(ret, dd, sh, tr)
                perturbed_scores.append(sc)
                print('  扰动 #%d: %s → 评分: %.3f (%.1f%%, %.1f%%)'
                      % (i + 1, {k: p[k] for k in best_params}, sc, ret, dd * 100))
            except Exception as e:
                print('  扰动 #%d: ERROR %s' % (i + 1, e))
                perturbed_scores.append(0)

        if perturbed_scores and orig_score > 0:
            stability_ratio = np.mean(perturbed_scores) / orig_score
        else:
            stability_ratio = 0

        grade = 'A' if stability_ratio > 0.85 else 'B' if stability_ratio > 0.65 else 'C' if stability_ratio > 0.4 else 'D'

        print('  稳定性比率: %.3f (等级: %s)' % (stability_ratio, grade))

        return {
            'original_score': orig_score,
            'perturbed_mean': float(np.mean(perturbed_scores)) if perturbed_scores else 0,
            'perturbed_std': float(np.std(perturbed_scores)) if perturbed_scores else 0,
            'stability_ratio': round(stability_ratio, 3),
            'grade': grade,
            'overfit_warning': stability_ratio < 0.4,
        }

    def _generate_perturbations(self, params, noise_level):
        """生成邻域参数组合。"""
        perturbations = []
        for key, val in params.items():
            if isinstance(val, (int, float)):
                # 每个参数独立扰动
                up = dict(params)
                down = dict(params)
                up[key] = val * (1 + noise_level)
                down[key] = val * (1 - noise_level)
                if isinstance(val, int):
                    up[key] = max(1, int(up[key]))
                    down[key] = max(1, int(down[key]))
                perturbations.append(up)
                perturbations.append(down)
        return perturbations

    @staticmethod
    def _compute_score(ret, maxdd, sharpe, trades):
        ret_score = max(-1.0, min(1.0, ret / 100.0))
        dd_score = max(0.0, min(1.0, 1.0 - abs(maxdd) / 0.20))
        sharpe_score = max(0.0, min(1.0, sharpe / 3.0))
        trade_score = max(0.0, min(1.0, 1.0 - trades / 500.0))
        return 0.40 * ret_score + 0.30 * dd_score + 0.20 * sharpe_score + 0.10 * trade_score


def quick_optimize_config():
    """
    快速优化 config.py 中的关键参数。

    使用本地回测作为评估函数, 搜索以下参数空间:
      - RSI_BUY: [27, 29, 31, 33]
      - ENTRY_THRESHOLD: [0.45, 0.50, 0.55]
      - STOP_LOSS_CAP: [0.06, 0.07, 0.08]
      - POSITION_PCT: [0.14, 0.16, 0.18, 0.20]

    Returns:
        dict: 最优参数组合
    """
    print('\n' + '=' * 60)
    print('  快速参数优化 (仿 Vibe-Trading Grid Search)')
    print('=' * 60)

    param_space = {
        'rsi_buy': [27, 29, 31, 33],
        'entry_threshold': [0.45, 0.50, 0.55],
        'stop_loss_cap': [0.06, 0.07, 0.08],
        'position_pct': [0.14, 0.16, 0.18, 0.20],
    }

    # V29.10: 预下载数据，避免 Grid Search 每次重复拉取
    import offline_backtest
    all_data = offline_backtest.preload_all_data(
        config.BACKTEST_START[:10], config.BACKTEST_END[:10]
    )
    print('[Optimizer] 预加载数据完成: %d 只股票' % len(all_data))

    def runner(params):
        """使用修改后的配置运行回测(复用预加载数据)。"""
        original = {}
        for k, v in params.items():
            attr = k.upper()
            if hasattr(config, attr):
                original[k] = getattr(config, attr)
                setattr(config, attr, v)

        try:
            # V29.10: 传入 all_data 避免重复下载
            result = offline_backtest.quick_eval(params, silent=True, all_data=all_data)
            if result is None:
                return 0.0, -0.15, 0.0, 999
            return result
        finally:
            for k, v in original.items():
                setattr(config, k.upper(), v)

    opt = GridSearchOptimizer(runner, param_space)
    results = opt.search(top_n=5)

    if results:
        best_params, best_score, best_ret, best_dd, best_sh, best_tr = results[0]
        print('\n  最优参数: %s' % best_params)
        print('  预期收益: %+.1f%% | 回撤: %.1f%% | Sharpe: %.2f | 交易: %d'
              % (best_ret, best_dd * 100, best_sh, best_tr))

        # 稳定性测试
        tester = ParamStabilityTester(runner)
        tester.test(best_params)

        return best_params

    return {}


class WalkForwardOptimizer:
    """
    Walk-Forward 优化器 — 仿 Vibe-Trading 滚动窗口验证。

    将回测区间分成训练集和测试集:
      - 训练集: 做 Grid Search 找最优参数
      - 测试集: 用最优参数验证样本外表现
      - 滚动: 窗口向前移动, 重复
    """

    def __init__(self, backtest_runner, param_space):
        self.runner = backtest_runner
        self.param_space = param_space

    def run(self, n_folds=4, verbose=True):
        """
        执行 Walk-Forward 优化。

        由于需要修改回测日期范围, 此方法仅做框架预留。
        实际使用时需 backtest_runner 支持日期范围参数。

        Returns:
            dict: {fold_results, overall_score}
        """
        print('\n[WalkForward] 预留接口 — 需 backtest_runner 支持日期范围')
        print('[WalkForward] 框架已就绪, 等待回测引擎适配')
        return {'status': 'ready', 'folds': n_folds}
