"""
Argovaa AI Benchmark Scraper
Fetches live model and benchmark data from free public APIs
Saves to data/benchmarks.json for the benchmark dashboard
"""

import requests
import json
import datetime
import time

# ─── GPU hardware reference data ──────────────────────────────────────────────
GPU_SPECS = {
    "h200-sxm": {
        "name": "NVIDIA H200 SXM",
        "vendor": "NVIDIA",
        "vram_gb": 141,
        "bandwidth_tbps": 4.8,
        "tdp_watts": 700,
        "fp16_tflops": 1979,
        "memory_type": "HBM3e"
    },
    "h100-sxm": {
        "name": "NVIDIA H100 SXM",
        "vendor": "NVIDIA",
        "vram_gb": 80,
        "bandwidth_tbps": 3.35,
        "tdp_watts": 700,
        "fp16_tflops": 1979,
        "memory_type": "HBM3"
    },
    "a100-80gb": {
        "name": "NVIDIA A100 80GB",
        "vendor": "NVIDIA",
        "vram_gb": 80,
        "bandwidth_tbps": 2.0,
        "tdp_watts": 400,
        "fp16_tflops": 312,
        "memory_type": "HBM2e"
    },
    "mi300x": {
        "name": "AMD MI300X",
        "vendor": "AMD",
        "vram_gb": 192,
        "bandwidth_tbps": 5.3,
        "tdp_watts": 750,
        "fp16_tflops": 1307,
        "memory_type": "HBM3"
    },
    "rtx-4090": {
        "name": "NVIDIA RTX 4090",
        "vendor": "NVIDIA",
        "vram_gb": 24,
        "bandwidth_tbps": 1.0,
        "tdp_watts": 450,
        "fp16_tflops": 82,
        "memory_type": "GDDR6X"
    }
}

# ─── Provider metadata ────────────────────────────────────────────────────────
PROVIDER_MAP = {
    "openai": {"label": "OpenAI", "color": "#10a37f"},
    "anthropic": {"label": "Anthropic", "color": "#c25b3e"},
    "azure": {"label": "Azure OAI", "color": "#0078d4"},
    "meta-llama": {"label": "Open source", "color": "#7c3aed"},
    "mistralai": {"label": "Open source", "color": "#7c3aed"},
    "google": {"label": "Google", "color": "#4285f4"},
    "cohere": {"label": "Cohere", "color": "#39594e"},
}

def safe_get(url, headers=None, timeout=15):
    """Safe HTTP GET with error handling"""
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        if r.ok:
            return r.json()
        else:
            print(f"  Warning: {url} returned {r.status_code}")
            return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None

def fetch_openrouter_models():
    """
    Fetch live model list from OpenRouter API
    Returns pricing, context length, and model metadata for all providers
    Free API - no key required for public model list
    """
    print("Fetching OpenRouter model data...")
    data = safe_get("https://openrouter.ai/api/v1/models")
    if not data:
        return []

    models = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        pricing = m.get("pricing", {})

        # Determine provider from model ID
        provider_key = model_id.split("/")[0] if "/" in model_id else "unknown"
        provider_info = PROVIDER_MAP.get(provider_key, {
            "label": provider_key.title(),
            "color": "#888888"
        })

        # Convert pricing from per-token to per-million-tokens
        try:
            input_cost = float(pricing.get("prompt", 0)) * 1_000_000
            output_cost = float(pricing.get("completion", 0)) * 1_000_000
        except (ValueError, TypeError):
            input_cost = 0
            output_cost = 0

        models.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "provider_key": provider_key,
            "provider_label": provider_info["label"],
            "provider_color": provider_info["color"],
            "context_length": m.get("context_length", 0),
            "input_cost_per_1m": round(input_cost, 4),
            "output_cost_per_1m": round(output_cost, 4),
            "description": m.get("description", ""),
            "source": "openrouter"
        })

    print(f"  Got {len(models)} models from OpenRouter")
    return models

def fetch_artificial_analysis():
    """
    Fetch benchmark data from Artificial Analysis
    Contains throughput, latency and quality scores across providers
    Note: Uses public endpoint - check artificialanalysis.ai for latest API docs
    """
    print("Fetching Artificial Analysis benchmark data...")

    # Try the public leaderboard endpoint
    endpoints = [
        "https://artificialanalysis.ai/api/v1/models",
        "https://artificialanalysis.ai/leaderboards/models"
    ]

    for url in endpoints:
        data = safe_get(url)
        if data:
            benchmarks = []
            items = data if isinstance(data, list) else data.get("data", data.get("models", []))
            for item in items:
                benchmarks.append({
                    "model_id": item.get("id") or item.get("model_id", ""),
                    "model_name": item.get("name") or item.get("model_name", ""),
                    "provider": item.get("provider", ""),
                    "output_tokens_per_second": item.get("output_tokens_per_second") or item.get("throughput", 0),
                    "time_to_first_token_ms": item.get("time_to_first_token") or item.get("ttft", 0),
                    "latency_ms": item.get("total_response_time") or item.get("latency", 0),
                    "quality_score": item.get("quality_index") or item.get("quality", 0),
                    "source": "artificial_analysis"
                })
            print(f"  Got {len(benchmarks)} benchmarks from Artificial Analysis")
            return benchmarks

    print("  Could not fetch from Artificial Analysis — using fallback")
    return []

