
<div align="center">

# 🌌 OmniLLM Gateway

<p align="center">
  <img src="images/OmniLLM Gateway.png" alt="OmniLLM Gateway" width="100%">
</p>


### Intelligent OpenAI-Compatible LLM Gateway & Orchestration Layer

**A production-ready, self-configuring LiteLLM gateway capable of discovering, validating, benchmarking, and routing across 400+ LLM models from multiple providers through a single API endpoint.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Docker Ready](https://img.shields.io/badge/Docker-Ready-blue?style=for-the-badge&logo=docker)](https://www.docker.com/)
[![Powered by LiteLLM](https://img.shields.io/badge/Powered%20by-LiteLLM-green?style=for-the-badge)](https://github.com/BerriAI/litellm)
[![Models](https://img.shields.io/badge/Models-400+-orange?style=for-the-badge)](https://github.com/Dinesh-DLanzer/OmniLLM-Gateway)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-black?style=for-the-badge)](https://platform.openai.com/docs/api-reference)

<p align="center">
  <a href="https://github.com/Dinesh-DLanzer/OmniLLM-Gateway/issues">Report Bug</a>
  ·
  <a href="https://github.com/Dinesh-DLanzer/OmniLLM-Gateway/issues">Request Feature</a>
</p>

</div>


---

# 📖 Overview

OmniLLM Gateway is an intelligent orchestration layer built on top of LiteLLM that automatically:

- Discovers models from enabled providers
- Validates and benchmarks them
- Generates optimized LiteLLM routing configs
- Creates automatic fallback chains
- Exposes a unified OpenAI-compatible API
- Supports caching, observability, and load balancing

Unlike static LLM proxies, OmniLLM dynamically adapts to the providers and API keys you configure.

---

# ✨ Key Features

## ⚡ Unified OpenAI-Compatible API
Works with:
- OpenAI SDKs
- Claude Code
- LangChain
- Open WebUI
- LibreChat
- Continue.dev
- Cline
- Roo Code
- cURL
- Any OpenAI-compatible client

---

## 🧠 Intelligent Model Discovery

The gateway dynamically:
- Queries provider APIs
- Fetches available models
- Validates functionality
- Measures latency
- Tests reasoning capabilities
- Generates optimized routing configs

Only working models are included.

---

## 🔀 Automatic Fallback Routing

If a provider:
- fails
- rate limits
- times out
- becomes unavailable

OmniLLM automatically retries using fallback models.

Example:
```text
gpt-4o
  ↓ fallback
claude-sonnet
  ↓ fallback
deepseek-r1
````

---

## 🚀 Redis Caching

Reduce:

* latency
* duplicate requests
* API costs

by caching repeated prompts automatically.

---

## 📊 Observability & Monitoring

Built-in support for:

* Prometheus metrics
* Langfuse tracing
* Spend logging
* Usage analytics
* Request tracking

---

## 🏷️ Intelligent Model Classification

Models are automatically tagged for:

* coding
* reasoning
* vision
* embeddings
* chat
* fast inference

---

## 🖥️ Admin Dashboard

Built-in LiteLLM Admin UI:

* API key management
* usage tracking
* model monitoring
* spend analytics

---

# 🏗️ High-Level Architecture

<p align="center">
  <img src="images/High-Level Architecture.png" alt="High-Level Architecture" width="100%">
</p>

---

# ⚡ Request Processing Flow

<p align="center">
  <img src="images/Request processing flow diagram.png" alt="Request Processing Flow" width="100%">
</p>

---

# 🧠 Dynamic Discovery Engine Flow

<p align="center">
  <img src="images/Dynamic discovery engine flowchart diagram.png" alt="Dynamic Discovery Engine Flow" width="100%">
</p>

---

# 🔀 Intelligent Fallback Routing Flow

<p align="center">
  <img src="images/Intelligent Fallback Routing Flow.png" alt="Intelligent Fallback Routing Flow" width="100%">
</p>

---

# 📊 Infrastructure Deployment Architecture

<p align="center">
  <img src="images/Infrastructure Deployment Architecture.png" alt="Infrastructure Deployment Architecture" width="100%">
</p>

---

# 🐳 Docker Container Architecture

<p align="center">
  <img src="images/Docker Container Architecture.png" alt="Docker Container Architecture" width="100%">
</p>

# 🔌 Supported Providers

| Provider    | Free Tier | Example Models          |
| ----------- | --------- | ----------------------- |
| Groq        | ✅         | llama-3.3-70b-versatile |
| OpenRouter  | ✅         | gpt-4o, deepseek-r1     |
| NVIDIA NIM  | ✅         | llama-3.1-70b           |
| Mistral AI  | ✅         | mistral-large           |
| Cerebras    | ✅         | gpt-oss-120b            |
| Cohere      | ✅         | command-r-plus          |
| clod.io     | ✅         | qwen-coder              |
| BOA API     | ❌         | claude-sonnet           |
| AWS Bedrock | ❌         | claude-4.5              |

> Only providers with valid API keys are enabled and queried.

---

# 🚀 Quick Start (Docker)

## 1. Clone Repository

```bash
git clone https://github.com/Dinesh-DLanzer/OmniLLM-Gateway.git
cd OmniLLM-Gateway
```

---

## 2. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Add only the provider keys you own.

Example:

```env
OPENROUTER_API_KEY=your_key
GROQ_API_KEY=your_key
MISTRAL_API_KEY=your_key
```

---

## 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Generate Dynamic Config

```bash
python3 generate_config.py
```

The discovery engine will:

* discover models
* validate responses
* benchmark latency
* build fallback chains
* generate `config.yaml`

---

## 5. Start Infrastructure

```bash
docker-compose up -d
```

This launches:

* LiteLLM Gateway
* Redis
* PostgreSQL

---

## 6. Verify Health

```bash
curl http://localhost:4000/health
```

Expected:

```json
{"status":"ok"}
```

---

# 💻 Local Python Setup (Without Docker)

## Requirements

* Python 3.10+
* Redis (optional)
* PostgreSQL (optional)

---

## Setup

```bash
git clone https://github.com/Dinesh-DLanzer/OmniLLM-Gateway.git
cd OmniLLM-Gateway

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
nano .env

python3 generate_config.py
```

---

## Run LiteLLM

```bash
litellm --config ./config.yaml --port 4000 --host 0.0.0.0
```

---

# ⚙️ How Dynamic Discovery Works

OmniLLM does not rely on static model lists.

The `generate_config.py` engine:

## 1. Provider Discovery

Queries provider APIs dynamically.

---

## 2. Validation Pipeline

Each discovered model undergoes:

* basic completion tests
* reasoning tests
* JSON formatting tests
* timeout handling
* retry logic

---

## 3. Benchmarking

Measures:

* latency
* response quality
* reasoning capability
* reliability

Results are stored locally.

---

## 4. Routing Optimization

Automatically generates:

* fallback chains
* load balancing groups
* provider prioritization
* rate limits

---

## 5. Config Generation

Finally generates:

```yaml
config.yaml
```

containing only validated working models.

---

# 📦 Example Usage

# Python (OpenAI SDK)

```python
import openai

openai.api_base = "http://localhost:4000"
openai.api_key = "litellm-master-key"

response = openai.ChatCompletion.create(
    model="groq/llama-3.3-70b-versatile",
    messages=[
        {"role": "user", "content": "Hello"}
    ]
)

print(response.choices[0].message.content)
```

---

# cURL

```bash
curl http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer litellm-master-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openrouter/deepseek-r1",
    "messages": [
      {
        "role": "user",
        "content": "Explain quantum computing"
      }
    ]
  }'
```

---

# Claude Code

```bash
export ANTHROPIC_BASE_URL="http://localhost:4000"
export ANTHROPIC_AUTH_TOKEN="litellm-master-key"

claude --model "groq/llama-3.3-70b-versatile"
```

---

# Open WebUI

Use:

```text
Base URL:
http://localhost:4000

API Key:
litellm-master-key
```

---

# 🔐 Environment Variables

| Variable              | Description           |
| --------------------- | --------------------- |
| LITELLM_MASTER_KEY    | Main gateway API key  |
| OPENROUTER_API_KEY    | OpenRouter API key    |
| GROQ_API_KEY          | Groq API key          |
| NIM_API_KEY           | NVIDIA NIM key        |
| MISTRAL_API_KEY       | Mistral API key       |
| COHERE_API_KEY        | Cohere API key        |
| CEREBRAS_API_KEY      | Cerebras API key      |
| BOA_API_KEY           | BOA API key           |
| AWS_ACCESS_KEY_ID     | AWS Bedrock access    |
| AWS_SECRET_ACCESS_KEY | AWS Bedrock secret    |
| REDIS_URL             | Redis connection      |
| DATABASE_URL          | PostgreSQL connection |
| LANGFUSE_SECRET_KEY   | Langfuse tracing      |

---

# 📊 Rate Limiting

OmniLLM automatically applies:

* provider-aware limits
* RPM controls
* TPM controls
* retry strategies

This prevents free-tier exhaustion.

Configuration is generated dynamically inside:

```python
generate_config.py
```

---

# 🧩 Intelligent Routing

Supported routing strategies:

* simple-shuffle
* latency-based
* least-busy
* weighted-routing
* fallback-priority

---

# 📈 Monitoring

## Metrics Endpoint

```bash
http://localhost:4000/metrics
```

Compatible with:

* Prometheus
* Grafana

---

## Langfuse Integration

Optional tracing support:

```env
LANGFUSE_SECRET_KEY=your_key
```

---

# 🖥️ Admin UI

Access:

```text
http://localhost:4000/ui
```

Default credentials:

```text
Username: admin
Password: litellm-master-key
```

---

# 🛠️ Troubleshooting

<details>
<summary><b>502 Bad Gateway</b></summary>

LiteLLM container may not be running.

Check logs:

```bash
docker-compose logs litellm
```

</details>

---

<details>
<summary><b>Model Not Found</b></summary>

The provider key may be missing or invalid.

Fix:

```bash
python3 generate_config.py
docker-compose restart litellm
```

</details>

---

<details>
<summary><b>429 Too Many Requests</b></summary>

Provider free-tier rate limit exceeded.

Solutions:

* wait for reset
* reduce concurrency
* upgrade provider tier

</details>

---

<details>
<summary><b>Redis Connection Error</b></summary>

Ensure Redis is running:

```bash
docker ps
```

</details>

---

<details>
<summary><b>PostgreSQL Authentication Failed</b></summary>

Verify:

```env
DATABASE_URL
```

matches docker-compose configuration.

</details>

---

# 🤝 Contributing

Contributions are welcome.

## Workflow

```bash
git checkout -b feature/amazing-feature
git commit -m "Add amazing feature"
git push origin feature/amazing-feature
```

Then open a Pull Request.

---

# 📄 License

Distributed under the MIT License.

See:

```text
LICENSE
```

for more information.

---

# 🙏 Credits

Built on top of amazing open-source projects:

* LiteLLM
* Redis
* PostgreSQL
* Langfuse
* OpenRouter
* Groq
* NVIDIA NIM
* Mistral AI
* Cohere
* Cerebras

---

# 📬 Support

## GitHub Issues

[https://github.com/Dinesh-DLanzer/OmniLLM-Gateway/issues](https://github.com/Dinesh-DLanzer/OmniLLM-Gateway/issues)

---

<div align="center">

## 🚀 Happy Building with OmniLLM Gateway

Unified • Intelligent • Dynamic • OpenAI-Compatible

</div>

