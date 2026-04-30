# AutoResearchAgent 实现计划

## Context

搭建一个**自动化深度研究智能体**（Web 应用），用户输入研究主题后，系统进行迭代式深度研究（分解子问题 → 搜索 → 提取发现 → 缺口分析 → 补搜 → 生成报告），最终输出结构化 Markdown 研究报告。

**技术选型**：
- 智能体框架：**LangChain + LangGraph**（StateGraph 管理研究循环）
- 后端：FastAPI + SSE（端口 **9000**）
- 前端：纯 HTML/CSS/JS（左右分栏：对话日志 + 结果面板）
- LLM：DeepSeek API（`deepseek-v4-flash` 快速节点，`deepseek-v4-pro` 深度报告生成），通过 `langchain-openai` 的 `ChatOpenAI` 调用
- 搜索：两级策略 — **Tier 1** LLM 内置搜索优先 → **Tier 2** opencli 抓取网页补充
- 持久化：文件存储（Markdown 报告 + JSON 状态）
- Python 3.14 + **uv** 管理环境

---

## 环境与常用命令

```bash
uv sync                          # 安装依赖
uv run python main.py            # 启动服务（http://localhost:9000）
uv run pytest                    # 运行测试
uv add <package>                 # 添加依赖
uv add --dev <package>           # 添加开发依赖
```

---

## 目录结构

```
AutoResearchAgent/
├── main.py                        # FastAPI 入口，uvicorn 启动（端口 9000）
├── pyproject.toml                 # 项目元数据 + 依赖
├── agent/                         # LangGraph 研究智能体
│   ├── __init__.py
│   ├── graph.py                   # StateGraph 组装 + compile + 条件路由
│   ├── state.py                   # ResearchState TypedDict
│   ├── llm.py                     # ChatOpenAI 初始化（flash/pro 双模型）
│   ├── progress.py                # 实时进度推送队列（asyncio.Queue 旁路）
│   ├── nodes/
│   │   ├── __init__.py            # 节点超时装饰器
│   │   ├── planning.py            # 主题分解为子问题
│   │   ├── search.py              # 两级搜索（Tier1 LLM + Tier2 opencli）
│   │   ├── extract.py             # 从搜索结果提取关键发现
│   │   ├── gap_analysis.py        # 评估知识缺口
│   │   └── report.py              # 综合生成 Markdown 报告
│   ├── tools/
│   │   ├── __init__.py            # 导出工具列表
│   │   ├── search_tools.py        # opencli 搜索工具（@tool 装饰器）
│   │   └── tier1_search.py        # LLM 内置搜索
│   └── prompts/
│       ├── __init__.py
│       └── templates.py           # 所有提示词模板
├── api/
│   ├── __init__.py
│   ├── routes.py                  # FastAPI SSE 路由
│   ├── sse.py                     # astream_events → SSE 事件转换
│   └── models.py                  # Pydantic 请求/响应模型
├── storage/
│   ├── __init__.py
│   └── file_store.py              # 报告 & 状态文件读写
├── frontend/
│   ├── index.html                 # 左右分栏布局
│   ├── styles.css                 # 样式
│   └── app.js                     # EventSource 消费 + DOM 更新
├── data/
│   └── reports/                   # 生成的研究报告
└── docs/
    └── plan.md                    # 本文档
```

---

## LangGraph 状态图

### 节点与边

```
__start__ → planning → search → extract → gap_analysis ─┬→ search（有缺口且未达上限）
                                                        └→ report → __end__
```

| 节点 | 职责 | 模型 | 输入 | 输出 |
|------|------|------|------|------|
| `planning` | 主题分解为 10-20 个子问题（覆盖 8 个维度） | flash | topic | plan: list[str] |
| `search` | 两级并发搜索（Tier1+Tier2 并行），每轮 3 个问题，每问题 5 个网页源 | flash | plan, completed | search_results |
| `extract` | 并发提取关键发现（5-10 条/问题），拼 10 个来源 | flash | search_results | findings, completed |
| `gap_analysis` | 识别知识缺口，决定是否继续 | flash | findings, iteration | gaps, iteration+1 |
| `report` | 综合所有发现生成报告（6000-10000 字） | **pro** | findings, plan | report（Markdown） |

### 条件路由

```python
def route_after_gap(state):
    if state["gaps"] and state["iteration"] < state["max_iterations"]:
        return "search"
    return "report"
```

停止条件：无新缺口 / 达到 max_iterations（默认 3）/ 所有子问题已充分覆盖

