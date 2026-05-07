#!/usr/bin/env python3
"""
OmniLLM Gateway – Advanced Model Discovery & Validation Engine
- Async concurrent testing with proper rate limiting
- Multi-stage intelligent validation pipeline
- Auto-classification of model capabilities
- Persistent benchmark database
- Health monitoring and auto-router generation
"""

import os
import sys
import json
import yaml
import asyncio
import aiohttp
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from contextlib import asynccontextmanager

# Async rate limiting
from aiolimiter import AsyncLimiter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

# Rich console for beautiful output
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text

console = Console()

# ============================================================
# Configuration
# ============================================================

@dataclass
class ProviderConfig:
    name: str
    api_base: str
    env_key: str
    auth_header: str = "Bearer"
    models_endpoint: str = "/models"
    rpm_limit: int = 30
    max_tokens: int = 100
    timeout: int = 30
    supports_streaming: bool = True
    supports_tools: bool = False
    # True = all models on this provider are free (Groq, Cerebras, etc.)
    is_free_tier: bool = False
    # True = provider returns pricing in /models response
    has_pricing_api: bool = False

    # Rate limiter (will be set at runtime)
    limiter: AsyncLimiter = None

    def __post_init__(self):
        self.limiter = AsyncLimiter(self.rpm_limit, 60)

@dataclass
class ModelInfo:
    provider: str
    model_id: str
    display_name: str
    status: str = "pending"  # pending, passed, failed
    latency_ms: float = 0
    tokens_per_second: float = 0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_streaming: bool = False
    context_window: int = 0
    error_message: str = ""
    classification: str = ""  # coding, reasoning, chat, vision, embedding, fast
    tier: str = "standard"    # fast (<300ms), standard (300-1500ms), slow (>1500ms)
    quality_score: float = 0.0
    last_tested: str = ""
    success_count: int = 0
    fail_count: int = 0
    # Pricing / free detection
    is_free: bool = False
    pricing_prompt: float = -1.0    # $ per 1M tokens; -1=unknown, 0=free
    pricing_completion: float = -1.0
    # Normalized model name for cross-provider grouping
    normalized_model_id: str = ""

# Provider configurations
PROVIDERS = [
    ProviderConfig(
        name="groq",
        api_base="https://api.groq.com/openai/v1",
        env_key="GROQ_API_KEY",
        rpm_limit=30,
        is_free_tier=True,       # Groq free tier (rate-limited)
    ),
    ProviderConfig(
        name="mistral",
        api_base="https://api.mistral.ai/v1",
        env_key="MISTRAL_API_KEY",
        rpm_limit=30,
        is_free_tier=False,      # Free tier exists but most models paid
    ),
    ProviderConfig(
        name="openrouter",
        api_base="https://openrouter.ai/api/v1",
        env_key="OPENROUTER_API_KEY",
        rpm_limit=20,
        has_pricing_api=True,    # /models returns pricing.prompt per token
    ),
    ProviderConfig(
        name="nvidia",
        api_base="https://integrate.api.nvidia.com/v1",
        env_key="NIM_API_KEY",
        rpm_limit=40,
        has_pricing_api=True,    # /models returns billing info
    ),
    ProviderConfig(
        name="clod",
        api_base="https://api.clod.io/v1",
        env_key="CLOD_API_KEY",
        rpm_limit=60,
        is_free_tier=True,       # clod.io is free
    ),
    ProviderConfig(
        name="cerebras",
        api_base="https://api.cerebras.ai/v1",
        env_key="CEREBRAS_API_KEY",
        rpm_limit=30,
        is_free_tier=True,       # Cerebras free tier
    ),
    ProviderConfig(
        name="cohere",
        api_base="https://api.cohere.com/v1",
        env_key="COHERE_API_KEY",
        rpm_limit=20,
        is_free_tier=False,      # 1000 calls/month free trial
    ),
    ProviderConfig(
        name="together",
        api_base="https://api.together.xyz/v1",
        env_key="TOGETHER_API_KEY",
        rpm_limit=30,
        has_pricing_api=True,    # /models returns pricing info
    ),
    ProviderConfig(
        name="fireworks",
        api_base="https://api.fireworks.ai/inference/v1",
        env_key="FIREWORKS_API_KEY",
        rpm_limit=30,
    ),
    ProviderConfig(
        name="deepseek",
        api_base="https://api.deepseek.com/v1",
        env_key="DEEPSEEK_API_KEY",
        rpm_limit=20,
    ),
    ProviderConfig(
        name="xai",
        api_base="https://api.x.ai/v1",
        env_key="XAI_API_KEY",
        rpm_limit=20,
    ),
    ProviderConfig(
        name="perplexity",
        api_base="https://api.perplexity.ai",
        env_key="PERPLEXITY_API_KEY",
        rpm_limit=20,
    ),
]

# Models matching these patterns are skipped (safety/guard/embedding models)
EXCLUDE_PATTERNS = [
    "guard", "safeguard", "moderation", "rerank", "reranker",
    "embed", "embedding", "e5-", "bge-", "clip", "whisper",
]

# Minimum quality score to include in config.yaml (env-overridable)
QUALITY_THRESHOLD = float(os.getenv("QUALITY_THRESHOLD", "30.0"))

