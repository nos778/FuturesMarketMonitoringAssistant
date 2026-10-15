"""主窗口 — 监控列表、工具栏、状态栏、系统托盘、闪烁高亮。
整合 data_source / monitor_engine / notifier / config_store / ui_dialogs。
"""
import logging
import os
import sys
from datetime import datetime

from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt5.QtGui import QIcon, QColor, QFont, QBrush, QPixmap
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QToolBar, QLabel, QStatusBar,
    QSystemTrayIcon, QMenu, QApplication, QMessageBox, QAbstractItemView,
    QPushButton, QFrame, QCheckBox
)

from config_store import ConfigStore
from data_source import SinaDataSource
from monitor_engine import MonitorEngine
from notifier import Notifier, AlertInfo
from ui_dialogs import AddSymbolDialog, RuleDialog, SettingsDialog, KlineDiagDialog
from symbols_db import get_symbol_dict
from trading_hours import session_label

logger = logging.getLogger(__name__)

# 列定义
COL_NAME = 0
COL_CODE = 1
COL_PRICE = 2
COL_CHANGE = 3
COL_CHG_PCT = 4
COL_STATUS = 5
COL_RANGE = 6
COL_AMPLITUDE = 7
COL_NOTE = 8
COL_COUNT = 9

HEADERS = ["品种", "代码", "最新价", "涨跌", "涨跌幅", "状态", "监控区间", "振幅", "备注"]

# 颜色（中国习惯：红涨绿跌）
COLOR_UP = QColor(220, 38, 38)        # 红
COLOR_DOWN = QColor(22, 163, 74)       # 绿
COLOR_FLAT = QColor(100, 116, 139)     # 灰
COLOR_FLASH = QColor(254, 240, 138)    # 闪烁黄底
COLOR_FLASH_ALERT = QColor(252, 165, 165)  # 闪烁红底
COLOR_STATUS_OK = QColor(22, 163, 74)
COLOR_STATUS_WARN = QColor(234, 88, 12)
COLOR_STATUS_OFF = QColor(148, 163, 184)
COLOR_PINNED_BG = QColor(239, 246, 255)       # 浅蓝背景 — 置顶合约
COLOR_PINNED_NAME = QColor(37, 99, 235)       # 蓝色文字 — 置顶合约品种名

# 数据库路径
DB_DIR = os.path.join(os.path.expanduser("~"), ".tdx_futures_monitor")
DB_PATH = os.path.join(DB_DIR, "config.db")


class PriceTableWidgetItem(QTableWidgetItem):
    """支持按数值排序的表格项"""
    def __init__(self, text="", value=0.0):
        super().__init__(text)
        self._value = value
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, PriceTableWidgetItem):
            return self._value < other._value
        return super().__lt__(other)


