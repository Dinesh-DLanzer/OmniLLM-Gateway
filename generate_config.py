#!/usr/bin/env python3
import os
from pathlib import Path

def load_dotenv(env_path: Path):
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' not in line:
                continue
            key, val = line.split('=', 1)
            os.environ[key.strip()] = val.strip()

def key_available(var: str) -> bool:
    return bool(os.getenv(var))

def generate_config():
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)

    models = []

    # GROQ
    if key_available('GROQ_API_KEY'):
        models.extend([
            {"model_name": "groq/llama-3.3-70b", "litellm_params": {"model": "groq/llama-3.3-70b-versatile", "api_key": os.environ["GROQ_API_KEY"]}},
            {"model_name": "groq/llama-3.1-8b", "litellm_params": {"model": "groq/llama-3.1-8b-instant", "api_key": os.environ["GROQ_API_KEY"]}},
            {"model_name": "groq/gpt-oss-120b", "litellm_params": {"model": "groq/gpt-oss-120b", "api_key": os.environ["GROQ_API_KEY"]}},
            {"model_name": "groq/deepseek-r1-distill", "litellm_params": {"model": "groq/deepseek-r1-distill-llama-70b", "api_key": os.environ["GROQ_API_KEY"]}},
        ])

    # CEREBRAS
    if key_available('CEREBRAS_API_KEY'):
        models.extend([
            {"model_name": "cerebras/gpt-oss-120b", "litellm_params": {"model": "cerebras/gpt-oss-120b", "api_key": os.environ["CEREBRAS_API_KEY"]}},
            {"model_name": "cerebras/llama-3.3-70b", "litellm_params": {"model": "cerebras/llama-3.3-70b", "api_key": os.environ["CEREBRAS_API_KEY"]}},
        ])

    # COHERE
    if key_available('COHERE_API_KEY'):
        models.extend([
            {"model_name": "cohere/command-r-plus", "litellm_params": {"model": "cohere/command-r-plus", "api_key": os.environ["COHERE_API_KEY"]}},
            {"model_name": "cohere/command", "litellm_params": {"model": "cohere/command", "api_key": os.environ["COHERE_API_KEY"]}},
        ])

    # MISTRAL
    if key_available('MISTRAL_API_KEY'):
        models.extend([
            {"model_name": "mistral/mistral-large-latest", "litellm_params": {"model": "mistral/mistral-large-latest", "api_key": os.environ["MISTRAL_API_KEY"]}},
            {"model_name": "mistral/mistral-small-latest", "litellm_params": {"model": "mistral/mistral-small-latest", "api_key": os.environ["MISTRAL_API_KEY"]}},
        ])

    # clod.io
    if key_available('CLOD_API_KEY'):
        models.extend([
            {"model_name": "clod/trinity-mini", "litellm_params": {"model": "openai/trinity-mini", "api_base": "https://api.clod.io/v1", "api_key": os.environ["CLOD_API_KEY"]}},
            {"model_name": "clod/gpt-oss-120b", "litellm_params": {"model": "openai/openai/gpt-oss-120b", "api_base": "https://api.clod.io/v1", "api_key": os.environ["CLOD_API_KEY"]}},
            {"model_name": "clod/qwen-3-235b-thinking", "litellm_params": {"model": "openai/Qwen/Qwen3-235B-A22B-Thinking-2507", "api_base": "https://api.clod.io/v1", "api_key": os.environ["CLOD_API_KEY"]}},
            {"model_name": "clod/qwen-coder-480b", "litellm_params": {"model": "openai/Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8", "api_base": "https://api.clod.io/v1", "api_key": os.environ["CLOD_API_KEY"]}},
        ])

    # BOA API
    if key_available('BOA_API_KEY'):
        models.extend([
            {"model_name": "boa/claude-sonnet", "litellm_params": {"model": "anthropic/claude-sonnet-4-6-thinking", "api_base": "https://api.bayofassets.com", "api_key": os.environ["BOA_API_KEY"]}, "model_info": {"mode": "chat", "supports_function_calling": True}},
            {"model_name": "boa/claude-haiku", "litellm_params": {"model": "anthropic/claude-haiku-4-5", "api_base": "https://api.bayofassets.com", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/claude-opus", "litellm_params": {"model": "anthropic/claude-opus-4-6-thinking", "api_base": "https://api.bayofassets.com", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gpt-5.5", "litellm_params": {"model": "openai/gpt-5.5", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gemini-3.1-pro", "litellm_params": {"model": "openai/gemini-3.1-pro", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gemini-3-flash", "litellm_params": {"model": "openai/gemini-3-flash", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gpt-5.1", "litellm_params": {"model": "openai/gpt-5.1", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gpt-5.2", "litellm_params": {"model": "openai/gpt-5.2", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
            {"model_name": "boa/gpt-5.4", "litellm_params": {"model": "openai/gpt-5.4", "api_base": "https://api.bayofassets.com/v1", "api_key": os.environ["BOA_API_KEY"]}},
        ])

    # OpenRouter
    if key_available('OPENROUTER_API_KEY'):
        models.extend([
            {"model_name": "or/gpt-4o-paid", "litellm_params": {"model": "openrouter/openai/gpt-4o", "api_key": os.environ["OPENROUTER_API_KEY"]}},
            {"model_name": "or/llama-3-8b-paid", "litellm_params": {"model": "openrouter/meta-llama/llama-3-8b-instruct", "api_key": os.environ["OPENROUTER_API_KEY"]}},
            {"model_name": "or/deepseek-r1-paid", "litellm_params": {"model": "openrouter/deepseek/deepseek-r1", "api_key": os.environ["OPENROUTER_API_KEY"]}},
            {"model_name": "or/router-free", "litellm_params": {"model": "openrouter/openrouter/free", "api_key": os.environ["OPENROUTER_API_KEY"]}},
        ])

    # NVIDIA NIM
    if key_available('NIM_API_KEY'):
        models.extend([
            {"model_name": "nim/llama-3.1-70b-paid", "litellm_params": {"model": "openai/meta/llama-3.1-70b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
            {"model_name": "nim/llama-3.1-8b-paid", "litellm_params": {"model": "openai/meta/llama-3.1-8b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
            {"model_name": "nim/llama-3.1-70b-free", "litellm_params": {"model": "openai/meta/llama-3.1-70b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
            {"model_name": "nim/llama-3.1-8b-free", "litellm_params": {"model": "openai/meta/llama-3.1-8b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
            {"model_name": "nim/llama-3.1-70b", "litellm_params": {"model": "openai/meta/llama-3.1-70b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
            {"model_name": "nim/llama-3.1-8b", "litellm_params": {"model": "openai/meta/llama-3.1-8b-instruct", "api_base": "https://integrate.api.nvidia.com/v1", "api_key": os.environ["NIM_API_KEY"]}},
        ])

    # AWS Bedrock
    if key_available('AWS_ACCESS_KEY_ID') and key_available('AWS_SECRET_ACCESS_KEY'):
        models.append(
            {"model_name": "bedrock/claude-sonnet-4.5", "litellm_params": {"model": "bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", "aws_region_name": "us-east-1"}}
        )

    # Custom mapping for Claude Code (DeepSeek R1)
    if key_available('OPENROUTER_API_KEY'):
        models.append(
            {"model_name": "claude-3-haiku-20240307", "litellm_params": {"model": "openrouter/deepseek/deepseek-r1", "api_key": os.environ["OPENROUTER_API_KEY"]},
             "model_info": {"description": "DeepSeek R1 mapped to Claude model name for Claude Code"}}
        )

    # ========== Build full configuration ==========
    config = {
        "model_list": models,
        "general_settings": {
            "master_key": os.environ.get("LITELLM_MASTER_KEY", "litellm-master-key"),
            "default_model": "boa/claude-sonnet",
            "enable_anthropic_compatibility": True,
            "disable_rate_limiting": False,
            "database_url": os.environ.get("DATABASE_URL"),
            "background_health_check": True,
            "rate_limiting": {
                "enabled": True,
                "default_limits": [{"rpm": 1000, "tpm": 100000}],
                "model_specific_limits": {
                    "boa/*": [{"rpm": 500}],
                    "or/*-free": [{"rpm": 2000}],
                    "nim/*-free": [{"rpm": 3000}],
                    "or/*-paid": [{"rpm": 1000}],
                    "nim/*-paid": [{"rpm": 1500}],
                    "groq/*": [{"rpm": 30}],
                    "cerebras/*": [{"rpm": 30}],
                    "cohere/*": [{"rpm": 20}],
                    "mistral/*": [{"rpm": 30}],
                }
            }
        },
        "router_settings": {
            "routing_strategy": "simple-shuffle",
            "num_retries": 2,
            "request_timeout": 120,
            "fallback_retries": 2,
            "cooldown_time": 30,
            "fallbacks": [
                {"boa/claude-sonnet": ["boa/gpt-5.5", "or/gpt-4o-paid", "nim/llama-3.1-70b-paid", "groq/llama-3.3-70b", "cerebras/gpt-oss-120b", "or/router-free"]},
                {"boa/claude-haiku": ["boa/gemini-3-flash", "or/llama-3-8b-paid", "nim/llama-3.1-8b-paid", "groq/llama-3.1-8b", "mistral/mistral-small-latest", "or/router-free"]},
                {"boa/claude-opus": ["boa/gpt-5.4", "or/deepseek-r1-paid", "nim/llama-3.1-70b-paid", "groq/deepseek-r1-distill", "cohere/command-r-plus", "or/router-free"]},
                {"or/gpt-4o-paid": ["or/router-free", "nim/llama-3.1-70b-free", "groq/llama-3.3-70b", "cerebras/gpt-oss-120b"]},
                {"or/deepseek-r1-paid": ["or/router-free", "nim/llama-3.1-70b-paid", "groq/deepseek-r1-distill", "mistral/mistral-large-latest"]},
                {"nim/llama-3.1-70b-paid": ["nim/llama-3.1-70b-free", "or/router-free", "groq/llama-3.3-70b", "cerebras/llama-3.3-70b"]},
            ],
            "model_group_alias": {
                "claude-sonnet-4-6-thinking": "boa/claude-sonnet",
                "claude-haiku-4-5": "boa/claude-haiku",
                "claude-opus-4-6-thinking": "boa/claude-opus",
                "gpt-5-latest": "boa/gpt-5.4",
                "gemini-pro-latest": "boa/gemini-3.1-pro",
                "best-free": "or/router-free",
                "best-paid": "or/gpt-4o-paid",
            }
        },
        "litellm_settings": {
            "drop_params": True,
            "set_verbose": False,
            "request_timeout": 120,
            "max_retries": 2,
            "retry_after": 1,
            "json_logs": True,
            "prometheus": {"enabled": True, "port": 9090, "endpoint": "/metrics"},
            "cache": True,
            "cache_params": {"type": "redis", "host": "redis", "port": 6379, "ttl": 86400},
            "callbacks": ["langfuse"] if key_available('LANGFUSE_SECRET_KEY') else []
        },
        "server": {
            "host": "0.0.0.0",
            "port": 4000,
            "workers": 4,
            "max_connections": 1000,
            "keep_alive_timeout": 30,
        }
    }

    import yaml
    output_path = Path(__file__).parent / "config.yaml"
    with output_path.open("w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    print(f"✅ Generated {output_path} with {len(models)} models")

if __name__ == "__main__":
    generate_config()