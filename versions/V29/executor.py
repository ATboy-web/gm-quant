"""

浠?main.py 鎶界鍏ュ満/鍑哄満鏍稿績閫昏緫锛屼娇涓荤▼搴忕畝娲併€?
鎵€鏈変氦鏄撳喅绛栭€昏緫闆嗕腑鍦ㄦ锛宮ain.py 鍙礋璐ｅ垵濮嬪寲鍜屽洖璋冦€?

鏍稿績娴佺▼:
  1. 妫€鏌ュ嚭鍦?鈫?澶氱瓥鐣ユ姇绁?
  2. 琛屼笟鍔ㄩ噺璁＄畻
  3. 澶氱瓥鐣ラ€夎偂 鈫?琛屼笟宸紓鍖栫瓥鐣?鈫?鎶曠エ铻嶅悎
  4. 浠撲綅绠＄悊 鈫?琛屼笟宸紓鍖栦粨浣?
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
    浜ゆ槗鎵ц鍣?鈥?灏佽鍏ュ満/鍑哄満鍏ㄩ儴閫昏緫銆?
    """

    def __init__(self):
        self.factory = strategy_factory.StrategyFactory()
        # 缂撳瓨: {sector: [strategy instances]}锛岄殢 regime 鏇存柊
        self._strategy_cache = {}
        self._cache_regime = None
        self.cooldown_days = 2   # V28: 3鈫?, V26(1)鍜孷27(3)涓偣
        self._sell_history = {}  # {symbol: sell_date_str}
        # V22: 杩炰簭鐔旀柇
        self._loss_streak = 0
        self._circuit_breaker_until = None  # 鐔旀柇鑷虫煇鏃?
        # V22: 琛屼笟鍔ㄩ噺缂撳瓨
        self._sector_momentum = {}
        # V26: 鍗曞彧鑲＄エ浜ゆ槗娆℃暟杩借釜锛堥槻姝㈤珮棰戦噸澶嶄氦鏄擄級
        self._symbol_buy_count = {}

    def update_sector_momentum(self, momentum_dict):
        """V22: 鏇存柊琛屼笟鍔ㄩ噺鏁版嵁銆?""
        self._sector_momentum = dict(momentum_dict)

    def note_trade_result(self, pnl_pct, today_str):
        """V27: 璁板綍浜ゆ槗缁撴灉锛岃窡韪繛浜忋€傜泩鍒╂椂閲嶇疆鐔旀柇銆?""
        if pnl_pct < 0:
            self._loss_streak += 1
            # 妫€鏌ユ槸鍚﹁Е鍙戠啍鏂?
            if self._loss_streak >= config.STREAK_CIRCUIT_BREAKER:
                from datetime import datetime as dt, timedelta
                self._circuit_breaker_until = (
                    dt.strptime(today_str, '%Y-%m-%d') +
                    timedelta(days=config.CIRCUIT_BREAKER_DAYS)
                ).strftime('%Y-%m-%d')
        else:
            # 鐩堝埄锛氶噸缃繛浜忚鏁板拰鐔旀柇鐘舵€?
            self._loss_streak = 0
            self._circuit_breaker_until = None

    def is_circuit_breaker_active(self, today_str):
        """V22: 妫€鏌ョ啍鏂槸鍚︾敓鏁堛€?""
        if self._circuit_breaker_until is None:
            return False
        if today_str <= self._circuit_breaker_until:
            return True
        # 鐔旀柇鍒版湡锛岄噸缃?
        self._circuit_breaker_until = None
        self._loss_streak = 0
        return False

    def _get_strategies(self, sector, regime):
        """鑾峰彇琛屼笟绛栫暐瀹炰緥锛堝甫缂撳瓨锛夈€?""
        if regime != self._cache_regime:
            self._strategy_cache.clear()
            self._cache_regime = regime
        if sector not in self._strategy_cache:
            self._strategy_cache[sector] = self.factory.create_for_sector(sector, regime)
        return self._strategy_cache[sector]

    def record_sell(self, symbol, sell_date_str):
        self._sell_history[symbol] = sell_date_str

    def record_buy(self, symbol):
        """V26: 璁板綍涔板叆锛岃拷韪崟鍙偂绁ㄤ氦鏄撴鏁般€?""
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
    # 鍑哄満妫€鏌?
    # ==================================================================

    def check_exits(self, pos_info_dict, data_cache, regime, context=None, today_str=''):
        """
        妫€鏌ユ墍鏈夋寔浠撴槸鍚﹂渶瑕佸嚭鍦恒€?

        Args:
            pos_info_dict:  {symbol: {cost, peak, sector, strategy, ...}}
            data_cache:     {symbol: DataFrame}
            regime:         甯傚満鐘舵€?
            context:        GM涓婁笅鏂?(鍙€?
            today_str:      褰撳墠鏃ユ湡

        Returns:
            list of (symbol, sell_info) 鈥?闇€瑕佸崠鍑虹殑鑲＄エ鍒楄〃
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

            sector = info.get('sector', '鏈煡')
            sector_cfg = sector_config.get_sector_config(sector, regime)
            strategies = self._get_strategies(sector, regime)

            # 鍚勭瓥鐣ユ鏌ュ嚭鍦?
            exit_signals = {}
            for strat in strategies:
                sig = strat.check_exit(df, info, regime, context,
                                       sector_cfg=sector_cfg,
                                       today_str=today_str)
                if sig is not None:
                    exit_signals[strat.name] = sig

            # 鏋勯€犺瀺鍚堟姇绁ㄦ墍闇€鍙傛暟
            mr_exit  = exit_signals.get('MR')
            mom_exit = exit_signals.get('MOM')
            vp_exit  = exit_signals.get('VP')
            bk_exit  = exit_signals.get('BK')
            dv_exit  = exit_signals.get('DV')
            rt_exit  = exit_signals.get('RT')

            owner_strategy = info.get('strategy', 'MR')
            vote_result = fusion.vote_exit(mr_exit, mom_exit, vp_exit,
                                           bk_exit=bk_exit, dv_exit=dv_exit, rt_exit=rt_exit,
                                           regime=regime, owner_strategy=owner_strategy)

            if vote_result['action'] == 'SELL':
                sells.append((sym, cur_price, vote_result, info))

        return sells

    # ==================================================================
    # 鍏ュ満閫夎偂
    # ==================================================================

    def find_buy_candidates(self, symbols, occupied_sectors, pos_info_dict,
                            data_cache, sector_momentum, regime, max_needed=999,
                            today_str=''):
        """
        鎵弿鍊欓€夎偂銆備粎淇濈暀蹇€熶环鏍艰繃婊わ紝涓嶉檺鍒跺€欓€夋暟淇濊瘉閫夎偂璐ㄩ噺銆?
        """
        # V27: 杩炰簭鐔旀柇妫€鏌ワ紙閫氳繃 is_circuit_breaker_active 姝ｇ‘澶勭悊鏃ユ湡閲婃斁锛?
        if self.is_circuit_breaker_active(today_str):
            return []  # 鐔旀柇涓紝涓嶅紑鏂颁粨

        symbol_sector = stock_pool.get_symbol_sector_map()
        candidates = []

        for sym in symbols:
            if len(candidates) >= max_needed:
                break

            if sym in pos_info_dict:
                continue

            if sym in self._sell_history:
                continue

            # V26: 鍗曞彧鑲＄エ鏈€澶т氦鏄撴鏁伴檺鍒?
            if self._symbol_buy_count.get(sym, 0) >= config.MAX_TRADES_PER_SYMBOL:
                continue

            sector = symbol_sector.get(sym, '鏈煡')

            df = data_cache.get(sym)
            if df is None:
                continue
            closes = df['close'].values
            if len(closes) < 3:
                continue
            cur_price = float(closes[-1])
            # 蹇€熶环鏍艰繃婊?
            if cur_price < config.PRICE_MIN or cur_price > config.PRICE_MAX:
                continue

            sector_cfg = sector_config.get_sector_config(sector, regime)
            strategies = self._get_strategies(sector, regime)

            if not strategies:
                continue

            # === V23: 甯傚満鎯呯华杩囨护 - 鎯呯华鍏堣 ===
            if hasattr(self, '_sentiment') and self._sentiment:
                if sentiment_engine.get_sector_freeze(sector, self._sentiment):
                    continue
                bias = sentiment_engine.get_sector_bias(sector, self._sentiment)
                if bias < 0.9:
                    sector_cfg = dict(sector_cfg)
                    sector_cfg['entry_threshold'] = sector_cfg.get('entry_threshold', 0.35) * (1.5 - bias * 0.5)

            # 鍚勭瓥鐣ユ墦鍒?
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

            # 琛屼笟宸紓鍖栨姇绁?
            vote_result = self._vote_with_sector_weights(
                mr_sig, mom_sig, vp_sig, bk_sig, dv_sig, rt_sig, regime, sector
            )

            if vote_result['action'] == 'BUY':
                cur_price = float(df['close'].values[-1])

                # 鎵惧嚭涓诲绛栫暐
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
        # V29.4: 绛栫暐閰嶉鍒?鈥?鎸夌瓥鐣ュ垎缁勫彇 top N锛岄槻姝㈠崟涓€绛栫暐鍨勬柇鎵€鏈変粨浣?
        return self._diversify_candidates(candidates)

    def _diversify_candidates(self, candidates, max_per_strategy=2):
        """
        V29.4: 绛栫暐閰嶉鍒?鈥?纭繚鍚勭瓥鐣ヤ俊鍙烽兘鏈変唬琛ㄣ€?

        VP 瓒嬪娍纭棬绉婚櫎鍚庝俊鍙烽噺澶у锛岀函 confidence 鎺掑簭瀵艰嚧 MR/BK/DV/RT
        姘歌繙鎶笉鍒拌祫閲戙€傛寜绛栫暐鍒嗙粍锛屾瘡缁勫彇 top max_per_strategy锛?
        淇濊瘉绛栫暐澶氭牱鎬с€傚悎骞跺悗鎸?confidence 闄嶅簭鎺掑垪銆?

        max_per_strategy=2: 6绛栫暐脳2=12鍊欓€夛紝寮曟搸鍐嶄粠涓€?浠擄紝姣忕绛栫暐鈮?鍙?
        """
        if len(candidates) <= 5:
            return candidates

        by_strategy = {}
        for c in candidates:
            strat = c['best_strategy']
            by_strategy.setdefault(strat, []).append(c)

        diversified = []
        for strat_name in ['MR', 'MOM', 'VP', 'BK', 'DV', 'RT']:
            if strat_name in by_strategy:
                diversified.extend(by_strategy[strat_name][:max_per_strategy])

        diversified.sort(key=lambda x: x['confidence'], reverse=True)
        return diversified

    def _vote_with_sector_weights(self, mr_sig, mom_sig, vp_sig, bk_sig, dv_sig, rt_sig, regime, sector):
        """琛屼笟宸紓鍖栨姇绁ㄨ瀺鍚堛€?绛栫暐: MR/MOM/VP/BK/DV/RT
        
        V29 鍘熷鐗堟湰 鈥?缃俊搴︾敤 avg(confidences)锛屼粨浣嶆瘮渚嬫寜鎶曠エ鏉冮噸鍒嗗眰銆?
        V29.2 鐨勭疆淇″害鍏紡鏀瑰姩锛坢ax+鍏辫瘑鍔犳垚锛夊鑷村绛栫暐淇″彿鎺掑悕婧环锛?
        鎸ゅ帇浜?MR 鍗曠嫭淇″彿鐨勮祫閲戝垎閰嶏紝MR 浠?+105% 璺岃嚦 -44%銆?
        鐜?revert 鍥?V29 鍘熷閫昏緫銆?
        """
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

            # 浠?sector_config 鑾峰彇璇ヨ涓氫笅璇ョ瓥鐣ョ殑鏉冮噸
            weight = sector_config.get_strategy_weight(sector, name, regime)

            if action == 'BUY':
                buy_votes += weight
                voters.append(name)
                confidences.append(conf)
            elif action == 'SELL':
                sell_votes += weight

        # ---- V29 鍘熷: 缃俊搴?= 骞冲潎缃俊搴?----
        if confidences:
            confidence = sum(confidences) / len(confidences)
        else:
            confidence = 0.4

        # ---- 浠撲綅姣斾緥锛圴29 鍘熷锛?---
        if buy_votes >= 2.0:
            return {
                'action': 'BUY', 'confidence': confidence,
                'position_pct': 1.0, 'voters': voters,
                'reason': 'FUSION[%s]' % '+'.join(voters),
            }
        elif buy_votes >= 1.5:
            return {
                'action': 'BUY', 'confidence': confidence,
                'position_pct': 0.80, 'voters': voters,
                'reason': 'FUSION_寮篬%s]' % '+'.join(voters),
            }
        elif buy_votes >= 1.0:
            return {
                'action': 'BUY', 'confidence': confidence,
                'position_pct': 0.60, 'voters': voters,
                'reason': 'FUSION_鍙岀‘璁%s]' % '+'.join(voters),
            }
        elif buy_votes >= 0.8:
            return {
                'action': 'BUY', 'confidence': confidence,
                'position_pct': 0.40, 'voters': voters,
                'reason': 'FUSION_鍗昜%s]' % '+'.join(voters),
            }

        return {
            'action': 'HOLD',
            'confidence': 0.0,
            'position_pct': 0.0,
            'voters': [],
            'reason': 'FUSION_绁ㄦ暟涓嶈冻(%.1f)' % buy_votes,
        }

    # ==================================================================
    # 浠撲綅璁＄畻
    # ==================================================================

    def calc_position_size(self, candidate, available_cash, remaining_slots):
        """
        V26: 鍩轰簬鍥哄畾姣斾緥鍒嗛厤浠撲綅锛屼笉鍐嶉櫎浠emaining_slots銆?
        姣忓彧鎸佷粨绾﹀崰鍙敤璧勯噾鐨?12%-18%锛堟牴鎹瀺鍚堜俊鍙峰己搴︼級锛?
        5鍙寔浠?鈫?绾?60%-75% 鎬昏祫閲戝埄鐢ㄧ巼銆?

        Args:
            candidate:      涔板叆鍊欓€?dict
            available_cash: 鍙敤鐜伴噾
            remaining_slots: 鍓╀綑鍙紑浠撴暟锛堜繚鐣欏弬鏁板吋瀹癸紝V26涓嶅啀浣跨敤锛?

        Returns:
            int: 涔板叆鏁伴噺锛堣偂锛夛紝0 琛ㄧず涓嶅
        """
        sector = candidate['sector']
        price = candidate['price']

        # 琛屼笟鍩虹浠撲綅姣?脳 铻嶅悎淇″彿浠撲綅姣?
        sector_cfg = sector_config.get_sector_config(sector)
        base_pct = sector_cfg.get('position_pct', config.POSITION_PCT)
        pos_pct = base_pct * candidate['position_pct']

        # V26: 鐩存帴鎸夋瘮渚嬪垎閰嶏紝涓嶉櫎浠emaining_slots
        # 闄愬埗鍗曞彧鏈€澶т粨浣嶄负20%闃叉杩囧害闆嗕腑
        pos_pct = min(pos_pct, 0.22)
        allocated = available_cash * pos_pct
        if allocated < price * 100:
            return 0

        qty = int(allocated / (price * 100)) * 100
        return qty if qty >= 100 else 0