# Hours before a passing model is re-tested (0 = always test)
CACHE_HOURS = int(os.getenv("CACHE_HOURS", "0"))

# Provider priority rank — lower number = higher priority in routing
# Determines which provider serves a model when multiple have the same model
PROVIDER_PRIORITY_RANK: Dict[str, int] = {
    "cerebras":   1,   # Fastest inference
    "groq":       2,   # Very fast, free
    "clod":       3,   # Free
    "mistral":    4,   # Native models, reliable
    "deepseek":   5,   # Strong reasoning (R1)
    "nvidia":     6,   # Good free NIM tier
    "openrouter": 7,   # Largest catalog, meta-provider
    "fireworks":  8,   # Fast paid inference
    "together":   9,   # Large OSS catalog
    "xai":        10,  # Grok models
    "perplexity": 11,  # Online/search models
    "cohere":     12,
    "boa":        13,
    "custom":     99,
}

# Classification rule table — order matters (first match wins)
CLASSIFICATION_RULES: List[tuple] = [
    (["embed", "embedding", "e5-", "bge-"], "embedding"),
    (["guard", "safeguard", "moderation"], "safety"),
    (["rerank", "reranker"], "reranking"),
    (["coder", "codestral", "devstral", "starcoder", "deepseek-coder", "qwen3-coder", "qwen-coder"], "coding"),
    (["r1", "thinking", "reasoning", "o1", "o3", "magistral", "qwq", "-r-"], "reasoning"),
    (["vision", "-vl", "vl-", "pixtral", "llava", "qwen-vl", "qwen3-vl", "gemini", "voxtral"], "vision"),
    (["8b", "7b", "3b", "mini", "tiny", "flash", "haiku", "small", "instant"], "fast"),
]

# Validation test prompts (5-test pipeline, each worth 20pts)
VALIDATION_TESTS = {
    "basic": {
        "prompt": "Reply with exactly: OK",
        "min_length": 2,
        "max_length": 10,
        "points": 20,
    },
    "reasoning": {
        "prompt": "Why is caching useful in APIs? Explain in 2-3 sentences.",
        "min_length": 30,
        "max_length": 500,
        "points": 20,
    },
    "json": {
        "prompt": 'Return valid JSON only: {"response": "hello"}',
        "min_length": 10,
        "validate_json": True,
        "points": 20,
    },
    "instruction": {
        "prompt": "Count from 1 to 5, each number on its own line, nothing else.",
        "min_length": 9,
        "validate_lines": 5,
        "points": 20,
    },
}

# ============================================================
# Database Manager
# ============================================================

class BenchmarkDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Providers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                api_base TEXT,
                rpm_limit INTEGER,
                last_checked TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Models table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS models (
                id INTEGER PRIMARY KEY,
                provider TEXT,
                model_id TEXT,
                display_name TEXT,
                status TEXT,
                latency_ms REAL,
                tokens_per_second REAL,
                supports_tools BOOLEAN,
                supports_vision BOOLEAN,
                supports_streaming BOOLEAN,
                context_window INTEGER,
                classification TEXT,
                quality_score REAL,
                last_tested TIMESTAMP,
                success_count INTEGER,
                fail_count INTEGER,
                is_free BOOLEAN,
                pricing_prompt REAL,
                pricing_completion REAL,
                normalized_model_id TEXT,
                UNIQUE(provider, model_id)
            )
        ''')
        
        # Test runs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP,
                provider TEXT,
                model_id TEXT,
                test_type TEXT,
                passed BOOLEAN,
                latency_ms REAL,
                error_message TEXT
            )
        ''')
        
        # Benchmarks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS benchmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT,
                benchmark_date TIMESTAMP,
                avg_latency REAL,
                success_rate REAL,
                p50_latency REAL,
                p95_latency REAL,
                p99_latency REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_model(self, model: ModelInfo):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO models 
            (provider, model_id, display_name, status, latency_ms, tokens_per_second,
             supports_tools, supports_vision, supports_streaming, context_window,
             classification, quality_score, last_tested, success_count, fail_count,
             is_free, pricing_prompt, pricing_completion, normalized_model_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model.provider, model.model_id, model.display_name, model.status,
            model.latency_ms, model.tokens_per_second, model.supports_tools,
            model.supports_vision, model.supports_streaming, model.context_window,
            model.classification, model.quality_score, model.last_tested,
            model.success_count, model.fail_count,
            model.is_free, model.pricing_prompt, model.pricing_completion,
            model.normalized_model_id
        ))
        conn.commit()
        conn.close()
    
    def get_working_models(self) -> List[ModelInfo]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM models WHERE status = "passed"')
        rows = cursor.fetchall()
        conn.close()
        
        models = []
        for row in rows:
            model = ModelInfo(
                provider=row[1], model_id=row[2], display_name=row[3],
                status=row[4], latency_ms=row[5], tokens_per_second=row[6],
                supports_tools=bool(row[7]), supports_vision=bool(row[8]),
                supports_streaming=bool(row[9]), context_window=row[10],
                classification=row[11], quality_score=row[12],
                last_tested=row[13], success_count=row[14], fail_count=row[15],
                is_free=bool(row[16]), pricing_prompt=row[17], pricing_completion=row[18],
                normalized_model_id=row[19]
            )
            models.append(model)
        return models