class MainWindow(QMainWindow):
    """期货盯盘助手主窗口"""

    def __init__(self):
        super().__init__()
        self._closing = False
        self._first_shown = True

        # ---- 核心组件初始化 ----
        self.store = ConfigStore(DB_PATH)
        self.settings = self.store.get_settings()
        self.data_source = SinaDataSource(timeout=8)
        self.notifier = Notifier(self.settings)
        self.notifier.set_flash_callback(self._flash_row)
        self.engine = MonitorEngine(self.store, self.notifier, self.data_source)

        # ---- UI 构建 ----
        self._init_window()
        self._init_table()
        self._init_toolbar()
        self._init_statusbar()
        self._init_tray()
        self._connect_signals()

        # ---- 闪烁管理 ----
        self._flash_timers = {}  # code -> QTimer

        # ---- 加载数据 ----
        self._load_symbols()

        # 记录窗口位置和大小，便于诊断
        geo = self.geometry()
        logger.info("窗口位置: x=%d y=%d w=%d h=%d, 品种数=%d",
                    geo.x(), geo.y(), geo.width(), geo.height(),
                    self.table.rowCount())

        # ---- 自动启动 ----
        if self.settings.get("auto_start", "1") == "1":
            QTimer.singleShot(800, self._start_engine)

    # ==================== UI 构建 ====================

    def _init_window(self):
        self.setWindowTitle("期货盯盘助手")
        self.setMinimumSize(960, 560)
        self.resize(1080, 640)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶栏
        topbar = self._build_topbar()
        layout.addWidget(topbar)

        # 表格
        self.table = QTableWidget()
        layout.addWidget(self.table, 1)

    def _build_topbar(self):
        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(8)

        title = QLabel("期货盯盘助手")
        title.setObjectName("apptitle")
        lay.addWidget(title)
        lay.addStretch()

        self.btn_start = QPushButton("启动监控")
        self.btn_start.setObjectName("btnPrimary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self._start_engine)
        lay.addWidget(self.btn_start)

        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setObjectName("btnGhost")
        self.btn_pause.setCursor(Qt.PointingHandCursor)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._pause_engine)
        lay.addWidget(self.btn_pause)

        self.btn_add = QPushButton("+ 添加品种")
        self.btn_add.setObjectName("btnAdd")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_symbol)
        lay.addWidget(self.btn_add)

        self.btn_pin = QPushButton("置顶")
        self.btn_pin.setObjectName("btnGhost")
        self.btn_pin.setCursor(Qt.PointingHandCursor)
        self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("点击置顶窗口，再次点击取消")
        self.btn_pin.clicked.connect(self._toggle_pin_top)
        lay.addWidget(self.btn_pin)

        self.btn_settings = QPushButton("设置")
        self.btn_settings.setObjectName("btnGhost")
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.clicked.connect(self._open_settings)
        lay.addWidget(self.btn_settings)

        return bar

    def _init_table(self):
        self.table.setColumnCount(COL_COUNT)
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(COL_NAME, QHeaderView.Fixed)
        header.resizeSection(COL_NAME, 100)
        header.setSectionResizeMode(COL_CODE, QHeaderView.Fixed)
        header.resizeSection(COL_CODE, 70)
        header.setSectionResizeMode(COL_PRICE, QHeaderView.Fixed)
        header.resizeSection(COL_PRICE, 90)
        header.setSectionResizeMode(COL_CHANGE, QHeaderView.Fixed)
        header.resizeSection(COL_CHANGE, 80)
        header.setSectionResizeMode(COL_CHG_PCT, QHeaderView.Fixed)
        header.resizeSection(COL_CHG_PCT, 80)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        header.resizeSection(COL_STATUS, 80)
        header.setSectionResizeMode(COL_RANGE, QHeaderView.Fixed)
        header.resizeSection(COL_RANGE, 160)
        header.setSectionResizeMode(COL_AMPLITUDE, QHeaderView.Fixed)
        header.resizeSection(COL_AMPLITUDE, 70)

        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._on_row_double_clicked)

    def _init_toolbar(self):
        pass  # 使用顶栏按钮代替传统工具栏

    def _init_statusbar(self):
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)

        self.lbl_engine = QLabel("● 监控未启动")
        self.lbl_engine.setStyleSheet("color:#94a3b8; font-weight:bold; padding:0 8px;")
        sb.addWidget(self.lbl_engine)

        self.lbl_conn = QLabel("行情: 未知")
        self.lbl_conn.setStyleSheet("color:#94a3b8; padding:0 8px;")
        sb.addWidget(self.lbl_conn)

        self.lbl_count = QLabel("监控 0 个品种")
        self.lbl_count.setStyleSheet("color:#64748b; padding:0 8px;")
        sb.addPermanentWidget(self.lbl_count)

        self.lbl_update = QLabel("--:--:--")
        self.lbl_update.setStyleSheet("color:#64748b; padding:0 8px;")
        sb.addPermanentWidget(self.lbl_update)

        self.setStatusBar(sb)

    def _init_tray(self):
        # 创建一个简单的图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(37, 99, 235))
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray_icon.setToolTip("期货盯盘助手")
        self.tray_icon.activated.connect(self._on_tray_activated)

        menu = QMenu()
        act_show = menu.addAction("显示主窗口")
        act_show.triggered.connect(self._show_window)
        act_start = menu.addAction("启动监控")
        act_start.triggered.connect(self._start_engine)
        act_pause = menu.addAction("暂停监控")
        act_pause.triggered.connect(self._pause_engine)
        menu.addSeparator()
        act_quit = menu.addAction("退出")
        act_quit.triggered.connect(self._quit_app)
        self.tray_menu = menu

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        self.notifier.set_tray(self.tray_icon)

    # ==================== 信号连接 ====================

    def _connect_signals(self):
        self.engine.quote_updated.connect(self._on_quote_updated)
        self.engine.alert_triggered.connect(self._on_alert)
        self.engine.status_changed.connect(self._on_status_changed)
        self.engine.engine_status.connect(self._on_engine_status)
        self.engine.tick_done.connect(self._on_tick_done)

    # ==================== 数据加载 ====================

    def _load_symbols(self):
        try:
            # 诊断：记录数据库路径和文件状态
            import os
            db_exists = os.path.exists(DB_PATH)
            db_size = os.path.getsize(DB_PATH) if db_exists else 0
            logger.info("数据库路径: %s, 存在=%s, 大小=%d", DB_PATH, db_exists, db_size)

            symbols = self.store.get_symbols()
            logger.info("加载数据库品种: %d 个 — %s", len(symbols), [s.code for s in symbols])

            if len(symbols) == 0:
                # 额外诊断：直接用SQL查询确认
                import sqlite3
                conn = sqlite3.connect(DB_PATH)
                count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
                all_rows = conn.execute("SELECT code,name FROM symbols").fetchall()
                logger.warning("数据库symbols表实际有 %d 行: %s", count, all_rows)
                conn.close()
        except Exception as e:
            logger.error("加载数据库品种失败: %s", e, exc_info=True)
            symbols = []
        self.table.setRowCount(len(symbols))
        sym_info = get_symbol_dict()
        for row, s in enumerate(symbols):
            info = sym_info.get(s.code, {})
            name = s.name or info.get("name", s.code)
            exchange = s.exchange or info.get("exchange", "")
            is_pinned = self.store.is_symbol_pinned(s.code)

            # 品种名（置顶合约加📌图标、蓝色加粗）
            display_name = f"📌 {name}" if is_pinned else name
            item_name = QTableWidgetItem(display_name)
            item_name.setData(Qt.UserRole, s.code)
            if is_pinned:
                item_name.setFont(QFont("Segoe UI", 9, QFont.Bold))
                item_name.setForeground(COLOR_PINNED_NAME)
            self.table.setItem(row, COL_NAME, item_name)

            # 代码（置顶合约加粗）
            item_code = QTableWidgetItem(s.code)
            item_code.setForeground(QColor(100, 116, 139) if not is_pinned else COLOR_PINNED_NAME)
            item_code.setTextAlignment(Qt.AlignCenter)
            if is_pinned:
                item_code.setFont(QFont("Segoe UI", 9, QFont.Bold))
            self.table.setItem(row, COL_CODE, item_code)

            # 价格占位
            item_price = PriceTableWidgetItem("--", 0)
            self.table.setItem(row, COL_PRICE, item_price)

            # 涨跌占位
            item_chg = PriceTableWidgetItem("--", 0)
            self.table.setItem(row, COL_CHANGE, item_chg)

            # 涨跌幅占位
            item_pct = PriceTableWidgetItem("--", 0)
            self.table.setItem(row, COL_CHG_PCT, item_pct)

            # 状态
            rule = self.store.get_rule_by_code(s.code)
            if not s.enabled:
                status_text = "已禁用"
                color = COLOR_STATUS_OFF
            elif not rule or not rule.enabled:
                status_text = "未配置"
                color = COLOR_STATUS_WARN
            else:
                status_text = "待启动"
                color = COLOR_STATUS_OFF
            item_st = QTableWidgetItem(status_text)
            item_st.setForeground(color)
            item_st.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, COL_STATUS, item_st)

            # 区间
            if rule and rule.lo > 0 and rule.hi > 0:
                if rule.mode == "auto_kline":
                    range_text = f"⚡{rule.lo:g}~{rule.hi:g}"
                    range_color = QColor(124, 58, 237)  # 紫色标识自动模式
                else:
                    range_text = f"{rule.lo:g} ~ {rule.hi:g}"
                    range_color = QColor(71, 85, 105)
            else:
                range_text = "—"
                range_color = QColor(148, 163, 184)
            item_range = QTableWidgetItem(range_text)
            item_range.setTextAlignment(Qt.AlignCenter)
            item_range.setForeground(range_color)
            self.table.setItem(row, COL_RANGE, item_range)

            # 振幅 = (区间上限 - 区间下限) / 区间下限 * 100%
            # 自动模式（K线极值）与手动输入上下限均自动计算振幅
            if rule and rule.lo > 0 and rule.hi > 0:
                amplitude = (rule.hi - rule.lo) / rule.lo * 100
                amp_text = f"{amplitude:.2f}%"
                # 振幅越大颜色越深
                if amplitude >= 3.0:
                    amp_color = QColor(220, 38, 38)     # 红色 — 大振幅
                elif amplitude >= 1.0:
                    amp_color = QColor(234, 88, 12)     # 橙色 — 中等振幅
                else:
                    amp_color = QColor(124, 58, 237)    # 紫色 — 小振幅（与自动模式标识同色）
            else:
                amp_text = "—"
                amp_color = QColor(148, 163, 184)
            item_amp = QTableWidgetItem(amp_text)
            item_amp.setTextAlignment(Qt.AlignCenter)
            item_amp.setForeground(amp_color)
            self.table.setItem(row, COL_AMPLITUDE, item_amp)

            # 备注
            note = rule.note if rule else ""
            item_note = QTableWidgetItem(note)
            item_note.setForeground(QColor(148, 163, 184))
            self.table.setItem(row, COL_NOTE, item_note)

            # 置顶合约整行浅蓝背景
            if is_pinned:
                for col in range(COL_COUNT):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(QBrush(COLOR_PINNED_BG))

        self.lbl_count.setText(f"监控 {len(symbols)} 个品种")

        # 验证表格内容已正确设置
        if self.table.rowCount() > 0:
            item_name = self.table.item(0, COL_NAME)
            item_code = self.table.item(0, COL_CODE)
            logger.info("表格验证: 行数=%d, 第1行品种=%s, 代码=%s",
                        self.table.rowCount(),
                        item_name.text() if item_name else "None",
                        item_code.text() if item_code else "None")
        else:
            logger.warning("表格行数为0，无数据可显示")

        # 强制刷新表格渲染
        self.table.viewport().update()
        self.table.repaint()

    # ==================== 引擎控制 ====================

    def _start_engine(self):
        if self.engine.isRunning():
            return
        self.engine.reload_config()
        self.engine.start()
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_pause.setText("暂停")
        self.lbl_engine.setText("● 监控启动中…")
        self.lbl_engine.setStyleSheet("color:#f59e0b; font-weight:bold; padding:0 8px;")

    def _pause_engine(self):
        if not self.engine.isRunning():
            return
        if self.engine._paused:
            self.engine.pause(False)
            self.btn_pause.setText("暂停")
        else:
            self.engine.pause(True)
            self.btn_pause.setText("恢复")

    # ==================== 信号处理 ====================

    def _on_quote_updated(self, quotes):
        """行情更新 — 刷新表格价格"""
        code_to_row = {}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item:
                code_to_row[item.data(Qt.UserRole)] = row

        for code, q in quotes.items():
            row = code_to_row.get(code)
            if row is None:
                continue

            # 最新价
            item_price = self.table.item(row, COL_PRICE)
            if item_price:
                item_price.setText(f"{q.price:.2f}")
                item_price._value = q.price
                item_price.setFont(QFont("Segoe UI", 10, QFont.Bold))
                color = COLOR_UP if q.change > 0 else (COLOR_DOWN if q.change < 0 else COLOR_FLAT)
                item_price.setForeground(color)

            # 涨跌额
            item_chg = self.table.item(row, COL_CHANGE)
            if item_chg:
                sign = "+" if q.change > 0 else ""
                item_chg.setText(f"{sign}{q.change:.2f}")
                item_chg._value = q.change
                color = COLOR_UP if q.change > 0 else (COLOR_DOWN if q.change < 0 else COLOR_FLAT)
                item_chg.setForeground(color)

            # 涨跌幅
            item_pct = self.table.item(row, COL_CHG_PCT)
            if item_pct:
                sign = "+" if q.change_pct > 0 else ""
                item_pct.setText(f"{sign}{q.change_pct:.2f}%")
                item_pct._value = q.change_pct
                color = COLOR_UP if q.change_pct > 0 else (COLOR_DOWN if q.change_pct < 0 else COLOR_FLAT)
                item_pct.setForeground(color)

        now = datetime.now().strftime("%H:%M:%S")
        self.lbl_update.setText(f"更新 {now}")

    def _on_alert(self, alert: AlertInfo):
        """触发提醒"""
        logger.info("提醒触发: %s %s @%.2f", alert.code, alert.direction_text, alert.price)
        self.notifier.notify(alert)
        # 闪烁对应行
        self._flash_row(alert.code, alert_type=True)

    def _on_status_changed(self, code, status):
        """品种状态变更"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item and item.data(Qt.UserRole) == code:
                item_st = self.table.item(row, COL_STATUS)
                if item_st:
                    item_st.setText(status)
                    if status == "监控中":
                        item_st.setForeground(COLOR_STATUS_OK)
                    elif status in ("触发中", "冷却中"):
                        item_st.setForeground(COLOR_STATUS_WARN)
                    elif status.startswith("等待K线") or status.startswith("区间更新"):
                        item_st.setForeground(QColor(124, 58, 237))  # 紫色
                    elif status.startswith("休市"):
                        item_st.setForeground(COLOR_STATUS_OFF)
                    elif status == "已暂停":
                        item_st.setForeground(COLOR_STATUS_OFF)
                    else:
                        item_st.setForeground(COLOR_STATUS_OFF)
                # 区间更新时同步刷新区间列和振幅列显示
                if status.startswith("区间更新"):
                    item_range = self.table.item(row, COL_RANGE)
                    if item_range:
                        rule = self.engine.get_rule_state(code)
                        if rule and rule.lo > 0 and rule.hi > 0:
                            item_range.setText(f"⚡{rule.lo:g}~{rule.hi:g}")
                            item_range.setForeground(QColor(124, 58, 237))
                    # 同步刷新振幅列
                    item_amp = self.table.item(row, COL_AMPLITUDE)
                    if item_amp and rule and rule.lo > 0 and rule.hi > 0:
                        amplitude = (rule.hi - rule.lo) / rule.lo * 100
                        item_amp.setText(f"{amplitude:.2f}%")
                        if amplitude >= 3.0:
                            item_amp.setForeground(QColor(220, 38, 38))
                        elif amplitude >= 1.0:
                            item_amp.setForeground(QColor(234, 88, 12))
                        else:
                            item_amp.setForeground(QColor(124, 58, 237))
                break

    def _on_engine_status(self, msg, ok):
        """引擎状态变更"""
        if ok:
            self.lbl_engine.setText(f"● {msg}")
            self.lbl_engine.setStyleSheet("color:#16a34a; font-weight:bold; padding:0 8px;")
            self.lbl_conn.setText(f"行情: {msg}")
            self.lbl_conn.setStyleSheet("color:#16a34a; padding:0 8px;")
        else:
            self.lbl_engine.setText(f"● {msg}")
            self.lbl_engine.setStyleSheet("color:#dc2626; font-weight:bold; padding:0 8px;")
            self.lbl_conn.setText(f"行情: {msg}")
            self.lbl_conn.setStyleSheet("color:#dc2626; padding:0 8px;")

    def _on_tick_done(self, count):
        """单轮取数完成"""
        pass  # 更新时间已在 quote_updated 中处理

    # ==================== 闪烁高亮 ====================

    def _flash_row(self, code, alert_type=False):
        """闪烁指定品种的行"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item and item.data(Qt.UserRole) == code:
                target_row = row
                break
        else:
            return

        # 停止旧定时器
        old_timer = self._flash_timers.get(code)
        if old_timer:
            old_timer.stop()

        flash_color = COLOR_FLASH_ALERT if alert_type else COLOR_FLASH
        # 闪烁结束后恢复到置顶背景色（若该合约已置顶），否则白色
        name_item = self.table.item(target_row, COL_NAME)
        restore_color = COLOR_PINNED_BG if (name_item and name_item.text().startswith("📌")) else QColor(255, 255, 255)
        steps = [flash_color, restore_color] * 3 + [None]
        step_idx = [0]

        def toggle():
            idx = step_idx[0]
            if idx >= len(steps):
                timer.stop()
                self._flash_timers.pop(code, None)
                return
            color = steps[idx]
            if color is None:
                timer.stop()
                self._flash_timers.pop(code, None)
                return
            for col in range(COL_COUNT):
                item = self.table.item(target_row, col)
                if item:
                    item.setBackground(QBrush(color))
            step_idx[0] += 1

        timer = QTimer()
        timer.timeout.connect(toggle)
        timer.start(400)
        self._flash_timers[code] = timer

    # ==================== 弹窗操作 ====================

    def _add_symbol(self):
        existing = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, COL_NAME)
            if item:
                existing.append(item.data(Qt.UserRole))
        dlg = AddSymbolDialog(existing, self)
        dlg.symbols_added.connect(self._on_symbols_added)
        dlg.exec_()

    def _on_symbols_added(self, picked):
        logger.info("保存 %d 个合约到数据库: %s", len(picked), picked)
        for code, name, exchange in picked:
            self.store.add_symbol(code, name, exchange)
        # 验证保存结果
        saved = self.store.get_symbols()
        logger.info("数据库现有 %d 个合约: %s", len(saved), [s.code for s in saved])
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    def _open_settings(self):
        dlg = SettingsDialog(self.store, self)
        dlg.settings_saved.connect(self._on_settings_saved)
        dlg.exec_()

    def _toggle_pin_top(self):
        """切换窗口置顶状态"""
        pinned = self.btn_pin.isChecked()
        if pinned:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.btn_pin.setText("取消置顶")
            self.btn_pin.setStyleSheet(
                "QPushButton{color:#2563eb; border:1px solid #2563eb; border-radius:6px; background:#eff6ff; font-weight:600;}"
            )
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.btn_pin.setText("置顶")
            self.btn_pin.setStyleSheet("")
        self.show()

    def _on_settings_saved(self, new_settings):
        self.settings = self.store.get_settings()
        self.notifier.settings = self.settings

    # ==================== 右键菜单 ====================

    def _show_context_menu(self, pos):
        row = self.table.indexAt(pos).row()
        if row < 0:
            return
        item = self.table.item(row, COL_NAME)
        if not item:
            return
        code = item.data(Qt.UserRole)
        name = item.text()

        menu = QMenu(self)
        act_rule = menu.addAction("配置监控规则")
        act_rule.triggered.connect(lambda: self._edit_rule(code, name))
        act_diag = menu.addAction("区间诊断（K线明细）")
        act_diag.triggered.connect(lambda: self._show_kline_diag(code, name))
        menu.addSeparator()

        # 置顶/取消置顶
        if self.store.is_symbol_pinned(code):
            act_unpin = menu.addAction("取消置顶")
            act_unpin.triggered.connect(lambda: self._unpin_symbol(code))
        else:
            act_pin = menu.addAction("置顶合约")
            act_pin.triggered.connect(lambda: self._pin_symbol(code))
        menu.addSeparator()

        sym = None
        for s in self.store.get_symbols():
            if s.code == code:
                sym = s
                break
        if sym:
            if sym.enabled:
                act_disable = menu.addAction("禁用此品种")
                act_disable.triggered.connect(lambda: self._toggle_symbol(code, False))
            else:
                act_enable = menu.addAction("启用此品种")
                act_enable.triggered.connect(lambda: self._toggle_symbol(code, True))
            menu.addSeparator()
            act_remove = menu.addAction("移除品种")
            act_remove.triggered.connect(lambda: self._remove_symbol(code))
            menu.addSeparator()
            act_test = menu.addAction("测试提醒（模拟触发）")
            act_test.triggered.connect(lambda: self._test_alert(code))

        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _edit_rule(self, code, name):
        dlg = RuleDialog(code, name, self.store, self)
        dlg.rule_saved.connect(self._on_rule_saved)
        dlg.exec_()

    def _show_kline_diag(self, code, name):
        """打开区间诊断窗口，展示自动区间计算使用的K线明细"""
        dlg = KlineDiagDialog(code, name, self.store, self.engine, self)
        dlg.exec_()

    def _on_rule_saved(self, code):
        # 刷新区间和状态显示
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    def _toggle_symbol(self, code, enabled):
        logger.info("品种状态变更: %s enabled=%s", code, enabled)
        self.store.update_symbol_enabled(code, enabled)
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    def _pin_symbol(self, code):
        """置顶合约到列表顶部"""
        logger.info("置顶合约: %s", code)
        self.store.pin_symbol(code)
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    def _unpin_symbol(self, code):
        """取消置顶，移到列表末尾"""
        logger.info("取消置顶: %s", code)
        self.store.unpin_symbol(code)
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    def _remove_symbol(self, code):
        reply = QMessageBox.question(
            self, "确认移除",
            f"确定要移除品种 {code} 及其监控规则吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            logger.info("用户确认移除品种: %s", code)
            self.store.remove_symbol(code)
            self._load_symbols()
            if self.engine.isRunning():
                self.engine.reload_config()

    def _test_alert(self, code):
        """模拟触发一条提醒（测试通知链路）"""
        self.engine.force_trigger(code, "enter")

    # ==================== 双击编辑规则 ====================

    def _on_row_double_clicked(self, index):
        row = index.row()
        item = self.table.item(row, COL_NAME)
        if not item:
            return
        code = item.data(Qt.UserRole)
        name = item.text()
        self._edit_rule(code, name)

    # ==================== 系统托盘 ====================

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        # 窗口从托盘恢复时重新加载数据
        self._load_symbols()
        if self.engine.isRunning():
            self.engine.reload_config()

    # ==================== 窗口事件 ====================

    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 不在这里重新加载数据，避免重复触发导致表格闪烁或数据丢失
        # 数据已在 __init__ 中加载完毕

    def closeEvent(self, event):
        """关闭时最小化到托盘"""
        if not self._closing and self.tray_icon.isVisible():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "期货盯盘助手",
                "程序已最小化到系统托盘，双击图标可恢复窗口。",
                QSystemTrayIcon.Information,
                3000
            )
        else:
            self._shutdown()
            event.accept()

    def _quit_app(self):
        self._closing = True
        self._shutdown()
        QApplication.quit()

    def _shutdown(self):
        """清理资源"""
        if self.engine.isRunning():
            self.engine.stop()
        self.tray_icon.hide()

    # ==================== 退出确认 ====================

    def _on_tray_quit(self):
        self._quit_app()
