"""Gemini Developer API configuration; credentials never enter prompts."""
import os
from dotenv import load_dotenv
from server.paths import PROJECT_ROOT


class ConfigurationError(ValueError):
    pass


def create_model(*, timeout: float = 60, max_output_tokens: int = 2048):
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    # Support the existing project configuration location without moving secrets.
    load_dotenv(PROJECT_ROOT / "server/semantic_search/.env", override=False)
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key or not key.strip():
        raise ConfigurationError("Set GOOGLE_API_KEY or GEMINI_API_KEY in the environment or project-root .env")
    name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    if not name:
        raise ConfigurationError("GEMINI_MODEL must not be empty")
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=name, api_key=key, vertexai=False,
        timeout=timeout, max_retries=0, max_tokens=max_output_tokens,
        response_mime_type="application/json"), name
