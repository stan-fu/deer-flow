"""CodeBuddy SDK provider for DeerFlow.

This module provides a LangChain-compatible ChatModel implementation
that uses the CodeBuddy Agent SDK to call large language models.

Usage in config.yaml::

    - name: codebuddy-deepseek
      display_name: CodeBuddy DeepSeek
      use: deerflow.models.codebuddy_provider:CodeBuddyChatModel
      model: deepseek-v3.1
      api_key: $CODEBUDDY_API_KEY
      timeout: 600.0
      supports_thinking: true
      supports_vision: false

Environment Variables:
    CODEBUDDY_API_KEY: API key for CodeBuddy (required if not using CLI auth)
    CODEBUDDY_INTERNET_ENVIRONMENT: Environment type (cn/overseas/ioa)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator, Callable, Literal, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

logger = logging.getLogger(__name__)

# Import CodeBuddy SDK
try:
    from codebuddy_agent_sdk import (
        query,
        CodeBuddySDKClient,
        CodeBuddyAgentOptions,
        AssistantMessage,
        TextBlock,
        ToolUseBlock,
        ToolResultBlock,
    )
    CODEBUDDY_SDK_AVAILABLE = True
except ImportError:
    CODEBUDDY_SDK_AVAILABLE = False
    logger.warning(
        "codebuddy-agent-sdk not installed. "
        "Install with: uv add codebuddy-agent-sdk"
    )


class CodeBuddyChatModel(BaseChatModel):
    """LangChain-compatible ChatModel for CodeBuddy SDK.

    This model wraps the CodeBuddy Agent SDK to provide a standard
    LangChain interface for DeerFlow integration.

    Attributes:
        model: The model name to use (e.g., "deepseek-v3.1")
        api_key: Optional API key for CodeBuddy
        internet_environment: Environment type (cn/overseas/ioa)
        timeout: Request timeout in seconds
        max_turns: Maximum conversation turns
        permission_mode: Permission mode for tool usage
        supports_thinking: Whether the model supports thinking mode
        supports_vision: Whether the model supports vision
    """

    model: str = Field(default="deepseek-v3.1")
    api_key: str | None = Field(default=None)
    internet_environment: Literal["cn", "overseas", "ioa"] | None = Field(default=None)
    timeout: float = Field(default=600.0)
    max_turns: int = Field(default=100)
    permission_mode: Literal[
        "default", "acceptEdits", "plan", "bypassPermissions"
    ] = Field(default="bypassPermissions")
    supports_thinking: bool = Field(default=True)
    supports_vision: bool = Field(default=False)

    # Internal state
    _client: CodeBuddySDKClient | None = None

    def __init__(self, **kwargs: Any):
        """Initialize the CodeBuddy chat model."""
        if not CODEBUDDY_SDK_AVAILABLE:
            raise ImportError(
                "codebuddy-agent-sdk is required. "
                "Install with: uv add codebuddy-agent-sdk"
            )

        super().__init__(**kwargs)

        # Set environment variables if provided
        if self.api_key:
            os.environ["CODEBUDDY_API_KEY"] = self.api_key
        if self.internet_environment:
            os.environ["CODEBUDDY_INTERNET_ENVIRONMENT"] = self.internet_environment

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a chat completion synchronously."""
        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop, run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a chat completion asynchronously."""
        # Convert LangChain messages to prompt
        prompt = self._convert_messages_to_prompt(messages)

        # Build options
        options = CodeBuddyAgentOptions(
            model=self.model,
            permission_mode=self.permission_mode,
            max_turns=self.max_turns,
        )

        # Execute query
        response_text = ""
        tool_calls = []

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                        elif isinstance(block, ToolUseBlock):
                            tool_calls.append({
                                "id": block.id,
                                "name": block.name,
                                "input": block.input,
                            })

                    # Handle tool results if present
                    for block in message.content:
                        if isinstance(block, ToolResultBlock):
                            # Tool results are handled internally by CodeBuddy
                            pass

        except Exception as e:
            logger.error(f"CodeBuddy SDK error: {e}")
            raise

        # Build AIMessage
        ai_message = AIMessage(
            content=response_text,
            additional_kwargs={"tool_calls": tool_calls} if tool_calls else {},
        )

        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Stream chat completion asynchronously."""
        prompt = self._convert_messages_to_prompt(messages)

        options = CodeBuddyAgentOptions(
            model=self.model,
            permission_mode=self.permission_mode,
            max_turns=self.max_turns,
        )

        current_text = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # Yield incremental text
                        delta = block.text[len(current_text):]
                        if delta:
                            current_text = block.text
                            yield ChatGenerationChunk(
                                message=AIMessageChunk(content=delta)
                            )

    def _convert_messages_to_prompt(self, messages: list[BaseMessage]) -> str:
        """Convert LangChain messages to a single prompt string.

        CodeBuddy SDK uses a simple prompt-based interface, so we concatenate
        messages into a conversation format.
        """
        parts = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                parts.append(f"System: {msg.content}")
            elif isinstance(msg, HumanMessage):
                parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                parts.append(f"Assistant: {msg.content}")
            elif isinstance(msg, ToolMessage):
                parts.append(f"Tool ({msg.name}): {msg.content}")
            else:
                parts.append(f"{msg.type}: {msg.content}")

        return "\n\n".join(parts)

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict],
        **kwargs: Any,
    ) -> CodeBuddyChatModel:
        """Bind tools to the model.

        Note: CodeBuddy SDK has its own tool system. This method returns
        self as tools are configured through the SDK's options.
        """
        logger.warning(
            "CodeBuddy SDK uses its own tool system. "
            "Tools should be configured via SDK options."
        )
        return self

    @property
    def _llm_type(self) -> str:
        """Return the type of LLM."""
        return "codebuddy"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Return identifying parameters."""
        return {
            "model": self.model,
            "timeout": self.timeout,
            "max_turns": self.max_turns,
            "permission_mode": self.permission_mode,
        }


class CodeBuddyChatModelWithSession(BaseChatModel):
    """CodeBuddy ChatModel with session support for multi-turn conversations.

    This variant maintains a session across multiple calls, preserving
    conversation context.
    """

    model: str = Field(default="deepseek-v3.1")
    api_key: str | None = Field(default=None)
    internet_environment: Literal["cn", "overseas", "ioa"] | None = Field(default=None)
    timeout: float = Field(default=600.0)
    max_turns: int = Field(default=100)
    permission_mode: Literal[
        "default", "acceptEdits", "plan", "bypassPermissions"
    ] = Field(default="bypassPermissions")
    supports_thinking: bool = Field(default=True)
    supports_vision: bool = Field(default=False)

    _client: CodeBuddySDKClient | None = None

    def __init__(self, **kwargs: Any):
        """Initialize with session support."""
        if not CODEBUDDY_SDK_AVAILABLE:
            raise ImportError(
                "codebuddy-agent-sdk is required. "
                "Install with: uv add codebuddy-agent-sdk"
            )

        super().__init__(**kwargs)

        if self.api_key:
            os.environ["CODEBUDDY_API_KEY"] = self.api_key
        if self.internet_environment:
            os.environ["CODEBUDDY_INTERNET_ENVIRONMENT"] = self.internet_environment

    async def _ensure_client(self) -> CodeBuddySDKClient:
        """Ensure the SDK client is initialized."""
        if self._client is None:
            options = CodeBuddyAgentOptions(
                model=self.model,
                permission_mode=self.permission_mode,
                max_turns=self.max_turns,
            )
            self._client = CodeBuddySDKClient(options=options)
            await self._client.__aenter__()
        return self._client

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate with session persistence (sync wrapper)."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(
            self._agenerate(messages, stop, run_manager, **kwargs)
        )

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate with session persistence."""
        client = await self._ensure_client()

        # Convert last message to query
        last_message = messages[-1]
        if isinstance(last_message, HumanMessage):
            prompt = last_message.content
        else:
            prompt = self._convert_messages_to_prompt(messages)

        await client.query(prompt)

        response_text = ""
        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        response_text += block.text

        ai_message = AIMessage(content=response_text)
        generation = ChatGeneration(message=ai_message)
        return ChatResult(generations=[generation])

    def _convert_messages_to_prompt(self, messages: list[BaseMessage]) -> str:
        """Convert messages to prompt."""
        parts = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                parts.append(f"System: {msg.content}")
            elif isinstance(msg, HumanMessage):
                parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                parts.append(f"Assistant: {msg.content}")
            elif isinstance(msg, ToolMessage):
                parts.append(f"Tool ({msg.name}): {msg.content}")
            else:
                parts.append(f"{msg.type}: {msg.content}")
        return "\n\n".join(parts)

    @property
    def _llm_type(self) -> str:
        return "codebuddy-session"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "timeout": self.timeout,
            "max_turns": self.max_turns,
        }

    async def aclose(self) -> None:
        """Close the session."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