### 完整研究循环流程图

```
用户输入主题
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 1: Planning 规划阶段 (0-5%)                                  │
│                                                                     │
│  ┌──────────────┐     ┌─────────────────────────────────┐          │
│  │ planning 节点 │────▶│ LLM(flash): 分解为 10-20 个子问题│          │
│  │   (flash)    │     │ 覆盖 8 个维度，确保全面覆盖       │          │
│  └──────────────┘     └───────────────┬─────────────────┘          │
│                                       │                             │
│                                       ▼                             │
│                          SSE: plan_created                          │
│                          前端: 更新计划 Tab                          │
└─────────────────────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 2: 迭代研究 (5-80%)                                          │
│                                                                     │
│  iteration = 1..max_iterations:                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ search 节点 (flash) — 全并发                               │  │
│  │                                                              │  │
│  │  asyncio.gather: 3 个问题同时搜索                             │  │
│  │  每个问题内部: Tier1 + Tier2 并发启动                         │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │ 【Tier 1】LLM 知识回答 (tier1_search)                 │   │  │
│  │  │   ├─ LLM(flash) + TIER1_SEARCH_PROMPT                │   │  │
│  │  │   ├─ 要求: 全面深入、多角度、结构化                    │   │  │
│  │  │   └─ 输出: List[{title, snippet, content, source}]   │   │  │
│  │  │                                                      │   │  │
│  │  │ 【Tier 2】opencli 并发搜索 + 并发抓取                  │   │  │
│  │  │   ├─ google_search(query, max_results=5)             │   │  │
│  │  │   ├─ asyncio.gather: 5 个网页并发 web_fetch(url)     │   │  │
│  │  │   ├─ 内容截断至 8000 词（取前 8000 词）              │   │  │
│  │  │   └─ opencli 不可用时优雅跳过                         │   │  │
│  │  │                                                      │   │  │
│  │  │  Tier1 + Tier2 通过 asyncio.gather 并发执行           │   │  │
│  │  │                                                      │   │  │
│  │  │  缺口补充搜索（第2轮+，并行于主搜索）:                  │   │  │
│  │  │   └─ gap_query → google_search + 并发 web_fetch      │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  │                                                              │  │
│  │  并发控制: LLM Semaphore(4), opencli Semaphore(5)            │  │
│  │  输出: search_results: Dict[question, List[SearchResult]]    │  │
│  │  SSE: progress（实时推送每个步骤）                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                          ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ extract 节点 (flash) — 全并发                               │  │
│  │                                                              │  │
│  │  asyncio.gather: 所有 pending 问题同时提取                    │  │
│  │  for each question (并发):                                   │  │
│  │    ├─ 拼接所有来源的 snippet/content（最多 10 个，各截断 4k） │  │
│  │    ├─ LLM(flash) + EXTRACT_PROMPT → 5-10 条关键发现          │  │
│  │    ├─ LLM Semaphore(4) 控制并发                              │  │
│  │    ├─ 记录 findings[question] = [...]                       │  │
│  │    └─ 标记 question 为 completed                             │  │
│  │                                                              │  │
│  │  输出: findings, completed_questions                         │  │
│  │  SSE: progress（实时）+ findings_update                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                          ▼                                         │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ gap_analysis 节点 (flash)                                    │  │
│  │                                                              │  │
│  │  ├─ LLM(flash) + GAP_ANALYSIS_PROMPT                        │  │
│  │  │   输入: plan, findings_summary, iteration, max_iterations│  │
│  │  │   评估: 是否充分覆盖？哪些维度缺失？                       │  │
│  │  │   输出: {gaps: [...], sufficient: bool}                   │  │
│  │  ├─ sufficient=true → gaps 强制清空                          │  │
│  │  └─ iteration += 1                                          │  │
│  │                                                              │  │
│  │  输出: gaps, iteration                                       │  │
│  │  SSE: gaps（前端显示缺口数量和继续/完成状态）                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                    ┌─────┴─────┐                                   │
│                    │ 条件路由:  │                                   │
│                    │ gaps非空  │                                   │
│                    │ 且        │                                   │
│                    │ iteration │                                   │
│                    │ < max?    │                                   │
│                    └─────┬─────┘                                   │
│                    是    │    否                                    │
│                     ▼    │    ▼                                    │
│                 search   │  report                                 │
│                     │    │                                         │
│                     └────┘                                         │
└─────────────────────────────────────────────────────────────────────┘
  │ (report 路径)
  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Phase 3: Report 报告生成 (80-100%)                                  │
│                                                                     │
│  ┌──────────────┐     ┌─────────────────────────────────┐          │
│  │ report 节点   │────▶│ LLM(pro): 综合所有发现           │          │
│  │   (pro)      │     │ 输入: topic, plan, findings      │          │
│  │              │     │ findings 最多传入 24000 字符     │          │
│  │              │     │ 输出: Markdown 6000-10000 字     │          │
│  └──────────────┘     └───────────────┬─────────────────┘          │
│                                       │                             │
│                                       ▼                             │
│                          ┌───────────────────────┐                  │
│                          │ storage.file_store     │                  │
│                          │ ├─ save_report() → .md│                  │
│                          │ └─ save_state() → .json│                 │
│                          └───────────────────────┘                  │
│                                       │                             │
│                                       ▼                             │
│                          SSE: report_chunk（完整，不截断）→ done│
│                          前端: 渲染 Markdown + 显示路径             │
└─────────────────────────────────────────────────────────────────────┘
```

