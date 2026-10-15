"""行情数据源 — 通过新浪财经 API 获取期货实时报价和K线数据。
实时报价: hq.sinajs.cn/rn={random}&list=nf_RB0,nf_AU0,nf_RB2610,...
K线数据: stock2.finance.sina.com.cn/futures/api/jsonp.php/...getFewMinLine
"""
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

SINA_URL = "https://hq.sinajs.cn/rn={rn}&list={codes}"
SINA_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Cache-Control": "no-cache",
    "Referer": "https://vip.stock.finance.sina.com.cn/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# nf_ 格式字段索引 (商品期货):
# 0:名称 1:时间 2:开 3:高 4:低 5:昨收 6:买价 7:卖价
# 8:现价 9:均价 10:昨结算 11:买量 12:卖量 13:持仓 14:成交量
NF_FIELDS = {
    "name": 0,
    "time": 1,
    "open": 2,
    "high": 3,
    "low": 4,
    "last_close": 5,
    "bid": 6,
    "ask": 7,
    "current": 8,
    "avg": 9,
    "settle": 10,
    "buy_vol": 11,
    "sell_vol": 12,
    "hold": 13,
    "volume": 14,
}

# 中金所品种字段索引 (50字段，与商品期货格式完全不同):
# 0:开 1:高 2:低 3:现价 4:成交量 5:成交额 6:持仓
# 9:涨停 10:跌停 13:买价 14:卖价 16:昨结算
# 36:日期 37:时间 48:均价 49:名称
CFFEX_FIELDS = {
    "open": 0,
    "high": 1,
    "low": 2,
    "current": 3,
    "volume": 4,
    "hold": 6,
    "bid": 13,
    "ask": 14,
    "settle": 16,
    "date": 36,
    "time_str": 37,
    "avg": 48,
    "name": 49,
}

# 中金所品种前缀
CFFEX_PREFIXES = {"IF", "IH", "IC", "IM", "T", "TF", "TS", "TL"}


@dataclass
class Quote:
    """单条期货行情快照"""
    code: str
    name: str = ""
    price: float = 0.0
    prev_close: float = 0.0      # 昨收盘
    prev_settle: float = 0.0     # 昨结算
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: int = 0
    bid_price: float = 0.0
    ask_price: float = 0.0
    open_interest: int = 0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def change(self) -> float:
        """涨跌额（相对昨结算）"""
        base = self.prev_settle if self.prev_settle > 0 else self.prev_close
        return self.price - base

    @property
    def change_pct(self) -> float:
        """涨跌幅%"""
        base = self.prev_settle if self.prev_settle > 0 else self.prev_close
        if base == 0:
            return 0.0
        return (self.price - base) / base * 100

    @property
    def is_up(self) -> bool:
        return self.change >= 0


@dataclass
class Kline:
    """单根K线"""
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    open_interest: int = 0
    # 异常极值修正前的原始 H/L（未修正为 None），供区间诊断展示修正记录
    orig_high: Optional[float] = None
    orig_low: Optional[float] = None


