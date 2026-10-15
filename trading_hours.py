"""期货交易时段判断 — 按交易所和品种判断当前是否在交易时段内。
商品期货白盘: 09:00-11:30, 13:30-15:00 (SHFE/INE/DCE/CZCE/GFEX)
中金所股指期货: 09:30-11:30, 13:00-15:00 (CFFEX)
中金所国债期货: 09:15-11:30, 13:00-15:15 (CFFEX)
夜盘: 21:00 开始，结束时间因品种而异（23:00 / 01:00 / 02:30）
支持具体月份合约: RB2610 / RB0 均可正确判断。
"""
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Optional

logger = logging.getLogger(__name__)

# 无夜盘品种前缀（白盘のみ）
NO_NIGHT_PREFIXES = {"JD", "FB", "BB", "LH", "RR"}

# 中金所品种前缀
CFFEX_STOCK_INDEX_PREFIXES = {"IF", "IH", "IC", "IM"}  # 股指期货
CFFEX_BOND_PREFIXES = {"T", "TF", "TS", "TL"}           # 国债期货

# 夜盘结束时间分类（用品种前缀匹配，兼容 RB0 / RB2610）
# 23:00 收盘: 大部分化工、农产品、广期所品种等
NIGHT_END_23_PREFIXES = {
    # SHFE
    "RB", "HC", "RU", "FU", "BU", "SP", "BR",
    # INE (LU, NR 到23:00; SC 到02:30; BC 到01:00)
    "LU", "NR",
    # DCE
    "I", "J", "JM", "M", "Y", "P", "C", "CS", "A", "B",
    "PP", "L", "V", "EB", "EG", "PG",
    # CZCE
    "CF", "TA", "MA", "SR", "OI", "RM", "FG", "AP", "CJ",
    "SF", "SM", "SA", "UR", "PF", "PK", "PX", "SH", "CY", "PL", "PR",
    # GFEX (工业硅/碳酸锂/多晶硅 21:00-23:00)
    "SI", "LC", "PS",
}

# 01:00 收盘: 有色金属（含不锈钢、氧化铝）
NIGHT_END_01_PREFIXES = {"CU", "AL", "ZN", "NI", "PB", "SN", "BC", "SS", "AO"}

# 02:30 收盘: 贵金属(黄金/白银)、原油夜盘延长
NIGHT_END_0230_PREFIXES = {"AU", "AG", "SC"}

# 白盘时段（所有交易所统一）
DAY_SESSIONS = [
    (dt_time(9, 0), dt_time(11, 30)),
    (dt_time(13, 30), dt_time(15, 0)),
]

# 夜盘开始
NIGHT_START = dt_time(21, 0)


def _get_prefix(code: str) -> str:
    """从合约代码提取品种前缀: RB2610 → RB, RB0 → RB, au2610 → AU"""
    result = ""
    for ch in code.upper():
        if ch.isalpha():
            result += ch
        else:
            break
    return result


def _has_night_session(code: str) -> bool:
    """判断该品种是否有夜盘"""
    prefix = _get_prefix(code)
    if prefix in NO_NIGHT_PREFIXES:
        return False
    return (prefix in NIGHT_END_23_PREFIXES
            or prefix in NIGHT_END_01_PREFIXES
            or prefix in NIGHT_END_0230_PREFIXES)


def _night_end_time(code: str) -> Optional[dt_time]:
    """返回该品种夜盘结束时间，无夜盘返回 None"""
    prefix = _get_prefix(code)
    if prefix in NIGHT_END_0230_PREFIXES:
        return dt_time(2, 30)
    if prefix in NIGHT_END_01_PREFIXES:
        return dt_time(1, 0)
    if prefix in NIGHT_END_23_PREFIXES:
        return dt_time(23, 0)
    return None


def _is_cffex(code: str) -> bool:
    """判断是否为中金所品种"""
    prefix = _get_prefix(code)
    return prefix in CFFEX_STOCK_INDEX_PREFIXES or prefix in CFFEX_BOND_PREFIXES