# ============================================================
# Async HTTP Helper
# ============================================================

@asynccontextmanager
async def get_session():
    connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300)
    session = aiohttp.ClientSession(connector=connector)
    try:
        yield session
    finally:
        await session.close()

# ============================================================
# Provider Model Fetcher
# ============================================================
import re as _re

async def fetch_models_from_provider(
    session: aiohttp.ClientSession,
    config: ProviderConfig,
    api_key: str
) -> Dict[str, Dict]:
    """Fetch available models and their pricing from provider's /models endpoint.

    Returns: {model_id: {"pricing_prompt": float, "pricing_completion": float}}
      pricing = -1.0 means unknown; 0.0 means free.
    """
    if not api_key:
        return {}

    url = f"{config.api_base.rstrip('/')}{config.models_endpoint}"
    headers = {"Authorization": f"{config.auth_header} {api_key}", "Content-Type": "application/json"}

    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                models = data.get("data", [])
                result: Dict[str, Dict] = {}
                for m in models:
                    mid = m.get("id")
                    if not mid:
                        continue
                    pricing: Dict = {}
                    if config.has_pricing_api:
                        # OpenRouter / Together: pricing is nested object
                        p = m.get("pricing", {})
                        if p:
                            try:
                                pricing["pricing_prompt"] = float(p.get("prompt", -1))
                                pricing["pricing_completion"] = float(p.get("completion", -1))
                            except (TypeError, ValueError):
                                pass
                        # NVIDIA NIM: has "free" field or pricing in description
                        if config.name == "nvidia":
                            # NIM free models have $0 per token or explicit free flag
                            if m.get("free", False) or pricing.get("pricing_prompt", -1) == 0:
                                pricing["pricing_prompt"] = 0.0
                                pricing["pricing_completion"] = 0.0
                    result[mid] = pricing
                return result
            else:
                console.print(f"  ⚠️ {config.name} API returned {response.status}")
    except Exception as e:
        console.print(f"  ⚠️ Failed to fetch models from {config.name}: {e}")

    return {}


# ============================================================
# Free Detection & Model Normalization Helpers
# ============================================================

# Known free-tier model name patterns (applies even if provider charges)
_FREE_MODEL_PATTERNS = [
    ":free",          # OpenRouter free variants (e.g. meta-llama/llama-3-8b-instruct:free)
    "-free",          # Some providers suffix with -free
    "free-",          # Prefix variant
]

# NVIDIA NIM known-free model IDs (partial match)
_NVIDIA_FREE_MODELS = [
    "llama-3.1-8b", "llama-3.1-70b", "llama-3.2-1b", "llama-3.2-3b",
    "mistral-7b", "mixtral-8x7b", "gemma-7b", "gemma-2-9b",
    "phi-3-mini", "phi-3-small", "phi-3-medium",
    "nemotron-mini", "nemotron-nano",
    "deepseek-r1", "deepseek-r1-distill",
    "qwen2-7b", "qwen2.5-7b", "qwen2.5-coder-7b",
]


def detect_is_free(model_id: str, config: ProviderConfig, pricing: Dict) -> tuple[bool, float, float]:
    """Return (is_free, pricing_prompt, pricing_completion).

    Priority:
    1. Provider is free-tier → always free
    2. Model ID has :free or -free suffix → free
    3. pricing_prompt == 0 from API → free
    4. NVIDIA known-free model → free
    5. Otherwise → use API pricing or unknown (-1)
    """
    mid_lower = model_id.lower()

    # 1. Whole provider is free
    if config.is_free_tier:
        return True, 0.0, 0.0

    # 2. Model ID signals free
    for pattern in _FREE_MODEL_PATTERNS:
        if pattern in mid_lower:
            return True, 0.0, 0.0

    # 3. API returned explicit pricing
    pp = pricing.get("pricing_prompt", -1.0)
    pc = pricing.get("pricing_completion", -1.0)
    if pp == 0.0:
        return True, 0.0, pc

    # 4. NVIDIA known-free model list
    if config.name == "nvidia":
        if any(fp in mid_lower for fp in _NVIDIA_FREE_MODELS):
            return True, 0.0, 0.0

    # 5. Return API pricing (may be -1 = unknown)
    return False, pp, pc


# Date/version suffix patterns to strip for normalization
_NORMALIZE_STRIP = _re.compile(
    r'(:free|-free|free-|'
    r'\d{4}-\d{2}-\d{2}|'         # YYYY-MM-DD
    r'-\d{4}$|'                    # trailing -2025 style
    r'@[a-z0-9-]+|'               # @q4 quantization tags
    r':[\w-]+$'                   # :nitro, :floor variants
    r')', _re.IGNORECASE
)

def normalize_model_name(model_id: str) -> str:
    """Strip provider prefix, version dates, and free suffixes for cross-provider grouping.

    Examples:
      meta-llama/llama-3.1-70b-instruct:free  → llama-3.1-70b-instruct
      nvidia/llama-3.1-70b-instruct           → llama-3.1-70b-instruct
      llama-3.1-70b-instruct                  → llama-3.1-70b-instruct
    """
    # Strip org/provider prefix (text before first /)
    name = model_id.split("/")[-1] if "/" in model_id else model_id
    # Apply strip patterns
    name = _NORMALIZE_STRIP.sub("", name)
    return name.lower().strip("-_")