### 搜索节点内部决策流程（并发）

```
search_node(state)
  │
  ├─ open_questions = [q for q in plan if q not in completed]
  ├─ batch = open_questions[:3]  ← 每轮最多 3 个问题
  │
  ├─ asyncio.gather: 3 个问题同时执行 _search_one_question:
  │    │
  │    ├── asyncio.gather: Tier1 + Tier2 并发启动
  │    │    │
  │    │    ├── 【Tier 1】tier1_search(question, llm)  ← LLM Semaphore(4)
  │    │    │    └─ 要求全面深入、多角度、结构化
  │    │    │
  │    │    └── 【Tier 2】_tier2_search_with_fetch(question)
  │    │         ├─ google_search(question, max_results=5)  ← opencli Semaphore(5)
  │    │         ├─ asyncio.gather: 5 个 web_fetch(url) 并发  ← opencli Semaphore(5)
  │    │         └─ 内容截断至 8000 词
  │    │
  │    └── 合并 Tier1 + Tier2 结果
  │
  └─ return {search_results, messages}
```

---

## State 定义（核心数据契约）

```python
class ResearchState(TypedDict):
    task_id: str                        # 任务标识（进度队列 key）
    topic: str                          # 研究主题
    max_iterations: int                 # 最大迭代次数
    plan: List[str]                     # 子问题列表（10-20 个）
    search_results: Dict[str, List]     # {子问题: [搜索结果]}
    findings: Dict[str, List[str]]      # {子问题: [关键发现]}（5-10 条/问题）
    completed_questions: List[str]      # 已完成的问题
    gaps: List[str]                     # 知识缺口
    iteration: int                      # 当前迭代
    report: str                         # 最终报告（6000-10000 字）
    report_path: Optional[str]          # 报告文件路径
    messages: List[dict]                # 前端展示用消息
    status: str                         # running | completed | error
    error: Optional[str]
```

---

## 搜索策略

### 并发执行模型
- 每轮 3 个问题通过 `asyncio.gather` 并行搜索
- 每个问题内部 Tier1（LLM）和 Tier2（opencli）通过 `asyncio.gather` 同时启动
- Tier2 中 5 个网页通过 `asyncio.gather` 并发抓取
- **LLM 并发限制**：`asyncio.Semaphore(4)` 防止 API 限流
- **opencli 并发限制**：`asyncio.Semaphore(5)` 防止资源耗尽

### Tier 1：LLM 知识回答
- LLM(flash) 用训练知识全面深入回答（多角度、结构化、包含关键事实和数据）
- 始终执行，作为信息基准

### Tier 2：opencli 补充搜索
- 始终与 Tier1 并发启动（不等待 Tier1 完成）
- `google_search(query, max_results=5)` → 5 个搜索结果
- 5 个网页 `web_fetch(url)` 并发抓取，单页 60s 超时
- 内容截断至 8000 词（取前 8000 词）
- opencli 不可用时优雅跳过，仅使用 Tier1 结果

### 缺口补充搜索（第 2 轮+）
- gap_query → google_search(max_results=3) → 并发 web_fetch
- 结果标记 source=tier2_gap

---

## SSE 事件映射

LangGraph 的 `astream_events(version="v1")` 产出的事件 + 进度队列映射为 SSE：

