# DeerFlow 2 周深度学习规划

> 目标：在 2 周内完全理解 DeerFlow 项目的设计与实现

## 项目全貌速览

**DeerFlow** 是字节跳动开源的 Super Agent 框架（Deep Exploration and Efficient Research Flow）：

- **后端**：Python + FastAPI + LangGraph，核心是 `deerflow-harness` 包
- **前端**：Next.js 15 + TypeScript + shadcn/ui
- **架构模式**：Lead Agent 编排多个 SubAgent，支持 MCP 工具、Skills 系统、长期记忆

---

## Week 1 — 理解架构与核心机制

### Day 1：项目启动 + 全局视角（2-3h）

**目标**：跑通项目，建立整体认知

```bash
# 先把项目跑起来
make install
make dev
```

> **重要**：始终通过 `http://localhost:2026` 访问，而不是 `localhost:3000`。
> 2026 是 nginx 反向代理入口，所有请求在此统一路由；3000 是裸 Next.js，无法处理后端 API 路由。

**启动模式说明**：

| 命令 | 启动服务 | 适用场景 |
|------|---------|---------|
| `make dev` | LangGraph(2024) + Gateway(8001) + Frontend(3000) + Nginx(2026) | 标准开发 |
| `make dev-pro` | Gateway(8001) + Frontend(3000) + Nginx(2026)，无 LangGraph | 测试 Gateway 模式/自定义 Provider |

**请求路由架构**（`dev-pro` 模式）：

```
浏览器 → localhost:2026 (Nginx)
              ├── /api/*                → Gateway:8001 (FastAPI，含 /api/models)
              ├── /api/langgraph-compat/* → Gateway:8001 (embedded agent runtime)
              └── 其他                  → Frontend:3000 (Next.js)
```

**阅读顺序**：

1. `README_zh.md` — 了解设计理念
2. `config.example.yaml` — 理解所有配置项（LLM/工具/Agent/Skills/Memory）
3. `docker/nginx/nginx.local.conf` — nginx 反向代理规则，理解路由分发
4. `scripts/serve.sh` — 启动脚本，理解各服务如何协作、`.env.local` 如何被自动管理
5. `backend/app/gateway/app.py` — 看所有路由注册，建立 API 全貌
6. `backend/packages/harness/deerflow/client.py` — 入口，理解内嵌 Client 设计

**产出**：画出服务拓扑图（Nginx/Gateway/LangGraph/Frontend 的端口与路由关系）

---

### Day 2：Agent 系统核心（3-4h）

**目标**：理解 Lead Agent + SubAgent 的设计

**阅读顺序**：

1. `backend/packages/harness/deerflow/agents/` — 重点看：
   - `lead_agent.py` / `agent.py` — Agent 基类与 Lead Agent 逻辑
   - `middleware.py` — Agent 中间件机制
   - `memory/` — 长期记忆子系统
2. `backend/packages/harness/deerflow/subagents/` — SubAgent 执行引擎

**关键问题**：

- Lead Agent 如何决策调用哪个 SubAgent？
- LangGraph 的 State Graph 是如何定义的？
- Tool Call → SubAgent 的路由机制是什么？

---

### Day 3：工具系统 + MCP 集成（3h）

**目标**：理解工具注册/调用机制

**阅读顺序**：

1. `backend/packages/harness/deerflow/tools/` — 内置工具（搜索/代码/浏览器等）
2. `backend/packages/harness/deerflow/mcp/` — MCP 协议集成
3. `extensions_config.example.json` — MCP 扩展配置格式

**实验**：

- 在配置文件中启用一个 MCP Server（如 filesystem）
- 跟踪一次工具调用的完整链路

---

### Day 4：Skills 系统（2-3h）

**目标**：理解 Skills 的加载、管理和执行机制

**阅读顺序**：

1. `backend/packages/harness/deerflow/skills/` — Skills 管理器
2. `skills/public/deep-research/` — 以深度研究技能为例，看技能定义格式
3. `skills/public/skill-creator/` — 技能自举，理解设计哲学
4. `backend/app/gateway/routers/skills.py` — Skills API

**关键问题**：

- 一个 Skill 如何描述自己？（SKILL.md 格式）
- Skill 如何被 Agent 调用？
- Skill 与 SubAgent 的边界在哪里？

---

### Day 5：LLM 模型层 + 配置系统（2-3h）

**目标**：理解多模型适配机制

**阅读顺序**：

1. `backend/packages/harness/deerflow/models/` — 模型工厂与适配器
2. `backend/packages/harness/deerflow/config/` — 配置管理（15+ 配置模块）
3. `backend/app/gateway/routers/models.py` — 模型枚举 API

**关键问题**：

- 如何支持 OpenAI / Claude / Gemini / 本地模型？
- 配置是如何分层的（全局/Agent 级/技能级）？

---

### Day 6：沙箱执行环境（2h）

**目标**：理解代码安全执行机制

**阅读顺序**：

