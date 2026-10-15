"""启动器 — 定位 pythonw.exe 并以无控制台窗口方式启动主程序。
由 启动盯盘助手.bat 调用，启动后自身立即退出。
"""
import subprocess
import sys
import os

_dir = os.path.dirname(os.path.abspath(__file__))
_pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
_app = os.path.join(_dir, "app.py")

if os.path.exists(_pythonw):
    # 用 pythonw 启动，完全无控制台窗口
    subprocess.Popen([_pythonw, _app], cwd=_dir)
else:
    # 回退方案：用 python 启动
    subprocess.Popen([sys.executable, _app], cwd=_dir)
