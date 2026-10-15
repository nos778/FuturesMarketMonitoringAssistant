"""UI 弹窗组件 — 添加品种、规则配置、系统设置。"""
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QLabel, QLineEdit,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton, QTabWidget,
    QWidget, QListWidget, QListWidgetItem, QGroupBox, QScrollArea,
    QButtonGroup, QRadioButton, QSlider, QFrame, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar, QFileDialog
)

from symbols_db import SYMBOLS, EXCHANGES, SHORTCUT_VARIETIES, get_by_exchange, search, get_symbol_dict, guess_exchange
from config_store import MonitorRule


class AddSymbolDialog(QDialog):
    """添加监控品种弹窗"""

    symbols_added = pyqtSignal(list)  # [(code, name, exchange), ...]
    # 跨线程信号：子线程查询完成后通过信号通知主线程更新 UI
    contract_query_result = pyqtSignal(bool, str)   # (success, message)
    contracts_browsed = pyqtSignal(list, str)        # (contracts, variety)
    picked_updated = pyqtSignal()                    # 已选品种变化通知
    contract_auto_picked = pyqtSignal(tuple)         # 查询成功后自动选中的合约

    def __init__(self, existing_codes, parent=None):
        super().__init__(parent)
        self.existing_codes = set(existing_codes)
        self.picked = []
        # 连接跨线程信号
        self.contract_query_result.connect(self._show_contract_result)
        self.contracts_browsed.connect(self._show_contracts)
        self.picked_updated.connect(self._update_picked_label)
        self.contract_auto_picked.connect(self._on_contract_auto_picked)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("添加监控品种")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)
        self.resize(680, 460)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._contract_tab(), "具体合约")
        tabs.addTab(self._manual_tab(), "主力连续")
        tabs.addTab(self._exchange_tab(), "交易所筛选")
        layout.addWidget(tabs)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("加入监控")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self._on_ok)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def _contract_tab(self):
        """具体合约输入页 — 支持手动输入 RB2610 等具体月份合约"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        # 说明（精简为单行）
        hint = QLabel("输入合约代码（如 RB2610）或点击下方品种按钮浏览可交易合约")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b; font-size:12px; padding:2px;")
        layout.addWidget(hint)

        # 输入框
        input_row = QHBoxLayout()
        self.contract_input = QLineEdit()
        self.contract_input.setPlaceholderText("合约代码，如 RB2610")
        self.contract_input.returnPressed.connect(self._on_query_contract)
        input_row.addWidget(self.contract_input)

        btn_query = QPushButton("查询")
        btn_query.setObjectName("primary")
        btn_query.clicked.connect(self._on_query_contract)
        input_row.addWidget(btn_query)

        layout.addLayout(input_row)

        # 查询结果
        self.contract_result_label = QLabel("输入代码查询验证，或点击品种按钮浏览")
        self.contract_result_label.setStyleSheet("color:#64748b; padding:2px; font-size:12px;")
        layout.addWidget(self.contract_result_label)

        # 快捷品种按钮 — 放入可滚动区域，避免撑高窗口
        shortcut_label = QLabel("快捷选择品种（点击查看可交易合约）：")
        shortcut_label.setStyleSheet("color:#475569; font-weight:600; padding-top:4px;")
        layout.addWidget(shortcut_label)

        # 按板块分组
        from collections import OrderedDict
        groups = OrderedDict()
        for code, name, cat in SHORTCUT_VARIETIES:
            groups.setdefault(cat, []).append((code, name))

        # 板块颜色
        cat_colors = {
            "黑色系": "#475569", "贵金属": "#b45309", "有色金属": "#1d4ed8",
            "能源": "#ea580c", "化工": "#0d9488", "农产品": "#9333ea",
            "新能源材料": "#059669", "林产品": "#92400e",
        }
        # 板块背景色（浅色）
        cat_bg_colors = {
            "黑色系": "#f1f5f9", "贵金属": "#fef3c7", "有色金属": "#dbeafe",
            "能源": "#ffedd5", "化工": "#ccfbf1", "农产品": "#f3e8ff",
            "新能源材料": "#d1fae5", "林产品": "#fef3c7",
        }

        # 用 QWidget 容器装载网格，再放进 QScrollArea
        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)
        cols_per_row = 10
        row = 0

        for cat, items in groups.items():
            color = cat_colors.get(cat, "#475569")
            bg_color = cat_bg_colors.get(cat, "#f8fafc")

            # 板块标签行（跨整行）
            cat_label = QLabel(f"【{cat}】")
            cat_label.setStyleSheet(
                f"color:{color}; font-size:11px; font-weight:600; padding:1px 0px;"
            )
            grid.addWidget(cat_label, row, 0, 1, cols_per_row)
            row += 1

            # 品种按钮（紧凑化）
            for i, (code, name) in enumerate(items):
                r = row + i // cols_per_row
                c = i % cols_per_row
                btn = QPushButton(f"{name}\n{code}")
                btn.setFixedSize(58, 34)
                btn.setToolTip(f"{name} ({code}) — {cat}板块\n点击查询 {code} 系列所有可交易合约")
                btn.setStyleSheet(f"""
                    QPushButton {{
                        text-align: center;
                        font-size: 9px;
                        color: {color};
                        border: 1px solid #cbd5e1;
                        border-radius: 4px;
                        background: {bg_color};
                        padding: 0px;
                    }}
                    QPushButton:hover {{
                        background: #e0f2fe;
                        border-color: #3b82f6;
                        color: #1e40af;
                    }}
                    QPushButton:pressed {{
                        background: #bae6fd;
                    }}
                """)
                btn.clicked.connect(lambda checked, v=code: self._browse_contracts(v))
                grid.addWidget(btn, r, c)

            # 计算下一板块的起始行
            rows_used = (len(items) + cols_per_row - 1) // cols_per_row
            row += rows_used

        # 把网格放进滚动区域，限制最大高度
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_container)
        scroll.setMaximumHeight(140)
        scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll)

        # 合约浏览表格
        self.contracts_table = QTableWidget()
        self.contracts_table.setColumnCount(6)
        self.contracts_table.setHorizontalHeaderLabels(["代码", "名称", "现价", "成交量", "持仓", "操作"])
        self.contracts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.contracts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.contracts_table.verticalHeader().setVisible(False)
        self.contracts_table.setColumnWidth(0, 100)
        self.contracts_table.setColumnWidth(1, 120)
        self.contracts_table.setColumnWidth(2, 80)
        self.contracts_table.setColumnWidth(3, 90)
        self.contracts_table.setColumnWidth(4, 90)
        self.contracts_table.setColumnWidth(5, 70)
        layout.addWidget(self.contracts_table, 1)

        self.picked_label = QLabel("已选品种：无")
        self.picked_label.setStyleSheet("font-size:12px; padding:2px;")
        layout.addWidget(self.picked_label)

        return widget

    def _on_query_contract(self):
        """查询用户输入的合约代码"""
        code = self.contract_input.text().strip().upper()
        if not code:
            return

        self.contract_result_label.setText("查询中…")
        self.contract_result_label.setStyleSheet("color:#f59e0b; padding:4px;")

        def do_query():
            from data_source import SinaDataSource
            ds = SinaDataSource(timeout=5)
            try:
                q = ds.fetch_single(code)
                if q and q.price > 0:
                    exchange = guess_exchange(code)
                    entry = (code, q.name, exchange)
                    # 通过信号在主线程安全地修改 picked 列表
                    self.contract_auto_picked.emit(entry)
                    result_text = f"✓ {q.name}({code})  现价={q.price:.2f}  昨结={q.prev_settle:.2f}"
                    self.contract_query_result.emit(True, result_text)
                else:
                    self.contract_query_result.emit(False, f"✗ 合约 {code} 无行情数据（可能不存在或已到期）")
            except Exception as e:
                self.contract_query_result.emit(False, f"✗ 查询失败: {e}")

        threading.Thread(target=do_query, daemon=True).start()

    def _on_contract_auto_picked(self, entry):
        """主线程中安全地将查询到的合约加入 picked 列表"""
        code = entry[0]
        if code in self.existing_codes:
            return
        if entry not in self.picked:
            self.picked.append(entry)
            self._update_picked_label()

    def _show_contract_result(self, success, msg):
        self.contract_result_label.setText(msg)
        self.contract_result_label.setStyleSheet(
            "color:#16a34a; padding:4px;" if success else "color:#dc2626; padding:4px;"
        )

    def _browse_contracts(self, variety):
        """浏览某品种的所有可交易合约"""
        self.contract_result_label.setText(f"查询 {variety} 系列合约中…")
        self.contract_result_label.setStyleSheet("color:#f59e0b; padding:4px;")
        self.contracts_table.setRowCount(0)

        def do_browse():
            from data_source import SinaDataSource
            ds = SinaDataSource(timeout=5)
            try:
                contracts = ds.fetch_contracts(variety)
                self.contracts_browsed.emit(contracts, variety)
            except Exception as e:
                self.contract_query_result.emit(False, f"查询失败: {e}")

        threading.Thread(target=do_browse, daemon=True).start()

    def _show_contracts(self, contracts, variety):
        if not contracts:
            self.contract_result_label.setText(f"未找到 {variety} 系列的可交易合约")
            self.contract_result_label.setStyleSheet("color:#dc2626; padding:4px;")
            return

        self.contracts_table.setRowCount(len(contracts))
        for row, c in enumerate(contracts):
            entry = (c["code"], c["name"], guess_exchange(c["code"]))
            already_picked = entry in self.picked or c["code"] in self.existing_codes

            code_item = QTableWidgetItem(c["code"])
            code_item.setData(Qt.UserRole, entry)
            self.contracts_table.setItem(row, 0, code_item)
            self.contracts_table.setItem(row, 1, QTableWidgetItem(c["name"]))
            price_item = QTableWidgetItem(f"{c['price']:.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.contracts_table.setItem(row, 2, price_item)
            vol_item = QTableWidgetItem(f"{c['volume']:,}")
            vol_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.contracts_table.setItem(row, 3, vol_item)
            oi_item = QTableWidgetItem(f"{c['open_interest']:,}")
            oi_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.contracts_table.setItem(row, 4, oi_item)

            # 操作列：添加按钮
            btn = QPushButton("已添加" if already_picked else "+ 添加")
            btn.setFixedHeight(26)
            btn.setProperty("entry", entry)
            btn.setProperty("row", row)
            if already_picked:
                btn.setEnabled(False)
                btn.setStyleSheet("color:#94a3b8; border:1px solid #e2e8f0; border-radius:4px; background:#f8fafc;")
            else:
                btn.setStyleSheet(
                    "QPushButton{color:#2563eb; border:1px solid #2563eb; border-radius:4px; background:#eff6ff; font-weight:600;}"
                    "QPushButton:hover{background:#dbeafe;}"
                    "QPushButton:pressed{background:#bfdbfe;}"
                )
            btn.clicked.connect(self._on_add_contract_btn)
            self.contracts_table.setCellWidget(row, 5, btn)

            if already_picked:
                self._set_row_highlight(row, True)

        self.contract_result_label.setText(f"找到 {len(contracts)} 个 {variety} 系列合约（点击「+添加」选择具体合约）")
        self.contract_result_label.setStyleSheet("color:#16a34a; padding:4px;")

    def _on_add_contract_btn(self):
        """点击表格行的「添加」按钮：直接选中该具体合约"""
        btn = self.sender()
        if not btn:
            return
        entry = btn.property("entry")
        if not entry:
            return
        code, name, exchange = entry
        if code in self.existing_codes:
            return
        if entry not in self.picked:
            self.picked.append(entry)
            self._update_picked_label()

        # 按钮变为已添加
        btn.setText("已添加")
        btn.setEnabled(False)
        btn.setStyleSheet("color:#94a3b8; border:1px solid #e2e8f0; border-radius:4px; background:#f8fafc;")

        # 高亮该行
        row = btn.property("row")
        if row is not None:
            self._set_row_highlight(row, True)

    def _pick_contract_from_table(self, index):
        """双击备用入口（保留兼容）"""
        self._toggle_pick_from_table(self.contracts_table.item(index.row(), 0))

    def _toggle_pick_from_table(self, item):
        """单击表格行：切换选中状态，已选行高亮"""
        if not item:
            return
        row = item.row()
        code_item = self.contracts_table.item(row, 0)
        if not code_item:
            return
        data = code_item.data(Qt.UserRole)
        if not data:
            return

        # 已存在则取消选中，否则添加
        if data in self.picked:
            self.picked.remove(data)
            self._set_row_highlight(row, False)
        else:
            if data[0] not in self.existing_codes:
                self.picked.append(data)
                self._set_row_highlight(row, True)

        self._update_picked_label()

    def _set_row_highlight(self, row, highlighted):
        """高亮/取消高亮表格行"""
        color = QColor(219, 234, 254) if highlighted else QColor(255, 255, 255)
        for col in range(self.contracts_table.columnCount()):
            cell = self.contracts_table.item(row, col)
            if cell:
                cell.setBackground(QBrush(color))

    def _manual_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入代码或名称，如 螺纹、RB0、黄金")
        self.search_input.textChanged.connect(self._on_search)
        form.addRow("搜索：", self.search_input)
        layout.addLayout(form)

        self.result_list = QListWidget()
        self.result_list.setMaximumHeight(200)
        self.result_list.itemDoubleClicked.connect(self._pick_item)
        layout.addWidget(QLabel("搜索结果（双击添加）："))
        layout.addWidget(self.result_list)

        self.picked_label = QLabel("已选品种：无")
        layout.addWidget(self.picked_label)

        # 初始填充全部
        self._show_results(SYMBOLS)
        return widget

    def _exchange_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vlay = QVBoxLayout(content)

        self.exch_checks = {}
        for exch_code, exch_name in EXCHANGES.items():
            grp = QGroupBox(exch_name)
            glay = QVBoxLayout()
            items = get_by_exchange(exch_code)
            self.exch_checks[exch_code] = []
            for code, name, exch, cat in items:
                cb = QCheckBox(f"{name} ({code})")
                cb.setProperty("code", code)
                cb.setProperty("name", name)
                cb.setProperty("exchange", exch)
                cb.stateChanged.connect(self._on_exch_check)
                glay.addWidget(cb)
                self.exch_checks[exch_code].append(cb)
            grp.setLayout(glay)
            vlay.addWidget(grp)

        vlay.addStretch()
        scroll.setWidget(content)
        return scroll

    def _on_search(self, text):
        results = search(text) if text.strip() else SYMBOLS
        self._show_results(results)

    def _show_results(self, results):
        self.result_list.clear()
        for code, name, exch, cat in results:
            if code in self.existing_codes:
                continue
            item = QListWidgetItem(f"{name}  ({code})  [{exch}]")
            item.setData(Qt.UserRole, (code, name, exch))
            self.result_list.addItem(item)

    def _pick_item(self, item):
        data = item.data(Qt.UserRole)
        if data not in self.picked:
            self.picked.append(data)
            self._update_picked_label()

    def _on_exch_check(self):
        pass  # 实时更新 picked

    def _update_picked_label(self):
        if not self.picked:
            self.picked_label.setText("已选品种：无")
        else:
            names = ", ".join(f"{n}({c})" for c, n, e in self.picked)
            self.picked_label.setText("已选品种：" + names)

    def _on_ok(self):
        # 收集交易所筛选页的勾选
        for exch_code, checks in self.exch_checks.items():
            for cb in checks:
                if cb.isChecked():
                    code = cb.property("code")
                    name = cb.property("name")
                    exch = cb.property("exchange")
                    if code not in self.existing_codes:
                        entry = (code, name, exch)
                        if entry not in self.picked:
                            self.picked.append(entry)
        if not self.picked:
            QMessageBox.information(self, "提示", "请先选择至少一个品种。")
            return
        self.symbols_added.emit(self.picked)
        self.accept()


class RuleDialog(QDialog):
    """监控规则配置弹窗"""

    rule_saved = pyqtSignal(str)  # code
    recalc_done = pyqtSignal(bool, str, float, float)  # (success, message, lo, hi)

    def __init__(self, code, name, store, parent=None):
        super().__init__(parent)
        self.code = code
        self.name = name
        self.store = store
        self.rule = store.get_rule_by_code(code) or MonitorRule(code=code)
        self.recalc_done.connect(self._on_recalc_done)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle(f"监控规则 — {self.name} ({self.code})")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)

        # 当前价格提示
        self.price_label = QLabel(f"当前品种：{self.name} ({self.code})")
        self.price_label.setStyleSheet("font-weight:bold; color:#15487a;")
        layout.addWidget(self.price_label)

        # ===== 区间模式选择 =====
        mode_grp = QGroupBox("区间模式")
        mode_lay = QHBoxLayout()
        self.mode_group = QButtonGroup()
        self.rb_manual = QRadioButton("手动输入")
        self.rb_auto = QRadioButton("K线自动计算")
        self.mode_group.addButton(self.rb_manual, 0)
        self.mode_group.addButton(self.rb_auto, 1)
        if self.rule.mode == "auto_kline":
            self.rb_auto.setChecked(True)
        else:
            self.rb_manual.setChecked(True)
        self.rb_manual.toggled.connect(self._on_mode_changed)
        mode_lay.addWidget(self.rb_manual)
        mode_lay.addWidget(self.rb_auto)
        mode_lay.addStretch()
        mode_grp.setLayout(mode_lay)
        layout.addWidget(mode_grp)

        # ===== 手动区间设定 =====
        self.manual_grp = QGroupBox("价格区间（手动）")
        glay = QHBoxLayout()
        glay.addWidget(QLabel("下限："))
        self.lo_spin = QDoubleSpinBox()
        self.lo_spin.setRange(0, 9999999)
        self.lo_spin.setDecimals(2)
        self.lo_spin.setSingleStep(1.0)
        self.lo_spin.setValue(self.rule.lo if self.rule.lo > 0 else 0)
        glay.addWidget(self.lo_spin)
        glay.addWidget(QLabel("上限："))
        self.hi_spin = QDoubleSpinBox()
        self.hi_spin.setRange(0, 9999999)
        self.hi_spin.setDecimals(2)
        self.hi_spin.setSingleStep(1.0)
        self.hi_spin.setValue(self.rule.hi if self.rule.hi > 0 else 0)
        glay.addWidget(self.hi_spin)
        self.manual_grp.setLayout(glay)
        layout.addWidget(self.manual_grp)

        # ===== K线自动计算面板 =====
        self.auto_grp = QGroupBox("K线自动区间")
        auto_lay = QFormLayout()
        self.kline_count_spin = QSpinBox()
        self.kline_count_spin.setRange(1, 60)
        self.kline_count_spin.setValue(self.rule.kline_count)
        self.kline_count_spin.setSuffix(" 根")
        auto_lay.addRow("K线根数：", self.kline_count_spin)

        self.kline_period_combo = QComboBox()
        for p in [1, 5, 10, 15, 30, 60]:
            self.kline_period_combo.addItem(f"{p} 分钟", p)
        idx = self.kline_period_combo.findData(self.rule.kline_period)
        if idx >= 0:
            self.kline_period_combo.setCurrentIndex(idx)
        auto_lay.addRow("K线周期：", self.kline_period_combo)

        hint_label = QLabel(
            "每个交易时段（上午/下午/夜盘）开盘后，自动取前N根K线的\n"
            "最高价为上限、最低价为下限。新时段覆盖旧区间。\n"
            "默认模板：6根5分钟K线。"
        )
        hint_label.setStyleSheet("color:#64748b; font-size:11px; padding:4px 0;")
        hint_label.setWordWrap(True)
        auto_lay.addRow("", hint_label)

        self.auto_status_label = QLabel()
        self.auto_status_label.setStyleSheet("color:#64748b; font-size:11px;")
        auto_lay.addRow("当前区间：", self.auto_status_label)

        btn_recalc = QPushButton("立即重新计算")
        btn_recalc.clicked.connect(self._on_recalculate)
        auto_lay.addRow("", btn_recalc)
        self.auto_grp.setLayout(auto_lay)
        layout.addWidget(self.auto_grp)

        # 可视化
        self.viz_label = QLabel()
        self.viz_label.setMinimumHeight(40)
        self.viz_label.setAlignment(Qt.AlignCenter)
        self.viz_label.setStyleSheet("background:#f4f6fa; border-radius:6px; font-family:monospace;")
        layout.addWidget(self.viz_label)
        self.lo_spin.valueChanged.connect(self._update_viz)
        self.hi_spin.valueChanged.connect(self._update_viz)
        self._update_viz()
        self._on_mode_changed()

        # 触发方向
        dir_grp = QGroupBox("触发方向")
        dir_lay = QHBoxLayout()
        self.dir_group = QButtonGroup()
        self.rb_enter = QRadioButton("仅进入")
        self.rb_leave = QRadioButton("仅离开")
        self.rb_both = QRadioButton("进入 + 离开")
        self.dir_group.addButton(self.rb_enter, 0)
        self.dir_group.addButton(self.rb_leave, 1)
        self.dir_group.addButton(self.rb_both, 2)
        mapping = {"enter": self.rb_enter, "leave": self.rb_leave, "both": self.rb_both}
        mapping.get(self.rule.direction, self.rb_both).setChecked(True)
        dir_lay.addWidget(self.rb_enter)
        dir_lay.addWidget(self.rb_leave)
        dir_lay.addWidget(self.rb_both)
        dir_lay.addStretch()
        dir_grp.setLayout(dir_lay)
        layout.addWidget(dir_grp)

        # 冷却 + 启用
        opt_grp = QGroupBox("高级选项")
        opt_lay = QFormLayout()
        self.cool_spin = QSpinBox()
        self.cool_spin.setRange(0, 1440)
        self.cool_spin.setSuffix(" 分钟")
        self.cool_spin.setValue(self.rule.cooldown)
        opt_lay.addRow("冷却时长：", self.cool_spin)

        self.enable_cb = QCheckBox("启用此规则")
        self.enable_cb.setChecked(self.rule.enabled)
        opt_lay.addRow("", self.enable_cb)

        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("如：突破即跟进多单")
        self.note_edit.setText(self.rule.note)
        self.note_edit.setMaxLength(50)
        opt_lay.addRow("备注：", self.note_edit)
        opt_grp.setLayout(opt_lay)
        layout.addWidget(opt_grp)

        # 按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_del = QPushButton("删除规则")
        btn_del.clicked.connect(self._on_delete)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存规则")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._on_save)
        btn_lay.addWidget(btn_del)
        btn_lay.addWidget(btn_cancel)
        btn_lay.addWidget(btn_save)
        layout.addLayout(btn_lay)

    def _update_viz(self):
        lo = self.lo_spin.value()
        hi = self.hi_spin.value()
        if lo >= hi and hi > 0:
            self.viz_label.setText("⚠ 下限需小于上限")
            self.viz_label.setStyleSheet("background:#fee2e2; border-radius:6px; color:#991b1b;")
            return
        if lo == 0 and hi == 0:
            self.viz_label.setText("请设定价格区间")
            self.viz_label.setStyleSheet("background:#f4f6fa; border-radius:6px; color:#64748b;")
            return
        self.viz_label.setStyleSheet("background:#f4f6fa; border-radius:6px; font-family:monospace; color:#15487a;")
        self.viz_label.setText(f"  区间外(下)  │  {lo:g} ───── {hi:g}  │  区间外(上)")

    def _on_mode_changed(self):
        """切换手动/K线自动模式时，启用/禁用对应面板"""
        is_auto = self.rb_auto.isChecked()
        self.manual_grp.setEnabled(not is_auto)
        self.auto_grp.setEnabled(is_auto)
        if is_auto:
            if self.rule.lo > 0 and self.rule.hi > 0:
                sess = f"（{self.rule.last_auto_session}）" if self.rule.last_auto_session else "（待计算）"
                self.auto_status_label.setText(f"{self.rule.lo:g} ~ {self.rule.hi:g}{sess}")
                self.auto_status_label.setStyleSheet("color:#7c3aed; font-size:11px;")
            else:
                self.auto_status_label.setText("尚未计算（等待开盘后K线数据）")
                self.auto_status_label.setStyleSheet("color:#94a3b8; font-size:11px;")
            self.viz_label.setText("⚡ K线自动模式：开盘后自动计算区间")
            self.viz_label.setStyleSheet("background:#f5f3ff; border-radius:6px; color:#7c3aed;")
        else:
            self._update_viz()

    def _on_recalculate(self):
        """立即重新计算K线区间（跨线程取数，通过信号回主线程更新UI）"""
        count = self.kline_count_spin.value()
        period = self.kline_period_combo.currentData()
        self.auto_status_label.setText("计算中…")
        self.auto_status_label.setStyleSheet("color:#f59e0b; font-size:11px;")

        def do_calc():
            from data_source import SinaDataSource
            from trading_hours import current_session_bound
            ds = SinaDataSource(timeout=8)
            session_id, session_start, label = current_session_bound(self.code)
            if session_id is None:
                self.recalc_done.emit(False, "当前非交易时段，无法计算", 0, 0)
                return
            klines, enough = ds.fetch_klines_front_n(self.code, period, count, session_start)
            got = len(klines)
            if not enough or got < count:
                self.recalc_done.emit(False, f"K线不足：{got}/{count}（等待更多K线收盘）", 0, 0)
                return
            hi = max(k.high for k in klines)
            lo = min(k.low for k in klines)
            self.rule.lo = lo
            self.rule.hi = hi
            self.rule.last_auto_session = session_id
            self.store.save_rule(self.rule)
            self.recalc_done.emit(True, f"{lo:g} ~ {hi:g}（{label}，{got}根{period}min）", lo, hi)

        threading.Thread(target=do_calc, daemon=True).start()

    def _on_recalc_done(self, success, msg, lo, hi):
        """重算完成回调（主线程安全更新UI）"""
        self.auto_status_label.setText(msg)
        if success:
            self.auto_status_label.setStyleSheet("color:#16a34a; font-size:11px;")
            self.viz_label.setText(f"  区间外(下)  │  {lo:g} ───── {hi:g}  │  区间外(上)")
            self.viz_label.setStyleSheet("background:#f4f6fa; border-radius:6px; font-family:monospace; color:#15487a;")
        else:
            self.auto_status_label.setStyleSheet("color:#dc2626; font-size:11px;")

    def _on_save(self):
        is_auto = self.rb_auto.isChecked()
        if is_auto:
            new_count = self.kline_count_spin.value()
            new_period = self.kline_period_combo.currentData()
            # 参数变更时清除上次计算标记，强制下个时段重新计算
            if new_count != self.rule.kline_count or new_period != self.rule.kline_period:
                self.rule.last_auto_session = ""
            self.rule.mode = "auto_kline"
            self.rule.kline_count = new_count
            self.rule.kline_period = new_period
        else:
            self.rule.mode = "manual"
            lo = self.lo_spin.value()
            hi = self.hi_spin.value()
            if lo <= 0 or hi <= 0 or lo >= hi:
                QMessageBox.warning(self, "输入有误", "请输入有效的价格区间：\n下限需大于 0，且小于上限。")
                return
            self.rule.lo = lo
            self.rule.hi = hi
        self.rule.direction = {0: "enter", 1: "leave", 2: "both"}[self.dir_group.checkedId()]
        self.rule.cooldown = self.cool_spin.value()
        self.rule.enabled = self.enable_cb.isChecked()
        self.rule.note = self.note_edit.text().strip()
        self.store.save_rule(self.rule)
        self.rule_saved.emit(self.code)
        self.accept()

    def _on_delete(self):
        if self.rule.id:
            self.store.delete_rule(self.rule.id)
        self.rule_saved.emit(self.code)
        self.accept()


class SettingsDialog(QDialog):
    """系统设置弹窗"""

    settings_saved = pyqtSignal(dict)

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.settings = store.get_settings()
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("系统设置")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # 微信推送
        grp_push = QGroupBox("微信推送")
        push_lay = QFormLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("PushPlus", "pushplus")
        self.channel_combo.addItem("Server酱", "serverchan")
        ch = self.settings.get("push_channel", "pushplus")
        idx = self.channel_combo.findData(ch)
        if idx >= 0:
            self.channel_combo.setCurrentIndex(idx)
        push_lay.addRow("推送渠道：", self.channel_combo)

        self.token_edit = QLineEdit()
        self.token_edit.setPlaceholderText("粘贴 PushPlus / Server酱 分配的 Token")
        self.token_edit.setText(self.settings.get("push_token", ""))
        push_lay.addRow("推送 Token：", self.token_edit)

        btn_test = QPushButton("发送测试推送")
        btn_test.clicked.connect(self._on_test_push)
        push_lay.addRow("", btn_test)

        self.push_status = QLabel()
        push_lay.addRow("", self.push_status)
        grp_push.setLayout(push_lay)
        layout.addWidget(grp_push)

        # 行情设置
        grp_quote = QGroupBox("行情设置")
        quote_lay = QFormLayout()

        self.freq_combo = QComboBox()
        self.freq_combo.addItem("1 秒", "1")
        self.freq_combo.addItem("3 秒（推荐）", "3")
        self.freq_combo.addItem("5 秒", "5")
        fi = self.freq_combo.findData(self.settings.get("refresh_interval", "3"))
        if fi >= 0:
            self.freq_combo.setCurrentIndex(fi)
        quote_lay.addRow("刷新频率：", self.freq_combo)

        self.thours_cb = QCheckBox("按各品种交易时段自动启停（休市不取数不推送）")
        self.thours_cb.setChecked(self.settings.get("trading_hours_filter", "1") == "1")
        quote_lay.addRow("交易时段：", self.thours_cb)
        grp_quote.setLayout(quote_lay)
        layout.addWidget(grp_quote)

        # 桌面提醒
        grp_alert = QGroupBox("桌面提醒")
        alert_lay = QFormLayout()

        self.sound_cb = QCheckBox("触发时播放提示音")
        self.sound_cb.setChecked(self.settings.get("sound_enabled", "1") == "1")
        alert_lay.addRow("声音：", self.sound_cb)

        self.sound_type_combo = QComboBox()
        self.sound_type_combo.addItem("默认（进入/离开不同音调）", "default")
        self.sound_type_combo.addItem("铃声1（急促三连音）", "ring1")
        self.sound_type_combo.addItem("铃声2（下降双音）", "ring2")
        self.sound_type_combo.addItem("自定义 wav 文件", "custom")
        self.sound_type_combo.addItem("静音", "none")
        si = self.sound_type_combo.findData(self.settings.get("sound_type", "default"))
        if si >= 0:
            self.sound_type_combo.setCurrentIndex(si)
        self.sound_type_combo.currentIndexChanged.connect(self._on_sound_type_changed)
        alert_lay.addRow("提示音类型：", self.sound_type_combo)

        # 自定义提示音文件选择
        sound_file_row = QHBoxLayout()
        self.sound_path_edit = QLineEdit()
        self.sound_path_edit.setPlaceholderText("选择 .wav 提示音文件")
        self.sound_path_edit.setText(self.settings.get("custom_sound_path", ""))
        sound_file_row.addWidget(self.sound_path_edit)
        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self._on_browse_sound)
        sound_file_row.addWidget(btn_browse)
        btn_test_sound = QPushButton("试听")
        btn_test_sound.clicked.connect(self._on_test_sound)
        sound_file_row.addWidget(btn_test_sound)
        alert_lay.addRow("自定义文件：", sound_file_row)
        self.sound_file_widget = sound_file_row  # 保存引用以便启用/禁用
        self._on_sound_type_changed()

        self.popup_cb = QCheckBox("触发时弹出桌面通知")
        self.popup_cb.setChecked(self.settings.get("popup_enabled", "1") == "1")
        alert_lay.addRow("弹窗：", self.popup_cb)

        self.flash_cb = QCheckBox("对应品种行闪烁高亮")
        self.flash_cb.setChecked(self.settings.get("flash_enabled", "1") == "1")
        alert_lay.addRow("闪烁：", self.flash_cb)

        self.popup_dur = QComboBox()
        self.popup_dur.addItem("5 秒", "5")
        self.popup_dur.addItem("10 秒", "10")
        self.popup_dur.addItem("常驻", "999")
        pi = self.popup_dur.findData(self.settings.get("popup_duration", "10"))
        if pi >= 0:
            self.popup_dur.setCurrentIndex(pi)
        alert_lay.addRow("弹窗停留：", self.popup_dur)

        # 测试弹窗：可选择4种突破类型
        test_popup_row = QHBoxLayout()
        self.test_breakthrough_combo = QComboBox()
        self.test_breakthrough_combo.addItem("▲ 上穿上限", "up_break_hi")
        self.test_breakthrough_combo.addItem("▼ 下穿下限", "down_break_lo")
        self.test_breakthrough_combo.addItem("▲ 上穿下限", "up_cross_lo")
        self.test_breakthrough_combo.addItem("▼ 下穿上限", "down_cross_hi")
        test_popup_row.addWidget(self.test_breakthrough_combo)
        btn_test_popup = QPushButton("发送测试弹窗")
        btn_test_popup.clicked.connect(self._on_test_popup)
        test_popup_row.addWidget(btn_test_popup)
        alert_lay.addRow("测试弹窗：", test_popup_row)

        grp_alert.setLayout(alert_lay)
        layout.addWidget(grp_alert)

        # 自启
        grp_sys = QGroupBox("系统")
        sys_lay = QFormLayout()
        self.autostart_cb = QCheckBox("开机自动启动监控引擎")
        self.autostart_cb.setChecked(self.settings.get("auto_start", "1") == "1")
        sys_lay.addRow("自启：", self.autostart_cb)
        grp_sys.setLayout(sys_lay)
        layout.addWidget(grp_sys)

        # 按钮
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存设置")
        btn_save.setObjectName("primary")
        btn_save.clicked.connect(self._on_save)
        btn_lay.addWidget(btn_cancel)
        btn_lay.addWidget(btn_save)
        layout.addLayout(btn_lay)

    def _on_test_push(self):
        token = self.token_edit.text().strip()
        channel = self.channel_combo.currentData()
        if not token:
            self.push_status.setText("⚠ 请先填写 Token")
            self.push_status.setStyleSheet("color:#dc2626;")
            return
        self.push_status.setText("发送中…")
        self.push_status.setStyleSheet("color:#64748b;")
        from notifier import Notifier
        notifier = Notifier({"push_token": token, "push_channel": channel})
        ok, msg = notifier.test_push(token, channel)
        self.push_status.setText(("✓ " if ok else "✗ ") + msg)
        self.push_status.setStyleSheet("color:#16a34a;" if ok else "color:#dc2626;")

    def _on_sound_type_changed(self):
        """提示音类型变化时，启用/禁用自定义文件选择行"""
        is_custom = self.sound_type_combo.currentData() == "custom"
        self.sound_path_edit.setEnabled(is_custom)
        # 找到 sound_file_row 中的浏览和试听按钮并设置启用状态
        for i in range(self.sound_file_widget.count()):
            widget = self.sound_file_widget.itemAt(i).widget()
            if widget:
                widget.setEnabled(is_custom or widget is self.sound_path_edit)
        self.sound_path_edit.setEnabled(is_custom)

    def _on_browse_sound(self):
        """浏览选择 wav 提示音文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择提示音文件", "", "WAV 音频文件 (*.wav);;所有文件 (*.*)"
        )
        if path:
            self.sound_path_edit.setText(path)

    def _on_test_sound(self):
        """试听当前选择的提示音"""
        from notifier import Notifier, AlertInfo
        settings = {
            "sound_type": self.sound_type_combo.currentData(),
            "custom_sound_path": self.sound_path_edit.text().strip(),
        }
        notifier = Notifier(settings)
        notifier._play_sound(AlertInfo(
            code="TEST", name="测试", price=0, change_pct=0,
            direction="enter", lo=0, hi=0, note=""
        ))

    def _on_test_popup(self):
        """发送测试弹窗（可选择4种突破类型）"""
        from notifier import Notifier
        settings = {
            "popup_enabled": "1",
            "popup_duration": self.popup_dur.currentData(),
        }
        notifier = Notifier(settings)
        breakthrough = self.test_breakthrough_combo.currentData()
        notifier.test_popup(breakthrough)

    def _on_save(self):
        new_settings = {
            "push_channel": self.channel_combo.currentData(),
            "push_token": self.token_edit.text().strip(),
            "refresh_interval": self.freq_combo.currentData(),
            "trading_hours_filter": "1" if self.thours_cb.isChecked() else "0",
            "sound_enabled": "1" if self.sound_cb.isChecked() else "0",
            "sound_type": self.sound_type_combo.currentData(),
            "custom_sound_path": self.sound_path_edit.text().strip(),
            "popup_enabled": "1" if self.popup_cb.isChecked() else "0",
            "flash_enabled": "1" if self.flash_cb.isChecked() else "0",
            "popup_duration": self.popup_dur.currentData(),
            "auto_start": "1" if self.autostart_cb.isChecked() else "0",
        }
        self.store.save_settings(new_settings)
        self.settings_saved.emit(new_settings)
        self.accept()