1. `backend/packages/harness/deerflow/sandbox/` — 沙箱设计

**关键问题**：

- 代码执行如何隔离？
- 支持哪些执行后端（本地/Docker/云）？

---

### Day 7：后端整体串联复盘（2-3h）

**目标**：从一次完整的研究请求，追踪全链路

**实验**：打开 LangSmith/Langfuse 追踪，发送一个复杂研究问题，观察：

1. HTTP 请求进入 gateway
2. LangGraph 状态机如何流转
3. Lead Agent 如何调度 SubAgent
4. 工具调用如何执行
5. 最终 SSE 流式响应如何返回

**产出**：画出完整的数据流时序图

---

## Week 2 — 前端 + 深度专题 + 实践

### Day 8：前端架构（3h）

**目标**：理解 Next.js App Router + 状态管理

**阅读顺序**：

1. `frontend/src/app/workspace/` — 工作台页面结构
2. `frontend/src/core/` — 核心状态与 API hooks（重点）
3. `frontend/src/components/ai-elements/` — AI 消息/推理/工件渲染组件
4. `frontend/src/app/api/` — Next.js API 路由（Auth/Memory）

**关键问题**：

- SSE 流式消息如何处理和渲染？
- `useWorkflowStream` 等 hooks 如何工作？
- 工件（Artifact）的渲染机制？

---

### Day 9：前端状态管理 + 实时通信（2-3h）

**目标**：深入理解前后端实时通信协议

**阅读顺序**：

1. 找到 SSE 事件类型定义（前后端对齐的 event types）
2. `frontend/src/components/workspace/` — Chat 面板、Agent 面板
3. `frontend/src/components/ai-elements/` — 推理过程展示（Chain-of-Thought 渲染）

---

### Day 10：IM 渠道集成（2h）

**目标**：理解多渠道架构设计

**阅读顺序**：

1. `backend/app/channels/` — 飞书/Slack/Telegram/WeCom 适配器
2. 选一个渠道（如飞书），完整阅读其实现

**关键问题**：

- 各渠道如何复用核心 Agent 逻辑？
- 渠道层的抽象接口是什么？

---

### Day 11：长期记忆 + 链路追踪（2-3h）

**目标**：理解两个重要横切关注点

**阅读顺序**：

1. `backend/packages/harness/deerflow/agents/memory/` — 记忆存储/检索/更新
2. `backend/packages/harness/deerflow/tracing/` — LangSmith/Langfuse 集成
3. `backend/app/gateway/routers/memory.py` — 记忆 API

**关键问题**：

- 记忆如何在多轮对话中积累和检索？
- 记忆的存储格式？向量化还是结构化？

---

### Day 12：测试体系 + 质量保障（2h）

**目标**：了解项目测试策略，学习测试写法

**阅读顺序**：

1. `backend/tests/` — 挑选 5-10 个典型测试文件阅读
2. 关注 Agent 行为如何被 mock/测试

---

### Day 13：自己动手——扩展一个 Skill（3-4h）

**目标**：通过实践验证理解

**任务**：基于 `skills/public/` 中的模板，创建一个自定义技能（例如：代码审查 Skill 或竞品分析 Skill）

**验证点**：

- Skill 定义文件格式是否正确
- Agent 能否正确调用该 Skill
- 输出格式是否符合预期

---

### Day 14：整体复盘 + 知识体系输出（2-3h）

**目标**：固化所有知识，形成可输出的理解

**产出物清单**：

1. **架构图**：完整的系统架构图（组件 + 数据流）
2. **核心概念词汇表**：Lead Agent / SubAgent / Skill / Tool / Memory / MCP 等
3. **关键设计决策清单**：为什么用 LangGraph？Skills 和 SubAgent 的分工？沙箱方案选型？
4. **自己的 Skill**：Day 13 完成的扩展

---

## 学习资源优先级

| 资源 | 重要性 | 说明 |
|------|--------|------|
| `config.example.yaml` | ⭐⭐⭐⭐⭐ | 最全面的功能文档 |
| `backend/packages/harness/deerflow/agents/` | ⭐⭐⭐⭐⭐ | 核心逻辑 |
| `backend/app/gateway/app.py` | ⭐⭐⭐⭐ | API 全貌入口 |
| `frontend/src/core/` | ⭐⭐⭐⭐ | 前端状态核心 |
| `skills/public/deep-research/` | ⭐⭐⭐⭐ | 最典型的 Skill 范例 |
| `backend/tests/` | ⭐⭐⭐ | 理解预期行为 |
| LangGraph 官方文档 | ⭐⭐⭐⭐ | 理解状态机框架 |

---

## 每日学习模板

```
上午（1.5h）：阅读代码，边读边注释
下午（1h）：实验/调试，验证理解
晚上（0.5h）：记录笔记，提炼问题
```

**核心学习法**：遇到不懂的设计，**先猜设计者的意图，再看代码验证**——这比直接看代码效率高 3 倍。
