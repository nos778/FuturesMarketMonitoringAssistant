"""生成启动配置文件 — 记录 pythonw.exe 的完整路径。
此脚本在开发环境中运行一次，将路径写入 launch_config.txt。
启动脚本(bat/vbs)读取此文件获取 pythonw.exe 路径。
"""
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
_pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
_config = os.path.join(_dir, "launch_config.txt")

with open(_config, "w", encoding="utf-8") as f:
    f.write(_pythonw)

print(f"已写入启动配置: {_config}")
print(f"pythonw.exe 路径: {_pythonw}")
print(f"文件存在: {os.path.exists(_pythonw)}")
