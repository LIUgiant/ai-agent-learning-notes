"""Task2 / 实验 2-9 system-hint 学习版：课程 run_experiment_2_8 的 hint on/off 对照，跑在 DeepSeek 上。

不修改课程代码：直接 import chapter2/system-hint/run_experiment_2_8.py 的
run_one / summarize / condition_order（与书方 Kimi K3 战役同一执行、打分与验收
逻辑），仅替换三处——
1. provider 换 DeepSeek（model 用往返一致的 "deepseek-flash"）；
2. 每套件取冻结协议的前 3 个案例（65 次预注册运行 -> 39 次）；案例内容不动，
   沙箱与提示词与书方完全相同；
3. 客户端包装统一关闭 thinking；pricing 置零并在 qualification 里写明
   "未配置 DeepSeek 价格，成本未计算"（run_one 一定会算 cost，只能显式置零）。
"""
import hashlib
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not KEY:
    raise SystemExit("DEEPSEEK_API_KEY missing; no calls made")
MODEL = "deepseek-flash"  # 请求与响应 model 往返一致，exact_model 验收门槛才过
CASES_PER_SUITE = 3
WORKERS = 4
OUT = ROOT / "learning/task2/runs/2-9_system_hint" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

data = {
    "experiment": "2-9 system-hint learning variant",
    "note": "course run_one/summarize reused verbatim; DeepSeek provider, first 3 frozen cases per suite instead of 5",
    "model": MODEL,
    "source_hashes": {},
    "failures": [],
}


def load(name, rel):
    p = ROOT / rel
    data["source_hashes"][rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


campaign = load("system_hint_campaign", "chapter2/system-hint/run_experiment_2_8.py")

from agentbook.providers import resolve_backend

backend = resolve_backend("deepseek", model=MODEL, api_key=KEY)
_raw_client = OpenAI(api_key=backend.api_key, base_url=backend.base_url, timeout=120, max_retries=3)


class _NoThinkingCompletions:
    def create(self, **req):
        req.setdefault("extra_body", {"thinking": {"type": "disabled"}})
        return _raw_client.chat.completions.create(**req)


client = SimpleNamespace(chat=SimpleNamespace(completions=_NoThinkingCompletions()))

frozen = json.loads((ROOT / "chapter2/system-hint/experiment_protocol.json").read_text())
PROTOCOL = {
    "experiment_id": "2-9-learning",
    "provider": {
        "name": "deepseek",
        "base_url": backend.base_url,
        "model": MODEL,
        "api": "OpenAI-compatible chat.completions with tools/tool_calls",
        "temperature": 0.3,
        "max_completion_tokens": 4096,
    },
    "design": {
        "matched_cases_per_contrast": CASES_PER_SUITE,
        "arm_order": frozen["design"]["arm_order"],
        "same_model": True,
        "same_user_prompt_within_case": True,
        "same_initial_sandbox_within_case": True,
        "max_llm_turns": frozen["design"]["max_llm_turns"],
        "acceptance_independent_of_hypothesis": True,
        "objective_scoring_only": True,
        "external_side_effects": frozen["design"]["external_side_effects"],
    },
    "conditions": frozen["conditions"],
    "cases": {suite: cases[:CASES_PER_SUITE] for suite, cases in frozen["cases"].items()},
    "contrasts": frozen["contrasts"],
    "pricing": {
        "currency": "CNY",
        "uncached_input_per_million": 0.0,
        "cached_input_per_million": 0.0,
        "output_per_million": 0.0,
        "source": "learning variant: DeepSeek pricing not configured; cost intentionally zero",
    },
    "historical_claim_policy": frozen["historical_claim_policy"],
}
protocol_bytes = json.dumps(PROTOCOL, ensure_ascii=False, sort_keys=True).encode()
protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()

print("Output:", OUT, flush=True)
expected = sum(
    len(campaign.condition_order(suite, index))
    for suite, cases in PROTOCOL["cases"].items()
    for index, _case in enumerate(cases)
)
print("model:", MODEL, "| expected runs:", expected, flush=True)

jobs = [
    (suite, case, campaign.condition_order(suite, index))
    for suite, cases in PROTOCOL["cases"].items()
    for index, case in enumerate(cases)
]
rows = []


def run_case(job):
    suite, case, conditions = job
    completed = []
    for position, condition in enumerate(conditions):
        completed.append(
            campaign.run_one(
                client, PROTOCOL, protocol_hash, OUT, suite, case, condition, conditions, position
            )
        )
    return completed


with ThreadPoolExecutor(max_workers=WORKERS) as executor:
    futures = {executor.submit(run_case, job): job for job in jobs}
    for future in as_completed(futures):
        job = futures[future]
        try:
            for row in future.result():
                rows.append(row)
                print(
                    f"{row['run_id']:<42} pass={row['objective_pass']} turns={row['llm_turns']} "
                    f"complete={row['complete']}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 - 记录失败案例，不让整个战役崩掉
            data["failures"].append({"suite": job[0], "case_id": job[1]["id"], "error": str(exc)})
            print(f"[{job[0]}/{job[1]['id']}] ERROR {exc}", flush=True)

if data["failures"]:
    (OUT / "transport_failures.json").write_text(json.dumps(data["failures"], ensure_ascii=False, indent=2))

rows.sort(key=lambda row: (row["suite"], row["case_id"], row["condition"]))
comparison = campaign.summarize(PROTOCOL, protocol_hash, OUT, rows)
(OUT / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2))

leaked = []
for path in sorted(OUT.rglob("*")):
    if path.is_file() and KEY in path.read_text(encoding="utf-8", errors="ignore"):
        leaked.append(str(path.relative_to(OUT)))
data["credential_scan_findings_deepseek"] = leaked
data["protocol"] = PROTOCOL
data["comparison"] = comparison
data["cases_run"] = [
    {
        "run_id": r["run_id"],
        "suite": r["suite"],
        "condition": r["condition"],
        "features": r["features"],
        "objective_pass": r["objective_pass"],
        "component_scores": r["component_scores"],
        "llm_turns": r["llm_turns"],
        "termination": r.get("termination"),
        "complete": r["complete"],
        "usage": r["usage"],
    }
    for r in rows
]
data["completed"] = not leaked and not data["failures"]
payload = json.dumps(data, ensure_ascii=False, indent=2)
assert KEY not in payload
(OUT / "evidence.json").write_text(payload)
(OUT / "evidence.sha256").write_text(
    hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
)
print("\n对照（DeepSeek 学习版）", flush=True)
for c in comparison["contrasts"]:
    print(
        f"  {c['feature']:<20} enabled {c['enabled_passes']}/{c['n']} vs control {c['control_passes']}/{c['n']}"
        f" | turns {c['enabled_mean_turns']:.1f} vs {c['control_mean_turns']:.1f}"
        f" | supported={c['hypothesis_supported']}",
        flush=True,
    )
print("campaign_complete:", comparison["campaign_complete"], flush=True)
print("DONE", len(rows), "runs,", comparison["usage"]["total_tokens"], "tokens", flush=True)
