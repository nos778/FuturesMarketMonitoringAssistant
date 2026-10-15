"""通知分发 — 桌面本地提醒 + 微信推送。
桌面: 自定义 Toast 弹窗 + 系统托盘通知 + 提示音 + 行闪烁信号
微信: PushPlus / Server酱 HTTP 接口
"""
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@dataclass
class AlertInfo:
    """提醒信息包"""
    code: str
    name: str
    price: float
    change_pct: float
    direction: str       # enter | leave
    lo: float
    hi: float
    note: str
    timestamp: datetime = None
    # 突破方向（细分4种）:
    #   up_break_hi   — 上穿上限（涨破上限离开区间）
    #   down_break_lo — 下穿下限（跌破下限离开区间）
    #   up_cross_lo   — 上穿下限（涨破下限进入区间）
    #   down_cross_hi — 下穿上限（跌穿上限进入区间）
    breakthrough: str = ""

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

    @property
    def direction_text(self) -> str:
        return "进入区间" if self.direction == "enter" else "离开区间"

    @property
    def is_enter(self) -> bool:
        return self.direction == "enter"

    @property
    def breakthrough_text(self) -> str:
        """突破方向中文描述"""
        mapping = {
            "up_break_hi":   "上穿上限",
            "down_break_lo": "下穿下限",
            "up_cross_lo":   "上穿下限",
            "down_cross_hi": "下穿上限",
        }
        return mapping.get(self.breakthrough, self.direction_text)

    @property
    def is_upward(self) -> bool:
        """是否为向上突破（上穿上限 / 上穿下限）"""
        return self.breakthrough in ("up_break_hi", "up_cross_lo")


