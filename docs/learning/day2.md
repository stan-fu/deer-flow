# Day 2：Agent 系统核心 — Lead Agent 与 SubAgent 深度分析

> **目标**：理解 Lead Agent + SubAgent 的设计哲学、架构模式、完整调用链路

---

## 一、整体架构概览

DeerFlow 的 Agent 系统采用 **"主编排器 + 子执行器"** 的二层架构：

```
┌─────────────────────────────────────────────────────────┐
│                      Lead Agent                         │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ 模型层   │  │ 中间件链 │  │ Prompt 模板引擎    │    │
│  │ (LLM)    │  │ (9+ MW)  │  │ (SubAgent/Skills)  │    │
│  └──────────┘  └──────────┘  └────────────────────┘    │
│                          │                              │
│              Tool Call: task(description,                │
│                 prompt, subagent_type)                   │
│                          │                              │
├──────────────────────────┼──────────────────────────────┤
│                      SubAgent 层                         │
│  ┌───────────────┐  ┌───────────────┐                   │
│  │ general-purpose│  │     bash      │                   │
│  │ (全工具继承)   │  │ (沙箱工具子集)│                   │
│  └───────────────┘  └───────────────┘                   │
│       ↑ 同一个 SubagentExecutor 引擎驱动 ↑              │
└─────────────────────────────────────────────────────────┘
```

**核心设计理念**：Lead Agent 是"指挥者"，只负责**拆解任务 + 分发 + 合成结果**；SubAgent 是"执行者"，在独立上下文中**自主完成子任务**。

---

## 二、Lead Agent 详细设计

### 2.1 入口函数：`make_lead_agent()`

完整路径：[agent.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py)

```python
def make_lead_agent(config: RunnableConfig):
```

这是 **Agent 工厂函数**，由 LangGraph 在每次请求时调用。它从 `config` 中提取运行时参数，构造并返回一个 Agent 实例。

### 2.2 配置解析层次

Lead Agent 的配置遵循 **三层优先级**（从高到低）：

```
请求参数（RunnableConfig）> Agent 配置（agents.yaml）> 全局默认（config.yaml）
```

核心配置项：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `thinking_enabled` | `True` | 是否启用模型思考模式（extended thinking） |
| `reasoning_effort` | `None` | 推理力度（low/medium/high） |
| `model_name` | 全局默认模型 | 可被请求级 model 参数覆盖 |
| `is_plan_mode` | `False` | 计划模式，启用 TodoList 中间件 |
| `subagent_enabled` | `False` | **核心开关**：是否启用 SubAgent 能力 |
| `max_concurrent_subagents` | `3` | 单轮最大并行 SubAgent 数 |
| `is_bootstrap` | `False` | 是否为 Bootstrap 模式（创建自定义 Agent） |

### 2.3 中间件链（Middleware Pipeline）

中间件是 LangGraph Agent 的**横切关注点**机制，执行顺序至关重要。完整的中间件链注释说明了精确的排列原因：

```
ThreadDataMiddleware → SandboxMiddleware → UploadsMiddleware
→ DanglingToolCallMiddleware → SummarizationMiddleware
→ TodoListMiddleware → TokenUsageMiddleware → TitleMiddleware
→ MemoryMiddleware → ViewImageMiddleware → DeferredToolFilterMiddleware
→ SubagentLimitMiddleware → LoopDetectionMiddleware
→ ToolErrorHandlingMiddleware → ClarificationMiddleware
```

按功能分类详解：

