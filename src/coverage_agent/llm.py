"""Chat-model factory for Groq, Together.ai, Gemini, and Ollama."""

import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from coverage_agent.errors import CoverageError, classify_provider_error

PROVIDERS = ("groq", "together", "gemini", "ollama")
ROLES = ("planner", "editor", "repair", "strategist")

DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "together": "openai/gpt-oss-120b",
    "gemini": "gemini-3.8-flash",
    "ollama": "qwen2.5:7b",
}

KEY_ENV = {
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

MODEL_ENV = {
    "groq": "GROQ_MODEL",
    "together": "TOGETHER_MODEL",
    "gemini": "GEMINI_MODEL",
    "ollama": "OLLAMA_MODEL",
}

ROLE_ENV = {
    "planner": "PLANNER_MODEL",
    "editor": "EDITOR_MODEL",
    "repair": "REPAIR_MODEL",
    "strategist": "STRATEGIST_MODEL",
}


@dataclass
class ChatHandle:
    provider: str
    model: str
    role: str | None
    client: Any


def resolve_provider(provider: str | None = None) -> str:
    name = (provider or os.getenv("LLM_PROVIDER") or "groq").strip().lower()
    if name not in PROVIDERS:
        known = ", ".join(PROVIDERS)
        raise CoverageError("provider_error", f"Unknown provider '{name}'. Use one of: {known}.")
    return name


def resolve_model(provider: str, role: str | None = None, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    if role:
        override = os.getenv(ROLE_ENV[role], "").strip()
        if override:
            return override
    configured = os.getenv(MODEL_ENV[provider], "").strip()
    return configured or DEFAULT_MODELS[provider]


def build_chat_model(provider: str, model: str, api_key: str | None) -> Any:
    temperature = 0
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(model=model, api_key=api_key, temperature=temperature)
    if provider == "together":
        from langchain_together import ChatTogether

        return ChatTogether(model=model, api_key=api_key, temperature=temperature)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=temperature)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return ChatOllama(model=model, base_url=base_url, temperature=temperature)
    raise CoverageError("provider_error", f"Unknown provider '{provider}'.")


def get_chat_model(
    provider: str | None = None,
    role: str | None = None,
    model: str | None = None,
) -> ChatHandle:
    load_dotenv()
    name = resolve_provider(provider)
    model_id = resolve_model(name, role=role, explicit=model)
    api_key = os.getenv(KEY_ENV[name], "").strip() if name in KEY_ENV else None
    if name in KEY_ENV and not api_key:
        env_name = KEY_ENV[name]
        raise CoverageError("missing_key", f"{name} needs {env_name} in the environment.")
    client = build_chat_model(name, model_id, api_key)
    return ChatHandle(provider=name, model=model_id, role=role, client=client)


def handles_for(provider: str | None) -> dict[str, ChatHandle]:
    return {role: get_chat_model(provider, role=role) for role in ROLES}


def invoke_structured(
    handle: ChatHandle, schema: type[BaseModel], system: str, human: str
) -> BaseModel:
    try:
        runnable = handle.client.with_structured_output(schema)
        result = runnable.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    except CoverageError:
        raise
    except Exception as exc:
        raise classify_provider_error(handle.provider, exc) from exc
    if isinstance(result, schema):
        return result
    if result is None:
        raise CoverageError(
            "provider_error", f"{handle.provider} returned an empty structured response."
        )
    return schema.model_validate(result)