class ToastWindow:
    """自定义 Toast 弹窗 — 不依赖 Windows 通知系统，确保弹窗一定可见。

    在屏幕右下角显示一个卡片式置顶窗口，自动在指定时间后消失。
    动效设计:
      - 入场: 从屏幕右侧弹簧回弹滑入 + 淡入（OutBack 缓动，动感流畅）
      - 突破场景: 内嵌 BreakoutScene 动画（价格圆点击穿边界线 + 光环爆开）
      - 扫光: 一道半透明光带周期性扫过卡片，增强流动感
      - 退场: 淡出 + 右滑出
    作为系统托盘通知的补充/回退方案，解决部分用户看不到弹窗的问题。
    """

    def __init__(self):
        self._active_toasts = []

    def show(self, title: str, body: str, duration_sec: int, is_upward: bool,
             boundary_label: str = ""):
        """显示一个 Toast 弹窗

        Args:
            is_upward: True=向上突破（红色，看涨）；False=向下突破（绿色，看跌）
            boundary_label: 突破的边界标签（如"上限 3074"），显示在动画场景中
        """
        try:
            from PyQt5.QtCore import (
                Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, QPoint
            )
            from PyQt5.QtGui import QColor, QFont, QCursor
            from PyQt5.QtWidgets import (
                QLabel, QFrame, QApplication, QDesktopWidget, QWidget,
                QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect
            )

            app = QApplication.instance()
            if app is None:
                return

            # 限制同时显示的 Toast 数量，避免堆积
            if len(self._active_toasts) >= 3:
                oldest = self._active_toasts.pop(0)
                try:
                    oldest.close()
                    oldest.deleteLater()
                except Exception:
                    pass

            # 颜色主题：向上突破红色（看涨），向下突破绿色（看跌）
            if is_upward:
                accent = "#dc2626"       # 红色 — 向上突破
                accent_light = "#fee2e2"
                icon = "▲"
                icon_color = "#dc2626"
            else:
                accent = "#16a34a"       # 绿色 — 向下突破
                accent_light = "#dcfce7"
                icon = "▼"
                icon_color = "#16a34a"

            # ===== 容器窗口（带阴影）=====
            toast = QFrame()
            toast.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
            toast.setAttribute(Qt.WA_ShowWithoutActivating)
            toast.setAttribute(Qt.WA_DeleteOnClose)
            toast.setAttribute(Qt.WA_TranslucentBackground)

            # 阴影效果
            shadow = QGraphicsDropShadowEffect(toast)
            shadow.setBlurRadius(28)
            shadow.setColor(QColor(0, 0, 0, 90))
            shadow.setOffset(0, 6)
            toast.setGraphicsEffect(shadow)

            # ===== 卡片主体（圆角白底 + 左侧色条）=====
            card = QFrame(toast)
            card.setObjectName("toastCard")
            card.setStyleSheet(f"""
                QFrame#toastCard {{
                    background: #ffffff;
                    border-radius: 12px;
                    border-left: 5px solid {accent};
                }}
            """)

            # 主布局：左侧图标区 + 右侧内容区
            main_lay = QHBoxLayout(card)
            main_lay.setContentsMargins(16, 14, 12, 14)
            main_lay.setSpacing(12)

            # 左侧大图标
            lbl_icon = QLabel(icon)
            lbl_icon.setFixedSize(40, 40)
            lbl_icon.setAlignment(Qt.AlignCenter)
            lbl_icon.setStyleSheet(f"""
                QLabel {{
                    background: {accent_light};
                    color: {icon_color};
                    border-radius: 20px;
                    font-size: 18px;
                    font-weight: bold;
                    border: none;
                }}
            """)
            main_lay.addWidget(lbl_icon)

            # 右侧内容区（垂直布局：标题行 + 正文）
            content = QWidget()
            content_lay = QVBoxLayout(content)
            content_lay.setContentsMargins(0, 0, 0, 0)
            content_lay.setSpacing(6)

            # 标题行：标题文字 + 关闭按钮
            title_row = QHBoxLayout()
            title_row.setContentsMargins(0, 0, 0, 0)
            title_row.setSpacing(8)

            lbl_title = QLabel(title)
            lbl_title.setStyleSheet(f"""
                QLabel {{
                    color: {accent};
                    font-size: 14px;
                    font-weight: bold;
                    border: none;
                }}
            """)
            title_row.addWidget(lbl_title, 1)

            # 关闭按钮
            btn_close = QPushButton("×")
            btn_close.setFixedSize(22, 22)
            btn_close.setCursor(Qt.PointingHandCursor)
            btn_close.setToolTip("关闭")
            btn_close.setStyleSheet("""
                QPushButton {
                    color: #94a3b8;
                    background: transparent;
                    border: none;
                    font-size: 18px;
                    font-weight: bold;
                    padding: 0px;
                }
                QPushButton:hover {
                    color: #dc2626;
                    background: #f1f5f9;
                    border-radius: 11px;
                }
                QPushButton:pressed {
                    color: #991b1b;
                    background: #fee2e2;
                    border-radius: 11px;
                }
            """)
            title_row.addWidget(btn_close, 0, Qt.AlignTop)
            content_lay.addLayout(title_row)

            # 正文
            lbl_body = QLabel(body)
            lbl_body.setStyleSheet("""
                QLabel {
                    color: #334155;
                    font-size: 13px;
                    border: none;
                }
            """)
            lbl_body.setWordWrap(True)
            lbl_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            content_lay.addWidget(lbl_body)

            # 突破动画场景（价格圆点击穿边界线）
            scene = BreakoutScene(accent, is_upward, boundary_label)
            content_lay.addWidget(scene)

            # 底部时间戳
            from datetime import datetime
            lbl_time = QLabel(datetime.now().strftime("%H:%M:%S"))
            lbl_time.setStyleSheet("""
                QLabel {
                    color: #94a3b8;
                    font-size: 11px;
                    border: none;
                }
            """)
            content_lay.addWidget(lbl_time)

            main_lay.addWidget(content, 1)

            # 外层布局只放卡片
            outer_lay = QVBoxLayout(toast)
            outer_lay.setContentsMargins(0, 0, 0, 0)
            outer_lay.addWidget(card)

            # 固定宽度，高度自适应
            toast.setFixedWidth(360)
            toast.adjustSize()
            toast.setFixedHeight(toast.sizeHint().height())

            # 定位到屏幕右下角，多个 Toast 向上堆叠
            screen = QDesktopWidget().availableGeometry()
            x = screen.right() - toast.width() - 20
            y_offset = 20
            for t in self._active_toasts:
                try:
                    y_offset += t.height() + 10
                except Exception:
                    pass
            y = screen.bottom() - toast.height() - y_offset
            toast.move(x, y)

            # ===== 入场动画: 从屏幕右侧弹簧滑入 + 淡入 =====
            final_pos = QPoint(x, y)
            toast.move(screen.right() + 30, y)   # 初始在屏幕右侧外
            toast.setWindowOpacity(0.0)

            fade_in = QPropertyAnimation(toast, b"windowOpacity", toast)
            fade_in.setDuration(150)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            slide_in = QPropertyAnimation(toast, b"pos", toast)
            slide_in.setDuration(450)
            slide_in.setEndValue(final_pos)
            slide_in.setEasingCurve(QEasingCurve.OutBack)   # 回弹缓动，动感流畅
            toast._fade_in = fade_in    # 保持引用避免被回收
            toast._slide_in = slide_in

            toast.show()
            fade_in.start()
            slide_in.start()

            # 启动突破动画场景
            toast._scene = scene
            scene.start()

            # ===== 扫光: 光带周期性扫过卡片（入场结束后开始）=====
            sweep = _SweepBand(card)
            toast._sweep = sweep

            def _run_sweep():
                if getattr(toast, '_closing', False):
                    return
                sweep.setGeometry(-80, 0, 80, card.height())
                sweep.show()
                sweep.raise_()
                anim = QPropertyAnimation(sweep, b"pos", toast)
                anim.setDuration(1100)
                anim.setStartValue(QPoint(-80, 0))
                anim.setEndValue(QPoint(card.width(), 0))
                anim.setEasingCurve(QEasingCurve.InOutQuad)

                def _again():
                    if not getattr(toast, '_closing', False):
                        QTimer.singleShot(700, _run_sweep)

                anim.finished.connect(_again)
                anim.start()
                toast._sweep_anim = anim

            QTimer.singleShot(520, _run_sweep)

            self._active_toasts.append(toast)

            # ===== 关闭逻辑（停止动画 + 淡出右滑退场）=====
            def _close():
                if getattr(toast, '_closing', False):
                    return
                toast._closing = True
                # 停止自动关闭定时器与所有动画
                if hasattr(toast, '_timer'):
                    toast._timer.stop()
                if hasattr(toast, '_scene'):
                    toast._scene.stop()
                if hasattr(toast, '_sweep_anim'):
                    toast._sweep_anim.stop()
                if hasattr(toast, '_sweep'):
                    toast._sweep.hide()
                fade_out = QPropertyAnimation(toast, b"windowOpacity", toast)
                fade_out.setDuration(280)
                fade_out.setStartValue(toast.windowOpacity())
                fade_out.setEndValue(0.0)
                fade_out.setEasingCurve(QEasingCurve.InCubic)
                slide_out = QPropertyAnimation(toast, b"pos", toast)
                slide_out.setDuration(280)
                slide_out.setEndValue(QPoint(toast.x() + 60, toast.y()))
                slide_out.setEasingCurve(QEasingCurve.InCubic)
                toast._slide_out = slide_out

                def _on_fade_out_finished():
                    try:
                        toast.close()
                        toast.deleteLater()
                    except Exception:
                        pass
                    if toast in self._active_toasts:
                        self._active_toasts.remove(toast)

                fade_out.finished.connect(_on_fade_out_finished)
                fade_out.start()
                slide_out.start()
                toast._fade_out = fade_out

            # 自动关闭定时器
            timer = QTimer(toast)
            timer.setSingleShot(True)
            timer.timeout.connect(_close)
            timer.start(duration_sec * 1000)
            toast._timer = timer

            # 关闭按钮点击
            btn_close.clicked.connect(_close)

            # 鼠标点击卡片任意位置也可关闭（但选中文本时不触发）
            def _on_mouse_press(e):
                if e.button() == Qt.LeftButton:
                    # 检查是否点击在可选中文本的标签上
                    widget = card.childAt(e.pos())
                    if isinstance(widget, QLabel) and widget.textInteractionFlags() & Qt.TextSelectableByMouse:
                        return
                    _close()
            card.mousePressEvent = _on_mouse_press

            logger.info("Toast 弹窗已显示: %s", title)
        except Exception as e:
            logger.warning("Toast 弹窗失败: %s", e)


