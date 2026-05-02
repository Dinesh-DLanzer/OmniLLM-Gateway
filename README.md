# OmniLLM Gateway

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![LiteLLM](https://img.shields.io/badge/Powered%20by-LiteLLM-green)](https://github.com/BerriAI/litellm)

A **production‑ready, OpenAI‑compatible proxy** that aggregates **40+ LLM models** from multiple providers behind a single API endpoint.  
**Only the models for which you provide API keys will be loaded** – perfect for open‑source deployments where users bring their own keys.

👉 **GitHub:** [https://github.com/Dinesh-DLanzer/OmniLLM-Gateway](https://github.com/Dinesh-DLanzer/OmniLLM-Gateway)

---

## 🚀 Features

- ✅ **Unified OpenAI‑compatible API** – Works with any OpenAI SDK, Claude Code, LangChain, cURL, etc.
- ✅ **Dynamic model loading** – Add a provider by simply adding its API key to `.env` and re‑running the generator.
- ✅ **Smart fallbacks & load balancing** – Automatic retry with alternative models when a primary model fails.
- ✅ **Redis caching** – Reduce latency and cost for repeated or identical prompts.
- ✅ **Rate limiting** – Per‑model and per‑user RPM/TPM controls (respects each provider’s free tier limits).
- ✅ **Observability** – Prometheus metrics (`/metrics`) + optional Langfuse tracing.
- ✅ **Docker Compose** – One‑command startup (PostgreSQL + Redis + LiteLLM).
- ✅ **Admin UI** – Web dashboard at `/ui` (log in with `admin` / `litellm-master-key`).
- ✅ **Claude Code compatible** – Use any model directly from Anthropic’s Claude Code CLI.

---

## 📦 Supported Providers & Models

| Provider | Free Tier | Example Models | Reference |
|----------|-----------|----------------|-----------|
| **BOA API** | No | `claude-sonnet-4-6-thinking`, `gpt-5.4`, `gemini-3.1-pro` | [api.bayofassets.com](https://api.bayofassets.com) |
| **OpenRouter** | Yes (limited) | `gpt-4o`, `deepseek-r1`, `openrouter/free` | [openrouter.ai](https://openrouter.ai) |
| **NVIDIA NIM** | Yes (~40 RPM) | `llama-3.1-70b-instruct`, `llama-3.1-8b` | [build.nvidia.com/models](https://build.nvidia.com/models) |
| **Groq** | Yes (30 RPM) | `llama-3.3-70b-versatile`, `deepseek-r1-distill-llama-70b` | [console.groq.com](https://console.groq.com) |
| **Cerebras** | Yes (30 RPM) | `gpt-oss-120b`, `llama-3.3-70b` | [cerebras.ai](https://cerebras.ai) |
| **Cohere** | 1k calls/month | `command-r-plus`, `command` | [dashboard.cohere.com](https://dashboard.cohere.com) |
| **Mistral AI** | Yes (1 RPS) | `mistral-large-latest`, `mistral-small-latest` | [console.mistral.ai](https://console.mistral.ai) |
| **clod.io** | Yes (quota limited) | `trinity-mini`, `qwen-coder-480b`, `gpt-oss-120b` | [clod.io](https://clod.io) |
| **AWS Bedrock** | Paid (credits apply) | `claude-sonnet-4.5` (cross‑region) | [aws.amazon.com/bedrock](https://aws.amazon.com/bedrock) |

> 💡 **Only providers with non‑empty API keys in `.env` will appear in `/v1/models`.**  
> If you don’t have a key for a provider, simply leave it commented – the proxy won’t attempt to load its models.

---

## 🐳 Quick Start (Docker Compose)

### 1. Clone the repository

```bash
git clone https://github.com/Dinesh-DLanzer/OmniLLM-Gateway.git
cd OmniLLM-Gateway
```

### 2. Install a single Python dependency (on your host)

```bash
pip3 install pyyaml
```

### 3. Configure your API keys

Copy the example environment file and edit it with the keys you own:

```bash
cp .env.example .env
nano .env   # uncomment and set your keys
```

All keys are optional – only the ones you set will activate the corresponding models.

### 4. Generate the LiteLLM configuration file

```bash
python3 generate_config.py
```

This reads your `.env` and creates a `config.yaml` **on your host** containing only the models for which you provided keys.

### 5. Start the proxy

```bash
docker-compose up -d
```

The proxy will:
- Start PostgreSQL, Redis, and the LiteLLM container.
- Use the pre‑generated `config.yaml` – no dynamic generation inside the container.
- Expose the API at `http://localhost:4000`.

### 6. Verify it’s running

```bash
curl http://localhost:4000/health
```

Expected output: `{"status":"ok"}`

### 7. List available models

```bash
curl -H "Authorization: Bearer litellm-master-key" \
     http://localhost:4000/v1/models | jq '.data[].id'
```

Only the models you have enabled will appear.

---

## 🖥️ Running Without Docker (Local Python)

For users who prefer a native Python environment or cannot use Docker, follow these steps.

### Prerequisites
- Python 3.10+
- `pip` installed

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Dinesh-DLanzer/OmniLLM-Gateway.git
cd OmniLLM-Gateway

# 2. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate

# 3. Install required packages
pip install litellm pyyaml redis psycopg2-binary

# 4. Copy and configure environment variables
cp .env.example .env
nano .env   # set your API keys (only those you own)

# 5. Generate the LiteLLM configuration
python3 generate_config.py

# 6. Start the proxy (with optional PostgreSQL and Redis)
# For a minimal setup (no DB, no cache), run:
litellm --config ./config.yaml --port 4000 --host 0.0.0.0

# For full features (PostgreSQL + Redis), you need to run those services separately.
# Example with Docker for dependencies only:
docker run -d --name litellm-postgres -e POSTGRES_PASSWORD=litellm -e POSTGRES_USER=litellm -p 5432:5432 postgres:16
docker run -d --name litellm-redis -p 6379:6379 redis:7-alpine
export DATABASE_URL=postgresql://litellm:litellm@localhost:5432/litellm
export REDIS_URL=redis://localhost:6379
litellm --config ./config.yaml --port 4000 --host 0.0.0.0
```

### Stop the local run
Press `Ctrl+C` to stop the LiteLLM process. To stop the dependency containers:
```bash
docker stop litellm-postgres litellm-redis
docker rm litellm-postgres litellm-redis
```

### Notes for local run
- The proxy will be available at `http://localhost:4000`.
- Use the same `curl`, Python, or Claude Code commands as described in the Docker section (just replace the host with `localhost`).
- When you change `.env`, re‑run `python3 generate_config.py` and restart the `litellm` process.

---

## 🧪 Usage Examples

### OpenAI SDK (Python)

```python
import openai
openai.api_base = "http://localhost:4000"
openai.api_key = "litellm-master-key"

response = openai.ChatCompletion.create(
    model="groq/llama-3.3-70b",   # any model from your list
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### cURL

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer litellm-master-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "or/router-free",
    "messages": [{"role": "user", "content": "Hi"}],
    "max_tokens": 20
  }'
```

### Claude Code (Anthropic CLI)

```bash
export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_AUTH_TOKEN="litellm-master-key"
export CLAUDE_MODEL="nim/llama-3.1-70b-free"

claude --model "groq/deepseek-r1-distill"
```

### Admin UI

Open `http://localhost:4000/ui` and log in with:

- **Username:** `admin`
- **Password:** `litellm-master-key`

---

## 🔧 Configuration Deep Dive

### Dynamic model generation – `generate_config.py`

The proxy **does not** use a static `config.yaml`. Instead, you run `generate_config.py` **on your host** (once after editing `.env`). The script:

1. Reads your `.env` file.
2. Checks which API keys are set and non‑empty.
3. Builds a `config.yaml` that **only** includes models for those providers.

**Benefits:**
- No “model not found” errors for providers you don’t use.
- Add a new provider simply by adding its key to `.env` and re‑running `python3 generate_config.py`.
- Clean `/v1/models` output – only the models you can actually call.
- No need to run Python inside the Docker container (avoids dependency hell).

### Environment variables reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LITELLM_MASTER_KEY` | No | `litellm-master-key` | Admin API key (used for auth) |
| `BOA_API_KEY` | No | – | BOA API key |
| `OPENROUTER_API_KEY` | No | – | OpenRouter key |
| `NIM_API_KEY` | No | – | NVIDIA NIM key |
| `GROQ_API_KEY` | No | – | Groq key |
| `CEREBRAS_API_KEY` | No | – | Cerebras key |
| `COHERE_API_KEY` | No | – | Cohere key |
| `MISTRAL_API_KEY` | No | – | Mistral key |
| `CLOD_API_KEY` | No | – | clod.io JWT token |
| `AWS_ACCESS_KEY_ID` | No | – | AWS Bedrock access key |
| `AWS_SECRET_ACCESS_KEY` | No | – | AWS Bedrock secret key |
| `LANGFUSE_SECRET_KEY` | No | – | Langfuse observability (optional) |
| `DATABASE_URL` | Yes* | – | PostgreSQL connection string |
| `REDIS_URL` | Yes* | – | Redis connection string |

*Defaults are already provided in `docker-compose.yml` for the local services.

### Rate limits

Default rate limits are set per provider to respect their free tier quotas. You can adjust them in `generate_config.py` under `rate_limiting` → `model_specific_limits`.

---

## 🧩 Architecture

```
User request → LiteLLM Proxy (port 4000)
                     │
    ┌────────────────┼────────────────┐
    │                │                │
  Redis          PostgreSQL      Dynamic router
 (cache)         (spend logs)    (fallbacks, load balancing)
```

- **Redis**: Caches identical requests, reduces latency and cost.
- **PostgreSQL**: Stores usage metrics, API keys, and budget alerts.
- **Router**: Decides which model to call based on `routing_strategy` (`simple-shuffle` by default). On failure, follows fallback chains defined in the generated config.

---

## 🛠️ Troubleshooting

| Problem | Likely cause | Solution |
|---------|--------------|----------|
| `502 Bad Gateway` | LiteLLM container not running | `docker-compose logs litellm` |
| `model not found` | API key for that model not set or empty | Check `.env` and re‑run `python3 generate_config.py`, then `docker-compose restart litellm` |
| `429 Too Many Requests` | Provider rate limit exceeded | Wait or upgrade to paid tier |
| Langfuse not sending traces | Missing `LANGFUSE_SECRET_KEY` | Add it to `.env` and re‑run generator, then restart |
| PostgreSQL authentication error | Wrong password in `.env` | Use static password `litellm` (no suffix) – see `docker-compose.yml` |
| Redis cache errors | Wrong cache parameters | Ensure `cache_params` uses `host` and `port`, not `url` |

---

## 🤝 Contributing

We welcome contributions!

1. Fork the repository: [https://github.com/Dinesh-DLanzer/OmniLLM-Gateway](https://github.com/Dinesh-DLanzer/OmniLLM-Gateway)
2. Create a feature branch (`git checkout -b feature/amazing`).
3. Commit your changes (`git commit -m 'Add amazing thing'`).
4. Push to the branch (`git push origin feature/amazing`).
5. Open a Pull Request.

Please follow the existing code style and add tests where appropriate.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

## 🙏 Acknowledgements & References

This project stands on the shoulders of many open‑source tools and free LLM providers. Special thanks to:

- [LiteLLM](https://github.com/BerriAI/litellm) – the core proxy engine
- [BOA API](https://api.bayofassets.com) – custom Claude API endpoint
- [OpenRouter](https://openrouter.ai) – model aggregation with free tier
- [NVIDIA NIM](https://build.nvidia.com/models) – free inference for Llama etc.
- [Groq](https://groq.com) – extremely fast inference
- [Cerebras](https://cerebras.ai) – high‑throughput inference
- [Cohere](https://cohere.com) – 1k free calls/month
- [Mistral AI](https://mistral.ai) – free tier for large models
- [clod.io](https://clod.io) – free reasoning models
- [AWS Bedrock](https://aws.amazon.com/bedrock) – enterprise‑grade models
- [Langfuse](https://langfuse.com) – LLM observability
- [PostgreSQL](https://www.postgresql.org/) & [Redis](https://redis.io/) – rock‑solid data layer
- The entire open‑source community for making LLMs accessible

---

## 📬 Support

- Open an [issue on GitHub](https://github.com/Dinesh-DLanzer/OmniLLM-Gateway/issues)
- Join the [LiteLLM Slack](https://slack.litellm.ai/) for community help

**Happy building!**