| 中间件 | 触发时机 | 核心作用 |
|--------|---------|---------|
| `ThreadDataMiddleware` | before_model | 注入 thread_id，确保沙箱中的数据隔离 |
| `SandboxMiddleware` | before_model | 管理沙箱环境生命周期 |
| `UploadsMiddleware` | before_model | 将用户上传文件列表注入到上下文 |
| `DanglingToolCallMiddleware` | before_model | 修复缺少 ToolMessage 的孤悬 tool_call，防止模型看到不一致的历史 |
| `SummarizationMiddleware` | after_model | 上下文过长时自动摘要，控制 token 消耗 |
| `TodoMiddleware` | before/after_model | **计划模式专用**：管理 todo list，跟踪多步骤任务进度 |
| `TokenUsageMiddleware` | after_model | 统计 token 用量，用于成本监控 |
| `TitleMiddleware` | after_model（首轮） | 根据首轮对话自动生成会话标题 |
| `MemoryMiddleware` | after_model | 分析对话、提取记忆、异步存入长期记忆 |
| `ViewImageMiddleware` | before_model | 为支持视觉的模型注入图片 base64 数据 |
| `DeferredToolFilterMiddleware` | wrap_tool_call | 隐藏延迟加载工具的 schema，减小模型上下文 |
| `SubagentLimitMiddleware` | after_model | **关键**：截断超过限制的 `task` 工具调用（硬限制 2-4） |
| `LoopDetectionMiddleware` | wrap_tool_call | 检测并打破重复工具调用死循环 |
| `ToolErrorHandlingMiddleware` | wrap_tool_call | 将工具异常转换为 ToolMessage，避免 Agent 崩溃 |
| `ClarificationMiddleware` | wrap_tool_call | **始终最后**：拦截 `ask_clarification` 调用，中断执行等待用户回复 |

### 2.4 Prompt 模板引擎

见 [prompt.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py) 中的 `SYSTEM_PROMPT_TEMPLATE` 和 `apply_prompt_template()`。

Prompt 采用**模块化拼接**设计，包含以下可替换插槽：

```
<role> → Agent 身份定义
<soul> → 可选的自定义人格（来自 SOUL.md）
<memory> → 长期记忆上下文注入
<thinking_style> → 思考风格指导
<clarification_system> → 澄清机制规则（强制先澄清后执行）
<skill_system> → 可用 Skills 列表
<available-deferred-tools> → 延迟工具列表
<subagent_system> → SubAgent 编排指南（仅 subagent_enabled=True 时）
<working_directory> → 工作目录说明
<response_style> → 响应风格
<citations> → 引用规则
<critical_reminders> → 关键提醒
<current_date> → 当前日期
```

### 2.5 Bootstrap 模式 vs 普通模式

```python
if is_bootstrap:
    # Bootstrap: 最小化 prompt + setup_agent 工具
    # 用于首次创建自定义 Agent 的引导流程
    return create_agent(
        ...
        tools=... + [setup_agent],
        system_prompt=apply_prompt_template(..., available_skills={"bootstrap"}),
    )

# 普通模式: 完整 prompt + 全量工具
return create_agent(
    model=...,
    tools=get_available_tools(...),
    middleware=_build_middlewares(...),
    system_prompt=apply_prompt_template(...),
    state_schema=ThreadState,
)
```

Bootstrap 模式是一个**精简版 Agent**，只包含 `setup_agent` 工具，用于引导用户完成首次 Agent 配置。

---

## 三、SubAgent 系统详细设计

### 3.1 架构层次图

```
task_tool (LangChain Tool)
    │
    ├─ 1. 解析参数，获取 SubagentConfig
    ├─ 2. 从父 Agent 提取上下文 (sandbox/thread/model/trace)
    ├─ 3. 过滤工具（禁止嵌套 task/ask_clarification）
    ├─ 4. 创建 SubagentExecutor
    ├─ 5. execute_async() → 后台线程池启动
    └─ 6. 轮询结果 + 流式推送 progress 事件
            │
            ▼
    SubagentExecutor
        ├─ _create_agent()   → 创建独立的 LangChain Agent
        ├─ _build_initial_state() → 继承父 Agent 状态
        ├─ _aexecute()       → 异步流式执行
        ├─ execute()         → 同步包装（含事件循环隔离）
        └─ execute_async()   → 后台执行入口
```

### 3.2 核心数据结构

#### SubagentConfig（[config.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/config.py)）

```python
@dataclass
class SubagentConfig:
    name: str                    # 唯一标识: "general-purpose" | "bash"
    description: str             # 给 LLM 看的用途说明
    system_prompt: str           # SubAgent 自身的 system prompt
    tools: list[str] | None      # 工具白名单，None=继承父Agent全部工具
    disallowed_tools: list[str]  # 工具黑名单，默认禁用 ["task"]
    model: str                   # 模型，"inherit" 表示使用父Agent模型
    max_turns: int               # 最大对话轮数，general-purpose=100, bash=60
    timeout_seconds: int         # 超时时间，默认 900s（15分钟）
```

