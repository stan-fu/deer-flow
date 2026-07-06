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

# nignx代理规则
见 `docker/nginx/nginx.local.conf`，路由规则具体见注释

# 服务协作
## 服务启动 - serve.sh
serve.sh 是 DeerFlow 的统一服务启动器，负责协调所有服务的生命周期管理（启动 / 停止 / 重启）

### 命令行参数
| 参数 | 说明 |
|------|------|
| `--dev` | 开发模式，热重载（默认） |
| `--prod` | 生产模式，无热重载，使用预构建前端 |
| `--gateway` | Gateway 模式（实验性），跳过 LangGraph 独立进程 |
| `--daemon` | 后台运行（nohup），启动后主进程退出 |
| `--skip-install` | 跳过依赖安装，加速重启 |
| `--stop` | 停止所有服务 |
| `--restart` | 先停止再以指定模式重启 |
注：热加载包括前后端热加载
- Frontend 热重载（pnpm run dev）
  - Next.js 开发服务器的标准 HMR（Hot Module Replacement），监听：
    - frontend/ 下所有 .tsx / .ts / .css 等源码文件
    - 保存即刷新，无需重启进程
- Backend 热重载（Gateway，--reload flags）
  - uvicorn 的 --reload 模式，只在 dev + 非 daemon 模式下启用，监听：
    - backend/ 下所有 .py 文件（uvicorn 默认）
    - 额外包含：*.yaml、.env
    - 排除：*.pyc、__pycache__/、sandbox/、.deer-flow/
- LangGraph 不热重载

### 服务架构
标准模式
```
http://localhost:2026
       │
    Nginx :2026 (反向代理)
    ├── /api/langgraph/* → LangGraph :2024 (Agent Runtime)
    └── /api/*          → Gateway    :8001 (REST API)
       Frontend          :3000 (Next.js)
```

Gateway 模式(跳过LangGraph)
```
http://localhost:2026
       │
    Nginx :2026
    ├── /api/langgraph-compat/* → Gateway :8001 (内嵌 Agent Runtime)
    └── /api/*                  → Gateway :8001
       Frontend :3000
```

### 启动流程
```
1. 加载 .env 环境变量
2. 停止现有服务 (stop_all)
3. 检查配置文件 (config.yaml)
4. 执行配置升级 (config-upgrade.sh)
5. 安装依赖
   ├── backend: uv sync
   └── frontend: pnpm install
6. 同步 frontend/.env.local
   ├── Gateway 模式: NEXT_PUBLIC_LANGGRAPH_BASE_URL=/api/langgraph-compat
   └── 标准模式:     移除该变量（回退到 /api/langgraph）
7. 顺序启动服务（每个服务等待端口就绪后才启动下一个）
   ├── LangGraph :2024  (超时 60s，Gateway 模式跳过)
   ├── Gateway   :8001  (超时 30s)
   ├── Frontend  :3000  (超时 120s)
   └── Nginx     :2026  (超时 10s)
```

### 各服务端口速查
| 服务 | 端口 | 进程 |
|------|------|------|
| LangGraph | 2024 | `uv run langgraph dev` |
| Gateway API | 8001 | `uvicorn app.gateway.app:app` |
| Frontend | 3000 | Next.js dev/preview |
| Nginx | 2026 | 反向代理（对外统一入口） |

## 内嵌client设计
> `backend/packages/harness/deerflow/client.py`


## 路由注册
具体见：`backend/app/gateway/app.py`
以`app.include_router(models.router)`为例，添加models.router中的路径，也就是
- 前缀为`/api`：router = APIRouter(prefix="/api", tags=["models"])
- 路径包括
  - "/models"
  - "/models/{model_name}"

