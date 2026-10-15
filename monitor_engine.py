"""监控引擎 — 在 QThread 中运行，定时取数、判定规则、触发提醒。

核心逻辑:
  1. 每隔 N 秒批量拉取所有监控品种的最新报价
  2. 对每个启用的规则执行区间位置判定
  3. 检测"进入/离开"转换，通过冷却窗口过滤
  4. 触发时发出 alert_triggered 信号
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal, QMutex

from config_store import ConfigStore, MonitorRule
from data_source import SinaDataSource, Quote
from notifier import AlertInfo, Notifier
from trading_hours import is_trading, next_session_time, current_session_bound
from symbols_db import get_symbol_dict

logger = logging.getLogger(__name__)


def compute_position(price, lo, hi):
    """计算价格相对区间的位置: in / above / below / -"""
    if lo <= 0 or hi <= 0 or lo >= hi:
        return "-"
    if price < lo:
        return "below"
    if price > hi:
        return "above"
    return "in"


class MonitorEngine(QThread):
    """监控引擎线程"""

    quote_updated = pyqtSignal(dict)
    alert_triggered = pyqtSignal(object)
    status_changed = pyqtSignal(str, str)
    engine_status = pyqtSignal(str, bool)
    tick_done = pyqtSignal(int)

    def __init__(self, store, notifier, data_source, parent=None):
        super().__init__(parent)
        self.store = store
        self.notifier = notifier
        self.data_source = data_source
        self._running = False
        self._paused = False
        self._mutex = QMutex()
        self._rules = {}
        self._symbol_info = get_symbol_dict()
        self._prev_quotes = {}
        self._diag = {}          # 区间诊断快照 {code: {...}}，独立于_rules，配置重载后仍保留
        self._refresh_rules()

    def _refresh_rules(self):
        db_rules = self.store.get_rules()
        old_states = {}
        for code, r in self._rules.items():
            old_states[code] = (r.pos_state, r.last_trig_enter_ts, r.last_trig_leave_ts,
                                r.last_auto_session, getattr(r, '_last_kline_fetch_ts', 0.0),
                                getattr(r, '_last_kline_got', 0), r.lo, r.hi)
        self._rules = {}
        for r in db_rules:
            if r.code in old_states:
                (r.pos_state, r.last_trig_enter_ts, r.last_trig_leave_ts,
                 r.last_auto_session, last_fetch, last_got, old_lo, old_hi) = old_states[r.code]
                r._last_kline_fetch_ts = last_fetch
                r._last_kline_got = last_got
                # 区间被修改时重置位置状态：价格未动但区间变了会引发假转换提醒
                if abs(r.lo - old_lo) > 1e-9 or abs(r.hi - old_hi) > 1e-9:
                    r.pos_state = "-"
            else:
                r._last_kline_fetch_ts = 0.0
                r._last_kline_got = 0
            self._rules[r.code] = r

    def reload_config(self):
        self._mutex.lock()
        try:
            self._refresh_rules()
        finally:
            self._mutex.unlock()
        logger.info("监控规则已重新加载: %d 条", len(self._rules))

    def pause(self, paused):
        self._paused = paused
        self.engine_status.emit("监控已暂停" if paused else "监控已恢复", not paused)

    def stop(self):
        self._running = False
        self.wait(3000)

    def run(self):
        self._running = True
        logger.info("监控引擎启动")
        ok = self.data_source.test_connection()
        if ok:
            self.engine_status.emit("行情连接正常", True)
        else:
            self.engine_status.emit("行情连接失败，正在重试…", False)
        consecutive_errors = 0
        while self._running:
            if self._paused:
                time.sleep(1)
                continue
            interval = int(self.store.get_setting("refresh_interval", "3"))
            interval = max(1, interval)
            try:
                self._tick()
                consecutive_errors = 0
                if not ok:
                    ok = True
                    self.engine_status.emit("行情连接已恢复", True)
            except Exception as e:
                consecutive_errors += 1
                logger.warning("取数异常 (#%d): %s", consecutive_errors, e)
                if consecutive_errors >= 3:
                    self.engine_status.emit("行情连接异常: %s" % e, False)
                    ok = False
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)
        logger.info("监控引擎停止")

    def _tick(self):
        symbols = self.store.get_symbols()
        if not symbols:
            return
        enabled_codes = [s.code for s in symbols if s.enabled]
        quotes = self.data_source.fetch_quotes(enabled_codes)
        if not quotes:
            return
        # 建立代码到存储名称的映射，用于检测需要更新的名称
        sym_map = {s.code: s for s in symbols}
        for code, q in quotes.items():
            if not q.name and code in self._symbol_info:
                q.name = self._symbol_info[code]["name"]
            # 仅修复空名称或 "0.0" 异常名称，不覆盖已有的正常名称
            stored = sym_map.get(code)
            if q.name and stored and (not stored.name or stored.name == "0.0") and q.name != "0.0":
                self.store.update_symbol_name(code, q.name)
                stored.name = q.name
        self.quote_updated.emit(quotes)
        trading_filter = self.store.get_setting("trading_hours_filter", "1") == "1"
        alerts = []
        self._mutex.lock()
        try:
            for code, quote in quotes.items():
                rule = self._rules.get(code)
                if not rule or not rule.enabled:
                    continue
                # 无效报价跳过：价格为0的异常数据会被误判为"跌破下限"产生假提醒
                if quote.price <= 0:
                    continue
                if trading_filter and not is_trading(code):
                    self.status_changed.emit(code, next_session_time(code))
                    continue

                # ===== K线自动区间计算 =====
                if rule.mode == "auto_kline":
                    session_id, session_start, label = current_session_bound(code)
                    if session_id is None:
                        self.status_changed.emit(code, next_session_time(code))
                        continue
                    # 时段切换 或 区间无效(lo/hi为0) 时重新计算
                    # 后者覆盖软件重启后 last_auto_session 已匹配但区间数据丢失的场景
                    need_calc = (session_id != rule.last_auto_session
                                 or (rule.lo <= 0 and rule.hi <= 0))
                    if need_calc:
                        now_ts = time.time()
                        last_fetch = getattr(rule, '_last_kline_fetch_ts', 0.0)
                        if last_fetch > 0 and (now_ts - last_fetch) < 10:
                            # 冷却期间显示上次获取的K线进度，避免用户以为卡住
                            last_got = getattr(rule, '_last_kline_got', 0)
                            self.status_changed.emit(code, f"等待K线 {last_got}/{rule.kline_count}")
                            continue
                        rule._last_kline_fetch_ts = now_ts
                        klines, enough = self.data_source.fetch_klines_front_n(
                            code, rule.kline_period, rule.kline_count, session_start
                        )
                        got = len(klines)
                        rule._last_kline_got = got
                        if not enough or got < rule.kline_count:
                            self.status_changed.emit(code, f"等待K线 {got}/{rule.kline_count}")
                            continue
                        hi = max(k.high for k in klines)
                        lo = min(k.low for k in klines)
                        rule.lo = lo
                        rule.hi = hi
                        rule.last_auto_session = session_id
                        # 区间更新后以当前价格为基准静默初始化位置状态，不触发提醒。
                        # 提醒仅在后续价格实际穿越区间边界时触发，避免"未突破却提示"。
                        rule.pos_state = compute_position(quote.price, lo, hi)
                        self.store.save_rule(rule)
                        # 诊断快照：记录本次区间计算使用的K线明细，供"区间诊断"查看
                        self._diag[code] = {
                            "session": session_id,
                            "label": label,
                            "period": rule.kline_period,
                            "count": rule.kline_count,
                            "calc_time": datetime.now(),
                            "lo": lo,
                            "hi": hi,
                            "klines": list(klines),
                        }
                        # 详细日志：记录每根K线信息，便于用户对比排查
                        kline_details = ", ".join(
                            f"{k.time.strftime('%H:%M')}H={k.high:g}L={k.low:g}" for k in klines
                        )
                        logger.info("K线自动区间 %s %s: %.2f~%.2f (session=%s, %d根%dmin)",
                                    code, label, lo, hi, session_id,
                                    rule.kline_count, rule.kline_period)
                        logger.info("K线明细 %s: %s", code, kline_details)
                        self.status_changed.emit(code, f"区间更新 {lo:g}~{hi:g}")

                new_pos = compute_position(quote.price, rule.lo, rule.hi)
                old_pos = rule.pos_state
                if old_pos == "-":
                    rule.pos_state = new_pos
                    self._update_status(code, rule, quote)
                    continue
                if new_pos == old_pos:
                    self._update_status(code, rule, quote)
                    continue
                transition = None
                breakthrough = ""
                if new_pos == "in" and old_pos != "in":
                    transition = "enter"
                    # 细分突破方向：从下方涨破下限 / 从上方跌穿上限
                    if old_pos == "below":
                        breakthrough = "up_cross_lo"   # 上穿下限
                    elif old_pos == "above":
                        breakthrough = "down_cross_hi"  # 下穿上限
                elif new_pos != "in" and old_pos == "in":
                    transition = "leave"
                    # 细分突破方向：涨破上限 / 跌破下限
                    if new_pos == "above":
                        breakthrough = "up_break_hi"   # 上穿上限
                    elif new_pos == "below":
                        breakthrough = "down_break_lo"  # 下穿下限
                rule.pos_state = new_pos
                if transition:
                    if rule.direction != "both" and rule.direction != transition:
                        self._update_status(code, rule, quote)
                        continue
                    now = time.time()
                    cooldown_sec = rule.cooldown * 60
                    last_ts = rule.last_trig_enter_ts if transition == "enter" else rule.last_trig_leave_ts
                    if cooldown_sec > 0 and (now - last_ts) < cooldown_sec:
                        self.status_changed.emit(code, "冷却中")
                        continue
                    if transition == "enter":
                        rule.last_trig_enter_ts = now
                    else:
                        rule.last_trig_leave_ts = now
                    alert = AlertInfo(
                        code=code, name=quote.name, price=quote.price,
                        change_pct=quote.change_pct, direction=transition,
                        lo=rule.lo, hi=rule.hi, note=rule.note,
                        breakthrough=breakthrough,
                    )
                    alerts.append(alert)
                    self.status_changed.emit(code, "触发中")
                self._update_status(code, rule, quote)
        finally:
            self._mutex.unlock()
        for alert in alerts:
            self.alert_triggered.emit(alert)
        self._prev_quotes = quotes
        self.tick_done.emit(len(quotes))

    def _update_status(self, code, rule, quote):
        if not rule.enabled:
            self.status_changed.emit(code, "已暂停")
        elif rule.mode == "auto_kline" and (rule.lo <= 0 or rule.hi <= 0):
            self.status_changed.emit(code, "等待K线…")
        elif rule.lo <= 0 or rule.hi <= 0:
            self.status_changed.emit(code, "未配置")
        else:
            now = time.time()
            in_cooldown = False
            if rule.cooldown > 0:
                if rule.pos_state == "in" and (now - rule.last_trig_enter_ts) < rule.cooldown * 60:
                    in_cooldown = True
                elif rule.pos_state not in ("in", "-") and (now - rule.last_trig_leave_ts) < rule.cooldown * 60:
                    in_cooldown = True
            self.status_changed.emit(code, "冷却中" if in_cooldown else "监控中")

    def get_rule_state(self, code):
        self._mutex.lock()
        try:
            return self._rules.get(code)
        finally:
            self._mutex.unlock()

    def get_diag(self, code):
        """返回指定合约最近一次区间计算的诊断快照（K线明细），无则 None"""
        self._mutex.lock()
        try:
            return self._diag.get(code)
        finally:
            self._mutex.unlock()

    def force_trigger(self, code, direction="enter", breakthrough=""):
        rule = self._rules.get(code)
        if not rule:
            return
        quote = self._prev_quotes.get(code)
        if not quote:
            quote = self.data_source.fetch_single(code)
        if not quote:
            return
        # 若未指定突破类型，根据方向给出默认值（测试用）
        if not breakthrough:
            breakthrough = "up_cross_lo" if direction == "enter" else "up_break_hi"
        alert = AlertInfo(
            code=code,
            name=quote.name or self._symbol_info.get(code, {}).get("name", code),
            price=quote.price, change_pct=quote.change_pct,
            direction=direction, lo=rule.lo, hi=rule.hi, note=rule.note,
            breakthrough=breakthrough,
        )
        self.alert_triggered.emit(alert)