| 来源 | SSE 事件 | 前端行为 |
|---|---|---|
| `on_chain_start`（节点名） | `phase_start` | 更新状态栏阶段图标 |
| `on_chain_end`（节点名） | `phase_end` + 数据事件 | 更新对应面板（plan/findings/gaps/report） |
| `progress_queue.get()` | `progress` | 实时更新状态栏文字 + 日志原地替换 |
| `on_chain_end`（report 节点） | `report_chunk`（完整） | 渲染完整报告（不截断） |
| `on_chain_end`（report 节点） | `done` | 显示完成，关闭 SSE |

### 进度队列（`agent/progress.py`）
- 基于 `asyncio.Queue` 的旁路机制
- 每个 task_id 对应一个独立队列
- 节点在关键步骤调用 `push(task_id, phase, message, detail)`
- SSE 生成器在每次 `astream_events` 事件后排空进度队列
- 前端 `progress` 事件处理：
  - 更新状态栏（阶段标签 + 消息 + 详情）
  - 同阶段连续进度在原日志条目原地替换
  - 阶段切换时追加新日志条目

FastAPI 使用 `StreamingResponse(text/event-stream)` 实现 SSE 端点。

路由：`GET /api/research/stream?topic=...`

### SSE 桥接数据流

```
浏览器 (EventSource)                    FastAPI (SSE)                    LangGraph
═══════════════════                    ══════════════                    ═════════
                                                           ┌─────────────────────────┐
const es = new          GET /api/research/stream           │  graph.astream_events() │
  EventSource(           ?topic=xxx                         │  version="v1"           │
    "/api/research/       │                                  │                          │
     stream?topic=...")   │                                  │  事件产出:               │
     │                    │                                  │  on_chain_start ────────▶│
     │                    ▼                                  │  on_chat_model_stream ──▶│
es.addEventListener───◀── StreamingResponse                 │  on_tool_start ──────────▶│
  ('phase_start',         (text/event-stream)               │  on_tool_end ────────────▶│
   handler)               │                                  │  on_chain_end ───────────▶│
     │                    │  event_generator(topic):         └─────────────────────────┘
     │ 更新日志            │   │
     │ 和面板              │   ├─ 创建 initial_state
     │                    │   ├─ 创建 graph + config
     │                    │   ├─ yield SSE("phase_start")  ← 预发送（通知前端开始）
     │                    │   │
     │                    │   ├─ async for event in astream_events():
     │                    │   │      │
     │                    │   │      ├─ on_chain_start?node=planning
     │                    │   │      │   → yield SSE("phase_start", {node:"planning"})
     │                    │   │      │
     │                    │   │      ├─ on_chain_end?node=planning
     │                    │   │      │   output = {plan: [...], messages: [...]}
     │                    │   │      │   → yield SSE("plan", {questions: plan})
     │                    │   │      │   → yield SSE("message", messages[i])
     │                    │   │      │
     │                    │   │      ├─ on_chain_start?node=search
     │                    │   │      │   → yield SSE("phase_start", {node:"search"})
     │                    │   │      │
     │                    │   │      ├─ on_tool_start?name=google_search
     │                    │   │      │   → yield SSE("tool_start", {tool, input})
     │                    │   │      │
     │                    │   │      ├─ on_tool_end?name=google_search
     │                    │   │      │   → yield SSE("tool_end", {tool, preview})
     │                    │   │      │
     │                    │   │      ├─ on_chain_end?node=search
     │                    │   │      │   → yield SSE("message", messages[i])
     │                    │   │      │
     │                    │   │      ├─ on_chain_end?node=extract
     │                    │   │      │   → yield SSE("findings_update", {findings, completed})
     │                    │   │      │
     │                    │   │      ├─ on_chain_end?node=gap_analysis
     │                    │   │      │   → yield SSE("gaps", {gaps, iteration})
     │                    │   │      │
     │                    │   │      ├─ (cycle back to search if gaps)
     │                    │   │      │
     │                    │   │      └─ on_chain_end?node=report
     │                    │   │          → yield SSE("report_chunk", {content})
     │                    │   │          → yield SSE("report_done", {path})
     │                    │   │
     │                    │   └─ yield SSE("done", {status:"completed"})
     │                    │      yield SSE("close")
     │                    │
     │                    └─ 异常处理 → yield SSE("error", {message})

前端 SSE 事件 → DOM 操作 映射:
─────────────────────────────────
phase_start   → addLogEntry(phase, label)        // 时间线新增条目
message       → addLogEntry(phase, content)       // 时间线新增消息
plan          → renderPlan()                      // 计划 Tab 渲染子问题列表
findings_update→ renderFindings() + renderPlan()  // 发现 Tab + 更新计划完成状态
gaps          → addLogEntry(gap, msg)             // 时间线显示缺口
report_chunk  → renderReport(content)             // 报告 Tab 渲染 + 自动切换
report_done   → addLogEntry(done, path)           // 时间线显示保存路径
tool_start    → addLogEntry(search, tool+input)   // 时间线显示工具调用
tool_end      → addLogEntry(search, complete)     // 时间线显示工具完成
done          → 启用按钮 + 隐藏进度条 + 关闭 SSE  // 结束状态
error         → addLogEntry(error, msg)           // 时间线显示错误
```

