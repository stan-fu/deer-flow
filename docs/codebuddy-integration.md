# CodeBuddy SDK 集成指南

本文档介绍如何在 Deer-Flow 中集成和使用 CodeBuddy SDK 调用大语言模型。

## 概述

CodeBuddy SDK 是腾讯推出的 AI 编程助手 SDK，支持多种大语言模型（如 DeepSeek、GPT 等）。通过本集成，Deer-Flow 可以直接使用 CodeBuddy 的模型能力。

## 安装

### 1. 安装 CodeBuddy SDK

```bash
# 使用 uv（推荐）
cd backend/packages/harness
uv add codebuddy-agent-sdk

# 或使用 pip
pip install codebuddy-agent-sdk
```

### 2. 配置认证

CodeBuddy SDK 支持三种认证方式：

#### 方式一：CLI 登录（推荐）

如果你已经在终端中通过 `codebuddy` 命令完成了交互式登录，SDK 会自动使用该认证信息：

```bash
# 登录 CodeBuddy
codebuddy login
```

#### 方式二：API Key

获取 API Key：
- 海外版：https://www.codebuddy.ai/profile/keys
- 中国版：https://copilot.tencent.com/profile/
- iOA 版：https://tencent.sso.copilot.tencent.com/profile/keys

设置环境变量：

```bash
export CODEBUDDY_API_KEY="your-api-key"
export CODEBUDDY_INTERNET_ENVIRONMENT="cn"  # cn/overseas/ioa
```

#### 方式三：OAuth Client Credentials（企业用户）

适用于企业用户，使用客户端凭证获取访问令牌。

## 配置模型

在 `config.yaml` 中添加 CodeBuddy 模型配置：

```yaml
models:
  - name: codebuddy-deepseek
    display_name: CodeBuddy DeepSeek
    use: deerflow.models.codebuddy_provider:CodeBuddyChatModel
    model: deepseek-v3.1
    api_key: $CODEBUDDY_API_KEY
    timeout: 600.0
    max_turns: 100
    permission_mode: bypassPermissions
    supports_thinking: true
    supports_vision: false

  - name: codebuddy-gpt4
    display_name: CodeBuddy GPT-4
    use: deerflow.models.codebuddy_provider:CodeBuddyChatModel
    model: gpt-4
    api_key: $CODEBUDDY_API_KEY
    timeout: 600.0
    permission_mode: bypassPermissions
    supports_thinking: false
    supports_vision: true
```

### 配置参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | string | 模型在 Deer-Flow 中的唯一标识 |
| `display_name` | string | 显示名称 |
| `use` | string | 模型类路径，固定为 `deerflow.models.codebuddy_provider:CodeBuddyChatModel` |
| `model` | string | CodeBuddy 支持的模型名称，如 `deepseek-v3.1`、`gpt-4` |
| `api_key` | string | API Key（可选，也可通过环境变量设置） |
| `timeout` | float | 请求超时时间（秒） |
| `max_turns` | int | 最大对话轮数 |
| `permission_mode` | string | 权限模式：`default`/`acceptEdits`/`plan`/`bypassPermissions` |
| `supports_thinking` | bool | 是否支持思考模式 |
| `supports_vision` | bool | 是否支持视觉 |

### 权限模式说明

| 模式 | 说明 |
|------|------|
| `default` | 默认模式，所有操作需确认 |
| `acceptEdits` | 自动批准文件编辑，Bash 仍需确认 |
| `plan` | 规划模式，仅允许读取操作 |
| `bypassPermissions` | 跳过所有权限检查（谨慎使用） |

## 使用示例

### 基本使用

配置完成后，Deer-Flow 会自动加载 CodeBuddy 模型。你可以在对话中选择使用：

1. 打开 Deer-Flow 界面
2. 在模型选择下拉框中选择 `CodeBuddy DeepSeek`
3. 开始对话

### API 调用示例

```python
from deerflow.models import create_chat_model

# 创建 CodeBuddy 模型实例
model = create_chat_model("codebuddy-deepseek")

# 调用模型
from langchain_core.messages import HumanMessage

messages = [HumanMessage(content="请解释什么是递归函数")]
response = await model.ainvoke(messages)
print(response.content)
```

### 流式输出

```python
# 流式调用
async for chunk in model.astream(messages):
    print(chunk.content, end="")
```

## 支持的模型

CodeBuddy SDK 支持以下模型（具体以官方文档为准）：

- `deepseek-v3.1` - DeepSeek V3.1
- `deepseek-reasoner` - DeepSeek 推理模型
- `gpt-4` - GPT-4
- `gpt-4o` - GPT-4o
- `claude-3-5-sonnet` - Claude 3.5 Sonnet
- 更多模型请参考 CodeBuddy 官方文档

## 故障排除

### SDK 未安装

```
ImportError: codebuddy-agent-sdk is required
```

解决方案：
```bash
uv add codebuddy-agent-sdk
```

### 认证失败

```
CodeBuddySDKError: Authentication failed
```

解决方案：
1. 检查 `CODEBUDDY_API_KEY` 环境变量是否正确设置
2. 确认 `CODEBUDDY_INTERNET_ENVIRONMENT` 环境变量与 API Key 版本匹配
3. 尝试使用 `codebuddy login` 进行 CLI 登录

### 模型不可用

```
ValueError: Model codebuddy-deepseek not found in config
```

解决方案：
1. 检查 `config.yaml` 中模型配置是否正确
2. 确认 `use` 路径为 `deerflow.models.codebuddy_provider:CodeBuddyChatModel`
3. 重启 Deer-Flow 服务

## 高级用法

### 使用 Session 模式

对于需要保持上下文的场景，可以使用 `CodeBuddyChatModelWithSession`：

```yaml
models:
  - name: codebuddy-session
    display_name: CodeBuddy (Session Mode)
    use: deerflow.models.codebuddy_provider:CodeBuddyChatModelWithSession
    model: deepseek-v3.1
    api_key: $CODEBUDDY_API_KEY
```

### 自定义工具权限

```python
from codebuddy_agent_sdk import CodeBuddyAgentOptions

options = CodeBuddyAgentOptions(
    model="deepseek-v3.1",
    permission_mode="default",  # 更严格的权限控制
    can_use_tool=lambda tool_name, input: tool_name in ["Read", "Glob"]
)
```

## 参考链接

- [CodeBuddy SDK 官方文档](https://www.codebuddy.ai/docs/zh/cli/sdk)
- [CodeBuddy Python SDK 参考](https://www.codebuddy.ai/docs/zh/cli/sdk-python)
- [Deer-Flow 配置文档](./configuration.md)
