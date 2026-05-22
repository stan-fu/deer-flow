# 快速启动


# 配置项
## 工具组与工具配置
工具组：权限分组
工具配置：
- name：工具名称
- group: 指定分组
- use: 指定工具，实际上是python模块导入路径，例如`deerflow.community.ddg_search.tools:web_search_tool`， 实际路径是`deerflow/community/ddg_search/tools.py`，
- max_results、timeout: 工具调用限制

tool_serach: 在`deerflow/tools/builtins/tool_search.py`中实现，属于内置工具
- 作用：搜索工具
- 机制：启用后，MCP工具延迟加载，而内置工具以及Config中配置的基础工具保持启动加载

## 沙箱
三种类型：
- LocalSandboxProvider: 本地沙箱, 无隔离，直接在宿主机执行；本地开发时使用
- AioSandboxProvider: 容器沙箱, 使用Docker/Apple容器执行；生产环境中使用
- AioSandboxProvider+provisioner_url: 云沙箱, k8s pod级隔离，大规模集群部署

沙箱设计：

```
Agent 层（Lead Agent / SubAgent）
└─ 调用 tools：bash, read_file, write_file...

Tool 层（sandbox/tools.py）
└─ 虚拟路径解析 → 安全校验 → 调用 Sandbox 执行

Sandbox 抽象层（sandbox/sandbox.py）
└─ 抽象类：execute_command, read_file, list_dir...

Provider 层（sandbox/sandbox_provider.py）
└─ 管理 Sandbox 生命周期：acquire / get / release

具体实现
├─ LocalSandboxProvider → LocalSandbox（宿主机）
└─ AioSandboxProvider → 远程容器沙箱
```

虚拟路径映射（核心设计）
Agent 看到的都是虚拟路径，实际映射到宿主机不同位置：

| 虚拟路径 | 实际映射 | 权限 |
|------|------|------|
| `/mnt/user-data/workspace` | `{backend}/threads/{thread_id}/user-data/workspace` | 读写 |
| `/mnt/user-data/uploads` | `{backend}/threads/{thread_id}/user-data/uploads` | 读写 |
| `/mnt/user-data/outputs` | `{backend}/threads/{thread_id}/user-data/outputs` | 读写 |
| `/mnt/skills` | `{project}/skills` | 只读 |
| `/mnt/acp-workspace` | `{backend}/acp-workspace` | 只读 |


## subagent
配置只暴露了两个参数:timeout_seconds 和 max_turns, Subagent 是 DeerFlow 的内置角色（类似于预设模板），它的提示词、工具集、工作流格式都是框架设计的一部分，不应该由用户随意改动——否则可能破坏 Lead Agent 对它的调用契约。

在deerflow中，subagent 是框架内置的执行者，用户不敢值其角色定义、工作流等；用户自定义的agent，是Lead Agent，负责调度subagent

## ACP Agent（外部ACP代理）
ACP = Agent Capability Protocol，允许 DeerFlow 调用外部 CLI Agent（如 Claude Code、Codex）作为子代理：
```yaml
acp_agents:
  claude_code:
    command: npx
    args: ["-y", "@zed-industries/claude-agent-acp"]
    description: Claude Code for implementation and debugging
```

##  summarization
达到上下文限制时自动触发对话总结，可配置项：
- 触发阈值（token大小）
- keep策略：
  - messages：保留最近N条消息
  - tokens：保留最近N个token的原始消息
  - fraction：保留最近N%的原始消息
- summary策略：保留是指最近的对话原样保留，更早的对话总结压缩

## memory
目的：个性化回复
记忆范围：用户上下文、对话历史
配置项：
- storage_path: 记忆存储路径
- max_facts: 最多存储 100 条事实，超旧时会被淘汰
- fact_confidence_threshold: 事实置信度门槛。LLM 从对话中提取事实时打分，>= threshold 才存
- injection_enabled: 是否开启记忆注入系统Prompt
- max_injection_tokens: 最大注入token数

## checkpointer
这是为 DeerFlow 内嵌客户端（DeerFlowClient）配置对话状态持久化的功能，底层基于 LangGraph 的 checkpoint 机制

实现原理：
LangGraph Agent 每次执行时会产生"状态快照"（thread state），checkpointer 决定这些快照存在哪里。配置后可实现：
- 多轮对话跨重启保持连续性（用户下次打开继续上次进度）
- 中断恢复（Agent 被打断后可从断点继续）

checkpointer类型
- memory：进程内存，重启后会丢失，无外部依赖，场景 - 开发调试、无状态场景
- sqlite: 本地文件，依赖`langgraph-checkpoint-sqlite`，场景 - 单机部署，个人使用
- postgres：数据库，依赖`langgraph-checkpoint-postgres + psycopg`，场景 - 多进程、生成环境

## guardrails
权限检查，agent调用任何工具前，都会检查
```
Agent 决定调用工具
       ↓
  Guardrail Provider
  evaluate(tool_call)
       ↓
  allow → 正常执行
  deny  → 拒绝，返回错误给 Agent
```
三种Guardrail Provider对比：
- 内置 AllowlistProvider：黑名单机制
- OAP（Open Agent Passport）标准：基于开放标准协议，任何符合 OAP 规范的实现都能接入；场景：企业级统一Agent安全策略
- CustomProvider：自定义Provider


## 其他
- skill配置：指定skill安装路径、沙箱挂在路径
- skill self-evolution：agent自主创建/修改skill，是将任务执行的经验沉淀为skill，而不是修改引入的外部skill
- model配置：指定模型
  - use：model引入，引入方式
    - 自定义provider：有非标准字段、bug或接入独立SDK（例如Codebuddy），自定义的provider
    - 官方provider：直接引入LangChain官方包
  - 其他：具体的模型配置
- im channels：支持多种IM渠道
