<h1 align="center">TradingAgents-Astock</h1>

<p align="center">
  基于 <a href="https://github.com/TauricResearch/TradingAgents">TauricResearch/TradingAgents</a>（65K ⭐）的 A 股深度特化 fork<br>
  全 Apache 2.0 开源 · pip install 即跑 · 零外部服务依赖
</p>

<p align="center">
  <b>⚠️ 免责声明：本项目仅供学习研究与技术演示，不构成任何投资建议。投资决策请咨询持牌专业机构。</b>
</p>

<p align="center">
  <a href="https://github.com/simonlin1212/tradingagents-astock/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://github.com/simonlin1212/tradingagents-astock/network/members"><img alt="Forks" src="https://img.shields.io/github/forks/simonlin1212/tradingagents-astock?style=social"/></a>
  <a href="https://arxiv.org/abs/2412.20138"><img alt="论文" src="https://img.shields.io/badge/论文-arXiv_2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="./LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache_2.0-blue"/></a>
  <a href="./CHANGES_FROM_UPSTREAM.md"><img alt="改动记录" src="https://img.shields.io/badge/改动记录-CHANGES-orange"/></a>
</p>

---

## 目录

- [为什么做这个 Fork](#为什么做这个-fork)
- [与上游对比](#与上游对比)
- [架构概览](#架构概览)
- [7 个 Analyst 角色](#7-个-analyst-角色)
- [数据源](#数据源)
- [快速开始](#快速开始)
- [Web UI](#web-ui)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [致谢](#致谢)
- [版本记录](#版本记录)
- [项目来源](#项目来源)
- [许可证](#许可证)

---

## 版本记录

### V1.0.8
- 修复报告标题区白字：移除生成侧 `signal-hold` 条件误设，新增展示侧 `.report-embed h1` 兜底，Buy/Sell/Hold 全信号兼容
- 修复多用户登录跳转：退出登录与登录成功时清理 `viewing_history` / `viewing_task`，防止跨用户报告残留

### V1.0.7
- 修复 History 页面 LLM 生成报告标题区文字不可见问题（深色背景 + 黑色文字）
- 隐藏登录页面密码框的 "Press Enter to submit form" 提示
- 修复 history 加载时 task JSON 缺失导致的 "No such file or directory" 错误
- 修复 runner 用户隔离 3 处缺陷（_run 参数传递、registry 单任务 fallback、auth_store import re）
- UI 对齐：登录/强制改密/修改密码三页表单位置统一居中
- 增加复制保护，防止报告页 Ctrl+C 触发 Streamlit "Clear caches" 弹窗

### V1.0.6
- 多用户体系：登录鉴权、角色分流（admin / user）
- 用户级任务隔离：历史分析、任务继续/删除均按用户隔离
- 管理员用户管理：增删改用户、重置密码
- 普通用户个人改密：首登强制改密
- 历史数据自动迁移：legacy 任务统一归属到默认管理员
- Runner 并发隔离：按 task_key 管理运行上下文，支持多用户并发分析

### V1.0.5
- README 重构：删除 Web UI 截图、删除 Donate 章节并替换为「项目来源」
- 发版流程提取为独立 skill：shmulti-release，不再内置在 AGENTS.md 中
- Web 任务生命周期：历史分析支持中断任务展示、继续恢复与删除清理
- Legacy CLI 旧日志兜底：旧 CLI 产物自动恢复为历史记录
- 报告页面布局：正文内容居中，宽度与 welcome 卡片对齐

### V1.0.4
- 历史分析增加 legacy CLI 旧日志兜底，message_tool.log + 阶段 md 也能恢复成历史行
- 继续 支持对旧 CLI 残留任务走补报告 / 补产物流程
- 删除按钮同时清理 Web 任务清单与 legacy CLI 旧产物

### V1.0.3
- 历史分析支持中断任务展示、继续恢复与删除清理
- Web 端任务状态落盘，支持断点续跑与报告补齐
- Google 客户端增加可选依赖懒导入兜底，默认环境可正常收集测试

### V1.0.2
- 历史分析支持中断任务展示、继续恢复与删除清理
- Web 端任务状态落盘，支持断点续跑与报告补齐
- 修复收尾阶段 `get_stock_name` 局部导入遮蔽导致的异常

### V1.0.1
- 报告页面布局优化：正文内容居中显示，宽度与 welcome 页面卡片对齐（~900px），sticky header 保持全宽

### V1.0.0
- Web UI 重构：侧边栏改为顶部导航条（首页 / 历史分析 / 新建分析三页面）
- 新增历史分析页面：表格展示、200 条自动清理、分析模式列
- 新增新建分析页面：股票输入 + 快速 / 中等 / 深度三档模式
- 报告页面优化：sticky header、下载按钮置顶、去掉 iframe 独立滚动条
- 风控评估中文 HTML 化：保存时由 LLM 翻译为中文 HTML 报告
- 性能优化：历史页面加载从 7s → 0.01s
- 字体替换：全局使用 Noto Sans SC（思源黑体）
- 表格样式优化：紧凑布局
- 版本号系统：首页显示版本号、README 记录版本

---

## 为什么做这个 Fork

原版 TradingAgents 是一个出色的多 Agent 投研框架，但它针对美股设计：数据走 Yahoo Finance / Alpha Vantage，分析师不懂 A 股制度，辩论和决策完全面向美股市场。

**本 Fork 的目标**：把 TradingAgents 的多 Agent 辩论架构真正落地到 A 股，不是简单翻译，而是从数据层、Agent 角色、交易规则三个维度做深度特化。

### 核心改造

| 维度 | 原版 | 本 Fork |
|------|------|---------|
| **数据源** | Yahoo Finance / Alpha Vantage | mootdx + 东财 + 新浪 + 同花顺（全免费直连） |
| **Analyst 角色** | 4 个（市场/情绪/新闻/基本面） | **7 个**（+政策分析师/游资追踪/解禁监控） |
| **交易规则** | 美股（T+0、无涨跌停） | A 股（T+1、涨跌停、最小手数、交易时段） |
| **输出语言** | 英文 | 中文报告（内部辩论保持英文以保证推理质量） |
| **Alpha 基准** | SPY | 沪深 300（CSI 300） |

---

## 与上游对比

| 特性 | 原版 TradingAgents | **本 Fork** |
|------|-------------------|-------------|
| 许可证 | Apache 2.0 | **全 Apache 2.0** |
| 部署依赖 | pip install | **开箱即用** |
| A 股数据 | ❌ | **mootdx + 东财 + 新浪 + 同花顺（直连 HTTP）** |
| A 股特化角色 | ❌ | **政策/游资/解禁 3 个深度角色** |
| A 股交易约束 | ❌ | **T+1/涨跌停/手数/ST 全覆盖** |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    7 Analyst 研报生成                      │
│  Market → Social → News → Fundamentals                   │
│  → Policy → Hot Money → Lockup                           │
│         （每个 Analyst 带工具循环）                          │
├─────────────────────────────────────────────────────────┤
│               Bull vs Bear 投研辩论                       │
│         Bull Researcher ←→ Bear Researcher               │
│               （最多 N 轮辩论）                             │
├─────────────────────────────────────────────────────────┤
│              Research Manager 综合研判                     │
│         （深度思考 LLM，输出投资计划）                       │
├─────────────────────────────────────────────────────────┤
│                  Trader 交易方案                          │
│         （A 股约束：T+1/涨跌停/手数）                       │
├─────────────────────────────────────────────────────────┤
│        Aggressive ←→ Conservative ←→ Neutral             │
│               三方风险辩论                                 │
├─────────────────────────────────────────────────────────┤
│            Portfolio Manager 最终决策                      │
│     （深度思考 LLM，输出 Buy/Hold/Sell + 仓位）             │
└─────────────────────────────────────────────────────────┘
```

**双 LLM 设计**：
- `quick_think_llm`：所有 Analyst、Researcher、Trader、Risk Debater
- `deep_think_llm`：Research Manager 和 Portfolio Manager（需要综合全局信息做决策）

---

## 7 个 Analyst 角色

### 原版 4 角色（A 股适配）

| 角色 | 职责 | 数据工具 |
|------|------|---------|
| 🏪 市场分析师 | K 线形态、技术指标、量价分析 | `get_stock_data`, `get_indicators` |
| 💬 舆情分析师 | 社交媒体情绪、散户讨论热度 | `get_news` |
| 📰 新闻分析师 | 行业新闻、公告、宏观事件 | `get_news`, `get_global_news`, `get_insider_transactions` |
| 📊 基本面分析师 | 财报三表、盈利能力、估值 | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` |

### A 股特化 3 角色（新增）

| 角色 | 职责 | 数据工具 | 为什么需要 |
|------|------|---------|-----------|
| 🏛️ 政策分析师 | 监管政策、产业政策、窗口指导 | `get_news`, `get_global_news` | A 股是政策市，政策变化直接影响板块轮动 |
| 🔥 游资追踪师 | 龙虎榜、大单流向、主力资金动态 | `get_stock_data`, `get_news`, `get_insider_transactions` | 游资是 A 股短线定价的核心力量 |
| 🔓 解禁监控师 | 限售股解禁、大股东减持、股权质押 | `get_insider_transactions`, `get_news`, `get_fundamentals` | 解禁是 A 股特有的重大供给冲击因素 |

所有 7 个 Analyst 的报告会流入后续的 Bull/Bear 辩论和三方风险辩论，确保 A 股特色因素贯穿整条决策链。

---

## 数据源

全部免费，无需 API Key，无积分墙：

| 来源 | 协议 | 提供内容 |
|------|------|---------|
| **mootdx** | TCP 7709 | OHLCV K 线、财务快照、F10 文本 |
| **腾讯财经** | HTTP (`qt.gtimg.cn`) | PE / PB / 市值 / 换手率（实时） |
| **东方财富** | HTTP (datacenter / push2) | 龙虎榜、限售解禁、板块行情、个股信息 |
| **新浪财经** | HTTP | K 线历史、财报三表 |
| **同花顺** | HTTP (10jqka) | EPS 一致预期 |
| **财联社** | HTTP (cls.cn) | 全球财经快讯 |
| **百度股市通** | HTTP (finance.pae.baidu) | 概念板块分类、资金流向 |

> 完全不依赖 Tushare（积分墙）、Alpha Vantage（海外 API）、Yahoo Finance（不支持 A 股）。

---

## 快速开始

### 1. 环境准备

```bash
# Python >= 3.10
git clone https://github.com/simonlin1212/tradingagents-astock.git
cd tradingagents-astock
pip install -e .

# 如需使用 Google Gemini 模型（可选）：
pip install -e ".[google]"
```

### 2. 配置 LLM

> **必须使用 API Key**，不能用 Claude/ChatGPT 订阅版。每次分析需 30-50 次 LLM 调用，只有 API 模式支持。

在项目根目录创建 `.env` 文件，按你选择的供应商配置：

```bash
# ── 方案 A：MiniMax（推荐，国内直连，性价比高）──────────
MINIMAX_API_KEY=sk-xxx
# 申请地址：https://platform.minimaxi.com/

# ── 方案 B：DeepSeek ─────────────────────────────────
DEEPSEEK_API_KEY=sk-xxx
# 申请地址：https://platform.deepseek.com/

# ── 方案 C：智谱 GLM ─────────────────────────────────
ZHIPU_API_KEY=xxx
# 申请地址：https://open.bigmodel.cn/

# ── 方案 D：通义千问 Qwen ────────────────────────────
DASHSCOPE_API_KEY=sk-xxx
# 申请地址：https://dashscope.console.aliyun.com/

# ── 方案 E：OpenAI ───────────────────────────────────
OPENAI_API_KEY=sk-xxx

# ── 方案 F：Anthropic ────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-xxx

# ── 方案 G：Kimi（Anthropic 兼容 API）────────────────
ANTHROPIC_AUTH_TOKEN=your-kimi-token
```

### 3. 运行分析

根据你选择的供应商修改 config：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# ── MiniMax 示例（推荐）─────────────────────────────
config = {
    "llm_provider": "minimax",
    "deep_think_llm": "MiniMax-M2.7",
    "quick_think_llm": "MiniMax-M2.7-highspeed",
    "output_language": "Chinese",
}

# ── DeepSeek 示例 ───────────────────────────────────
# config = {
#     "llm_provider": "deepseek",
#     "deep_think_llm": "deepseek-chat",
#     "quick_think_llm": "deepseek-chat",
#     "output_language": "Chinese",
# }

# ── Anthropic + Kimi 示例 ───────────────────────────
# config = {
#     "llm_provider": "anthropic",
#     "deep_think_llm": "claude-sonnet-4-6",
#     "quick_think_llm": "claude-sonnet-4-6",
#     "backend_url": "https://api.kimi.com/coding/",
#     "output_language": "Chinese",
# }

ta = TradingAgentsGraph(debug=True, config=config)
final_state, decision = ta.propagate("688017", "2026-05-12")
print(decision)
```

### 4. CLI 方式

```bash
tradingagents            # 交互式 CLI
tradingagents --help     # 查看所有选项
```

---

## Web UI

内置 Streamlit 可视化界面，支持在侧边栏选择 LLM 供应商和模型，输入股票代码即可一键分析，适合不写代码的用户。

> **默认账号**：首次启动后系统自动创建管理员账号 `admin`，初始密码 `Admin@123!`，首次登录强制修改密码。

### 启动

```bash
# 方式一：命令行启动（推荐）
tradingagents-web

# 方式二：直接运行
streamlit run web/app.py
```

打开浏览器访问 `http://localhost:8501`。

### 功能

- **模型自选**：侧边栏支持 9 个 LLM 供应商切换（MiniMax/DeepSeek/Qwen/GLM/OpenAI/Anthropic/Google/xAI/Ollama）
- **一键分析**：输入 6 位 A 股代码 + 日期，点击「开始分析」
- **实时进度**：12 阶段 pipeline 实时显示（7 分析师 → 质量门控 → 辩论 → 风控 → 决策），所有已完成阶段的报告均可展开查看
- **完整报告**：信号卡片（Buy/Hold/Sell）、7 份分析师报告、多空辩论、风控评估
- **PDF 导出**：一键下载完整 PDF 分析报告
- **历史记录**：自动保存并展示所有历史分析

---

## 配置说明

所有配置通过 `config` 字典传入，完整选项：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `llm_provider` | `"minimax"` | LLM 提供商：`minimax` / `deepseek` / `qwen` / `glm` / `openai` / `anthropic` / `google` / `xai` / `ollama` |
| `deep_think_llm` | `"MiniMax-M2.7"` | Research Manager + Portfolio Manager 用的模型 |
| `quick_think_llm` | `"MiniMax-M2.7-highspeed"` | 所有 Analyst / Researcher / Trader 用的模型 |
| `backend_url` | `None` | 自定义 API 端点（Kimi、deepseek 等兼容 API） |
| `output_language` | `"Chinese"` | 报告输出语言（内部辩论始终英文） |
| `max_debate_rounds` | `1` | Bull vs Bear 辩论轮数 |
| `max_risk_discuss_rounds` | `1` | 风险三方辩论轮数 |
| `data_vendors` | 全部 `"a_stock"` | 数据供应商路由 |
| `checkpoint_enabled` | `False` | 启用 SQLite 断点续跑 |
| `memory_log_max_entries` | `None` | 交易记忆最大条目数 |

---

## 项目结构

```
TradingAgents-Astock/
├── tradingagents/
│   ├── agents/
│   │   ├── analysts/          # 7 个分析师
│   │   │   ├── market_analyst.py
│   │   │   ├── social_media_analyst.py
│   │   │   ├── news_analyst.py
│   │   │   ├── fundamentals_analyst.py
│   │   │   ├── policy_analyst.py        # A 股特化
│   │   │   ├── hot_money_tracker.py     # A 股特化
│   │   │   └── lockup_watcher.py        # A 股特化
│   │   ├── researchers/       # Bull / Bear 研究员
│   │   ├── risk_mgmt/         # 激进 / 保守 / 中立 辩手
│   │   ├── managers/          # Research Manager + Portfolio Manager
│   │   ├── trader/            # Trader（A 股交易约束）
│   │   └── utils/             # 状态定义、工具函数
│   ├── dataflows/
│   │   ├── a_stock.py         # A 股数据 vendor（直连 HTTP API，零第三方库）
│   │   ├── interface.py       # 数据接口抽象层
│   │   └── ...
│   └── graph/
│       ├── trading_graph.py   # 主入口：TradingAgentsGraph
│       ├── setup.py           # LangGraph 拓扑定义
│       ├── propagation.py     # 状态初始化与传播
│       ├── reflection.py      # 交易反思（CSI 300 基准）
│       └── conditional_logic.py
├── web/
│   ├── app.py                 # Streamlit 主入口
│   ├── runner.py              # 后台线程运行分析
│   ├── progress.py            # 线程安全进度追踪
│   ├── history.py             # 历史记录扫描
│   ├── pdf_export.py          # PDF 报告生成
│   ├── launch.py              # CLI 启动器
│   └── components/            # UI 组件
│       ├── sidebar.py         # 侧边栏（输入 + 历史）
│       ├── progress_panel.py  # 实时进度面板
│       └── report_viewer.py   # 报告展示
├── test_astock.py             # E2E 集成测试
├── CHANGES_FROM_UPSTREAM.md   # 与上游的完整改动记录
├── NOTICE                     # Apache 2.0 归属声明
├── LICENSE                    # Apache 2.0 许可证
└── pyproject.toml             # 包定义与依赖
```

---

## 致谢

本项目基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 开源项目进行 A 股特化改造。感谢原作者的出色工作和 Apache 2.0 开源精神。

**原始论文**：[TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

---

## 许可证

[Apache License 2.0](./LICENSE)

本项目是 TauricResearch/TradingAgents 的 fork，继承 Apache 2.0 许可证。详见 [NOTICE](./NOTICE)。

## 项目来源

本项目 fork 自 [simonlin1212/TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock)，在其基础上进行了深度特化与功能扩展。

---

## 免责声明

> **本项目仅供学习研究与技术演示，不构成任何投资建议。**
>
> - 本系统产出的所有分析报告和交易信号均由 AI 自动生成，可能存在错误或偏差
> - 投资决策请咨询持有中国证监会颁发资质的专业机构
> - 作者不对使用本工具产生的任何投资损失承担责任
> - 股市有风险，投资需谨慎
