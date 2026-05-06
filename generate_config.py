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
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
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
    classification: str = ""  # coding, reasoning, chat, vision, embedding
    quality_score: float = 0.0
    last_tested: str = ""
    success_count: int = 0
    fail_count: int = 0

# Provider configurations
PROVIDERS = [
    ProviderConfig(
        name="groq",
        api_base="https://api.groq.com/openai/v1",
        env_key="GROQ_API_KEY",
        rpm_limit=30,
    ),
    ProviderConfig(
        name="mistral",
        api_base="https://api.mistral.ai/v1",
        env_key="MISTRAL_API_KEY",
        rpm_limit=30,
    ),
    ProviderConfig(
        name="openrouter",
        api_base="https://openrouter.ai/api/v1",
        env_key="OPENROUTER_API_KEY",
        rpm_limit=20,
    ),
    ProviderConfig(
        name="nvidia",
        api_base="https://integrate.api.nvidia.com/v1",
        env_key="NIM_API_KEY",
        rpm_limit=40,
    ),
    ProviderConfig(
        name="clod",
        api_base="https://api.clod.io/v1",
        env_key="CLOD_API_KEY",
        rpm_limit=60,
    ),
    ProviderConfig(
        name="cerebras",
        api_base="https://api.cerebras.ai/v1",
        env_key="CEREBRAS_API_KEY",
        rpm_limit=30,
    ),
    ProviderConfig(
        name="cohere",
        api_base="https://api.cohere.com/v1",
        env_key="COHERE_API_KEY",
        rpm_limit=20,
    ),
]

