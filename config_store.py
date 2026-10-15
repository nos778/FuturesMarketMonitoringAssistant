"""配置持久化 — SQLite 存储品种列表、监控规则、全局设置。
首次启动自动建表并写入默认设置。
"""
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认设置
DEFAULT_SETTINGS = {
    "push_token": "",           # PushPlus / Server酱 Token
    "push_channel": "pushplus", # pushplus | serverchan
    "refresh_interval": "3",    # 秒
    "auto_start": "1",          # 开机自启
    "trading_hours_filter": "1",# 按交易时段过滤
    "sound_enabled": "1",       # 声音提醒
    "sound_type": "default",    # default | ring1 | ring2 | custom | none
    "custom_sound_path": "",    # 自定义提示音 wav 文件路径
    "popup_enabled": "1",       # 弹窗提醒
    "popup_duration": "10",     # 弹窗停留秒数
    "flash_enabled": "1",       # 闪烁高亮
    "data_source": "sina",      # sina | pytdx
}


@dataclass
class MonitoredSymbol:
    """被监控的品种"""
    code: str
    name: str = ""
    exchange: str = ""
    group: str = "全部"
    enabled: bool = True
    sort_order: int = 0


@dataclass
class MonitorRule:
    """监控规则"""
    id: int = 0
    code: str = ""
    lo: float = 0.0       # 区间下限
    hi: float = 0.0       # 区间上限
    direction: str = "both"  # enter | leave | both
    cooldown: int = 15    # 冷却分钟
    enabled: bool = True
    note: str = ""
    # ===== K线自动区间 =====
    mode: str = "manual"            # manual | auto_kline
    kline_count: int = 30           # K线根数
    kline_period: int = 1           # K线周期(分钟): 1/5/10/15/30/60
    last_auto_session: str = ""     # 已计算过的时段标识，如 "2026-07-31-上午"
    # 运行时状态（不持久化，但存在内存中）
    pos_state: str = "-"          # in | above | below | -
    last_trig_enter_ts: float = 0.0
    last_trig_leave_ts: float = 0.0