class KlineDiagDialog(QDialog):
    """区间诊断 — 展示自动区间计算使用的K线明细（时间/OHLC/异常修正记录）

    数据来源优先级：
      1. 引擎中的计算快照（与当前区间完全同源，含修正前原值）
      2. 无快照时（如软件重启后未重算）实时拉取当前时段K线，仅供参考
    """

    klines_loaded = pyqtSignal(list, bool, str)   # (klines, enough, note)

    def __init__(self, code, name, store, engine, parent=None):
        super().__init__(parent)
        self.code = code
        self.engine = engine
        self.rule = store.get_rule_by_code(code)
        self.klines_loaded.connect(self._on_klines_loaded)
        self.setWindowTitle(f"区间诊断 — {name}({code})")
        self.resize(700, 580)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size:13px; padding:2px;")
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        self.source_label = QLabel()
        self.source_label.setStyleSheet("color:#64748b; font-size:12px; padding:2px;")
        self.source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.source_label)

        self.hint_label = QLabel()
        self.hint_label.setStyleSheet("color:#f59e0b; font-size:12px; padding:2px;")
        self.hint_label.setWordWrap(True)
        self.hint_label.hide()
        layout.addWidget(self.hint_label)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["#", "时间", "开", "高", "低", "收", "成交量", "备注"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self.table.horizontalHeader()
        for c in range(7):
            header.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color:#64748b; font-size:12px; padding:2px;")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        btn = QPushButton("关闭")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)

    def _load_data(self):
        rule = self.rule
        if not rule or rule.mode != "auto_kline":
            lo = rule.lo if rule else 0
            hi = rule.hi if rule else 0
            self.summary_label.setText(f"当前区间 {lo:g} ~ {hi:g}")
            self.source_label.setText(
                "该规则为手动区间模式，上下限由用户直接设定，无K线明细。")
            return

        amp = (f"{(rule.hi - rule.lo) / rule.lo * 100:.2f}%"
               if rule.lo > 0 and rule.hi > 0 else "—")
        self.summary_label.setText(
            f"当前区间 {rule.lo:g} ~ {rule.hi:g}    振幅 {amp}    "
            f"口径 {rule.kline_count}根 × {rule.kline_period}分钟")

        from trading_hours import current_session_bound
        cur_session, _, cur_label = current_session_bound(self.code)

        # 优先使用引擎中的计算快照（与区间完全同源）
        snap = self.engine.get_diag(self.code) if self.engine else None
        if snap:
            self.source_label.setText(
                f"数据来源：{snap['label']}时段计算快照 · "
                f"计算于 {snap['calc_time'].strftime('%H:%M:%S')}（{snap['session']}）")
            # 区间来源时段 ≠ 当前时段：提示区间即将被新时段重算
            if (cur_session is not None and snap["session"]
                    and cur_session != snap["session"]):
                self.hint_label.setText(
                    f"注意：区间计算于{snap['label']}时段，当前已进入{cur_label}时段，"
                    f"新时段K线凑齐后区间将自动重算。")
                self.hint_label.show()
            self._fill_table(snap["klines"])
            return

        # 无快照 → 实时拉取当前时段K线
        if cur_session is None:
            self.source_label.setText(
                "无计算快照，且当前为非交易时段，无法实时拉取K线。"
                "可在交易时段内重新打开本窗口查看。")
            return
        self.source_label.setText(f"正在实时拉取{cur_label}时段K线…")
        if rule.last_auto_session and cur_session != rule.last_auto_session:
            self.hint_label.setText(
                f"注意：当前区间计算于上一时段（{rule.last_auto_session}），"
                f"下方展示的是当前{cur_label}时段K线，仅供参考，并非区间来源。")
            self.hint_label.show()

        def do_fetch():
            from data_source import SinaDataSource
            from trading_hours import current_session_bound as csb
            sid, sstart, label = csb(self.code)
            if sid is None:
                self.klines_loaded.emit([], False, "当前非交易时段")
                return
            ds = SinaDataSource(timeout=8)
            try:
                ks, enough = ds.fetch_klines_front_n(
                    self.code, self.rule.kline_period, self.rule.kline_count, sstart)
                self.klines_loaded.emit(ks, enough, f"实时拉取 · {label}时段（{sid}）")
            except Exception as e:
                self.klines_loaded.emit([], False, f"拉取失败: {e}")

        threading.Thread(target=do_fetch, daemon=True).start()

    def _on_klines_loaded(self, klines, enough, note):
        self.source_label.setText(f"数据来源：{note}")
        if not klines:
            self.status_label.setText("未获取到K线数据。")
            return
        self._fill_table(klines)
        if not enough:
            want = self.rule.kline_count if self.rule else 0
            self.status_label.setText(
                f"仅获取到 {len(klines)}/{want} 根K线，区间尚未最终确定 · "
                + self.status_label.text())

    def _fill_table(self, klines):
        """填充K线明细表，标记区间来源K线与异常修正记录"""
        hi_idx = max(range(len(klines)), key=lambda i: klines[i].high)
        lo_idx = min(range(len(klines)), key=lambda i: klines[i].low)
        hi_bg = QBrush(QColor(220, 38, 38, 30))
        lo_bg = QBrush(QColor(37, 99, 235, 30))
        fix_brush = QBrush(QColor("#dc2626"))
        src_brush = QBrush(QColor("#16a34a"))

        self.table.setRowCount(len(klines))
        fixed_cnt = 0
        for i, k in enumerate(klines):
            notes = []
            note_brush = None
            was_fixed = False
            if k.orig_high is not None and abs(k.orig_high - k.high) > 1e-9:
                notes.append(f"H修正 {k.orig_high:g}→{k.high:g}")
                was_fixed = True
            if k.orig_low is not None and abs(k.orig_low - k.low) > 1e-9:
                notes.append(f"L修正 {k.orig_low:g}→{k.low:g}")
                was_fixed = True
            if was_fixed:
                fixed_cnt += 1
                note_brush = fix_brush
            if i == hi_idx:
                notes.append("▲ 区间上限来源")
                note_brush = src_brush
            if i == lo_idx:
                notes.append("▼ 区间下限来源")
                note_brush = src_brush

            cells = [
                str(i + 1),
                k.time.strftime("%H:%M"),
                f"{k.open:g}", f"{k.high:g}", f"{k.low:g}", f"{k.close:g}",
                str(k.volume),
                "；".join(notes),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c < 7:
                    item.setTextAlignment(Qt.AlignCenter)
                if i == hi_idx:
                    item.setBackground(hi_bg)
                elif i == lo_idx:
                    item.setBackground(lo_bg)
                if c == 7 and note_brush is not None:
                    item.setForeground(note_brush)
                self.table.setItem(i, c, item)

        self.status_label.setText(
            f"共 {len(klines)} 根K线 · {fixed_cnt} 根经异常值修正 · "
            f"▲上限=第{hi_idx + 1}根（{klines[hi_idx].high:g}） "
            f"▼下限=第{lo_idx + 1}根（{klines[lo_idx].low:g}）")