# Validation test prompts
VALIDATION_TESTS = {
    "basic": {
        "prompt": "Reply with exactly: OK",
        "min_length": 2,
        "max_length": 5,
    },
    "reasoning": {
        "prompt": "Why is caching useful in APIs? Explain in 2-3 sentences.",
        "min_length": 30,
        "max_length": 500,
    },
    "json": {
        "prompt": 'Return valid JSON only: {"response": "hello"}',
        "min_length": 10,
        "validate_json": True,
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
             classification, quality_score, last_tested, success_count, fail_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            model.provider, model.model_id, model.display_name, model.status,
            model.latency_ms, model.tokens_per_second, model.supports_tools,
            model.supports_vision, model.supports_streaming, model.context_window,
            model.classification, model.quality_score, model.last_tested,
            model.success_count, model.fail_count
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
                last_tested=row[13], success_count=row[14], fail_count=row[15]
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

async def fetch_models_from_provider(
    session: aiohttp.ClientSession,
    config: ProviderConfig,
    api_key: str
) -> List[str]:
    """Fetch available models from provider's /models endpoint."""
    if not api_key:
        return []
    
    url = f"{config.api_base.rstrip('/')}{config.models_endpoint}"
    headers = {"Authorization": f"{config.auth_header} {api_key}", "Content-Type": "application/json"}
    
    try:
        async with session.get(url, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                models = data.get("data", [])
                return [m.get("id") for m in models if m.get("id")]
            else:
                console.print(f"  ⚠️ {config.name} API returned {response.status}")
    except Exception as e:
        console.print(f"  ⚠️ Failed to fetch models from {config.name}: {e}")
    
    return []

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
                            json.loads(content)
                        except:
                            return False, "Invalid JSON response", elapsed, {}
                    
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

async def validate_model_comprehensive(
    session: aiohttp.ClientSession,
    config: ProviderConfig,
    api_key: str,
    model_id: str
) -> ModelInfo:
    """Run comprehensive validation on a model."""
    
    model_info = ModelInfo(
        provider=config.name,
        model_id=model_id,
        display_name=model_id.split('/')[-1] if '/' in model_id else model_id,
        last_tested=datetime.now().isoformat()
    )
    
    # Test 1: Basic completion
    basic_passed, basic_msg, basic_latency, basic_meta = await test_model_with_retry(
        session, config, api_key, model_id, "basic"
    )
    
    if not basic_passed:
        model_info.status = "failed"
        model_info.error_message = basic_msg
        return model_info
    
    model_info.latency_ms = basic_latency
    model_info.success_count += 1
    
    # Test 2: Reasoning
    reasoning_passed, reasoning_msg, reasoning_latency, reasoning_meta = await test_model_with_retry(
        session, config, api_key, model_id, "reasoning"
    )
    
    if reasoning_passed:
        model_info.quality_score += 0.5
        model_info.latency_ms = (model_info.latency_ms + reasoning_latency) / 2
    
    # Test 3: JSON output
    json_passed, json_msg, json_latency, json_meta = await test_model_with_retry(
        session, config, api_key, model_id, "json"
    )
    
    if json_passed:
        model_info.quality_score += 0.5
    
    # Calculate final score (0-100)
    model_info.quality_score = (model_info.quality_score / 1.5) * 100
    
    # Classify based on model name and performance
    model_id_lower = model_id.lower()
    if "coder" in model_id_lower or "code" in model_id_lower:
        model_info.classification = "coding"
    elif "reasoning" in model_id_lower or "r1" in model_id_lower or "thinking" in model_id_lower:
        model_info.classification = "reasoning"
    elif "vision" in model_id_lower or "vl" in model_id_lower:
        model_info.classification = "vision"
    else:
        model_info.classification = "chat"
    
    # Check tool support (optional - would need separate API call)
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
        # Fetch all models
        progress.update(progress_task, description=f"🔍 Discovering {config.name} models...")
        model_ids = await fetch_models_from_provider(session, config, api_key)
        
        if not model_ids:
            progress.update(progress_task, description=f"⚠️ No models found for {config.name}")
            return results
        
        progress.update(progress_task, total=len(model_ids), description=f"🧪 Testing {config.name} models...")
        
        # Test models with concurrency limit
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent tests per provider
        
        async def test_with_semaphore(model_id):
            async with semaphore:
                return await validate_model_comprehensive(session, config, api_key, model_id)
        
        # Run all tests
        tasks = [test_with_semaphore(mid) for mid in model_ids]
        
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            model_info = await coro
            results.append(model_info)
            progress.update(progress_task, advance=1)
            
            # Update progress description with current result
            if model_info.status == "passed":
                progress.console.print(f"  ✅ {model_info.display_name[:40]:40} [{model_info.latency_ms:.0f}ms]")
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

def generate_dynamic_router(working_models: List[ModelInfo]) -> Dict:
    """Generate intelligent fallback chains based on model classifications."""
    
    # Group by classification
    by_type = defaultdict(list)
    for model in working_models:
        by_type[model.classification].append(model)
    
    # Sort by quality score
    for classification in by_type:
        by_type[classification].sort(key=lambda x: x.quality_score, reverse=True)
    
    fallbacks = []
    
    # Create fallback chains for each classification
    for classification, models in by_type.items():
        if len(models) >= 2:
            chain = {models[0].display_name: [m.display_name for m in models[1:4]]}
            fallbacks.append(chain)
    
    return {"fallbacks": fallbacks}

# ============================================================
# Main Async Generator
# ============================================================

async def generate_config_async():
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
                            classification="chat"
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
            supports_streaming=True
        )
        all_results.append(custom_model)
        console.print(f"\n[green]✅ Added custom mapping: claude-3-haiku-20240307[/green]")
    
    # Generate dynamic router
    working_models = [m for m in all_results if m.status == "passed"]
    dynamic_router = generate_dynamic_router(working_models)
    
    # Generate final config.yaml
    config = {
        "model_list": [
            {
                "model_name": f"{m.provider}/{m.display_name}",
                "litellm_params": {
                    "model": m.model_id,
                    "api_key": f"os.environ/{m.provider.upper()}_API_KEY" if m.provider != "custom" else "os.environ/OPENROUTER_API_KEY",
                    "custom_llm_provider": m.provider if m.provider != "nvidia" else "openai",
                },
                "model_info": {
                    "mode": "chat",
                    "supports_function_calling": m.supports_tools,
                    "classification": m.classification,
                    "quality_score": m.quality_score,
                }
            }
            for m in working_models
        ],
        "general_settings": {
            "master_key": os.environ.get("LITELLM_MASTER_KEY", "litellm-master-key"),
            "default_model": "openrouter/gpt-4o",
            "enable_anthropic_compatibility": True,
            "disable_rate_limiting": False,
            "database_url": os.environ.get("DATABASE_URL"),
            "background_health_check": True,
            "disable_budget_reset_job": True,
        },
        "router_settings": {
            "routing_strategy": "simple-shuffle",
            "num_retries": 2,
            "request_timeout": 120,
            "fallback_retries": 2,
            "cooldown_time": 30,
            **dynamic_router,
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
    
    # Write config file
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
    table.add_column("Success Rate", style="yellow")
    
    # Group by provider
    provider_stats = defaultdict(lambda: {"working": 0, "failed": 0})
    for model in all_results:
        if model.status == "passed":
            provider_stats[model.provider]["working"] += 1
        else:
            provider_stats[model.provider]["failed"] += 1
    
    for provider, stats in provider_stats.items():
        total = stats["working"] + stats["failed"]
        success_rate = (stats["working"] / total * 100) if total > 0 else 0
        table.add_row(
            provider.upper(),
            str(stats["working"]),
            str(stats["failed"]),
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
    """Entry point for the config generator."""
    try:
        # Install required packages if missing
        try:
            import aiohttp
            import aiolimiter
            import rich
            import tenacity
        except ImportError:
            console.print("[yellow]Installing required packages...[/yellow]")
            os.system("pip install aiohttp aiolimiter rich tenacity")
        
        # Run async main
        total = asyncio.run(generate_config_async())
        
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