class BreakoutScene(QWidget):
    """突破动画场景 — 价格圆点击穿边界线的动态可视化。

    一轮时序（约1.6s，连播3轮后停在"已突破"终态）:
      蓄势(圆点加速靠近) → 击穿瞬间(光环爆开+边界线闪光) → 边界线断开缺口 → 带拖尾冲出
    向上突破: 圆点自下而上击穿边界线；向下突破: 自上而下。
    让用户"看到"价格如何穿越关键价位，比纯文字更直观。
    """

    LOOP_MS = 1600
    LOOP_COUNT = 3
    TICK_MS = 33          # ~30fps
    CROSS_T = 0.45        # 击穿时刻（归一化进度）

    def __init__(self, accent: str, is_upward: bool, label: str = "", parent=None):
        super().__init__(parent)
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import QTimer

        self._accent = QColor(accent)
        self._is_up = is_upward
        self._label = label
        self._elapsed = 0
        self._loops = 0
        self._t = 0.0
        self.setFixedHeight(52)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)

    def start(self):
        self._elapsed = 0
        self._loops = 0
        self._timer.start(self.TICK_MS)

    def stop(self):
        self._timer.stop()

    def _on_tick(self):
        self._elapsed += self.TICK_MS
        if self._elapsed >= self.LOOP_MS:
            self._elapsed = 0
            self._loops += 1
            if self._loops >= self.LOOP_COUNT:
                # 播完3轮，定格在终态（圆点停在区间外、边界线留缺口）
                self._timer.stop()
                self._t = 1.0
                self.update()
                return
        self._t = self._elapsed / self.LOOP_MS
        self.update()

    def _path_point(self, e: float, w: float, h: float):
        """按归一化进度 e 计算圆点坐标（0=起点侧，1=击穿点，>1=冲出）"""
        from PyQt5.QtCore import QPointF
        cx = w * 0.62
        px = cx - 66 + e * 120
        line_y = h / 2
        py_out = 9 if self._is_up else h - 9     # 突破后的目标侧
        py_in = h - 9 if self._is_up else 9      # 起始侧（区间内）
        if e <= 1.0:
            py = py_in + (line_y - py_in) * e
        else:
            py = line_y + (py_out - line_y) * min(1.0, (e - 1) / 0.85)
        return QPointF(px, py), QPointF(cx, line_y)

    def paintEvent(self, _):
        from PyQt5.QtCore import Qt, QPointF, QRectF
        from PyQt5.QtGui import QPainter, QColor, QPen, QFont

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        t = self._t
        cross = self.CROSS_T
        line_y = h / 2
        cx = w * 0.62
        neutral = QColor(148, 163, 184)

        # ===== 1. 边界线（虚线；击穿后断开缺口、击穿瞬间闪光变粗）=====
        flash = 0.0
        if cross <= t <= cross + 0.28:
            flash = 1.0 - (t - cross) / 0.28
        line_color = self._accent if flash > 0 else neutral
        pen = QPen(line_color, 1.0 + 1.6 * flash, Qt.DashLine)
        p.setPen(pen)
        gap = 0.0 if t < cross else min(1.0, (t - cross) / 0.22)
        gap_w = gap * 24
        if gap_w > 0.5:
            p.drawLine(QPointF(6, line_y), QPointF(cx - gap_w, line_y))
            p.drawLine(QPointF(cx + gap_w, line_y), QPointF(w - 6, line_y))
        else:
            p.drawLine(QPointF(6, line_y), QPointF(w - 6, line_y))

        # 边界标签（右上角小字，如"上限 3074"）
        if self._label:
            f = QFont(self.font())
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(neutral)
            p.drawText(QRectF(w - 96, line_y - 20, 90, 14),
                       Qt.AlignRight | Qt.AlignVCenter, self._label)

        # ===== 2. 圆点进度 =====
        if t < cross:
            k = t / cross
            e = k * k                      # ease-in: 蓄势加速
        else:
            k = (t - cross) / (1 - cross)
            e = 1.0 + k * 0.9              # 击穿后继续冲出

        # ===== 3. 拖尾（运动中的残影）=====
        for i in range(1, 5):
            ee = e - i * 0.09
            if ee <= 0:
                continue
            pos, _ = self._path_point(ee, w, h)
            alpha = int(80 * (1 - i / 5))
            trail = QColor(self._accent)
            trail.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(trail)
            r = 4.0 * (1 - i / 6)
            p.drawEllipse(pos, r, r)

        # ===== 4. 击穿光环爆开 =====
        if cross <= t <= cross + 0.35:
            q = (t - cross) / 0.35
            r = 5 + q * 26
            ring = QColor(self._accent)
            ring.setAlpha(int(210 * (1 - q)))
            p.setPen(QPen(ring, 2.5 * (1 - q) + 0.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(cx, line_y), r, r)
            fill = QColor(self._accent)
            fill.setAlpha(int(50 * (1 - q)))
            p.setPen(Qt.NoPen)
            p.setBrush(fill)
            p.drawEllipse(QPointF(cx, line_y), r * 0.55, r * 0.55)

        # ===== 5. 价格圆点（外发光圈 + 实心圆）=====
        pos, _ = self._path_point(e, w, h)
        glow = QColor(self._accent)
        glow.setAlpha(70)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(pos, 8.0, 8.0)
        p.setBrush(self._accent)
        p.drawEllipse(pos, 4.5, 4.5)
        p.end()


class _SweepBand(QWidget):
    """卡片扫光条 — 一道半透明白色光带周期性扫过卡片，增强动感。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt5.QtCore import Qt
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedWidth(80)

    def paintEvent(self, _):
        from PyQt5.QtGui import QPainter, QLinearGradient, QColor
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        g.setColorAt(0.0, QColor(255, 255, 255, 0))
        g.setColorAt(0.5, QColor(255, 255, 255, 42))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillRect(self.rect(), g)
        p.end()



class Notifier:
    """统一通知分发器"""

    def __init__(self, settings: dict):
        self.settings = settings
        self._tray = None
        self._flash_callback = None
        self._toast = ToastWindow()

    def set_tray(self, tray):
        """设置系统托盘图标（QSystemTrayIcon）"""
        self._tray = tray

    def set_flash_callback(self, callback):
        """设置行闪烁回调"""
        self._flash_callback = callback

    def notify(self, alert: AlertInfo):
        """发送所有通知（桌面 + 微信）"""
        if self.settings.get("popup_enabled", "1") == "1":
            self._show_popup(alert)
        if self.settings.get("sound_enabled", "1") == "1":
            self._play_sound(alert)
        if self.settings.get("flash_enabled", "1") == "1" and self._flash_callback:
            self._flash_callback(alert.code)

        token = self.settings.get("push_token", "")
        if token:
            threading.Thread(
                target=self._push_wechat,
                args=(alert, token),
                daemon=True
            ).start()

    def _show_popup(self, alert: AlertInfo):
        """显示桌面弹窗 — 先显示自定义 Toast（确保可见），再尝试系统托盘通知"""
        # 标题使用细分突破方向（上穿上限 / 下穿上限 / 上穿下限 / 下穿下限）
        arrow = "▲" if alert.is_upward else "▼"
        title = f"{arrow} {alert.breakthrough_text} · {alert.name}"
        body = (
            f"{alert.code}  最新价 {alert.price:.2f}  "
            f"{'+'if alert.change_pct>=0 else ''}{alert.change_pct:.2f}%\n"
            f"区间 {alert.lo:g} ~ {alert.hi:g}"
        )
        if alert.note:
            body += f"  | {alert.note}"
        duration_sec = int(self.settings.get("popup_duration", "10"))
        if duration_sec <= 0 or duration_sec >= 999:
            duration_sec = 10

        # 突破动画场景的边界标签（显示被击穿的边界价位）
        if alert.breakthrough in ("up_break_hi", "down_cross_hi"):
            boundary_label = f"上限 {alert.hi:g}"
        elif alert.breakthrough in ("down_break_lo", "up_cross_lo"):
            boundary_label = f"下限 {alert.lo:g}"
        else:
            boundary_label = ""

        # 1. 始终显示自定义 Toast 弹窗（不依赖 Windows 通知设置，确保用户一定能看到）
        #    向上突破用红色（进入/上穿），向下突破用绿色（离开/下穿）
        self._toast.show(title, body, duration_sec, alert.is_upward, boundary_label)

        # 2. 尝试系统托盘通知（作为补充）
        if self._tray:
            try:
                from PyQt5.QtWidgets import QSystemTrayIcon
                if self._tray.isVisible() and QSystemTrayIcon.supportsMessages():
                    icon = (QSystemTrayIcon.Warning if alert.is_upward
                            else QSystemTrayIcon.Information)
                    self._tray.showMessage(title, body, icon, duration_sec * 1000)
                    logger.debug("托盘通知已发送")
                else:
                    logger.warning("托盘不可见或不支持消息: isVisible=%s",
                                   self._tray.isVisible())
            except Exception as e:
                logger.warning("托盘弹窗失败: %s", e)

        logger.info("弹窗: %s - %s", title, body)

    def _play_sound(self, alert: AlertInfo):
        """播放提示音 — 支持 default/ring1/ring2/custom/none"""
        sound_type = self.settings.get("sound_type", "default")
        if sound_type == "none":
            return
        try:
            import winsound

            if sound_type == "custom":
                # 播放用户自定义 wav 文件
                wav_path = self.settings.get("custom_sound_path", "")
                if wav_path and os.path.isfile(wav_path):
                    # SND_FILENAME: 播放文件, SND_ASYNC: 异步播放不阻塞
                    winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    logger.debug("播放自定义提示音: %s", wav_path)
                else:
                    logger.warning("自定义提示音文件不存在: %s，回退到默认提示音", wav_path)
                    self._play_default_beep(alert)
                return

            if sound_type == "ring1":
                # 铃声1: 急促三连音（高音）
                winsound.Beep(1200, 150)
                winsound.Beep(1400, 150)
                winsound.Beep(1200, 150)
            elif sound_type == "ring2":
                # 铃声2: 下降双音（低沉）
                winsound.Beep(600, 250)
                winsound.Beep(400, 350)
            else:
                # default: 根据方向区分
                self._play_default_beep(alert)

        except Exception as e:
            logger.debug("播放声音失败: %s", e)

    def _play_default_beep(self, alert: AlertInfo):
        """播放默认提示音（向上突破用上升音调，向下突破用下降音调）"""
        import winsound
        if alert.is_upward:
            # 向上突破：上升音调（880 → 1100）
            winsound.Beep(880, 200)
            winsound.Beep(1100, 200)
        else:
            # 向下突破：下降音调（880 → 660）
            winsound.Beep(880, 200)
            winsound.Beep(660, 200)

    def _push_wechat(self, alert: AlertInfo, token: str):
        """通过 PushPlus / Server酱 推送微信消息"""
        channel = self.settings.get("push_channel", "pushplus")
        arrow = "▲" if alert.is_upward else "▼"
        title = f"{arrow} {alert.breakthrough_text} · {alert.name} {alert.code}"
        content = self._format_message(alert)

        try:
            if channel == "pushplus":
                self._push_pushplus(token, title, content)
            elif channel == "serverchan":
                self._push_serverchan(token, title, content)
            logger.info("微信推送成功: %s %s", alert.code, alert.breakthrough_text)
        except Exception as e:
            logger.warning("微信推送失败: %s", e)

    def _format_message(self, alert: AlertInfo) -> str:
        """格式化微信消息内容"""
        pct = alert.change_pct
        pct_str = f"{'+'if pct>=0 else ''}{pct:.2f}%"
        time_str = alert.timestamp.strftime("%H:%M:%S")
        arrow = "▲" if alert.is_upward else "▼"
        lines = [
            f"<b>{alert.name} {alert.code}</b>",
            f"",
            f"触发: <b>{arrow} {alert.breakthrough_text}</b>",
            f"最新价: <b>{alert.price:.2f}</b> ({pct_str})",
            f"区间: {alert.lo:g} ~ {alert.hi:g}",
            f"时间: {time_str}",
        ]
        if alert.note:
            lines.append(f"备注: {alert.note}")
        lines.append(f"\n— 期货盯盘助手 · 实时监控")
        return "\n".join(lines)

    def _push_pushplus(self, token: str, title: str, content: str):
        """PushPlus 推送"""
        url = "http://www.pushplus.plus/send"
        payload = {
            "token": token,
            "title": title,
            "content": content,
            "template": "html",
        }
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("code") != 200:
            raise Exception(f"PushPlus 返回: {data}")

    def _push_serverchan(self, key: str, title: str, content: str):
        """Server酱 推送"""
        url = f"https://sctapi.ftqq.com/{key}.send"
        payload = {"title": title, "desp": content}
        resp = requests.post(url, data=payload, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            raise Exception(f"Server酱 返回: {data}")

    def test_push(self, token: str, channel: str = "pushplus") -> tuple:
        """发送测试推送，返回 (success, message)"""
        try:
            title = "期货盯盘助手 · 测试推送"
            content = (
                "<b>测试消息</b><br><br>"
                "如果您收到此消息，说明推送通道配置成功。<br><br>"
                "— 期货盯盘助手"
            )
            if channel == "pushplus":
                self._push_pushplus(token, title, content)
            elif channel == "serverchan":
                self._push_serverchan(token, title, content)
            return True, "测试消息已发送，请检查微信"
        except Exception as e:
            return False, f"发送失败: {e}"

    def test_popup(self, breakthrough="up_break_hi"):
        """发送测试弹窗（用于诊断弹窗是否正常显示）

        Args:
            breakthrough: 突破类型，默认 up_break_hi（上穿上限）
                up_break_hi   — 上穿上限（向上，红色）
                down_break_lo — 下穿下限（向下，绿色）
                up_cross_lo   — 上穿下限（向上，红色）
                down_cross_hi — 下穿上限（向下，绿色）
        """
        direction = "enter" if breakthrough in ("up_cross_lo", "down_cross_hi") else "leave"
        is_up = breakthrough in ("up_break_hi", "up_cross_lo")
        test_alert = AlertInfo(
            code="RB2610", name="螺纹钢2610", price=3065.00 if is_up else 2995.00,
            change_pct=1.52 if is_up else -0.84, direction=direction,
            lo=3000, hi=3060, note="这是一条测试提醒",
            breakthrough=breakthrough,
        )
        self._show_popup(test_alert)
        self._play_sound(test_alert)
        return True, f"测试弹窗已发送（{test_alert.breakthrough_text}），请检查屏幕右下角"
