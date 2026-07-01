import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class OpenAIConfig(BaseModel):
    """Configuration for the OpenAI provider."""

    model: str = Field(..., min_length=1, description="Chat model name (e.g. 'gpt-4o-mini')")
    base_url: str | None = Field(
        default=None,
        description="Optional custom base URL for OpenAI-compatible local servers",
    )
    api_key_env: str = Field(
        default="OPENAI_API_KEY",
        description="Name of the environment variable holding the API key",
    )


class LlamaCppConfig(BaseModel):
    """Configuration for local models via an OpenAI-compatible API server."""

    model: str = Field(..., min_length=1, description="Model name as expected by the local server")
    base_url: str = Field(..., description="OpenAI-compatible API endpoint (e.g. 'http://localhost:8080/v1')")
    extra_body: dict | None = Field(
        default=None,
        description="Extra fields to pass in every request body (e.g. {'chat_template_kwargs': {'enable_thinking': false}})",
    )


class VectorDBConfig(BaseModel):
    """Configuration for the ChromaDB vector store and embeddings."""

    embedding_provider: str = Field(
        default="openai",
        description="Provider for embeddings: 'openai' (remote or local-compatible) or 'huggingface' (local, no API key required)",
    )
    embedding_name: str = Field(..., min_length=1, description="Embedding model name")
    embedding_base_url: str | None = Field(
        default=None,
        description="Optional custom base URL for OpenAI-compatible local embedding servers (e.g. Ollama, llama.cpp)",
    )
    embedding_api_key_env: str = Field(
        default="OPENAI_API_KEY",
        description="Name of the environment variable holding the embeddings API key (only used for 'openai' provider)",
    )
    docs_path: Path = Field(..., description="Path to the source documents directory")
    docs_glob: str = Field(default="**/*.md", min_length=1, description="Glob pattern for document discovery")
    db_path: Path = Field(..., description="Path to the ChromaDB persistence directory")
    collection_name: str = Field(..., min_length=1, description="ChromaDB collection name")


class AgentConfig(BaseModel):
    """Configuration for agent runtime behaviour."""

    memory_path: Path = Field(..., description="Path to the persistent memory JSON file")
    history_window: int = Field(default=10, ge=1, description="Number of messages to retain in conversation history")


class Config(BaseModel):
    """Top-level configuration model for the AI agent application."""

    provider: str = Field(..., description="Active LLM provider: 'openai' or 'llamacpp'")
    openai: OpenAIConfig | None = None
    llamacpp: LlamaCppConfig | None = None
    vectordb: VectorDBConfig
    agent: AgentConfig

    @model_validator(mode="after")
    def validate_provider_config(self) -> "Config":
        if self.provider == "openai" and self.openai is None:
            raise ValueError("'openai' section is required when provider is 'openai'")
        if self.provider == "llamacpp" and self.llamacpp is None:
            raise ValueError("'llamacpp' section is required when provider is 'llamacpp'")
        if self.provider not in ("openai", "llamacpp"):
            raise ValueError(f"Unknown provider '{self.provider}'. Must be 'openai' or 'llamacpp'.")
        return self

    @staticmethod
    def load_from_file(file_path: str) -> "Config":
        """Load configuration from a JSON file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
