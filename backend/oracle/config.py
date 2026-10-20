"""App settings.

Static settings come from environment variables (prefix ORACLE_). User-editable
settings (provider keys, model roles) live in var/settings.json and are managed
through the settings API, so they survive restarts without touching .env files.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"


class Env(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORACLE_", env_file=".env", extra="ignore")

    var_dir: Path = BACKEND_DIR / "var"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]


env = Env()
env.var_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = env.var_dir / "oracle.db"
SETTINGS_PATH = env.var_dir / "settings.json"


# Provider name -> environment variable LiteLLM reads for its key.
PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "xai": "XAI_API_KEY",
    "azure": "AZURE_API_KEY",
    "nvidia_nim": "NVIDIA_NIM_API_KEY",
    "tavily": "TAVILY_API_KEY",
}

# Extra non-secret provider settings LiteLLM reads from the environment.
PROVIDER_EXTRA_ENV: dict[str, list[str]] = {
    "azure": ["AZURE_API_BASE", "AZURE_API_VERSION"],
    "ollama": ["OLLAMA_API_BASE"],
    "nvidia_nim": ["NVIDIA_NIM_API_BASE"],
}


class ModelRoles(BaseModel):
    """Which model handles which job. Any LiteLLM model string works,
    e.g. "openai/gpt-4o-mini", "anthropic/claude-haiku-4-5", "ollama/llama3.1",
    "openrouter/meta-llama/llama-3.1-70b-instruct". "mock/oracle" runs offline."""

    planner: str = "mock/oracle"
    crowd: list[str] = Field(default_factory=lambda: ["mock/oracle"])
    analyst: str = "mock/oracle"


# Secrets that are never exported to the environment; they are passed straight to
# the calls that need them (AWS Bedrock), so nothing else on the machine sees them.
SECRET_FIELDS = {"AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"}
# Plain Bedrock settings, also passed per call rather than exported.
BEDROCK_PLAIN = {"AWS_REGION_NAME", "AWS_PROFILE"}


class UserSettings(BaseModel):
    roles: ModelRoles = Field(default_factory=ModelRoles)
    keys: dict[str, str] = Field(default_factory=dict)
    extra: dict[str, str] = Field(default_factory=dict)
    secrets: dict[str, str] = Field(default_factory=dict)
    bedrock_machine_credentials: bool = Field(
        default=False,
        description="Allow Bedrock to use this computer's AWS credentials (default chain or AWS_PROFILE) when no keys are saved",
    )
    search_provider: str = "duckduckgo"  # duckduckgo | tavily | none
    max_concurrency: int = 16
    request_timeout_s: int = 90


class SettingsStore:
    """Thread-safe JSON-backed settings that also export keys to os.environ."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self._path = path
        self._lock = threading.Lock()
        self._machine_bedrock_key: str | None = None  # remembered before we hide it
        self._settings = self._load()
        self._apply_env()

    def _load(self) -> UserSettings:
        if self._path.exists():
            try:
                return UserSettings.model_validate_json(self._path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return UserSettings()

    def _apply_env(self) -> None:
        for provider, value in self._settings.keys.items():
            var = PROVIDER_KEY_ENV.get(provider)
            if var and value:
                os.environ[var] = value
        for var, value in self._settings.extra.items():
            if value and var not in BEDROCK_PLAIN:
                os.environ[var] = value
        # LiteLLM reads a Bedrock API key from the environment on its own. Unless the user
        # allowed this computer's AWS credentials, keep any such key out of this process.
        if self._machine_bedrock_key is None:
            self._machine_bedrock_key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
        if self._settings.bedrock_machine_credentials and self._machine_bedrock_key:
            os.environ["AWS_BEARER_TOKEN_BEDROCK"] = self._machine_bedrock_key
        else:
            os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)

    def get(self) -> UserSettings:
        with self._lock:
            return self._settings.model_copy(deep=True)

    def update(self, patch: dict[str, Any]) -> UserSettings:
        with self._lock:
            data = self._settings.model_dump()
            keys = patch.pop("keys", None)
            extra = patch.pop("extra", None)
            secrets = patch.pop("secrets", None)
            data.update({k: v for k, v in patch.items() if v is not None})
            if keys is not None:
                for provider, value in keys.items():
                    if value is None or value == "":
                        data["keys"].pop(provider, None)
                        var = PROVIDER_KEY_ENV.get(provider)
                        if var:
                            os.environ.pop(var, None)
                    elif not str(value).startswith("••"):
                        data["keys"][provider] = value
            if extra is not None:
                for var, value in extra.items():
                    if value:
                        data["extra"][var] = value
                    else:
                        data["extra"].pop(var, None)
                        os.environ.pop(var, None)
            if secrets is not None:
                for var, value in secrets.items():
                    if var not in SECRET_FIELDS:
                        continue
                    if value is None or value == "":
                        data["secrets"].pop(var, None)
                    elif not str(value).startswith("••"):
                        data["secrets"][var] = value.strip()
            self._settings = UserSettings.model_validate(data)
            self._path.write_text(self._settings.model_dump_json(indent=2), encoding="utf-8")
            self._apply_env()
            return self._settings.model_copy(deep=True)

    def public(self) -> dict[str, Any]:
        """Settings safe to send to the browser (keys masked)."""
        s = self.get()
        keys = {}
        for provider in PROVIDER_KEY_ENV:
            value = s.keys.get(provider) or os.environ.get(PROVIDER_KEY_ENV[provider], "")
            keys[provider] = {
                "set": bool(value),
                "source": "settings" if s.keys.get(provider) else ("environment" if value else None),
                "masked": f"••••{value[-4:]}" if len(value) >= 8 else ("••••" if value else ""),
            }
        secrets = {
            var: {
                "set": bool(s.secrets.get(var)),
                "masked": f"••••{s.secrets[var][-4:]}" if len(s.secrets.get(var, "")) >= 8 else ("••••" if s.secrets.get(var) else ""),
            }
            for var in sorted(SECRET_FIELDS)
        }
        return {
            "roles": s.roles.model_dump(),
            "keys": keys,
            "secrets": secrets,
            "bedrock_machine_credentials": s.bedrock_machine_credentials,
            "extra": s.extra,
            "search_provider": s.search_provider,
            "max_concurrency": s.max_concurrency,
            "request_timeout_s": s.request_timeout_s,
        }


