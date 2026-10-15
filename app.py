"""期货盯盘助手 — 应用入口
启动 QApplication，应用全局样式表，显示主窗口。
"""
import sys
sys.dont_write_bytecode = True  # 禁止生成pyc缓存，避免加载旧代码

import logging
import os
from datetime import datetime

# 将当前目录加入 path，确保模块导入正常
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont

from main_window import MainWindow

# ---- 日志配置 ----
LOG_DIR = os.path.join(os.path.expanduser("~"), ".tdx_futures_monitor")
os.makedirs(LOG_DIR, exist_ok=True)

# pythonw 模式下 sys.stdout 为 None，需要兼容处理
# 使用 delay=True 延迟打开文件，避免旧进程文件句柄未释放时冲突
_handlers = []
try:
    _handlers.append(logging.FileHandler(
        os.path.join(LOG_DIR, "monitor.log"), encoding="utf-8", delay=True))
except Exception as _e:
    pass
if sys.stdout is not None:
    _handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_handlers if _handlers else [logging.NullHandler()],
)
logger = logging.getLogger("app")

# ---- 全局样式表 ----
GLOBAL_QSS = """
/* ===== 基础 ===== */
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 13px;
    outline: none;
}

QMainWindow, QWidget {
    background: #f8fafc;
    color: #1e293b;
}

/* ===== 顶栏 ===== */
QFrame#topbar {
    background: #ffffff;
    border-bottom: 1px solid #e2e8f0;
}

QLabel#apptitle {
    font-size: 16px;
    font-weight: 700;
    color: #1e293b;
    letter-spacing: 1px;
}

/* ===== 按钮 ===== */
QPushButton {
    padding: 6px 16px;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    background: #ffffff;
    color: #475569;
    font-weight: 500;
}

QPushButton:hover {
    background: #f1f5f9;
    border-color: #cbd5e1;
}

QPushButton:pressed {
    background: #e2e8f0;
}

QPushButton:disabled {
    color: #cbd5e1;
    background: #f8fafc;
}

QPushButton#btnPrimary {
    background: #2563eb;
    border: none;
    color: #ffffff;
    font-weight: 600;
}

QPushButton#btnPrimary:hover {
    background: #1d4ed8;
}

QPushButton#btnPrimary:pressed {
    background: #1e40af;
}

QPushButton#btnPrimary:disabled {
    background: #93c5fd;
    color: #ffffff;
}

QPushButton#btnAdd {
    background: #ffffff;
    border: 1px solid #2563eb;
    color: #2563eb;
    font-weight: 600;
}

QPushButton#btnAdd:hover {
    background: #eff6ff;
}

QPushButton#btnGhost {
    background: transparent;
    border: 1px solid #cbd5e1;
    color: #64748b;
}

QPushButton#btnGhost:hover {
    background: #f1f5f9;
    border-color: #94a3b8;
}

QPushButton#btnGhost:disabled {
    color: #cbd5e1;
    border-color: #e2e8f0;
}

/* ===== 表格 ===== */
QTableWidget {
    background: #ffffff;
    border: none;
    gridline-color: #f1f5f9;
    selection-background-color: #dbeafe;
    selection-color: #1e293b;
}

QTableWidget::item {
    padding: 4px 8px;
    border-bottom: 1px solid #f1f5f9;
}

QTableWidget::item:alternate {
    background: #fafbfc;
}

QHeaderView::section {
    background: #f1f5f9;
    color: #64748b;
    padding: 8px 6px;
    border: none;
    border-bottom: 2px solid #e2e8f0;
    font-weight: 600;
    font-size: 12px;
}

QTableCornerButton::section {
    background: #f1f5f9;
    border: none;
    border-bottom: 2px solid #e2e8f0;
}

/* ===== 状态栏 ===== */
QStatusBar {
    background: #ffffff;
    border-top: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 12px;
}

QStatusBar::item {
    border: none;
}

/* ===== 输入控件 ===== */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    padding: 5px 8px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background: #ffffff;
    color: #1e293b;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563eb;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox QAbstractItemView {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background: #ffffff;
    selection-background-color: #dbeafe;
    selection-color: #1e293b;
    padding: 2px;
}

/* ===== 对话框 ===== */
QDialog {
    background: #f8fafc;
}

QGroupBox {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    background: #ffffff;
    font-weight: 600;
    color: #334155;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #2563eb;
}

/* ===== 列表 ===== */
QListWidget {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background: #ffffff;
    padding: 4px;
}

QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}

QListWidget::item:hover {
    background: #f1f5f9;
}

QListWidget::item:selected {
    background: #dbeafe;
    color: #1e293b;
}

/* ===== 复选框 / 单选 ===== */
QCheckBox, QRadioButton {
    spacing: 6px;
    color: #475569;
}

QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #cbd5e1;
    border-radius: 3px;
    background: #ffffff;
}

QRadioButton::indicator {
    border-radius: 9px;
}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: #2563eb;
    border-color: #2563eb;
}

/* ===== 滚动条 ===== */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ===== 菜单 ===== */
QMenu {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background: #dbeafe;
    color: #1e293b;
}

QMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 4px 8px;
}

/* ===== 滚动区域 ===== */
QScrollArea {
    border: none;
    background: transparent;
}

/* ===== 消息框 ===== */
QMessageBox {
    background: #f8fafc;
}

QMessageBox QLabel {
    color: #1e293b;
    font-size: 13px;
}

/* ===== Tab ===== */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    background: #ffffff;
    margin-top: -1px;
}

QTabBar::tab {
    padding: 6px 16px;
    border: 1px solid #e2e8f0;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    background: #f1f5f9;
    color: #64748b;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #2563eb;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background: #e2e8f0;
}
"""