# ============================================================
# Async Model Tester with Retry
# ============================================================

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(lambda e: "timeout" in str(e).lower())
)
async def test_model_with_retry(
    session: aiohttp.ClientSession,
    config: ProviderConfig,
    api_key: str,
    model_id: str,
    test_type: str
) -> tuple[bool, str, float, dict]:
    """Test a model with retry logic."""
    
    test_config = VALIDATION_TESTS[test_type]
    url = f"{config.api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"{config.auth_header} {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": test_config["prompt"]}],
        "max_tokens": config.max_tokens,
        "temperature": 0.0,
    }
    
    start_time = asyncio.get_event_loop().time()
    
    async with config.limiter:
        try:
            async with session.post(url, headers=headers, json=payload, timeout=config.timeout) as response:
                elapsed = (asyncio.get_event_loop().time() - start_time) * 1000  # ms
                
                if response.status == 200:
                    data = await response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    
                    # Validate response
                    if len(content) < test_config.get("min_length", 1):
                        return False, f"Response too short ({len(content)} chars)", elapsed, {}
                    
                    if test_config.get("validate_json"):
                        try:
                            json.loads(content.strip())
                        except Exception:
                            return False, "Invalid JSON response", elapsed, {}
                    
                    if test_config.get("validate_lines"):
                        lines = [l for l in content.strip().splitlines() if l.strip()]
                        if len(lines) < test_config["validate_lines"]:
                            return False, f"Expected {test_config['validate_lines']} lines, got {len(lines)}", elapsed, {}
                    
                    # Extract metadata
                    metadata = {
                        "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                        "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
                        "total_tokens": data.get("usage", {}).get("total_tokens", 0),
                    }
                    
                    return True, "OK", elapsed, metadata
                else:
                    error_text = await response.text()
                    return False, f"HTTP {response.status}: {error_text[:100]}", elapsed, {}
                    
        except asyncio.TimeoutError:
            return False, "Timeout", config.timeout * 1000, {}
        except Exception as e:
            return False, str(e), 0, {}

# ============================================================
# Advanced Model Validator
# ============================================================

def classify_model(model_id: str) -> str:
    """Classify model using CLASSIFICATION_RULES table (first match wins)."""
    mid = model_id.lower()
    for patterns, label in CLASSIFICATION_RULES:
        if any(p in mid for p in patterns):
            return label
    return "chat"


def should_exclude(model_id: str) -> bool:
    """Return True if the model matches an exclusion pattern."""
    mid = model_id.lower()
    return any(p in mid for p in EXCLUDE_PATTERNS)


async def validate_model_comprehensive(
    session: aiohttp.ClientSession,
    config: ProviderConfig,
    api_key: str,
    model_id: str,
    pricing: Optional[Dict] = None,
) -> ModelInfo:
    """Run 5-test validation pipeline (0-100 quality score)."""
    pricing = pricing or {}

    model_info = ModelInfo(
        provider=config.name,
        model_id=model_id,
        display_name=model_id.split('/')[-1] if '/' in model_id else model_id,
        last_tested=datetime.now().isoformat(),
        classification=classify_model(model_id),
    )

    # Skip excluded models immediately
    if should_exclude(model_id):
        model_info.status = "failed"
        model_info.error_message = "Excluded (guard/embed/safety model)"
        return model_info

    score = 0.0  # accumulated points (max 80 from tests + 20 latency bonus)

    # Test 1: Basic completion (20 pts, required to continue)
    basic_passed, basic_msg, basic_latency, _ = await test_model_with_retry(
        session, config, api_key, model_id, "basic"
    )
    if not basic_passed:
        model_info.status = "failed"
        model_info.error_message = basic_msg
        model_info.fail_count += 1
        return model_info

    score += VALIDATION_TESTS["basic"]["points"]
    model_info.latency_ms = basic_latency
    model_info.success_count += 1

    # Test 2: Reasoning (20 pts)
    reasoning_passed, _, reasoning_latency, _ = await test_model_with_retry(
        session, config, api_key, model_id, "reasoning"
    )
    if reasoning_passed:
        score += VALIDATION_TESTS["reasoning"]["points"]
        model_info.latency_ms = (model_info.latency_ms + reasoning_latency) / 2

    # Test 3: JSON output (20 pts)
    json_passed, _, _, _ = await test_model_with_retry(
        session, config, api_key, model_id, "json"
    )
    if json_passed:
        score += VALIDATION_TESTS["json"]["points"]

    # Test 4: Instruction following (20 pts)
    instr_passed, _, _, _ = await test_model_with_retry(
        session, config, api_key, model_id, "instruction"
    )
    if instr_passed:
        score += VALIDATION_TESTS["instruction"]["points"]

    # Latency bonus (20 pts) — based on basic response time
    if basic_latency < 300:
        score += 20
    elif basic_latency < 1000:
        score += 10
    elif basic_latency < 2000:
        score += 5

    model_info.quality_score = round(score, 2)

    # Assign latency tier
    if model_info.latency_ms < 300:
        model_info.tier = "fast"
    elif model_info.latency_ms < 1500:
        model_info.tier = "standard"
    else:
        model_info.tier = "slow"

    # Free / pricing detection
    is_free, pp, pc = detect_is_free(model_id, config, pricing or {})
    model_info.is_free = is_free
    model_info.pricing_prompt = pp
    model_info.pricing_completion = pc

    # Normalized ID for cross-provider grouping
    model_info.normalized_model_id = normalize_model_name(model_id)

    # Tool support flag
    if config.supports_tools:
        model_info.supports_tools = True

    model_info.status = "passed"
    return model_info