完整的路由如下：
| Method | 路径 | 说明 | Router 文件 |
|--------|------|------|------------|
| GET | `/api/models` | 列出所有模型 | models |
| GET | `/api/models/{model_name}` | 获取指定模型详情 | models |
| GET | `/api/mcp/config` | 获取 MCP 配置 | mcp |
| PUT | `/api/mcp/config` | 更新 MCP 配置 | mcp |
| GET | `/api/memory` | 获取记忆数据 | memory |
| POST | `/api/memory/reload` | 重新加载记忆 | memory |
| DELETE | `/api/memory` | 清空记忆 | memory |
| POST | `/api/memory/facts` | 添加事实 | memory |
| DELETE | `/api/memory/facts/{fact_id}` | 删除指定事实 | memory |
| PATCH | `/api/memory/facts/{fact_id}` | 更新指定事实 | memory |
| GET | `/api/memory/export` | 导出记忆 | memory |
| POST | `/api/memory/import` | 导入记忆 | memory |
| GET | `/api/memory/config` | 获取记忆配置 | memory |
| GET | `/api/memory/status` | 获取记忆状态 | memory |
| GET | `/api/skills` | 列出所有 skill | skills |
| POST | `/api/skills/install` | 安装 skill | skills |
| GET | `/api/skills/custom` | 列出自定义 skill | skills |
| GET | `/api/skills/custom/{skill_name}` | 获取自定义 skill 内容 | skills |
| PUT | `/api/skills/custom/{skill_name}` | 编辑自定义 skill | skills |
| DELETE | `/api/skills/custom/{skill_name}` | 删除自定义 skill | skills |
| GET | `/api/skills/custom/{skill_name}/history` | 获取自定义 skill 历史 | skills |
| POST | `/api/skills/custom/{skill_name}/rollback` | 回滚自定义 skill | skills |
| GET | `/api/skills/{skill_name}` | 获取指定 skill 详情 | skills |
| PUT | `/api/skills/{skill_name}` | 更新指定 skill 启用状态 | skills |
| GET | `/api/threads/{thread_id}/artifacts/{path:path}` | 获取 artifact 文件 | artifacts |
| POST | `/api/threads/{thread_id}/uploads` | 上传文件 | uploads |
| GET | `/api/threads/{thread_id}/uploads/list` | 列出已上传文件 | uploads |
| DELETE | `/api/threads/{thread_id}/uploads/{filename}` | 删除上传文件 | uploads |
| POST | `/api/threads` | 创建 thread | threads |
| POST | `/api/threads/search` | 搜索 thread | threads |
| GET | `/api/threads/{thread_id}` | 获取 thread | threads |
| PATCH | `/api/threads/{thread_id}` | 更新 thread | threads |
| DELETE | `/api/threads/{thread_id}` | 删除 thread | threads |
| GET | `/api/threads/{thread_id}/state` | 获取 thread 状态 | threads |
| POST | `/api/threads/{thread_id}/state` | 更新 thread 状态 | threads |
| POST | `/api/threads/{thread_id}/history` | 获取 thread 历史 | threads |
| GET | `/api/agents` | 列出所有 agent | agents |
| GET | `/api/agents/check` | 检查 agent 配置 | agents |
| GET | `/api/agents/{name}` | 获取指定 agent | agents |
| POST | `/api/agents` | 创建 agent | agents |
| PUT | `/api/agents/{name}` | 更新 agent | agents |
| DELETE | `/api/agents/{name}` | 删除 agent | agents |
| GET | `/api/user-profile` | 获取用户 profile | agents |
| PUT | `/api/user-profile` | 更新用户 profile | agents |
| POST | `/api/threads/{thread_id}/suggestions` | 生成对话建议 | suggestions |
| GET | `/api/channels/` | 获取 IM channel 状态 | channels |
| POST | `/api/channels/{name}/restart` | 重启指定 channel | channels |
| POST | `/api/assistants/search` | 搜索 assistant（兼容层） | assistants_compat |
| GET | `/api/assistants/{assistant_id}` | 获取 assistant（兼容层） | assistants_compat |
| GET | `/api/assistants/{assistant_id}/graph` | 获取 assistant graph | assistants_compat |
| GET | `/api/assistants/{assistant_id}/schemas` | 获取 assistant schemas | assistants_compat |
| POST | `/api/threads/{thread_id}/runs` | 创建 run | thread_runs |
| POST | `/api/threads/{thread_id}/runs/stream` | 流式 run | thread_runs |
| POST | `/api/threads/{thread_id}/runs/wait` | 等待 run 完成 | thread_runs |
| GET | `/api/threads/{thread_id}/runs` | 列出 runs | thread_runs |
| GET | `/api/threads/{thread_id}/runs/{run_id}` | 获取指定 run | thread_runs |
| POST | `/api/threads/{thread_id}/runs/{run_id}/cancel` | 取消 run | thread_runs |
| GET | `/api/threads/{thread_id}/runs/{run_id}/join` | 等待 run 结束 | thread_runs |
| GET/POST | `/api/threads/{thread_id}/runs/{run_id}/stream` | 流式获取 run 结果 | thread_runs |
| POST | `/api/runs/stream` | 无状态流式 run | runs |
| POST | `/api/runs/wait` | 无状态等待 run | runs |
| GET | `/health` | 健康检查 | app.py 内联 |

