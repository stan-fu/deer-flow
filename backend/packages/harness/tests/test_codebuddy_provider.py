"""Tests for CodeBuddy provider."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# Skip all tests if SDK is not installed
try:
    from deerflow.models.codebuddy_provider import (
        CodeBuddyChatModel,
        CodeBuddyChatModelWithSession,
        CODEBUDDY_SDK_AVAILABLE,
    )
    HAS_SDK = CODEBUDDY_SDK_AVAILABLE
except ImportError:
    HAS_SDK = False


pytestmark = pytest.mark.skipif(not HAS_SDK, reason="codebuddy-agent-sdk not installed")


class TestCodeBuddyChatModel:
    """Test cases for CodeBuddyChatModel."""

    def test_initialization(self):
        """Test model initialization."""
        model = CodeBuddyChatModel(
            model="deepseek-v3.1",
            api_key="test-key",
            timeout=300.0,
        )
        assert model.model == "deepseek-v3.1"
        assert model.api_key == "test-key"
        assert model.timeout == 300.0
        assert model._llm_type == "codebuddy"

    def test_identifying_params(self):
        """Test identifying params."""
        model = CodeBuddyChatModel(model="deepseek-v3.1")
        params = model._identifying_params
        assert params["model"] == "deepseek-v3.1"
        assert "timeout" in params
        assert "max_turns" in params

    def test_convert_messages_to_prompt(self):
        """Test message conversion."""
        model = CodeBuddyChatModel()

        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello!"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?"),
        ]

        prompt = model._convert_messages_to_prompt(messages)

        assert "System: You are a helpful assistant." in prompt
        assert "User: Hello!" in prompt
        assert "Assistant: Hi there!" in prompt
        assert "User: How are you?" in prompt

    @pytest.mark.asyncio
    async def test_agenerate(self):
        """Test async generation."""
        model = CodeBuddyChatModel(model="deepseek-v3.1")

        # Mock the SDK query function
        mock_message = MagicMock()
        mock_message.content = [
            MagicMock(spec=["text"], text="Hello, I'm an AI assistant.")
        ]

        with patch("deerflow.models.codebuddy_provider.query") as mock_query:
            mock_query.return_value = AsyncMock()
            mock_query.return_value.__aiter__.return_value = [mock_message]

            messages = [HumanMessage(content="Hello!")]
            result = await model._agenerate(messages)

            assert len(result.generations) == 1
            assert isinstance(result.generations[0].message, AIMessage)

    def test_bind_tools_warning(self):
        """Test that bind_tools shows warning."""
        model = CodeBuddyChatModel()

        with pytest.warns(UserWarning):
            result = model.bind_tools([])
            assert result is model


class TestCodeBuddyChatModelWithSession:
    """Test cases for CodeBuddyChatModelWithSession."""

    def test_initialization(self):
        """Test session model initialization."""
        model = CodeBuddyChatModelWithSession(
            model="deepseek-v3.1",
            api_key="test-key",
        )
        assert model.model == "deepseek-v3.1"
        assert model._llm_type == "codebuddy-session"

    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test session creation and cleanup."""
        model = CodeBuddyChatModelWithSession()

        # Mock the client
        mock_client = AsyncMock()

        with patch(
            "deerflow.models.codebuddy_provider.CodeBuddySDKClient",
            return_value=mock_client,
        ):
            # Ensure client is created
            client = await model._ensure_client()
            assert client is not None
            assert model._client is not None

            # Test close
            await model.aclose()
            assert model._client is None


class TestCodeBuddyProviderWithoutSDK:
    """Test cases when SDK is not available."""

    def test_import_error_without_sdk(self):
        """Test that import fails gracefully without SDK."""
        with patch(
            "deerflow.models.codebuddy_provider.CODEBUDDY_SDK_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError):
                CodeBuddyChatModel()

    def test_session_import_error_without_sdk(self):
        """Test that session model fails gracefully without SDK."""
        with patch(
            "deerflow.models.codebuddy_provider.CODEBUDDY_SDK_AVAILABLE",
            False,
        ):
            with pytest.raises(ImportError):
                CodeBuddyChatModelWithSession()