settings_store = SettingsStore()


def load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def bedrock_kwargs(s: UserSettings) -> dict[str, Any]:
    """Credentials for one Bedrock call. Saved keys win; otherwise the machine's AWS
    credentials, but only when the user has explicitly allowed that."""
    region = s.extra.get("AWS_REGION_NAME") or "us-east-1"
    if s.secrets.get("AWS_BEARER_TOKEN_BEDROCK"):
        # A Bedrock API key (long-term, or short-term up to 12 hours). It belongs to one region.
        return {"api_key": s.secrets["AWS_BEARER_TOKEN_BEDROCK"], "aws_region_name": region}
    if s.secrets.get("AWS_ACCESS_KEY_ID") and s.secrets.get("AWS_SECRET_ACCESS_KEY"):
        out: dict[str, Any] = {
            "aws_access_key_id": s.secrets["AWS_ACCESS_KEY_ID"],
            "aws_secret_access_key": s.secrets["AWS_SECRET_ACCESS_KEY"],
            "aws_region_name": region,
        }
        if s.secrets.get("AWS_SESSION_TOKEN"):
            out["aws_session_token"] = s.secrets["AWS_SESSION_TOKEN"]
        return out
    if s.bedrock_machine_credentials:
        out = {"aws_region_name": region}
        if s.extra.get("AWS_PROFILE"):
            out["aws_profile_name"] = s.extra["AWS_PROFILE"]
        return out
    raise PermissionError(
        "AWS Bedrock has no keys. Add a Bedrock API key or an access key on the Models page, or allow this computer's AWS credentials there."
    )
