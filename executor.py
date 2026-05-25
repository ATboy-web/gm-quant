"""

从 main.py 抽离入场/出场核心逻辑，使主程序简洁。
所有交易决策逻辑集中在此，main.py 只负责初始化和回调。

核心流程:
  1. 检查出场 → 多策略投票
  2. 行业动量计算
  3. 多策略选股 → 行业差异化策略 → 投票融合
  4. 仓位管理 → 行业差异化仓位
"""

import config
import indicators
import stock_pool
import sector_config
import sentiment_engine
import strategy_factory
import fusion


class TradeExecutor:
    """
    交易执行器 — 封装入场/出场全部逻辑。
    """

    def __init__(self):
        self.factory = strategy_factory.StrategyFactory()
        # 缓存: {sector: [strategy instances]}，随 regime 更新
        self._strategy_cache = {}
        self._cache_regime = None
        self.cooldown_days = 1   # 只冷却1天
        self._sell_history = {}  # {symbol: sell_date_str}
        # V22: 连亏熔断
        self._loss_streak = 0
        self._circuit_breaker_until = None  # 熔断至某日
        # V22: 行业动量缓存
        self._sector_momentum = {}
        # V26: 单只股票交易次数追踪（防止高频重复交易）
        self._symbol_buy_count = {}

    def update_sector_momentum(self, momentum_dict):
        """V22: 更新行业动量数据。"""
        self._sector_momentum = dict(momentum_dict)

    def note_trade_result(self, pnl_pct, today_str):
        """V22: 记录交易结果，跟踪连亏。"""
        if pnl_pct < 0:
            self._loss_streak += 1
        else:
            self._loss_streak = 0
        # 检查是否触发熔断
        if self._loss_streak >= config.STREAK_CIRCUIT_BREAKER:
            from datetime import datetime as dt, timedelta
            self._circuit_breaker_until = (
                dt.strptime(today_str, '%Y-%m-%d') +
                timedelta(days=config.CIRCUIT_BREAKER_DAYS)
            ).strftime('%Y-%m-%d')

    def is_circuit_breaker_active(self, today_str):
        """V22: 检查熔断是否生效。"""
        if self._circuit_breaker_until is None:
            return False
        if today_str <= self._circuit_breaker_until:
            return True
        # 熔断到期，重置
        self._circuit_breaker_until = None
        self._loss_streak = 0
        return False

    def _get_strategies(self, sector, regime):
        """获取行业策略实例（带缓存）。"""
        if regime != self._cache_regime:
            self._strategy_cache.clear()
            self._cache_regime = regime
        if sector not in self._strategy_cache:
            self._strategy_cache[sector] = self.factory.create_for_sector(sector, regime)
        return self._strategy_cache[sector]

    def record_sell(self, symbol, sell_date_str):
        self._sell_history[symbol] = sell_date_str

    def record_buy(self, symbol):
        """V26: 记录买入，追踪单只股票交易次数。"""
        self._symbol_buy_count[symbol] = self._symbol_buy_count.get(symbol, 0) + 1

    def cleanup_cooldowns(self, today_str):
        from datetime import datetime as dt
        expired = []
        for sym, sell_date in self._sell_history.items():
            try:
                days = (dt.strptime(today_str, '%Y-%m-%d') -
                        dt.strptime(sell_date, '%Y-%m-%d')).days
                if days >= self.cooldown_days:
                    expired.append(sym)
            except Exception:
                expired.append(sym)
        for sym in expired:
            del self._sell_history[sym]

    # ==================================================================
    # 出场检查
    # ==================================================================

    def check_exits(self, pos_info_dict, data_cache, regime, context=None, today_str=''):
        """
        检查所有持仓是否需要出场。

        Args:
            pos_info_dict:  {symbol: {cost, peak, sector, strategy, ...}}
            data_cache:     {symbol: DataFrame}
            regime:         市场状态
            context:        GM上下文 (可选)
            today_str:      当前日期

        Returns:
            list of (symbol, sell_info) — 需要卖出的股票列表
        """
        sells = []

        for sym in list(pos_info_dict.keys()):
            info = pos_info_dict[sym]
            df = data_cache.get(sym)
            if df is None:
                continue

            closes = df['close'].values
            if len(closes) < 2:
                continue

            cur_price = float(closes[-1])
            if cur_price > info.get('peak', cur_price):
                info['peak'] = cur_price

            sector = info.get('sector', '未知')
            sector_cfg = sector_config.get_sector_config(sector, regime)
            strategies = self._get_strategies(sector, regime)

            # 各策略检查出场
            exit_signals = {}
            for strat in strategies:
                sig = strat.check_exit(df, info, regime, context,
                                       sector_cfg=sector_cfg,
                                       today_str=today_str)
                if sig is not None:
                    exit_signals[strat.name] = sig

            # 构造融合投票所需参数
            mr_exit  = exit_signals.get('MR')
            mom_exit = exit_signals.get('MOM')
            vp_exit  = exit_signals.get('VP')
            bk_exit  = exit_signals.get('BK')
            dv_exit  = exit_signals.get('DV')
            rt_exit  = exit_signals.get('RT')

            owner_strategy = info.get('strategy', 'MR')
            vote_result = fusion.vote_exit(mr_exit, mom_exit, vp_exit, regime,
                                           owner_strategy=owner_strategy)

            if vote_result['action'] == 'SELL':
                sells.append((sym, cur_price, vote_result, info))

        return sells

    # ==================================================================
    # 入场选股
    # ==================================================================

    def find_buy_candidates(self, symbols, occupied_sectors, pos_info_dict,
                            data_cache, sector_momentum, regime, max_needed=999):
        """
        扫描候选股。仅保留快速价格过滤，不限制候选数保证选股质量。
        """
        symbol_sector = stock_pool.get_symbol_sector_map()
        candidates = []

        for sym in symbols:
            if len(candidates) >= max_needed:
                break

            if sym in pos_info_dict:
                continue

            if sym in self._sell_history:
                continue

            # V26: 单只股票最大交易次数限制
            if self._symbol_buy_count.get(sym, 0) >= config.MAX_TRADES_PER_SYMBOL:
                continue

            sector = symbol_sector.get(sym, '未知')

            df = data_cache.get(sym)
            if df is None:
                continue
            closes = df['close'].values
            if len(closes) < 3:
                continue
            cur_price = float(closes[-1])
            # 快速价格过滤
            if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
                continue

            sector_cfg = sector_config.get_sector_config(sector, regime)
            strategies = self._get_strategies(sector, regime)

            if not strategies:
                continue

            # === V23: 市场情绪过滤 - 情绪先行 ===
            if hasattr(self, '_sentiment') and self._sentiment:
                if sentiment_engine.get_sector_freeze(sector, self._sentiment):
                    continue
                bias = sentiment_engine.get_sector_bias(sector, self._sentiment)
                if bias < 0.9:
                    sector_cfg = dict(sector_cfg)
                    sector_cfg['entry_threshold'] = sector_cfg.get('entry_threshold', 0.35) * (1.5 - bias * 0.5)

            # 各策略打分
            strategy_signals = {}
            for strat in strategies:
                sig = strat.get_signal(df, sector, sector_momentum, regime,
                                       sector_cfg=sector_cfg)
                if sig is not None:
                    strategy_signals[strat.name] = sig

            mr_sig  = strategy_signals.get('MR')
            mom_sig = strategy_signals.get('MOM')
            vp_sig  = strategy_signals.get('VP')
            bk_sig  = strategy_signals.get('BK')
            dv_sig  = strategy_signals.get('DV')
            rt_sig  = strategy_signals.get('RT')

            # 行业差异化投票
            vote_result = self._vote_with_sector_weights(
                mr_sig, mom_sig, vp_sig, bk_sig, dv_sig, rt_sig, regime, sector
            )

            if vote_result['action'] == 'BUY':
                cur_price = float(df['close'].values[-1])

                # 找出主导策略
                best_strat = 'MR'
                best_score = 0
                for sig, name in [(mr_sig, 'MR'), (mom_sig, 'MOM'), (vp_sig, 'VP'),
                                   (bk_sig, 'BK'), (dv_sig, 'DV'), (rt_sig, 'RT')]:
                    if sig and sig.get('action') == 'BUY':
                        if sig.get('score', 0) > best_score:
                            best_score = sig['score']
                            best_strat = name

                rsi_val = mr_sig.get('rsi', 0) if mr_sig and 'rsi' in mr_sig else 0

                candidates.append({
                    'symbol': sym,
                    'sector': sector,
                    'price': cur_price,
                    'confidence': vote_result['confidence'],
                    'position_pct': vote_result['position_pct'],
                    'voters': vote_result['voters'],
                    'reason': vote_result['reason'],
                    'best_strategy': best_strat,
                    'rsi': rsi_val,
                })

        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        return candidates

    def _vote_with_sector_weights(self, mr_sig, mom_sig, vp_sig, bk_sig, dv_sig, rt_sig, regime, sector):
        """行业差异化投票融合。6策略: MR/MOM/VP/BK/DV/RT"""
        signals = [
            ('MR',  mr_sig), ('MOM', mom_sig), ('VP',  vp_sig),
            ('BK',  bk_sig), ('DV',  dv_sig),  ('RT',  rt_sig),
        ]

        buy_votes = 0.0
        sell_votes = 0.0
        voters = []
        confidences = []

        for name, sig in signals:
            if sig is None:
                continue
            action = sig.get('action', 'HOLD')
            conf = sig.get('confidence', 0.0)

            # 从 sector_config 获取该行业下该策略的权重
            weight = sector_config.get_strategy_weight(sector, name, regime)

            if action == 'BUY':
                buy_votes += weight
                voters.append(name)
                confidences.append(conf)
            elif action == 'SELL':
                sell_votes += weight

        # ---- 决策 ----
        if buy_votes >= 2.0:
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
            return {
                'action': 'BUY', 'confidence': avg_conf,
                'position_pct': 1.0, 'voters': voters,
                'reason': 'FUSION[%s]' % '+'.join(voters),
            }
        elif buy_votes >= 1.0:
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.5
            return {
                'action': 'BUY', 'confidence': avg_conf,
                'position_pct': 0.70, 'voters': voters,
                'reason': 'FUSION_弱[%s]' % '+'.join(voters),
            }
        elif buy_votes >= 0.5:
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.3
            return {
                'action': 'BUY', 'confidence': avg_conf,
                'position_pct': 0.40, 'voters': voters,
                'reason': 'FUSION_单[%s]' % '+'.join(voters),
            }

        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'position_pct': 0.0,
            'voters': [],
            'reason': 'FUSION_票数不足(%.1f)' % buy_votes,
        }

    # ==================================================================
    # 仓位计算
    # ==================================================================

    def calc_position_size(self, candidate, available_cash, remaining_slots):
        """
        V26: 基于固定比例分配仓位，不再除以remaining_slots。
        每只持仓约占可用资金的 12%-18%（根据融合信号强度），
        5只持仓 → 约 60%-75% 总资金利用率。

        Args:
            candidate:      买入候选 dict
            available_cash: 可用现金
            remaining_slots: 剩余可开仓数（保留参数兼容，V26不再使用）

        Returns:
            int: 买入数量（股），0 表示不够
        """
        sector = candidate['sector']
        price = candidate['price']

        # 行业基础仓位比 × 融合信号仓位比
        sector_cfg = sector_config.get_sector_config(sector)
        base_pct = sector_cfg.get('position_pct', config.POSITION_PCT)
        pos_pct = base_pct * candidate['position_pct']

        # V26: 直接按比例分配，不除以remaining_slots
        # 限制单只最大仓位为20%防止过度集中
        pos_pct = min(pos_pct, 0.22)
        allocated = available_cash * pos_pct
        if allocated < price * 100:
            return 0

        qty = int(allocated / (price * 100)) * 100
        return qty if qty >= 100 else 0