class SinaDataSource:
    """新浪行情数据源，使用 nf_ 前缀格式，支持具体月份合约"""

    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(SINA_HEADERS)

    def fetch_quotes(self, codes: List[str]) -> Dict[str, Quote]:
        """批量获取多个品种的实时行情

        Args:
            codes: 品种代码列表，如 ["RB0", "AU0", "RB2610"]

        Returns:
            {code: Quote} 字典，获取失败的品种不包含在内
        """
        if not codes:
            return {}

        quotes: Dict[str, Quote] = {}
        batch_size = 30
        for i in range(0, len(codes), batch_size):
            batch = codes[i:i + batch_size]
            try:
                result = self._fetch_batch(batch)
                quotes.update(result)
            except Exception as e:
                logger.warning("批量取数失败 batch%d: %s", i, e)
                # 不再逐个重试（会导致长时间卡顿），直接跳过本批
        return quotes

    def _fetch_batch(self, codes: List[str]) -> Dict[str, Quote]:
        """使用 nf_ 前缀格式批量获取行情（支持商品期货和中金所品种）"""
        rn = format(random.randint(0, 2147483648), 'x')
        nf_codes = ",".join("nf_" + c for c in codes)
        url = SINA_URL.format(rn=rn, codes=nf_codes)

        resp = self._session.get(url, timeout=self.timeout)
        resp.encoding = "gbk"
        quotes: Dict[str, Quote] = {}

        for line in resp.text.strip().split("\n"):
            if '="' not in line:
                continue
            try:
                var_part = line.split("=", 1)
                raw_code = var_part[0].split("_")[-1].strip()
                if raw_code.startswith("nf"):
                    code = raw_code[2:]
                else:
                    code = raw_code

                val = var_part[1].strip().strip('";')
                if not val:
                    continue
                fields = val.split(",")
                if len(fields) < 8:
                    continue

                def f(idx):
                    if idx >= len(fields):
                        return 0.0
                    return self._safe_float(fields[idx])

                def s(idx):
                    if idx >= len(fields):
                        return ""
                    return fields[idx].strip()

                # 中金所品种：字段格式不同（50字段 vs 商品期货15字段）
                # 中金所第0字段是开盘价（数字），商品期货第0字段是名称（中文）
                prefix = code.rstrip("0123456789")
                is_cffex = prefix in CFFEX_PREFIXES
                if is_cffex and len(fields) >= 40:
                    q = Quote(
                        code=code,
                        name=s(CFFEX_FIELDS["name"]),
                        price=f(CFFEX_FIELDS["current"]),
                        prev_close=f(CFFEX_FIELDS["settle"]),
                        prev_settle=f(CFFEX_FIELDS["settle"]),
                        open=f(CFFEX_FIELDS["open"]),
                        high=f(CFFEX_FIELDS["high"]),
                        low=f(CFFEX_FIELDS["low"]),
                        volume=self._safe_int(fields[CFFEX_FIELDS["volume"]]) if CFFEX_FIELDS["volume"] < len(fields) else 0,
                        bid_price=f(CFFEX_FIELDS["bid"]),
                        ask_price=f(CFFEX_FIELDS["ask"]),
                        open_interest=self._safe_int(fields[CFFEX_FIELDS["hold"]]) if CFFEX_FIELDS["hold"] < len(fields) else 0,
                    )
                else:
                    q = Quote(
                        code=code,
                        name=s(NF_FIELDS["name"]),
                        price=f(NF_FIELDS["current"]),
                        prev_close=f(NF_FIELDS["last_close"]),
                        prev_settle=f(NF_FIELDS["settle"]),
                        open=f(NF_FIELDS["open"]),
                        high=f(NF_FIELDS["high"]),
                        low=f(NF_FIELDS["low"]),
                        volume=self._safe_int(fields[NF_FIELDS["volume"]]) if NF_FIELDS["volume"] < len(fields) else 0,
                        bid_price=f(NF_FIELDS["bid"]),
                        ask_price=f(NF_FIELDS["ask"]),
                        open_interest=self._safe_int(fields[NF_FIELDS["hold"]]) if NF_FIELDS["hold"] < len(fields) else 0,
                    )
                if q.price > 0:
                    quotes[code] = q
            except (IndexError, ValueError) as e:
                logger.debug("解析行失败: %s -> %s", line[:80], e)

        return quotes

    def fetch_single(self, code: str) -> Optional[Quote]:
        result = self.fetch_quotes([code])
        return result.get(code)

    @staticmethod
    def _safe_float(val: str) -> float:
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_int(val: str) -> int:
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return 0

    def test_connection(self) -> bool:
        """测试连接是否正常"""
        try:
            q = self.fetch_single("RB0")
            return q is not None and q.price > 0
        except Exception:
            return False

    def fetch_contracts(self, variety: str) -> List[dict]:
        """获取某品种的所有可交易合约列表（用于合约浏览）
        
        Args:
            variety: 品种前缀，如 "RB", "AU", "CU"
            
        Returns:
            [{"code": "RB2610", "name": "螺纹钢2610", "price": 2995.0}, ...]
        """
        contracts = []
        # 只查近2年，减少无效查询（远月合约通常无数据）
        years = [25, 26]
        months = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
        
        test_codes = []
        for y in years:
            for m in months:
                code = f"{variety}{y:02d}{m:02d}"
                test_codes.append(code)
        
        # 批量查询，单次请求全部24个代码（在30个限制内）
        try:
            quotes = self._fetch_batch(test_codes)
        except Exception as e:
            logger.warning("fetch_contracts 批量查询失败: %s", e)
            quotes = {}
        
        for code in test_codes:
            q = quotes.get(code)
            if q and q.price > 0:
                contracts.append({
                    "code": code,
                    "name": q.name,
                    "price": q.price,
                    "volume": q.volume,
                    "open_interest": q.open_interest,
                })
        
        # 按成交量排序（主力合约在前）
        contracts.sort(key=lambda x: x["volume"], reverse=True)
        return contracts

    # ==================== K线数据 ====================

    KLINE_URL = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
        "var%20_{symbol}_{freq}_{ts}=/InnerFuturesNewService.getFewMinLine"
        "?symbol={symbol}&type={freq}"
    )
    KLINE_HEADERS = {"Referer": "https://finance.sina.com.cn/"}
    VALID_PERIODS = {1, 5, 10, 15, 30, 60}

    def fetch_klines(self, code: str, period: int = 5) -> List[Kline]:
        """获取期货品种M分钟K线

        Args:
            code: 合约代码，如 RB0 / RB2610（不带 nf_ 前缀）
            period: 分钟周期，仅支持 1/5/10/15/30/60

        Returns:
            按时间正序排列的 Kline 列表；解析失败返回空列表
        """
        if period not in self.VALID_PERIODS:
            logger.warning("不支持的K线周期: %s", period)
            return []
        ts = int(time.time() * 1000)
        url = self.KLINE_URL.format(symbol=code.upper(), freq=period, ts=ts)
        try:
            resp = self._session.get(url, timeout=self.timeout, headers=self.KLINE_HEADERS)
            return self._parse_kline_jsonp(resp.text)
        except Exception as e:
            logger.warning("K线取数失败 %s %smin: %s", code, period, e)
            return []

    @staticmethod
    def _parse_kline_jsonp(text: str) -> List[Kline]:
        """解析 JSONP: var _RB0_5_xxx=([{...},...]);"""
        result: List[Kline] = []
        if "=(" not in text:
            return result
        try:
            json_str = text.split("=(", 1)[1]
            idx = json_str.rfind("]")
            if idx >= 0:
                json_str = json_str[:idx + 1]
            raw_list = json.loads(json_str)
        except (ValueError, IndexError) as e:
            logger.warning("K线JSONP解析失败: %s", e)
            return result
        for item in raw_list:
            try:
                t = datetime.strptime(item["d"], "%Y-%m-%d %H:%M:%S")
                result.append(Kline(
                    time=t,
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=int(float(item["v"])),
                    open_interest=int(float(item.get("p", 0))),
                ))
            except (KeyError, ValueError, TypeError):
                continue
        result.sort(key=lambda k: k.time)
        return result

    def fetch_klines_front_n(self, code: str, period: int, count: int,
                             since_dt: datetime) -> Tuple[List[Kline], bool]:
        """取 since_dt 之后、已收盘的前 count 根K线（剔除数据源异常极值）

        新浪K线时间标签为结束时间（如21:35代表21:30-21:35这根K线）。
        - 结束时间 > since_dt 才属于本时段（首根K线结束时间严格大于开盘时间）
        - 结束时间在当前时间之后 → 未收盘，需排除
        - 结束时间刚过但不足10秒 → 新浪数据可能未更新完，需排除
        - 新浪API可能产生两种可识别的异常模式（均为残留挂单/数据错误的可靠指纹）：
          模式1：H/L精确等于前收盘价prev_close 且 偏离实体超过0.5倍参考宽度
                 （如AG2610的16054案例；跳空日昨收在K线范围外，不会误触发）
          模式3：H<实体高点 或 L>实体低点（数据本身矛盾，如SC2609的558.6案例H<open/close）
          处理方式：用该K线的max/min(open, close)替代异常H/L。
          正常极值（含跳空日第一根K线真实的开盘冲高/探低）一律保留。
          注意：不要引入"唯一极值+大幅偏离实体"类判定——跳空高开/低开日的第一根
          K线天然满足该形态，会被误判为异常导致区间偏窄（2026-08-17夜盘案例）。

        Returns:
            (klines, enough) — enough 表示是否凑够 count 根
        """
        all_k = self.fetch_klines(code, period)
        now = datetime.now()
        # 过滤出本时段内、且不超过当前时间的K线
        session_k = [k for k in all_k if k.time > since_dt and k.time <= now]
        session_k.sort(key=lambda k: k.time)
        # 排除刚收盘的最后一根K线（新浪数据可能有数秒延迟）
        if session_k:
            last = session_k[-1]
            seconds_since_close = (now - last.time).total_seconds()
            if seconds_since_close < 10:
                session_k = session_k[:-1]
        # 剔除数据源异常极值（仅限可靠指纹，正常极值一律保留）
        #   模式1：H/L精确等于前收盘价prev_close 且 偏离实体>0.5倍参考宽度
        #          （集合竞价残留挂单；跳空日昨收在K线范围外，不会误触发）
        #   模式3：H<实体高点 或 L>实体低点（数据矛盾）
        # 处理方式：用该K线的max/min(open, close)替代异常H/L
        if len(session_k) >= 1:
            # 从all_k中获取前收盘价（避免重复API请求）
            prev_close = None
            prev_k = [k for k in all_k if k.time < since_dt and k.time <= now]
            if prev_k:
                prev_close = max(prev_k, key=lambda x: x.time).close
            for i in range(len(session_k)):
                k = session_k[i]
                body_hi = max(k.open, k.close)
                body_lo = min(k.open, k.close)
                new_hi = k.high
                new_lo = k.low
                # 模式3判定：H/L低于/高于自身实体（数据矛盾）— 无需参考K线
                hi_invalid = k.high < body_hi
                lo_invalid = k.low > body_lo
                if hi_invalid:
                    new_hi = body_hi
                if lo_invalid:
                    new_lo = body_lo
                # 模式1/2判定：需要参考K线计算偏离阈值
                if len(session_k) >= 3:
                    # 用相邻K线计算参考范围（前后各取最多4根，排除自身）
                    start = max(0, i - 4)
                    end = min(len(session_k), i + 5)
                    ref = session_k[start:i] + session_k[i+1:end]
                    if ref:
                        ref_hi = max(x.high for x in ref)
                        ref_lo = min(x.low for x in ref)
                        ref_range = ref_hi - ref_lo
                        if ref_range > 0:
                            # 模式1判定：H/L精确等于前收盘价（集合竞价残留的可靠指纹）
                            # 注：跳空日昨收价必然在K线范围之外，不会误触发
                            hi_eq_prev = (prev_close is not None and k.high == prev_close)
                            lo_eq_prev = (prev_close is not None and k.low == prev_close)
                            # 偏离实体判定
                            hi_dev = k.high - body_hi > ref_range * 0.5
                            lo_dev = body_lo - k.low > ref_range * 0.5
                            # H异常：精确等于前收盘价 且 偏离实体超过0.5倍参考宽度
                            # 不再使用"唯一极值+偏离实体"判定（原模式2）：该判定在跳空
                            # 高开/低开日会把第一根K线真实的开盘冲高/探低误判为异常
                            # （2026-08-17夜盘 HC/AG/L/EB/SA 等误伤案例）
                            if hi_eq_prev and hi_dev:
                                new_hi = body_hi
                            if lo_eq_prev and lo_dev:
                                new_lo = body_lo
                if new_hi != k.high or new_lo != k.low:
                    session_k[i] = Kline(
                        time=k.time,
                        open=k.open,
                        high=new_hi,
                        low=new_lo,
                        close=k.close,
                        volume=k.volume,
                        open_interest=k.open_interest,
                        orig_high=k.high,
                        orig_low=k.low,
                    )
        return session_k[:count], len(session_k) >= count

    def fetch_prev_session_close(self, code: str, period: int,
                                 current_session_start: datetime) -> Optional[float]:
        """获取当前时段开盘前的最后一根K线收盘价（即上一时段收盘价）

        Args:
            code: 合约代码
            period: K线周期(分钟)
            current_session_start: 当前时段开盘时间（如 09:00 / 13:30 / 21:00）

        Returns:
            最后一根K线收盘价，无数据返回 None
        """
        from trading_hours import is_trading
        all_k = self.fetch_klines(code, period)
        now = datetime.now()
        # 取当前时段开盘前的K线，排除未来时间戳，并用 is_trading 过滤非交易时段的异常K线
        prev_k = [k for k in all_k
                  if k.time < current_session_start
                  and k.time <= now
                  and is_trading(code, k.time)]
        prev_k.sort(key=lambda k: k.time)
        return prev_k[-1].close if prev_k else None