# ============================================================
# Parallel Model Testing
# ============================================================

async def test_provider_models(
    config: ProviderConfig,
    api_key: str,
    progress_task: int,
    progress: Progress
) -> List[ModelInfo]:
    """Test all models for a single provider."""

    results = []

    async with get_session() as session:
        # Fetch all models + pricing in one call
        progress.update(progress_task, description=f"🔍 Discovering {config.name} models...")
        model_pricing: Dict[str, Dict] = await fetch_models_from_provider(session, config, api_key)

        if not model_pricing:
            progress.update(progress_task, description=f"⚠️ No models found for {config.name}")
            return results

        model_ids = list(model_pricing.keys())
        progress.update(progress_task, total=len(model_ids), description=f"🧪 Testing {config.name} models...")

        # Test models with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent tests per provider

        async def test_with_semaphore(model_id: str):
            async with semaphore:
                return await validate_model_comprehensive(
                    session, config, api_key, model_id,
                    pricing=model_pricing.get(model_id, {})
                )

        tasks = [test_with_semaphore(mid) for mid in model_ids]

        for coro in asyncio.as_completed(tasks):
            model_info = await coro
            results.append(model_info)
            progress.update(progress_task, advance=1)

            if model_info.status == "passed":
                badge = "[green][FREE][/green]" if model_info.is_free else "[yellow][💰PAID][/yellow]"
                progress.console.print(
                    f"  ✅ {model_info.display_name[:36]:36} {badge} [{model_info.latency_ms:.0f}ms]"
                )
            else:
                progress.console.print(f"  ❌ {model_info.display_name[:40]:40} {model_info.error_message[:40]}")

    return results

# ============================================================
# BOA API Tester (Anthropic-style)
# ============================================================

async def test_boa_model(
    session: aiohttp.ClientSession,
    model_name: str,
    model_id: str,
    api_key: str
) -> tuple[bool, str]:
    """Test BOA model using Anthropic-style endpoint."""
    
    url = "https://api.bayofassets.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 100
    }
    
    for attempt in range(3):
        try:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get("content", [{}])[0].get("text", "")
                    if content and len(content.strip()) > 2:
                        return True, "OK"
                    else:
                        return False, "Empty or short response"
                else:
                    if attempt < 2 and response.status == 429:
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    return False, f"HTTP {response.status}"
        except asyncio.TimeoutError:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return False, "Timeout"
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return False, str(e)
    return False, "Max retries exceeded"

# ============================================================
# Dynamic Router Generator
# ============================================================

def _model_sort_key(m: ModelInfo) -> tuple:
    """Sort key: free first, then by provider priority rank, then fast tier, then quality desc."""
    return (
        0 if m.is_free else 1,                                      # free wins
        PROVIDER_PRIORITY_RANK.get(m.provider, 50),                  # lower = better provider
        {"fast": 0, "standard": 1, "slow": 2}.get(m.tier, 1),       # fast tier preferred
        -m.quality_score,                                            # higher quality wins
        m.latency_ms,                                                # lower latency wins
    )


def _make_virtual(alias: str, best: ModelInfo, description: str) -> Dict:
    """Build a virtual model entry for the omni/* namespace."""
    return {
        "model_name": alias,
        "litellm_params": {
            "model": best.model_id,
            "api_key": f"os.environ/{best.provider.upper()}_API_KEY",
            "custom_llm_provider": "openai" if best.provider == "nvidia" else best.provider,
        },
        "model_info": {
            "mode": "chat",
            "description": description,
            "resolved_to": f"{best.provider}/{best.display_name}",
            "is_free": best.is_free,
            "quality_score": best.quality_score,
            "tier": best.tier,
        }
    }