#### SubagentStatus（状态机）

```python
class SubagentStatus(Enum):
    PENDING   → RUNNING → COMPLETED
                        → FAILED
                        → CANCELLED
                        → TIMED_OUT
```

#### SubagentResult（执行结果）

```python
@dataclass
class SubagentResult:
    task_id: str                 # 唯一任务ID
    trace_id: str                # 分布式追踪ID（关联父子日志）
    status: SubagentStatus       # 当前状态
    result: str | None           # 最终结果文本
    error: str | None            # 错误信息
    started_at: datetime | None
    completed_at: datetime | None
    ai_messages: list[dict]      # 执行过程中的 AI 消息（用于实时进度推送）
    cancel_event: threading.Event # 协作式取消信号
```

### 3.3 线程池三层架构

DeerFlow 为 SubAgent 执行设计了**三层线程池隔离**：

```
_scheduler_pool  (3 workers)  ← 调度层：接收 execute_async 请求
        │
        ├── submit(execution) ──→ _execution_pool (3 workers)
        │                              │  执行层：实际运行 SubAgent
        │                              │  带超时控制 (Future.result(timeout))
        │
        └── (当检测到已在事件循环中)
            ──→ _isolated_loop_pool (3 workers)
                   隔离层：在全新事件循环中执行，避免 httpx 等共享资源冲突
```

**关键设计决策：事件循环隔离**

```python
def execute(self, task, result_holder=None):
    try:
        loop = asyncio.get_running_loop()  # 检测是否已在事件循环中
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已在事件循环中 → 使用隔离线程池
        future = _isolated_loop_pool.submit(
            self._execute_in_isolated_loop, task, result_holder
        )
        return future.result()

    # 标准路径：无运行中的事件循环，直接 asyncio.run
    return asyncio.run(self._aexecute(task, result_holder))
```

`_execute_in_isolated_loop` 会创建**全新的事件循环**，并在 finally 中彻底清理，避免 asyncio 原语（如 httpx 客户端）与父事件循环冲突。

### 3.4 执行流程（完整时序）

```mermaid
sequenceDiagram
    participant U as User
    participant LA as Lead Agent
    participant TT as task_tool
    participant SP as Scheduler Pool
    participant EP as Execution Pool
    participant SA as SubAgent
    participant FW as Frontend(SSE)

    U->>LA: 复杂问题请求
    LA->>LA: 思考→拆解为N个子任务
    LA->>TT: task(description, prompt, "general-purpose")
    Note over LA: 最多同时发起 max_concurrent 个 task 调用

    TT->>TT: 获取 SubagentConfig
    TT->>TT: 从父Agent提取上下文<br/>(sandbox/thread/model/trace)
    TT->>TT: 过滤工具(禁用task/ask_clarification)
    TT->>TT: 创建 SubagentExecutor

    TT->>SP: execute_async(task, task_id)
    SP-->>TT: 返回 task_id
    SP->>EP: submit(execute)

    TT->>FW: SSE: task_started

    loop 轮询 (每5秒)
        TT->>TT: get_background_task_result(task_id)
        alt 有新AI消息
            TT->>FW: SSE: task_running (message)
        end
    end

    EP->>SA: _create_agent() + astream()
    SA->>SA: 自主执行多轮 Tool Call
    SA-->>EP: final_state (AIMessage)

    EP-->>SP: SubagentResult (COMPLETED)

    TT->>FW: SSE: task_completed
    TT-->>LA: "Task Succeeded. Result: ..."

    LA->>LA: 合成所有 SubAgent 结果
    LA->>U: 最终答案
```

### 3.5 协作式取消机制

SubAgent 不能通过 `Future.cancel()` 强制终止（线程无法被强制杀死），因此采用**协作式取消**：

```python
# 1. 设置取消信号
def request_cancel_background_task(task_id):
    result.cancel_event.set()

# 2. SubAgent 在每次 astream 迭代时检查
async for chunk in agent.astream(state, ...):
    if result.cancel_event.is_set():
        # 停止执行，标记为 CANCELLED
        result.status = SubagentStatus.CANCELLED
        return result
```

