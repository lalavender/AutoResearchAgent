# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

AutoResearchAgent —— 基于 LangChain/LangGraph 的自动化深度研究智能体。输入研究主题，自动迭代搜索、提取、分析缺口，最终生成 Markdown 研究报告。

- Python 3.14，使用 **uv** 管理环境
- FastAPI 后端（端口 9000）
- DeepSeek API（flash + pro 双模型）
- opencli 作为补充搜索工具

## 常用命令

```bash
uv sync                          # 安装依赖
uv run python main.py            # 启动服务（http://localhost:9000）
uv run pytest                    # 运行测试
uv add <package>                 # 添加依赖
uv add --dev <package>           # 添加开发依赖
```

## 架构

- `agent/` — LangGraph 状态图：planning → search → extract → gap_analysis → report（条件循环）
- `api/` — FastAPI 路由 + SSE 事件桥接
- `storage/` — 文件持久化（Markdown 报告 + JSON 状态）
- `frontend/` — 纯 HTML/CSS/JS（左右分栏布局 + EventSource）
