# XIANG · 中国象棋

Cardputer Zero 中国象棋。Debian 包名为 `xiang`，应用名为 **XIANG**，商店分享码拟用 **ZGXQ**。

## 安装

将 `dist/xiang_1.0.1-1_arm64.deb` 复制到 Zero，在设备上运行：

```sh
sudo apt install ./xiang_1.0.1-1_arm64.deb
```

安装后从 APPLaunch 打开 **XIANG**。商店发布信息见 store.json。AppStore 按 5 查询分享码，须先在 CardputerZero Hub 发布并完成审核。

## 对弈

- 离线人机提供象棋小巫师的入门、业余、专业三档。可选执红或执黑，执黑时棋盘旋转，己方在下方。
- 同机双人轮流走棋。应用保存未完成的本地棋局，开新局前会确认是否替换存档。
- 使用与 Five 一致的左棋盘、右状态栏，提供简体中文、英文、走棋音效和可走位置提示。
- 浅木色圆棋子用红、黑刻字。红方为帥、仕、相、馬、車、炮、兵，黑方为將、士、象、馬、車、炮、卒。九宫、楚河漢界按传统棋盘绘制。

| 按键 | 操作 |
| --- | --- |
| 方向键或 F / X / Z / C | 选棋时跳到当前可走的己方棋子，选中后跳到该棋子的合法目标 |
| Enter | 选择己方棋子，再按 Enter 走到目标格 |
| U | 悔棋。同机退一手，人机回到玩家上一次走棋之前 |
| Esc / Backspace | 已选棋时取消选中。短按 Esc 返回菜单，长按 3 秒退出 |
| 终局后 Enter | 重新开始。联机需要双方确认 |

棋局包含将军、应将、双将照面限制、将死与困毙。重复局面三次时，单方连续将军的一方判负，其他情况判和。长捉等比赛棋例采用上述重复局面判定。

AI 使用开源的 [象棋小巫师 XQWLight](xqwlight/UPSTREAM.md)。沿用上游三档搜索预算 10、100、1000 毫秒，通过 Node.js 子进程离线运行。原始引擎源码及许可证随包提供。

## 局域网联机

两台 Zero 接入同一局域网。房主选「创建房间」，指定执红方和是否允许悔棋，再分享 10 位房间码。对手选「加入房间」并输入房间码。房间码有效期为五分钟，配对时需要联网，棋步通过 WebRTC 直连传输。

在 [xiangzero.vercel.app](https://xiangzero.vercel.app/) 可在浏览器创建或加入房间、离开对局、悔棋和再来一局，可与 Zero 或浏览器互通。由 `vercel.json` 构建 `web/`，同源的 `api/pair.js` 转发配对请求。默认复用 Five 的信令服务，并使用独立的 `xiang` 数据频道。自建信令时，应在网页部署和 Zero 端配置同一个 `XIANG_SIGNAL_URL`。浏览器版以联机对战为用途。

## 本地开发

安装 Python 3.9+、Pillow 9.2+、Node.js 18+、Tk 和中文字体。Linux 可安装 `fonts-noto-cjk`，也可用 `XIANG_FONT` 指定字体路径。桌面体验联机需要额外安装 `aiortc`。

```sh
python xiang.py
python build_package.py
```

设备接口、音效、部分界面和 WebRTC 传输改编自 Five。项目采用 GPL-3.0-or-later，见 [LICENSE](LICENSE)。