def fetch_together_ai_models():
    """
    Fetch open source model benchmarks from Together AI public pricing page
    Good source for open source model performance data
    """
    print("Fetching Together AI model data...")
    data = safe_get("https://api.together.xyz/v1/models")
    if not data:
        return []

    models = []
    for m in data if isinstance(data, list) else data.get("data", []):
        if m.get("type") == "language":
            models.append({
                "id": m.get("id", ""),
                "name": m.get("display_name") or m.get("id", ""),
                "context_length": m.get("context_length", 0),
                "input_cost_per_1m": float(m.get("pricing", {}).get("input", 0)) * 1_000_000 if m.get("pricing") else 0,
                "output_cost_per_1m": float(m.get("pricing", {}).get("output", 0)) * 1_000_000 if m.get("pricing") else 0,
                "source": "together_ai"
            })

    print(f"  Got {len(models)} models from Together AI")
    return models

def fetch_mlperf_results():
    """
    Fetch latest MLPerf inference results from their public GitHub
    Returns standardised hardware benchmark results
    """
    print("Fetching MLPerf results...")

    # MLPerf publishes results as CSV on GitHub
    mlperf_url = "https://raw.githubusercontent.com/mlcommons/inference_results_v4.1/main/open/results.json"
    data = safe_get(mlperf_url)

    if not data:
        # Fallback: return curated static MLPerf v4.1 highlights
        print("  Using curated MLPerf v4.1 data")
        return [
            {"gpu": "h100-sxm", "workload": "llm-70b", "scenario": "Server",
             "metric": "tokens_per_second", "value": 3640, "submitter": "NVIDIA",
             "system": "1x H100 SXM 80GB", "source": "mlperf_v4.1"},
            {"gpu": "h200-sxm", "workload": "llm-70b", "scenario": "Server",
             "metric": "tokens_per_second", "value": 4820, "submitter": "NVIDIA",
             "system": "1x H200 SXM 141GB", "source": "mlperf_v4.1"},
            {"gpu": "mi300x", "workload": "llm-70b", "scenario": "Server",
             "metric": "tokens_per_second", "value": 3180, "submitter": "AMD",
             "system": "1x MI300X 192GB", "source": "mlperf_v4.1"},
            {"gpu": "a100-80gb", "workload": "llm-70b", "scenario": "Server",
             "metric": "tokens_per_second", "value": 1980, "submitter": "NVIDIA",
             "system": "1x A100 SXM 80GB", "source": "mlperf_v4.1"},
            {"gpu": "h100-sxm", "workload": "bert-99", "scenario": "Server",
             "metric": "queries_per_second", "value": 14200, "submitter": "NVIDIA",
             "system": "1x H100 SXM 80GB", "source": "mlperf_v4.1"},
            {"gpu": "h100-sxm", "workload": "stable-diffusion-xl", "scenario": "Server",
             "metric": "samples_per_second", "value": 108, "submitter": "NVIDIA",
             "system": "1x H100 SXM 80GB", "source": "mlperf_v4.1"},
        ]

    return data if isinstance(data, list) else []

def build_provider_summary(models):
    """Build summary stats per provider from model list"""
    providers = {}
    for m in models:
        pk = m.get("provider_key", m.get("provider", "unknown"))
        if pk not in providers:
            providers[pk] = {
                "key": pk,
                "label": m.get("provider_label", pk.title()),
                "color": m.get("provider_color", "#888888"),
                "model_count": 0,
                "avg_input_cost": 0,
                "min_context": 0,
                "max_context": 0,
                "models": []
            }
        providers[pk]["model_count"] += 1
        providers[pk]["models"].append(m.get("name", ""))
        ctx = m.get("context_length", 0)
        if ctx > providers[pk]["max_context"]:
            providers[pk]["max_context"] = ctx
    return list(providers.values())

def main():
    print("=" * 50)
    print("Argovaa Benchmark Scraper")
    print(f"Started: {datetime.datetime.utcnow().isoformat()}")
    print("=" * 50)

    # Fetch all data sources
    openrouter_models = fetch_openrouter_models()
    time.sleep(1)  # be polite to APIs

    artificial_benchmarks = fetch_artificial_analysis()
    time.sleep(1)

    together_models = fetch_together_ai_models()
    time.sleep(1)

    mlperf_results = fetch_mlperf_results()

    # Merge and deduplicate models
    all_models = openrouter_models + together_models

    # Deduplicate by model name
    seen = set()
    unique_models = []
    for m in all_models:
        key = m.get("name", "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique_models.append(m)

    # Build provider summary
    provider_summary = build_provider_summary(unique_models)

    # Assemble final output
    output = {
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "version": "1.0",
        "summary": {
            "total_models": len(unique_models),
            "total_providers": len(provider_summary),
            "total_gpus": len(GPU_SPECS),
            "mlperf_round": "v4.1"
        },
        "gpu_specs": GPU_SPECS,
        "providers": provider_summary,
        "models": unique_models,
        "benchmarks": artificial_benchmarks,
        "mlperf_results": mlperf_results
    }

    # Write to file
    with open("data/benchmarks.json", "w") as f:
        json.dump(output, f, indent=2)

    print("=" * 50)
    print(f"Done! Saved {len(unique_models)} models, "
          f"{len(artificial_benchmarks)} benchmarks, "
          f"{len(mlperf_results)} MLPerf results")
    print(f"Output: data/benchmarks.json")
    print("=" * 50)

if __name__ == "__main__":
    main()
