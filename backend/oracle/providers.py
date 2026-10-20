"""Catalogue of model providers for the Models screen.

Every model goes through LiteLLM, so the model string is "<provider>/<model>".
`base_env` is the environment variable for a custom endpoint, where one applies.
Suggested models are starting points; any model the provider serves works.
"""

from __future__ import annotations

PROVIDERS: list[dict] = [
    {
        "id": "nvidia_nim", "label": "NVIDIA NIM", "key_env": "NVIDIA_NIM_API_KEY", "base_env": "NVIDIA_NIM_API_BASE",
        "base_default": "https://integrate.api.nvidia.com/v1", "key_url": "https://build.nvidia.com",
        "models": ["meta/llama-3.3-70b-instruct", "nvidia/llama-3.1-nemotron-70b-instruct", "meta/llama-3.1-8b-instruct", "mistralai/mixtral-8x22b-instruct-v0.1", "qwen/qwen2.5-7b-instruct"],
        "note": "Hosted NIM endpoints at build.nvidia.com, or point the endpoint at your own NIM deployment.",
    },
    {
        "id": "bedrock", "label": "AWS Bedrock", "key_env": None, "key_url": "https://console.aws.amazon.com/bedrock",
        "models": [
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            "us.anthropic.claude-3-5-haiku-20241022-v1:0",
            "amazon.nova-lite-v1:0",
            "amazon.nova-pro-v1:0",
            "meta.llama3-1-70b-instruct-v1:0",
            "mistral.mistral-large-2407-v1:0",
        ],
        "fields": [
            {"env": "AWS_ACCESS_KEY_ID", "label": "Access key ID", "secret": True},
            {"env": "AWS_SECRET_ACCESS_KEY", "label": "Secret access key", "secret": True},
            {"env": "AWS_SESSION_TOKEN", "label": "Session token (only for temporary credentials)", "secret": True, "optional": True},
            {"env": "AWS_REGION_NAME", "label": "Region", "placeholder": "us-east-1"},
        ],
        "machine_credentials": True,
        "note": "Use any model ID enabled in your Bedrock console for this region. IDs starting with us. or eu. are cross-region inference profiles.",
    },
    {
        "id": "openai", "label": "OpenAI", "key_env": "OPENAI_API_KEY", "key_url": "https://platform.openai.com/api-keys",
        "models": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1", "o4-mini"],
    },
    {
        "id": "anthropic", "label": "Anthropic", "key_env": "ANTHROPIC_API_KEY", "key_url": "https://console.anthropic.com",
        "models": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    },
    {
        "id": "gemini", "label": "Google Gemini", "key_env": "GEMINI_API_KEY", "key_url": "https://aistudio.google.com/apikey",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
    },
    {"id": "groq", "label": "Groq", "key_env": "GROQ_API_KEY", "key_url": "https://console.groq.com/keys", "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
    {"id": "deepseek", "label": "DeepSeek", "key_env": "DEEPSEEK_API_KEY", "key_url": "https://platform.deepseek.com", "models": ["deepseek-chat", "deepseek-reasoner"]},
    {"id": "mistral", "label": "Mistral", "key_env": "MISTRAL_API_KEY", "key_url": "https://console.mistral.ai", "models": ["mistral-small-latest", "mistral-large-latest"]},
    {
        "id": "openrouter", "label": "OpenRouter", "key_env": "OPENROUTER_API_KEY", "key_url": "https://openrouter.ai/keys",
        "models": ["meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct", "google/gemini-2.5-flash"],
    },
    {"id": "together_ai", "label": "Together AI", "key_env": "TOGETHERAI_API_KEY", "key_url": "https://api.together.ai", "models": ["meta-llama/Llama-3.3-70B-Instruct-Turbo"]},
    {"id": "xai", "label": "xAI", "key_env": "XAI_API_KEY", "key_url": "https://console.x.ai", "models": ["grok-3-mini", "grok-3"]},
    {
        "id": "azure", "label": "Azure OpenAI", "key_env": "AZURE_API_KEY", "base_env": "AZURE_API_BASE", "version_env": "AZURE_API_VERSION",
        "models": ["<your-deployment-name>"], "note": "Use your deployment name as the model.",
    },
    {
        "id": "ollama", "label": "Ollama (local)", "key_env": None, "base_env": "OLLAMA_API_BASE", "base_default": "http://localhost:11434",
        "models": ["llama3.1", "qwen2.5", "mistral"], "note": "Runs on your machine. No key needed.",
    },
    {"id": "mock", "label": "Demo (offline)", "key_env": None, "models": ["oracle"], "note": "Runs without any model. Shows how Oracle works; not predictions."},
]


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else "openai"
