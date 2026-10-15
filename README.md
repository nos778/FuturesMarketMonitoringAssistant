# 期货盯盘助手

国内期货价格区间监控桌面工具。基于新浪财经公开行情，支持多品种自选、K 线自动区间计算、集合竞价残留剔除、突破提醒（桌面动画弹窗 + 微信推送）。

## 功能特性

- 📊 **多品种行情监控** — 批量获取国内期货实时报价，主力合约自动跟随换月
- 🎯 **智能区间计算** — 支持手动区间 / K 线自动区间（默认开盘 30 根 1 分钟 K 线）
- 🧹 **集合竞价残留剔除** — 自动识别并修复 K 线极值异常（指纹型判据）
- 🔔 **突破提醒** — 价格穿越区间边界时桌面动画弹窗，支持 PushPlus / Server酱 微信推送
- 📌 **自选管理** — 置顶、振幅着色、主力合约自动跟随换月
- 🔧 **区间诊断** — 右键查看 K 线明细与异常修正记录，定位区间计算问题

## 环境要求

- Python 3.10+
- Windows 7 / 10 / 11
- 无账号、无 API Key（新浪财经公开行情）

## 快速开始

```bash
pip install -r requirements.txt
python write_config.py     # 生成启动配置（写入本机 pythonw 路径）
python app.py              # 或双击 启动盯盘助手.bat / 启动盯盘助手.vbs
```

## 数据说明

- **行情源**：新浪财经（`hq.sinajs.cn`），公开免 Key
- **用户数据**（自选 / 持仓 / 设置）：存储在 `~/.tdx_futures_monitor/config.db`，不上传仓库
- **推送 Token**（PushPlus / Server酱）：存储在本地 config.db，不进源码

## 打包 exe

```bash
pip install pyinstaller
pyinstaller tdx_monitor.spec
```

产物：`dist/tdx_monitor.exe`

## 免责声明

本工具仅供学习交流，不构成任何投资建议。期货交易有风险，使用后果自负。
