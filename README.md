# iwencai-cli

**同花顺问财（iWenCai）** 命令行工具 — 用自然语言选股，返回结构化结果。

[问财（iwencai.com）](https://www.iwencai.com/) 是同花顺（Hithink RoyalFlush）旗下的 AI 选股平台，支持用中文自然语言描述筛选条件（如"市盈率小于20"、"连续三天涨停"、"日线 MACD 金叉"等），后端自动解析为量化条件。本工具把问财的网页查询能力封装为本地 CLI，可作为问财 CLI、同花顺问财命令行工具，用于 A 股选股、股票筛选、量化选股和脚本化查询。

## 特性

- **自然语言查询**：直接用中文描述筛选条件，等同于在问财网页/App 的搜索框输入
- **本地运行**：通过 Playwright 驱动你本机的 Chrome，无需登录、无需 API Key
- **无反爬问题**：使用真 Chrome + 去掉自动化指纹，和手动打开浏览器行为一致
- **表格 / JSON 输出**：便于管道处理或配合脚本使用
- **Cookie 持久化**：首次运行后 session 复用，后续查询更快

## 安装

安装最新发布版：

```bash
pip install git+https://github.com/shaw-baobao/iwencai-cli.git@v0.1.0
```

安装 main 分支最新版：

```bash
pip install git+https://github.com/shaw-baobao/iwencai-cli.git
```

查看所有版本：[Releases](https://github.com/shaw-baobao/iwencai-cli/releases)。

第一次运行时如果没有 Playwright，加 `--install-playwright -y` 自动安装：

```bash
iwencai-query -q "上证50" --install-playwright -y
```

**前置要求**：系统已安装 Google Chrome（工具会通过 Playwright 的 `channel="chrome"` 调用）。如果系统没有 Chrome，会退回到 Playwright 自带 Chromium（可能被问财的反爬拦截）。

## 使用

```bash
# 基本查询
iwencai-query -q "市盈率小于20，市值大于100亿"

# JSON 输出
iwencai-query -q "连续涨停3天" --json

# 调试：显示浏览器窗口
iwencai-query -q "..." --headful

# 查询无结果时输出原始响应（调试用）
iwencai-query -q "..." --raw
```

### 参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `-q, --question` | 自然语言查询语句（必填） | — |
| `--json` | 以 JSON 格式输出 | 关 |
| `--headful` | 显示浏览器窗口 | 关 |
| `--wait-ms` | 页面加载后等待毫秒 | 4000 |
| `--profile-dir` | Playwright 持久化 profile 目录 | `~/.iwencai-profile` |
| `--raw` | 查询无结果时输出原始响应 | 关 |
| `--install-playwright` | 缺失 Playwright 时自动安装 | 关 |
| `-y, --yes` | 安装时跳过确认 | 关 |

## 工作原理

1. 启动本机 Chrome（持久化 profile 在 `~/.iwencai-profile`）
2. 去除 `navigator.webdriver` 等自动化特征，避开反爬
3. 打开 `https://www.iwencai.com/unifiedwap/result?w=<你的查询>`
4. 等待页面 JS 渲染结果表格
5. 从 DOM 提取股票列表（合并问财的固定左列 + 滚动右列双栏表格）
6. 输出为表格或 JSON

## 注意事项

- 问财网页的结果列会根据查询语句动态变化；工具输出的列名就是页面上显示的表头
- 问财免费版结果上限一般为 50 条
- 频繁大量查询可能触发问财的速率限制 —— 脚本使用时建议合理间隔
- 本项目与同花顺 / 问财官方无任何关联，仅是对其公开网页结果的自动化封装

## License

Apache-2.0