def is_trading(code: str, dt: Optional[datetime] = None) -> bool:
    """判断某品种当前是否在交易时段

    Args:
        code: 品种代码，支持 RB0（主力连续）和 RB2610（具体月份合约）
        dt: 待判断时间，默认当前时间

    Returns:
        True 如果在交易时段内
    """
    if dt is None:
        dt = datetime.now()

    t = dt.time()
    weekday = dt.weekday()  # 0=Monday, 6=Sunday

    # ===== 中金所品种：无夜盘，交易时段与商品期货不同 =====
    if _is_cffex(code):
        if weekday >= 5:  # 周末休市
            return False
        prefix = _get_prefix(code)
        if prefix in CFFEX_BOND_PREFIXES:
            # 国债期货: 09:15-11:30, 13:00-15:15
            if dt_time(9, 15) <= t <= dt_time(11, 30):
                return True
            if dt_time(13, 0) <= t <= dt_time(15, 15):
                return True
        else:
            # 股指期货: 09:30-11:30, 13:00-15:00
            if dt_time(9, 30) <= t <= dt_time(11, 30):
                return True
            if dt_time(13, 0) <= t <= dt_time(15, 0):
                return True
        return False

    # ---- 周末处理 ----
    # 周六：凌晨可能有周五夜盘延续（仅限夜盘到 01:00/02:30 的品种）
    if weekday == 5:
        if t <= dt_time(2, 30):
            night_end = _night_end_time(code)
            # 仅凌晨收盘的品种（01:00 / 02:30）才会延续到周六凌晨
            if night_end and night_end <= dt_time(2, 30) and t <= night_end:
                return True
        return False

    # 周日：全天休市（周日夜盘从周一 00:00 开始算，实际是周日晚 21:00 不对）
    # 注意：中国期货夜盘是周一至周五晚上，周日晚上没有夜盘
    if weekday == 6:
        return False

    # ---- 周一到周五 ----
    # 检查白盘（周一到周五）
    for start, end in DAY_SESSIONS:
        if start <= t <= end:
            return True

    # 检查夜盘（21:00 起）
    if t >= NIGHT_START:
        if not _has_night_session(code):
            return False
        # 仅 23:00 当日收盘的品种需要在 21:00-23:59 区间内判断收盘
        # 01:00/02:30 是次日时间，21:00-23:59 均在夜盘内
        night_end = _night_end_time(code)
        if night_end == dt_time(23, 0) and t > night_end:
            return False
        return True

    # 检查夜盘延续到凌晨（0:00-02:30）
    # 只有夜盘结束时间在凌晨（01:00 / 02:30）的品种才会延续到第二天凌晨
    # 23:00 收盘的品种夜盘当天晚上就结束了，不延续到凌晨
    # 注意：周一凌晨（weekday=0）没有夜盘延续，因为周日晚上没有夜盘
    if t <= dt_time(2, 30) and weekday >= 1:
        night_end = _night_end_time(code)
        # 夜盘结束时间在凌晨范围（00:00-02:30）才表示跨日延续
        if night_end and night_end <= dt_time(2, 30):
            if t <= night_end:
                return True

    return False


def session_label(code: str, dt: Optional[datetime] = None) -> str:
    """返回交易时段标签: 白盘 / 夜盘 / 休市"""
    if is_trading(code, dt):
        if dt is None:
            dt = datetime.now()
        t = dt.time()
        # 中金所品种无夜盘，交易时间内均为白盘
        if _is_cffex(code):
            return "白盘"
        if dt_time(9, 0) <= t <= dt_time(11, 30) or dt_time(13, 30) <= t <= dt_time(15, 0):
            return "白盘"
        return "夜盘"
    return "休市"


def next_session_time(code: str, dt: Optional[datetime] = None) -> str:
    """返回下一个交易时段的描述（用于休市时显示）"""
    if dt is None:
        dt = datetime.now()

    if is_trading(code, dt):
        return session_label(code, dt)

    t = dt.time()
    has_night = _has_night_session(code)

    # 中金所品种无夜盘，休市提示不同
    if _is_cffex(code):
        prefix = _get_prefix(code)
        if prefix in CFFEX_BOND_PREFIXES:
            # 国债期货: 09:15开盘, 15:15收盘
            if t < dt_time(9, 15):
                return "休市(待开盘)"
            elif dt_time(11, 30) < t < dt_time(13, 0):
                return "休市(午休)"
            elif t > dt_time(15, 15):
                return "休市(今日收盘)"
        else:
            # 股指期货: 09:30开盘, 15:00收盘
            if t < dt_time(9, 30):
                return "休市(待开盘)"
            elif dt_time(11, 30) < t < dt_time(13, 0):
                return "休市(午休)"
            elif t > dt_time(15, 0):
                return "休市(今日收盘)"
        return "休市"

    # 休市时，提示下一个交易时段
    if t < dt_time(9, 0):
        return "休市(待白盘)"
    elif dt_time(11, 30) < t < dt_time(13, 30):
        return "休市(午休)"
    elif dt_time(15, 0) < t < dt_time(21, 0):
        if has_night:
            return "休市(待夜盘)"
        return "休市(今日收盘)"
    elif t >= dt_time(21, 0) or t <= dt_time(2, 30):
        if has_night:
            return "休市(夜盘收盘)"
        return "休市(今日收盘)"
    return "休市"