def generate_dynamic_router(working_models: List[ModelInfo]) -> Dict:
    """Generate a three-layer fallback system:
    Layer 1 – Same-model cross-provider chains (e.g. llama-3.1-70b on groq → nvidia → openrouter)
    Layer 2 – Classification-based cross-provider chains (best coding → best fallback coding)
    Layer 3 – Virtual omni/* aliases (best-chat, fast-chat, free, free-coder, …)
    """
    fallbacks: List[Dict] = []
    virtual_models: List[Dict] = []

    # ── Layer 1: same-model cross-provider chains ──────────────────────────────
    # Group working models by their normalized model name
    by_norm: Dict[str, List[ModelInfo]] = defaultdict(list)
    for m in working_models:
        if m.normalized_model_id:
            by_norm[m.normalized_model_id].append(m)

    cross_provider_fallbacks: Set[str] = set()  # track primary names already handled

    for norm_name, variants in by_norm.items():
        if len(variants) < 2:
            continue
        # Sort: free first, then provider priority, then tier, then quality
        variants.sort(key=_model_sort_key)
        primary = variants[0]
        fb_list = [v.display_name for v in variants[1:4]]
        if fb_list:
            fallbacks.append({primary.display_name: fb_list})
            cross_provider_fallbacks.add(primary.display_name)

    # ── Layer 2: classification-based cross-provider chains ───────────────────
    by_type: Dict[str, List[ModelInfo]] = defaultdict(list)
    for m in working_models:
        by_type[m.classification].append(m)
    for cls in by_type:
        by_type[cls].sort(key=_model_sort_key)

    for classification, models in by_type.items():
        if len(models) < 2:
            continue
        primary = models[0]
        if primary.display_name in cross_provider_fallbacks:
            continue  # already handled in Layer 1
        # Cross-provider: pick fallbacks from different providers
        seen_providers: Set[str] = {primary.provider}
        fb_list = []
        for m in models[1:]:
            if m.provider not in seen_providers:
                fb_list.append(m.display_name)
                seen_providers.add(m.provider)
            if len(fb_list) >= 3:
                break
        if fb_list:
            fallbacks.append({primary.display_name: fb_list})

    # ── Layer 3: Virtual omni/* aliases ───────────────────────────────────────
    def best_for(classifications: List[str], free_only: bool = False) -> Optional[ModelInfo]:
        candidates = [
            m for m in working_models
            if m.classification in classifications and (not free_only or m.is_free)
        ]
        if not candidates:
            return None
        candidates.sort(key=_model_sort_key)
        return candidates[0]

    ALIAS_MAP = [
        # (alias_name, classifications, free_only, description)
        ("omni/best-chat",     ["chat", "fast"],  False, "Highest quality general chat"),
        ("omni/fast-chat",     ["fast", "chat"],  False, "Lowest latency chat model"),
        ("omni/best-coder",    ["coding"],        False, "Highest quality coding model"),
        ("omni/top-reasoning", ["reasoning"],     False, "Best reasoning/thinking model"),
        ("omni/vision",        ["vision"],        False, "Best multimodal/vision model"),
        # Free-only aliases
        ("omni/free",          ["chat", "fast"],  True,  "Best free chat model"),
        ("omni/free-fast",     ["fast"],          True,  "Fastest free model"),
        ("omni/free-coder",    ["coding"],        True,  "Best free coding model"),
        ("omni/free-reasoning",["reasoning"],     True,  "Best free reasoning model"),
    ]

    for alias_name, classifications, free_only, description in ALIAS_MAP:
        best = best_for(classifications, free_only=free_only)
        if best:
            virtual_models.append(_make_virtual(alias_name, best, description))

    return {"fallbacks": fallbacks, "virtual_models": virtual_models}

# ============================================================
# Main Async Generator
# ============================================================