注意：取消只在 `astream` 的迭代边界生效，单个工具调用内部无法被中断。

---

## 四、两种内置 SubAgent 对比

| 维度 | general-purpose | bash |
|------|----------------|------|
| **用途** | 通用多步骤任务（研究/代码探索/文件操作/分析） | 命令行执行（git/npm/docker/build/test） |
| **工具白名单** | `None`（继承父Agent全部工具） | `["bash", "ls", "read_file", "write_file", "str_replace"]` |
| **工具黑名单** | `["task", "ask_clarification", "present_files"]` | `["task", "ask_clarification", "present_files"]` |
| **模型** | `"inherit"`（使用父Agent的模型） | `"inherit"` |
| **最大轮数** | 100 turns | 60 turns |
| **何时使用** | 需要多步推理、工具组合的复杂任务 | 需要隔离执行一系列 shell 命令 |
| **可用条件** | 始终可用 | 仅当宿主 bash 被允许时（`is_host_bash_allowed()`） |

### 工具过滤逻辑

```python
def _filter_tools(all_tools, allowed, disallowed):
    if allowed is not None:
        filtered = [t for t in filtered if t.name in allowed_set]  # 白名单优先
    if disallowed is not None:
        filtered = [t for t in filtered if t.name not in disallowed_set]  # 黑名单排除
    return filtered
```

**关键设计**：所有 SubAgent 的 `disallowed_tools` 都包含 `"task"`，**彻底防止 SubAgent 递归嵌套**，避免无限创建子代理的爆炸问题。

---

## 五、并发控制：双重保险

DeerFlow 采用 **Prompt 层 + 中间件层** 双重机制控制 SubAgent 并发数：

### 5.1 Prompt 层（软限制）

在 `<subagent_system>` 段落中明确告知 LLM：

```
⛔ HARD CONCURRENCY LIMIT: MAXIMUM 3 `task` CALLS PER RESPONSE.
- Before launching, COUNT your sub-tasks
- If count > 3: Pick the 3 most important for this turn
- Multi-batch execution for >3 sub-tasks
```

同时引导 LLM 遵循 **DECOMPOSE → COUNT → BATCH → EXECUTE → SYNTHESIZE** 的工作流。

### 5.2 中间件层（硬截断）

[SubagentLimitMiddleware](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py) 在 `after_model` 时执行：

```python
class SubagentLimitMiddleware(AgentMiddleware):
    def _truncate_task_calls(self, state):
        # 统计所有 task 调用
        task_indices = [i for i, tc in enumerate(tool_calls)
                        if tc.get("name") == "task"]
        if len(task_indices) <= self.max_concurrent:
            return None  # 未超限，放行

        # 只保留前 max_concurrent 个，其余丢弃
        indices_to_drop = set(task_indices[self.max_concurrent:])
        truncated = [tc for i, tc in enumerate(tool_calls)
                     if i not in indices_to_drop]
        # 替换原始 AIMessage
        return {"messages": [last_msg.model_copy(
            update={"tool_calls": truncated}
        )]}
```

**并发数合法范围**：`[2, 4]`，可通过 `max_concurrent_subagents` 配置。

---

## 六、状态传递与继承

SubAgent 继承父 Agent 的关键运行时状态：

```python
# task_tool 中提取父上下文
sandbox_state = runtime.state.get("sandbox")       # 沙箱环境
thread_data  = runtime.state.get("thread_data")    # 工作目录路径
thread_id    = runtime.context.get("thread_id")    # 线程ID
parent_model = metadata.get("model_name")          # 父模型名
trace_id     = metadata.get("trace_id")            # 分布式追踪ID
```

这些状态被传递给 `SubagentExecutor`，在 `_build_initial_state()` 中注入到 SubAgent 的初始状态：

```python
def _build_initial_state(self, task):
    state = {"messages": [HumanMessage(content=task)]}
    if self.sandbox_state:
        state["sandbox"] = self.sandbox_state   # 共享沙箱
    if self.thread_data:
        state["thread_data"] = self.thread_data # 共享工作目录
    return state
```

---

## 七、Streaming 与实时反馈

