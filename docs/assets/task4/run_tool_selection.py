#!/usr/bin/env python3
"""Task4 / 附：工具选型实验学习版（active-tool-selection）——三臂对照，先离线后在线。

课程项目用同一批 10 个带金标工具的基准任务对比三种策略：
  all-tools  把全部工具 schema 一次性塞进上下文（PassiveToolAgent）
  retrieval  一次性 TF-IDF 检索 top-k 后注入（RetrievalToolAgent）
  active     MCP-Zero 式迭代发现：模型自己声明能力缺口，再检索注入（ActiveToolAgent）

学习版两步：
1. 离线臂（零 API 调用）：课程 benchmark.evaluate_offline + run_offline_benchmark 原样跑，
   给出 recall@k 与 schema token 随目录规模的缩放曲线——这是确定性证据；
2. 在线臂：把课程硬编码的 OpenAI 端点换成 DeepSeek（deepseek-flash，thinking 关闭，
   temperature 0），实测「模型是否真的调用了金标工具」、平均 token 与延迟。

注入方式：先设置 LLM_PROVIDER=openai + OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL，
再 import（config.py 在导入时读环境变量）；随后把 agent 模块里的 OpenAI 换成
provider 感知包装（关 thinking）。课程检索侧（TF-IDF 语义路由）零改动。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_KEY:
    raise SystemExit("DEEPSEEK_API_KEY is required for the online arm")

MODEL = "deepseek-flash"
ENDPOINT = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TOP_K = 5

# --- 注入 1：在 import 项目模块之前把端点指向 DeepSeek -------------------------
os.environ["LLM_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = DEEPSEEK_KEY
os.environ["OPENAI_BASE_URL"] = ENDPOINT
os.environ["OPENAI_MODEL"] = MODEL
os.environ.pop("OPENROUTER_API_KEY", None)

TOOLSEL_DIR = ROOT / "chapter4/active-tool-selection"
sys.path.insert(0, str(TOOLSEL_DIR))
import agent as agent_module  # noqa: E402
import benchmark as bench_module  # noqa: E402
import config as config_module  # noqa: E402
import demo_comparison as demo  # noqa: E402

# --- 注入 2：thinking 关闭 + 温度归零（与其余学习实验一致）--------------------
_real_openai = OpenAI


class _NoThinkingCompletions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **request):
        request.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
        request.setdefault("temperature", 0)
        return self._inner.create(**request)


class _NoThinkingOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        self.chat = SimpleNamespace(completions=_NoThinkingCompletions(inner.chat.completions))


agent_module.OpenAI = _NoThinkingOpenAI
config_module.AGENT_TEMPERATURE = 0

OUT_ROOT = ROOT / "learning/task4/runs/tool_selection"
OUT = OUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=False)
    print("output:", OUT, flush=True)
    print(f"online model: {MODEL} @ {ENDPOINT} (thinking disabled, temperature 0); top_k={TOP_K}", flush=True)

    catalog = bench_module.build_catalog(0)
    offline = demo.run_offline_benchmark(catalog, TOP_K, scaling=True)
    online = demo.run_online_benchmark(catalog, ["all", "retrieval", "active"], TOP_K, MODEL)

    summary_rows = []
    for strategy, payload in online.items():
        tasks = payload["per_task"]
        summary_rows.append({
            "strategy": strategy,
            "accuracy_calls_gold": payload["accuracy"],
            "tasks": len(tasks),
            "tokens_total": sum(row["tokens"] for row in tasks),
            "tokens_mean": sum(row["tokens"] for row in tasks) / len(tasks),
            "latency_mean_s": sum(row["latency"] for row in tasks) / len(tasks),
            "hits": sum(int(row["hit"]) for row in tasks),
        })

    offline_strategies = offline["benchmark"]["strategies"]
    evidence = {
        "experiment": "tool selection three strategies (learning variant)",
        "run_dir": str(OUT.relative_to(ROOT)),
        "online_model": {"provider": "deepseek", "model": MODEL, "endpoint": ENDPOINT,
                         "thinking": "disabled", "temperature": 0},
        "catalog_tools": offline["benchmark"]["num_tools"],
        "top_k": TOP_K,
        "benchmark_tasks": len(bench_module.BENCHMARK_TASKS),
        "offline": {
            "strategies": offline_strategies,
            "per_task": offline["benchmark"]["per_task"],
            "scaling": offline["scaling"],
        },
        "online": {
            "summary": summary_rows,
            "per_task": {strategy: payload["per_task"] for strategy, payload in online.items()},
        },
        "course_evidence": {
            "source": "chapter4/active-tool-selection/{benchmark,demo_comparison,agent}.py "
                      "(three strategies, 10 gold-labeled tasks and TF-IDF semantic routing "
                      "reused verbatim; only the LLM endpoint and temperature changed)",
        },
        "source_hashes": {
            rel: sha256_bytes((ROOT / rel).read_bytes())
            for rel in [
                "chapter4/active-tool-selection/benchmark.py",
                "chapter4/active-tool-selection/demo_comparison.py",
                "chapter4/active-tool-selection/agent.py",
                "chapter4/active-tool-selection/config.py",
                "learning/task4/run_tool_selection.py",
            ]
        },
        "credential_scan_findings": [],
        "completed": True,
    }
    leaked = []
    for key_name in ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY"):
        key = os.getenv(key_name, "")
        if key and key in json.dumps(evidence):
            leaked.append(key_name)
    evidence["credential_scan_findings"] = leaked
    evidence["completed"] = not leaked
    payload = json.dumps(evidence, ensure_ascii=False, indent=2, default=str)
    assert DEEPSEEK_KEY not in payload
    (OUT / "evidence.json").write_text(payload, encoding="utf-8")
    (OUT / "evidence.sha256").write_text(
        sha256_bytes((OUT / "evidence.json").read_bytes()) + "  evidence.json\n")

    print("\n离线（确定性）", flush=True)
    for name, row in offline_strategies.items():
        print(f"  {name:<12} tools_in_ctx={row['tools_in_context']:<4} "
              f"schema_tokens={row['avg_schema_tokens']:>9,.0f} recall={row['recall']:.2f}", flush=True)
    print("\n在线（DeepSeek）", flush=True)
    for row in summary_rows:
        print(f"  {row['strategy']:<10} calls_gold={row['hits']}/{row['tasks']} "
              f"tokens_mean={row['tokens_mean']:,.0f} latency_mean={row['latency_mean_s']:.2f}s", flush=True)
    print("leak scan:", leaked or "clean", flush=True)
    print("DONE", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