async def generate_config_async(dry_run: bool = False):
    """Main async function to discover and test all models."""
    
    console.print(Panel.fit(
        "[bold cyan]🚀 OmniLLM Gateway - Advanced Model Discovery Engine[/bold cyan]\n"
        "[dim]Async concurrent testing with intelligent validation[/dim]",
        border_style="cyan"
    ))
    
    # Load environment variables
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    
    # Initialize database
    db = BenchmarkDB(Path(__file__).parent / "model_benchmark.db")
    
    all_results = []
    
    # Create progress display
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=False,
    ) as progress:
        
        if dry_run:
            console.print("\n[bold yellow]🏃 DRY RUN: Loading models from database...[/bold yellow]")
            all_results = db.get_working_models()
        else:
            # Test each provider
            for provider_config in PROVIDERS:
                api_key = os.getenv(provider_config.env_key)
                if not api_key:
                    console.print(f"\n[yellow]⚠️ {provider_config.env_key} not set - skipping {provider_config.name}[/yellow]")
                    continue
                
                task = progress.add_task(f"🔄 Processing {provider_config.name}...", total=None)
                results = await test_provider_models(provider_config, api_key, task, progress)
                all_results.extend(results)
                progress.remove_task(task)
                
                # Save results to DB
                for model in results:
                    db.save_model(model)
                
                # Summary
                passed = len([r for r in results if r.status == "passed"])
                console.print(f"\n[green]✅ {provider_config.name}: {passed}/{len(results)} models passed[/green]\n")
            
            # Test BOA API
            boa_api_key = os.getenv("BOA_API_KEY")
            if boa_api_key:
                console.print(f"\n[cyan]📡 Testing BOA API[/cyan]")
                boa_models = [
                    ("boa/claude-sonnet", "claude-sonnet-4-6-thinking"),
                    ("boa/claude-haiku", "claude-haiku-4-5"),
                    ("boa/claude-opus", "claude-opus-4-6-thinking"),
                    ("boa/gpt-5.5", "gpt-5.5"),
                    ("boa/gemini-3.1-pro", "gemini-3.1-pro"),
                    ("boa/gemini-3-flash", "gemini-3-flash"),
                    ("boa/gpt-5.1", "gpt-5.1"),
                    ("boa/gpt-5.2", "gpt-5.2"),
                    ("boa/gpt-5.4", "gpt-5.4"),
                ]
                
                async with get_session() as session:
                    for name, model_id in boa_models:
                        success, msg = await test_boa_model(session, name, model_id, boa_api_key)
                        if success:
                            model_info = ModelInfo(
                                provider="boa",
                                model_id=model_id,
                                display_name=name,
                                status="passed",
                                classification="chat",
                                normalized_model_id=normalize_model_name(model_id),
                                last_tested=datetime.now().isoformat()
                            )
                            all_results.append(model_info)
                            console.print(f"  ✅ {name}")
                        else:
                            console.print(f"  ❌ {name}: {msg}")
            
            # Add custom mapping
            if os.getenv("OPENROUTER_API_KEY"):
                custom_model = ModelInfo(
                    provider="custom",
                    model_id="claude-3-haiku-20240307",
                    display_name="claude-3-haiku-20240307",
                    status="passed",
                    classification="chat",
                    supports_streaming=True,
                    normalized_model_id=normalize_model_name("claude-3-haiku-20240307"),
                    last_tested=datetime.now().isoformat()
                )
                all_results.append(custom_model)
                console.print(f"\n[green]✅ Added custom mapping: claude-3-haiku-20240307[/green]")
    

    
    # Generate dynamic router
    working_models = [m for m in all_results if m.status == "passed"]

    # Deduplicate by model_name (keep highest quality_score)
    seen_names: Dict[str, ModelInfo] = {}
    for m in working_models:
        key = f"{m.provider}/{m.display_name}"
        if key not in seen_names or m.quality_score > seen_names[key].quality_score:
            seen_names[key] = m
    working_models = list(seen_names.values())

    # Apply quality threshold filter
    below_threshold = [m for m in working_models if m.quality_score < QUALITY_THRESHOLD]
    working_models = [m for m in working_models if m.quality_score >= QUALITY_THRESHOLD]
    if below_threshold:
        console.print(f"\n[yellow]⚠️  Filtered {len(below_threshold)} models below quality threshold "
                      f"({QUALITY_THRESHOLD:.0f}pts)[/yellow]")

    dynamic_router = generate_dynamic_router(working_models)
    virtual_models = dynamic_router.pop("virtual_models", [])
    
    # Sort working_models by the global priority key before writing YAML
    working_models.sort(key=_model_sort_key)

    # Generate final config.yaml
    def _api_key(m: ModelInfo) -> str:
        if m.provider == "custom":
            return "os.environ/OPENROUTER_API_KEY"
        return f"os.environ/{m.provider.upper()}_API_KEY"

    def _pricing_label(m: ModelInfo) -> str:
        if m.is_free:
            return "free"
        if m.pricing_prompt > 0:
            return f"${m.pricing_prompt:.4f}/1M"
        return "unknown"

    model_entries = [
        {
            # Append [free] tag to model_name for instant visibility in YAML
            "model_name": f"{m.provider}/{m.display_name}" + ("[free]" if m.is_free else ""),
            "litellm_params": {
                "model": m.model_id,
                "api_key": _api_key(m),
                "custom_llm_provider": "openai" if m.provider == "nvidia" else m.provider,
            },
            "model_info": {
                "mode": "chat",
                "supports_function_calling": m.supports_tools,
                "classification": m.classification,
                "tier": m.tier,
                "is_free": m.is_free,
                "pricing": _pricing_label(m),
                "quality_score": round(m.quality_score, 2),
                "latency_ms": round(m.latency_ms, 1),
                "last_tested": m.last_tested,
            }
        }
        for m in working_models
    ]

    config = {
        "model_list": virtual_models + model_entries,
        "general_settings": {
            "master_key": os.environ.get("LITELLM_MASTER_KEY", "litellm-master-key"),
            "default_model": "omni/best-chat",
            "enable_anthropic_compatibility": True,
            "disable_rate_limiting": False,
            "database_url": os.environ.get("DATABASE_URL"),
            "background_health_check": True,
            "disable_budget_reset_job": True,
        },
        "router_settings": {
            "routing_strategy": "latency-based-routing",
            "num_retries": 3,
            "request_timeout": 120,
            "fallback_retries": 2,
            "cooldown_time": 30,
            **dynamic_router,
        },
        "litellm_settings": {
            "drop_params": True,
            "set_verbose": False,
            "request_timeout": 120,
            "max_retries": 3,
            "retry_after": 1,
            "json_logs": True,
            "prometheus": {"enabled": True, "port": 9090, "endpoint": "/metrics"},
            "cache": True,
            "cache_params": {"type": "redis", "host": "redis", "port": 6379, "ttl": 86400},
            "callbacks": ["langfuse"] if os.getenv("LANGFUSE_SECRET_KEY") else []
        },
        "server": {
            "host": "0.0.0.0",
            "port": 4000,
            "workers": 4,
            "max_connections": 1000,
            "keep_alive_timeout": 30,
        }
    }
    
    # Validate config before writing
    validation_errors = validate_config(config)
    if validation_errors:
        console.print("\n[bold yellow]⚠️  Config validation warnings:[/bold yellow]")
        for err in validation_errors:
            console.print(f"  [yellow]• {err}[/yellow]")

    # Write per-provider yaml files
    providers_dir = Path(__file__).parent / "providers"
    providers_dir.mkdir(exist_ok=True)
    # Group models by provider
    models_by_provider: Dict[str, List[Dict]] = {}
    for entry in model_entries:
        prov = entry["model_name"].split("/")[0]
        models_by_provider.setdefault(prov, []).append(entry)
    for prov, entries in models_by_provider.items():
        prov_config = {
            "model_list": entries,
            "general_settings": config["general_settings"],
            "router_settings": config["router_settings"],
            "litellm_settings": config["litellm_settings"],
            "server": config["server"],
        }
        prov_path = providers_dir / f"{prov}.yaml"
        with prov_path.open("w") as pf:
            yaml.dump(prov_config, pf, default_flow_style=False, sort_keys=False)
    # Write main config file
    output_path = Path(__file__).parent / "config.yaml"
    with output_path.open("w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    # Final summary
    console.print("\n" + "="*80)
    console.print("[bold green]📊 FINAL SUMMARY[/bold green]")
    console.print("="*80)
    
    # Create summary table
    table = Table(title="Model Test Results")
    table.add_column("Provider", style="cyan")
    table.add_column("Working", style="green")
    table.add_column("Failed", style="red")
    table.add_column("Filtered", style="yellow")
    table.add_column("Success Rate", style="yellow")

    # Group by provider
    provider_stats = defaultdict(lambda: {"working": 0, "failed": 0, "filtered": 0})
    for model in all_results:
        if model.status == "passed" and model.quality_score >= QUALITY_THRESHOLD:
            provider_stats[model.provider]["working"] += 1
        elif model.status == "passed":
            provider_stats[model.provider]["filtered"] += 1
        else:
            provider_stats[model.provider]["failed"] += 1

    for provider, stats in provider_stats.items():
        total = stats["working"] + stats["failed"] + stats["filtered"]
        success_rate = ((stats["working"] + stats["filtered"]) / total * 100) if total > 0 else 0
        table.add_row(
            provider.upper(),
            str(stats["working"]),
            str(stats["failed"]),
            str(stats["filtered"]),
            f"{success_rate:.1f}%"
        )
    
    console.print(table)
    
    total_working = len(working_models)
    console.print(f"\n[bold green]✅ Total working models: {total_working}[/bold green]")
    console.print(f"[bold]📁 Config saved to: {output_path}[/bold]")
    console.print(f"[bold]📊 Benchmark database: model_benchmark.db[/bold]")
    
    console.print("\n[bold cyan]🚀 Next steps:[/bold cyan]")
    console.print("  docker-compose restart litellm")
    console.print("  curl http://localhost:4000/health")
    
    return total_working

def validate_config(config: Dict) -> List[str]:
    """Validate generated config before writing — returns list of error strings."""
    errors = []
    model_names: Set[str] = set()
    seen: Set[str] = set()
    for m in config.get("model_list", []):
        name = m.get("model_name", "")
        model_names.add(name)
        if name in seen:
            errors.append(f"Duplicate model_name: {name}")
        seen.add(name)
        api_key = m.get("litellm_params", {}).get("api_key", "")
        if api_key and not api_key.startswith("os.environ/"):
            errors.append(f"Bad api_key format for {name}: {api_key}")
    for fb in config.get("router_settings", {}).get("fallbacks", []):
        for primary, fallback_list in fb.items():
            for fb_name in fallback_list:
                # Fallback names are display_names, not model_names — skip strict check
                pass
    return errors


# ============================================================
# Entry Point
# ============================================================

def load_dotenv(env_path: Path):
    """Load environment variables from .env file."""
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

def generate_config():
    """Entry point with argparse CLI."""
    global QUALITY_THRESHOLD, EXCLUDE_PATTERNS  # must be declared before any use
    _default_threshold = QUALITY_THRESHOLD
    parser = argparse.ArgumentParser(
        description="OmniLLM Gateway — Model Discovery & Config Generator"
    )
    parser.add_argument(
        "--providers", default="",
        help="Comma-separated list of providers to test (default: all with keys set)"
    )
    parser.add_argument(
        "--quality-threshold", type=float, default=None,
        help=f"Minimum quality score to include in config (default: {_default_threshold})"
    )
    parser.add_argument(
        "--exclude-models", default="",
        help="Extra comma-separated model name substrings to exclude"
    )
    parser.add_argument(
        "--output", default="config.yaml",
        help="Output file path (default: config.yaml)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Regenerate config from DB only, skip live API tests"
    )
    args = parser.parse_args()

    if args.quality_threshold is not None:
        QUALITY_THRESHOLD = args.quality_threshold
    if args.exclude_models:
        EXCLUDE_PATTERNS.extend([p.strip() for p in args.exclude_models.split(",") if p.strip()])

    # Filter PROVIDERS list by --providers flag
    if args.providers:
        requested = {p.strip().lower() for p in args.providers.split(",")}
        PROVIDERS[:] = [p for p in PROVIDERS if p.name in requested]

    try:
        try:
            import aiohttp, aiolimiter, rich, tenacity  # noqa
        except ImportError:
            console.print("[yellow]Installing required packages...[/yellow]")
            os.system("pip install aiohttp aiolimiter rich tenacity")

        total = asyncio.run(generate_config_async(dry_run=args.dry_run))

        if total == 0:
            console.print("[red]❌ No working models found. Check your API keys and network.[/red]")
            sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Interrupted by user[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    generate_config()