### 前端 EventSource → DOM 状态映射

```
EventSource                    DOM 操作
══════════                     ════════
research:phase_start  ──────▶ timeline.appendChild(entry)
  {node, phase}                entry.className = "timeline-entry phase-{phase}"
                               entry.innerHTML = icon + text
                               timeline.scrollTop = timeline.scrollHeight

research:plan  ─────────────▶ tab-plan.innerHTML
  {questions}                   questions.map(q => plan-item + status-icon)

research:findings_update  ──▶ tab-findings.innerHTML
  {findings, completed}        findings.map((q, items) => finding-group + list)
                               tab-plan 更新状态图标 (⬜ → ✅)

research:report_chunk  ─────▶ tab-report.innerHTML
  {content}                     marked.parse(content) → report-content
                                tabs 切换到 report（强制高亮 report tab）

research:done  ─────────────▶ btnStart.disabled = false
  {path, status}               progressBar.classList.add('hidden')
                               es.close()
```

---

## API 路由

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/api/research/stream` | SSE 流，`?topic=xxx` 启动研究 |
| GET | `/api/research/history` | 列出历史报告 |
| GET | `/api/reports/{filename}` | 下载/查看报告文件 |
| GET | `/` | 前端页面 |

---

## 前端布局

```
┌─ Header ──────────────────────────────────────────────┐
│  AutoResearch Agent                    [历史] [?]      │
├─ 输入区 ───────────────────────────────────────────────┤
│  研究主题: [___________________________] [开始研究]     │
│  ▸ 高级设置（最大迭代: 3）                              │
├─ 状态栏 ────────────────────────────────────────────────┤
│  ● 搜索中 │ 并发搜索: "子问题1" │ 第1轮，Tier1+Tier2 │
├─────────────────────────┬───────────────────────────────┤
│  研究日志 (左 40%)      │  结果面板 (右 60%)            │
│  时间线：               │  Tab: [计划] [发现] [报告]    │
│  📋 规划阶段            │                               │
│  🔍 搜索: "子问题1"     │  选中 Tab 的内容区             │
│  📄 并发抓取网页...     │                               │
│  💡 提取 5 条发现       │                               │
│  📊 缺口分析 (第2轮)    │                               │
│  📝 生成报告...         │                               │
│  ✅ 研究完成            │                               │
└─────────────────────────┴───────────────────────────────┘
```

状态栏特性：
- 阶段颜色编码：规划(紫)、搜索(蓝)、提取(绿)、缺口分析(橙)、报告生成(金)
- 脉冲动画指示器：活跃时呼吸式脉冲
- 同阶段进度原地替换日志条目，阶段切换时追加新条目
- 显示：阶段图标 + 消息 + 详情

技术：原生 HTML/CSS/JS + EventSource API + marked.js（CDN）

---

## 依赖

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "langgraph>=0.4.0",
    "langchain-core>=0.3.0",
    "langchain-openai>=0.3.0",
    "pydantic>=2.0",
    "httpx>=0.28.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25.0",
]
```

`langchain-openai` 的 `ChatOpenAI` 兼容 DeepSeek API（设置 `base_url="https://api.deepseek.com/v1"`）。

---

## 实现顺序

### 第一阶段：基础设施 ✅
1. ✅ 更新 `pyproject.toml`，`uv sync` 安装依赖
2. ✅ `agent/state.py` — TypedDict 定义
3. ✅ `agent/llm.py` — ChatOpenAI 双模型初始化
4. ✅ `agent/prompts/templates.py` — 提示词模板
5. ✅ `storage/file_store.py` — 文件读写