`task_tool` 通过 `get_stream_writer()` 向前端推送 SSE 事件，实现 SubAgent 执行进度的实时可视化：

| SSE 事件类型 | 触发时机 | 携带数据 |
|-------------|---------|---------|
| `task_started` | SubAgent 开始执行 | `task_id`, `description` |
| `task_running` | SubAgent 产出新的 AI 消息 | `task_id`, `message`, `message_index`, `total_messages` |
| `task_completed` | SubAgent 成功完成 | `task_id`, `result` |
| `task_failed` | SubAgent 执行失败 | `task_id`, `error` |
| `task_cancelled` | SubAgent 被取消 | `task_id`, `error` |
| `task_timed_out` | SubAgent 超时 | `task_id`, `error` |

轮询间隔为 **5 秒**，每个周期检查新消息并推送增量更新。

---

## 八、关键设计决策总结

| 决策 | 方案 | 理由 |
|------|------|------|
| **为何用 SubAgent 而非直接工具调用？** | Lead Agent 通过 `task` tool 委托 SubAgent | 上下文隔离：复杂任务的中间推理不污染主对话窗口；并行执行：多个 SubAgent 可同时运行 |
| **如何防止递归嵌套？** | 所有 SubAgent 的 `disallowed_tools` 包含 `"task"` | 从工具层面彻底阻断 SubAgent 再创建 SubAgent |
| **如何控制并发？** | Prompt 软限制 + SubagentLimitMiddleware 硬截断 | 双重保险：LLM 可能不遵守 prompt 指令，中间件保证上限 |
| **为何用协作式取消？** | `threading.Event` + astream 迭代检查 | Python 线程无法被强制杀死，只能在安全的 yield 点退出 |
| **为何需要三层线程池？** | Scheduler / Execution / IsolatedLoop | 调度解耦 + 超时控制 + 事件循环隔离，防止 httpx 等异步客户端冲突 |
| **SubAgent 如何选择模型？** | `model="inherit"` 使用父 Agent 模型 | 保持推理能力一致性，也可独立指定模型 |
| **为何 SubAgent 禁用 thinking？** | `thinking_enabled=False` | SubAgent 是执行者，无需深度推理；减少 token 消耗和延迟 |

---

## 九、源码文件索引

| 文件 | 核心内容 |
|------|---------|
| [agent.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py) | `make_lead_agent()` 工厂函数、中间件链构建 |
| [prompt.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/prompt.py) | System Prompt 模板引擎、SubAgent 编排指南 |
| [task_tool.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/tools/builtins/task_tool.py) | `task` 工具实现、轮询逻辑、SSE 事件推送 |
| [executor.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/executor.py) | `SubagentExecutor` 核心执行引擎、线程池管理 |
| [config.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/config.py) | `SubagentConfig` 数据结构定义 |
| [registry.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/registry.py) | SubAgent 注册表、配置覆盖 |
| [general_purpose.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/builtins/general_purpose.py) | `general-purpose` SubAgent 定义 |
| [bash_agent.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/subagents/builtins/bash_agent.py) | `bash` SubAgent 定义 |
| [subagent_limit_middleware.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/middlewares/subagent_limit_middleware.py) | 并发数硬截断中间件 |
| [thread_state.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/thread_state.py) | `ThreadState` 共享状态定义 |
| [factory.py](/Users/cooper/workload/deer-flow/backend/packages/harness/deerflow/agents/factory.py) | `create_deerflow_agent()` SDK 级工厂入口 |

---

## 十、动手实验建议

1. **开启 SubAgent 模式**：在请求参数中设置 `subagent_enabled=True`，发送一个复杂研究问题，观察 LangSmith trace 中 Lead Agent 如何拆分子任务。

2. **跟踪一次完整的 task 调用**：在 `task_tool` 的轮询循环中打断点，观察 SubAgent 的执行进度如何通过 SSE 事件推送到前端。

3. **测试并发限制**：构造一个需要 5 个以上子任务的问题，验证 `SubagentLimitMiddleware` 是否正确截断。

4. **测试取消机制**：在 SubAgent 执行期间发送取消请求，观察 `cancel_event` 如何被检查并安全退出。