def current_session_bound(code: str, now: Optional[datetime] = None) -> tuple:
    """返回当前所属"开盘时段"的标识与开盘时间点。

    每个交易时段（上午/下午/夜盘）独立，新时段会覆盖旧区间。

    Returns:
        (session_id, session_start_dt, label)
        - session_id: 唯一标识，如 "2026-07-31-上午" / "2026-07-31-下午" / "2026-07-30-夜盘"
        - session_start_dt: 该时段开盘时刻（datetime）
        - label: "上午" / "下午" / "夜盘" / None
        休市或非该品种交易时段返回 (None, None, None)。
    """
    if now is None:
        now = datetime.now()
    t = now.time()
    weekday = now.weekday()

    # ===== 中金所品种：无夜盘，交易时段不同 =====
    if _is_cffex(code):
        if weekday >= 5:
            return (None, None, None)
        prefix = _get_prefix(code)
        if prefix in CFFEX_BOND_PREFIXES:
            # 国债期货: 09:15-11:30, 13:00-15:15
            if dt_time(9, 15) <= t <= dt_time(11, 30):
                start = datetime.combine(now.date(), dt_time(9, 15))
                return (f"{now.date()}-上午", start, "上午")
            if dt_time(11, 30) < t < dt_time(13, 0):
                start = datetime.combine(now.date(), dt_time(9, 15))
                return (f"{now.date()}-上午", start, "上午")
            if dt_time(13, 0) <= t <= dt_time(15, 15):
                start = datetime.combine(now.date(), dt_time(13, 0))
                return (f"{now.date()}-下午", start, "下午")
        else:
            # 股指期货: 09:30-11:30, 13:00-15:00
            if dt_time(9, 30) <= t <= dt_time(11, 30):
                start = datetime.combine(now.date(), dt_time(9, 30))
                return (f"{now.date()}-上午", start, "上午")
            if dt_time(11, 30) < t < dt_time(13, 0):
                start = datetime.combine(now.date(), dt_time(9, 30))
                return (f"{now.date()}-上午", start, "上午")
            if dt_time(13, 0) <= t <= dt_time(15, 0):
                start = datetime.combine(now.date(), dt_time(13, 0))
                return (f"{now.date()}-下午", start, "下午")
        return (None, None, None)

    # 周末
    if weekday == 5:
        # 周六凌晨：夜盘延续（仅限凌晨收盘品种）
        if t <= dt_time(2, 30):
            night_end = _night_end_time(code)
            if night_end and night_end <= dt_time(2, 30) and t <= night_end:
                yesterday = now - timedelta(days=1)
                start = datetime.combine(yesterday.date(), dt_time(21, 0))
                return (f"{yesterday.date()}-夜盘", start, "夜盘")
        return (None, None, None)
    if weekday == 6:
        return (None, None, None)

    # 上午时段: 09:00-11:30
    if dt_time(9, 0) <= t <= dt_time(11, 30):
        start = datetime.combine(now.date(), dt_time(9, 0))
        return (f"{now.date()}-上午", start, "上午")

    # 午休时段: 11:30-13:30 → 返回上午的 session_id（不重算）
    if dt_time(11, 30) < t < dt_time(13, 30):
        start = datetime.combine(now.date(), dt_time(9, 0))
        return (f"{now.date()}-上午", start, "上午")

    # 下午时段: 13:30-15:00
    if dt_time(13, 30) <= t <= dt_time(15, 0):
        start = datetime.combine(now.date(), dt_time(13, 30))
        return (f"{now.date()}-下午", start, "下午")

    # 夜盘时段: 21:00 起
    if t >= NIGHT_START and _has_night_session(code):
        # 23:00 收盘品种超过 23:00 即休市，不返回 session（避免非交易时段错误计算）
        night_end = _night_end_time(code)
        if night_end == dt_time(23, 0) and t > night_end:
            return (None, None, None)
        start = datetime.combine(now.date(), dt_time(21, 0))
        return (f"{now.date()}-夜盘", start, "夜盘")

    # 夜盘凌晨延续: 00:00-02:30（周一凌晨除外，周日无夜盘）
    if t <= dt_time(2, 30) and weekday >= 1 and _has_night_session(code):
        night_end = _night_end_time(code)
        if night_end and night_end <= dt_time(2, 30) and t <= night_end:
            yesterday = now - timedelta(days=1)
            start = datetime.combine(yesterday.date(), dt_time(21, 0))
            return (f"{yesterday.date()}-夜盘", start, "夜盘")

    return (None, None, None)