### 第二阶段：工具 + 单节点 ✅
6. ✅ `agent/tools/search_tools.py` — opencli 搜索工具
7. ✅ `agent/tools/tier1_search.py` — LLM 搜索
8. ✅ 逐节点实现并测试：planning → search → extract → gap_analysis → report

### 第三阶段：图组装 + SSE + API ✅
9. ✅ `agent/graph.py` — StateGraph 组装
10. ✅ `agent/nodes/__init__.py` — 节点超时装饰器
11. ✅ `api/sse.py` — astream_events → SSE 转换 + 进度队列桥接
12. ✅ `api/routes.py` + `main.py` — FastAPI 启动

### 第四阶段：前端 ✅
13. ✅ `frontend/index.html` + `styles.css` — 布局 + 状态栏样式
14. ✅ `frontend/app.js` — SSE 消费 + 面板更新 + 进度事件处理

### 后续优化（已实施）
15. ✅ `agent/progress.py` — 实时进度推送队列
16. ✅ concurrency 全并发化：search/extract 节点 asyncio.gather
17. ✅ report 完整输出不截断
18. ✅ planning 扩展至 10-20 子问题 + 8 维度覆盖
19. ✅ extract 扩展至 5-10 条发现、10 来源拼接

---

## 关键架构决策

1. **LangGraph StateGraph**：研究循环天然适合状态图 —— 节点是研究阶段，边是流转，条件路由处理迭代循环
2. **双模型策略**：flash 用于快速节点（规划、搜索、提取、缺口），pro 用于最终报告生成
3. **全并发执行模型**：所有 I/O 密集操作通过 `asyncio.gather` 并发执行 —— 3 个问题同时搜索，Tier1+Tier2 同时启动，5 个网页并发抓取，所有 pending 问题并发提取
4. **双层并发控制**：LLM 调用 `asyncio.Semaphore(4)` 防止 API 限流，opencli 调用 `asyncio.Semaphore(5)` 防止系统资源耗尽
5. **进度旁路机制**：`agent/progress.py` 基于 `asyncio.Queue` 的独立进度通道，节点实时推送进度而不阻塞 LangGraph 状态流转，SSE 生成器在每次图事件后排空队列
6. **LangGraph checkpointer**：使用 `MemorySaver` 提供状态检查点，未来可切换 `SqliteSaver` 持久化
7. **内容截断策略**：网页内容截断至 8000 词（取前 8000 词），extract 阶段每个来源 snippet 截断至 4000 字符（前后各 2000），组合内容上限 16000 字符

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| DeepSeek 内置搜索能力不确定 | 已确认不支持；Tier1 使用 LLM 训练知识全面回答，Tier2 补充实时搜索 |
| opencli 需要 Chrome 浏览器扩展 | `try/except` 优雅跳过，进度消息提示用户，仅使用 Tier1 结果 |
| LangGraph astream_events 版本兼容 | 固定 `version="v1"`，锁定 `langgraph>=0.4.0` |
| DeepSeek API 限流 | LLM 调用 Semaphore(4) 并发控制，避免瞬时并发过高 |
| 网页内容超 token | 网页截断至 8000 词；extract 阶段每个来源 snippet 截断至 4000 字符，组合上限 16000 字符 |
| opencli 资源耗尽 | Semaphore(5) 限制并发进程数，单次调用 30s 超时，web_fetch 60s 超时 |

---

## 环境变量配置 (`.env`)

```bash
# DeepSeek API
DEEPSEEK_API_KEY=sk-xxx                    # API 密钥（必填）
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash     # 快速节点模型
DEEPSEEK_PRO_MODEL=deepseek-v4-pro         # 深度报告模型
```

由 `main.py` 启动时通过 `python-dotenv` 的 `load_dotenv()` 加载。

---

## 验证方式

1. **基础设施**：`uv run python -c "from agent.state import ResearchState; from agent.llm import get_flash_llm, get_pro_llm; print('OK')"`
2. **节点独立测试**：每个节点函数可单独调用验证
3. **SSE 流测试**：`curl "http://localhost:9000/api/research/stream?topic=测试主题"` 观察 SSE 事件流，验证 progress 事件实时推送
4. **进度系统验证**：观察 SSE `progress` 事件频率（应连续推送），验证状态栏实时更新、日志原地替换
5. **端到端测试**：浏览器 `localhost:9000`，提交真实研究主题，验证完整流程：规划 → 并发搜索 → 并发提取 → 缺口分析 → 迭代 → 报告生成
6. **错误降级**：opencli 不可用时验证 Tier1 独立完成，状态栏正确提示
