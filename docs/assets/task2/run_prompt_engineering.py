"""Task2 / 实验 2-4 提示词消融学习版：课程 run_ablation 的六臂消融套件，跑在 DeepSeek 上。

不修改课程代码：完整复用 run_ablation.run_full_suite（六臂循环、冻结协议校验、
append-only 检查点、汇总与 manifest 全部是课程原逻辑），仅替换四处——
1. litellm.completion 打补丁统一关闭 thinking（必须发生在 import tau_bench 之前：
   user.py 与 ablation_agent.py 都在模块级 `from litellm import completion`）；
2. provider 换 DeepSeek（argparse 的 --model-provider choices 没有 deepseek，
   因此 parse_args 后手动覆写 model_provider / user_model_provider）；
3. 自拼学习协议：任务 10 -> 4（airline test split 前 4 题），temperature 1 -> 0.3
   （书方 1.0 是 Kimi K3 推理模型被迫取值；DeepSeek 关思考后取低方差温度），
   seed 沿用 20260730；
4. pricing 置零（native 成本仅在 model == kimi-k3 时计算，DeepSeek 自动跳过）。
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not KEY:
    raise SystemExit("DEEPSEEK_API_KEY missing; no calls made")
MODEL = "deepseek-flash"  # litellm 请求与响应 model 往返一致
TASK_IDS = [0, 1, 2, 3]
TEMPERATURE = 0.3
SEED = 20260730
OUT = ROOT / "learning/task2/runs/2-4_prompt_engineering" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

# --- 注入：litellm 关 thinking（必须在 import tau_bench / ablation_agent 之前）---
import litellm

_real_completion = litellm.completion


def _no_thinking_completion(**kwargs):
    kwargs.setdefault("extra_body", {}).setdefault("thinking", {"type": "disabled"})
    return _real_completion(**kwargs)


litellm.completion = _no_thinking_completion

# --- 课程模块（其内部的 `from litellm import completion` 现在拿到补丁版本）-------
sys.path.insert(0, str(ROOT / "chapter2/prompt-engineering"))
import run_ablation  # noqa: E402

data = {
    "experiment": "2-4 prompt-engineering learning variant",
    "note": "course run_full_suite reused verbatim; DeepSeek provider, 4 airline tasks x 6 arms instead of 10 x 6; temperature 0.3 instead of kimi-forced 1.0",
    "model": MODEL,
    "source_hashes": {
        "chapter2/prompt-engineering/run_ablation.py": hashlib.sha256(
            (ROOT / "chapter2/prompt-engineering/run_ablation.py").read_bytes()
        ).hexdigest(),
        "chapter2/prompt-engineering/ablation_agent.py": hashlib.sha256(
            (ROOT / "chapter2/prompt-engineering/ablation_agent.py").read_bytes()
        ).hexdigest(),
        "chapter2/prompt-engineering/ablation_utils.py": hashlib.sha256(
            (ROOT / "chapter2/prompt-engineering/ablation_utils.py").read_bytes()
        ).hexdigest(),
    },
}

frozen = json.loads((ROOT / "chapter2/prompt-engineering/experiment_protocol.json").read_text())
PROTOCOL = dict(frozen)
PROTOCOL.update(
    {
        "protocol_version": "task2-deepseek-learning",
        "frozen_on": "2026-09-19",
        "provider": "DeepSeek official OpenAI-compatible endpoint via litellm",
        "model": MODEL,
        "user_model": MODEL,
        "temperature": TEMPERATURE,
        "task_ids": TASK_IDS,
        "trials_per_task": 1,
        "max_agent_steps": 30,
        "pricing": {
            "currency": "CNY",
            "uncached_input_per_million_tokens": 0,
            "cached_input_per_million_tokens": 0,
            "output_per_million_tokens": 0,
            "qualification": "learning variant: DeepSeek pricing not configured; native cost intentionally zero",
        },
    }
)
protocol_path = OUT / "experiment_protocol.json"
protocol_path.write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2))

sys.argv = [
    "run_ablation.py",
    "--all",
    "--env", "airline",
    "--model", MODEL,
    "--user-model", MODEL,
    "--temperature", str(TEMPERATURE),
    "--seed", str(SEED),
    "--task-ids", *[str(t) for t in TASK_IDS],
    "--max-agent-steps", "30",
    "--log-dir", str(OUT),
    "--max-concurrency", "3",
    "--protocol", str(protocol_path),
    "--output", str(OUT / "ablation_summary.json"),
    "--no-verbose",
]
args = run_ablation.parse_args()
args.model_provider = "deepseek"
args.user_model_provider = "deepseek"

print("Output:", OUT, flush=True)
print("model:", MODEL, "| arms: 6 | tasks:", TASK_IDS, flush=True)

suite_results = run_ablation.run_full_suite(args)

summary = json.loads((OUT / "ablation_summary.json").read_text())
leaked = []
for path in sorted(OUT.rglob("*")):
    if path.is_file() and KEY in path.read_text(encoding="utf-8", errors="ignore"):
        leaked.append(str(path.relative_to(OUT)))
data["credential_scan_findings_deepseek"] = leaked
data["summary"] = summary
data["suite_results"] = {k: [float(r) for r in v] for k, v in suite_results.items()}
data["completed"] = not leaked
payload = json.dumps(data, ensure_ascii=False, indent=2)
assert KEY not in payload
(OUT / "evidence.json").write_text(payload)
(OUT / "evidence.sha256").write_text(
    hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
)
print("\n六臂成功率（DeepSeek 学习版）", flush=True)
for name, rewards in suite_results.items():
    print(f"  {name:<15} {sum(rewards):.0f}/{len(rewards)}", flush=True)
usage = summary["usage_and_cost"]
print(
    "DONE",
    usage["total_real_api_calls"],
    "calls,",
    usage["total_tokens"],
    "tokens | campaign_complete:",
    summary["campaign_complete"],
    flush=True,
)