class ConfigStore:
    """SQLite 配置存储"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._conn() as conn:
            # 将上一个进程可能残留的 WAL 数据写回主数据库文件
            # 防止进程被强杀后 WAL 数据未 checkpoint 导致读取不到
            try:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception as e:
                logger.warning("WAL checkpoint 失败: %s", e)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS symbols (
                    code TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    exchange TEXT NOT NULL DEFAULT '',
                    grp TEXT NOT NULL DEFAULT '全部',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    lo REAL NOT NULL DEFAULT 0,
                    hi REAL NOT NULL DEFAULT 0,
                    direction TEXT NOT NULL DEFAULT 'both',
                    cooldown INTEGER NOT NULL DEFAULT 15,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    note TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'manual',
                    kline_count INTEGER NOT NULL DEFAULT 30,
                    kline_period INTEGER NOT NULL DEFAULT 1,
                    last_auto_session TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            # 写入默认设置
            for k, v in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                    (k, str(v))
                )
            conn.commit()
        # 老库迁移：补齐 rules 表新增列
        self._migrate_rules()

    def _migrate_rules(self):
        """rules 表结构迁移：幂等添加新增列"""
        with self._conn() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(rules)").fetchall()}
            additions = [
                ("mode",             "TEXT NOT NULL DEFAULT 'manual'"),
                ("kline_count",      "INTEGER NOT NULL DEFAULT 30"),
                ("kline_period",     "INTEGER NOT NULL DEFAULT 1"),
                ("last_auto_session", "TEXT NOT NULL DEFAULT ''"),
            ]
            for name, decl in additions:
                if name not in cols:
                    conn.execute(f"ALTER TABLE rules ADD COLUMN {name} {decl}")
            conn.commit()

    # ---- 品种管理 ----
    def get_symbols(self) -> List[MonitoredSymbol]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM symbols ORDER BY sort_order, code"
            ).fetchall()
            return [MonitoredSymbol(
                code=r["code"], name=r["name"], exchange=r["exchange"],
                group=r["grp"], enabled=bool(r["enabled"]),
                sort_order=r["sort_order"]
            ) for r in rows]

    def add_symbol(self, code: str, name: str, exchange: str, group: str = "全部"):
        with self._conn() as conn:
            max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM symbols").fetchone()[0]
            conn.execute(
                "INSERT OR REPLACE INTO symbols(code, name, exchange, grp, enabled, sort_order) "
                "VALUES(?, ?, ?, ?, 1, ?)",
                (code, name, exchange, group, max_order + 1)
            )
            conn.commit()

    def update_symbol_name(self, code: str, name: str):
        """更新品种名称（当从 API 获取到正确名称时调用）"""
        if not name or name == "0.0":
            return
        with self._conn() as conn:
            conn.execute("UPDATE symbols SET name=? WHERE code=?", (name, code))
            conn.commit()

    def remove_symbol(self, code: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM symbols WHERE code=?", (code,))
            conn.execute("DELETE FROM rules WHERE code=?", (code,))
            conn.commit()

    def update_symbol_enabled(self, code: str, enabled: bool):
        with self._conn() as conn:
            conn.execute("UPDATE symbols SET enabled=? WHERE code=?",
                         (1 if enabled else 0, code))
            conn.commit()

    def pin_symbol(self, code: str):
        """将指定合约置顶（sort_order 设为负值，确保排在所有普通合约之前）"""
        with self._conn() as conn:
            min_order = conn.execute(
                "SELECT COALESCE(MIN(sort_order),0) FROM symbols"
            ).fetchone()[0]
            # 确保置顶的 sort_order 一定为负值（小于所有普通合约的 0+）
            new_order = min(min_order - 1, -1)
            conn.execute(
                "UPDATE symbols SET sort_order=? WHERE code=?",
                (new_order, code)
            )
            conn.commit()

    def unpin_symbol(self, code: str):
        """取消置顶（sort_order 设为当前最大值+1，移到末尾）"""
        with self._conn() as conn:
            max_order = conn.execute(
                "SELECT COALESCE(MAX(sort_order),0) FROM symbols"
            ).fetchone()[0]
            conn.execute(
                "UPDATE symbols SET sort_order=? WHERE code=?",
                (max_order + 1, code)
            )
            conn.commit()

    def is_symbol_pinned(self, code: str) -> bool:
        """判断合约是否已置顶（sort_order < 0）"""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT sort_order FROM symbols WHERE code=?", (code,)
            ).fetchone()
            return row is not None and row["sort_order"] < 0

    # ---- 规则管理 ----
    def get_rules(self) -> List[MonitorRule]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM rules").fetchall()
            return [MonitorRule(
                id=r["id"], code=r["code"], lo=r["lo"], hi=r["hi"],
                direction=r["direction"], cooldown=r["cooldown"],
                enabled=bool(r["enabled"]), note=r["note"],
                mode=r["mode"], kline_count=r["kline_count"],
                kline_period=r["kline_period"], last_auto_session=r["last_auto_session"]
            ) for r in rows]

    def get_rule_by_code(self, code: str) -> Optional[MonitorRule]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM rules WHERE code=?", (code,)).fetchone()
            if row:
                return MonitorRule(
                    id=row["id"], code=row["code"], lo=row["lo"], hi=row["hi"],
                    direction=row["direction"], cooldown=row["cooldown"],
                    enabled=bool(row["enabled"]), note=row["note"],
                    mode=row["mode"], kline_count=row["kline_count"],
                    kline_period=row["kline_period"], last_auto_session=row["last_auto_session"]
                )
            return None

    def save_rule(self, rule: MonitorRule):
        with self._conn() as conn:
            if rule.id:
                conn.execute(
                    "UPDATE rules SET code=?, lo=?, hi=?, direction=?, cooldown=?, "
                    "enabled=?, note=?, mode=?, kline_count=?, kline_period=?, last_auto_session=? "
                    "WHERE id=?",
                    (rule.code, rule.lo, rule.hi, rule.direction, rule.cooldown,
                     1 if rule.enabled else 0, rule.note,
                     rule.mode, rule.kline_count, rule.kline_period, rule.last_auto_session,
                     rule.id)
                )
            else:
                conn.execute(
                    "INSERT INTO rules(code, lo, hi, direction, cooldown, enabled, note, "
                    "mode, kline_count, kline_period, last_auto_session) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rule.code, rule.lo, rule.hi, rule.direction, rule.cooldown,
                     1 if rule.enabled else 0, rule.note,
                     rule.mode, rule.kline_count, rule.kline_period, rule.last_auto_session)
                )
            conn.commit()

    def delete_rule(self, rule_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM rules WHERE id=?", (rule_id,))
            conn.commit()

    # ---- 设置管理 ----
    def get_settings(self) -> Dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {r["key"]: r["value"] for r in rows}

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def save_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                (key, str(value))
            )
            conn.commit()

    def save_settings(self, settings: Dict[str, str]):
        with self._conn() as conn:
            for k, v in settings.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)",
                    (k, str(v))
                )
            conn.commit()