def _kill_existing_instances():
    """如果有已运行的实例，终止它（避免多实例冲突和数据库锁）"""
    import ctypes
    import ctypes.wintypes
    import time

    user32 = ctypes.windll.user32
    # 多次查找，确保找到所有旧窗口（可能残留多个）
    for _ in range(3):
        hwnd = user32.FindWindowW(None, "期货盯盘助手")
        if not hwnd:
            break

        wpid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        old_pid = wpid.value
        if not old_pid:
            break

        # SYNCHRONIZE 允许等待进程退出；PROCESS_TERMINATE 允许终止
        PROCESS_TERMINATE = 0x0001
        SYNCHRONIZE = 0x00100000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False, old_pid)
        if handle:
            kernel32.TerminateProcess(handle, 0)
            # 等待进程真正退出（最多5秒），避免旧窗口残留
            WAIT_OBJECT_0 = 0
            result = kernel32.WaitForSingleObject(handle, 5000)
            kernel32.CloseHandle(handle)
            if result == WAIT_OBJECT_0:
                logger.info("已终止旧实例 PID=%d", old_pid)
            else:
                logger.warning("终止旧实例超时 PID=%d, result=%d", old_pid, result)
            # 额外等待确保文件句柄和窗口资源释放
            time.sleep(0.5)
        else:
            logger.warning("无法打开旧进程 PID=%d (可能已退出)", old_pid)
            break


def main():
    # 启动诊断：用最原始的方式写一行日志，确认程序确实运行到这里
    try:
        with open(os.path.join(LOG_DIR, "startup.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()} PID={os.getpid()} main()开始执行\n")
    except Exception:
        pass

    # 强制重新初始化日志（解决 delay=True 或文件锁导致日志不写入的问题）
    try:
        log_path = os.path.join(LOG_DIR, "monitor.log")
        # 先清空可能被锁的handler
        root_logger = logging.getLogger()
        for h in root_logger.handlers[:]:
            root_logger.removeHandler(h)
        # 重新创建FileHandler，不带delay，确保立即打开文件
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_logger.addHandler(fh)
        root_logger.setLevel(logging.INFO)
        if sys.stdout is not None:
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
            root_logger.addHandler(sh)
    except Exception as e:
        # 如果日志初始化也失败，写到startup.log
        try:
            with open(os.path.join(LOG_DIR, "startup.log"), "a", encoding="utf-8") as f:
                f.write(f"{datetime.now()} 日志初始化失败: {e}\n")
        except Exception:
            pass

    # 终止可能残留的旧实例，避免数据库锁冲突
    _kill_existing_instances()

    # 如果是python.exe（有控制台）启动，隐藏控制台窗口
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE = 0
            logger.info("已隐藏控制台窗口")
    except Exception:
        pass

    logger.info("=" * 50)
    logger.info("期货盯盘助手启动")
    logger.info("=" * 50)

    # 设置 AppUserModelID（必须在 QApplication 创建前设置）
    # Windows 10/11 要求应用设置 AUMID 才能正常显示系统托盘通知
    # 缺少 AUMID 是 pythonw.exe 启动时弹窗不显示的最常见原因
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "TdxFuturesMonitor.FuturesAlert.1"
        )
        logger.info("已设置 AppUserModelID")
    except Exception as e:
        logger.warning("设置 AppUserModelID 失败: %s", e)

    # 启用高 DPI 缩放（必须在 QApplication 创建前设置）
    # 解决笔记本高分辨率屏幕下界面元素过小的问题
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("期货盯盘助手")
    app.setQuitOnLastWindowClosed(False)  # 关闭窗口时不退出，最小化到托盘
    app.setStyleSheet(GLOBAL_QSS)

    # 设置默认字体
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)

    window = MainWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    # 用 Windows API 强制设置前台窗口（不修改windowFlags，避免触发showEvent重载）
    def _force_foreground():
        try:
            import ctypes
            hwnd = int(window.winId())
            ctypes.windll.user32.AllowSetForegroundWindow(-1)
            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
        except Exception as e:
            logger.warning("强制设置前台窗口失败: %s", e)

    _force_foreground()
    logger.info("已强制设置前台窗口")

    # 多次重试强制置顶（500ms、1s、2s），防止被TRAE IDE等抢回焦点
    for delay in [500, 1000, 2000]:
        QTimer.singleShot(delay, _force_foreground)

    # 延迟强制刷新表格，确保数据渲染到屏幕
    def _refresh_table():
        try:
            window._load_symbols()
            window.table.viewport().update()
            window.table.repaint()
            logger.info("延迟表格刷新完成, 行数=%d", window.table.rowCount())
        except Exception as e:
            logger.warning("延迟表格刷新失败: %s", e)

    QTimer.singleShot(200, _refresh_table)

    logger.info("主窗口已显示，等待用户操作")
    exit_code = app.exec_()
    logger.info("应用退出，code=%d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
