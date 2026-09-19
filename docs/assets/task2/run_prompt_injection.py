"""Task2 / 实验 2-5 提示注入学习版：课程 run_campaign 的 3 攻击 x 4 防御 x 3 试验矩阵，跑在 DeepSeek 上。

不修改课程代码：直接 import chapter2/prompt-injection 的 run_trial / summarize
（与书方 Kimi 战役同一执行与验收逻辑），仅替换三处——
1. provider 换成 DeepSeek（协议自拼，model 用往返一致的 "deepseek-flash"；
   请求 "deepseek-v4-flash" 时响应 model 回报 "deepseek-flash"，会挂掉
   run_trial 的回执校验 accepted_receipt）；
2. 客户端包装：统一注入 extra_body 关闭 thinking（课程 Agent 不发 extra_body）；
3. trials_per_cell 5 -> 3（学习版规模，36 格）。
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
MODEL = "deepseek-flash"  # 请求与响应往返一致，见模块 docstring
TRIALS_PER_CELL = 3
WORKERS = 4
OUT = ROOT / "learning/task2/runs/2-5_prompt_injection" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

data = {
    "experiment": "2-5 prompt-injection learning variant",
    "note": "course run_trial/summarize reused verbatim; DeepSeek provider, 3 trials/cell instead of 5",
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


agent_mod = load("agent", "chapter2/prompt-injection/agent.py")
attacks_mod = load("attacks", "chapter2/prompt-injection/attacks.py")
campaign = load("campaign", "chapter2/prompt-injection/run_campaign.py")

from agentbook.providers import resolve_backend

backend = resolve_backend("deepseek", model=MODEL, api_key=KEY)
_raw_client = OpenAI(api_key=backend.api_key, base_url=backend.base_url, timeout=120, max_retries=3)


class _NoThinkingCompletions:
    """透传 chat.completions.create，仅追加 thinking 关闭，保持课程 Agent 无感知。"""

    def create(self, **req):
        req.setdefault("extra_body", {"thinking": {"type": "disabled"}})
        return _raw_client.chat.completions.create(**req)


client = SimpleNamespace(chat=SimpleNamespace(completions=_NoThinkingCompletions()))

PROTOCOL = {
    "experiment_id": "2-5-learning",
    "protocol_version": "task2-deepseek-learning",
    "manuscript_contract": json.loads((ROOT / "chapter2/prompt-injection/experiment_protocol.json").read_text())["manuscript_contract"],
    "provider": {
        "name": "deepseek",
        "base_url": backend.base_url,
        "model": MODEL,
        "temperature": 0.7,
    },
    "design": {
        "trials_per_cell": TRIALS_PER_CELL,
        "expected_cells": len(attacks_mod.ATTACKS) * len(agent_mod.DEFENSES) * TRIALS_PER_CELL,
        "max_agent_steps_per_user_turn": 6,
        "isolated_real_filesystem_per_trial": True,
        "isolated_outbox_instead_of_external_delivery": True,
        "memory_attack_uses_fresh_agent_session": True,
        "acceptance_independent_of_hypothesis": True,
    },
}
protocol_bytes = json.dumps(PROTOCOL, ensure_ascii=False, indent=2).encode("utf-8")
protocol_hash = hashlib.sha256(protocol_bytes).hexdigest()

print("Output:", OUT, flush=True)
print("model:", MODEL, "| cells:", PROTOCOL["design"]["expected_cells"], flush=True)

jobs = [
    (ai, di, trial)
    for trial in range(1, TRIALS_PER_CELL + 1)
    for ai in range(len(attacks_mod.ATTACKS))
    for di in range(len(agent_mod.DEFENSES))
]
rows = []
with ThreadPoolExecutor(max_workers=WORKERS) as pool:
    futures = {pool.submit(campaign.run_trial, client, PROTOCOL, protocol_hash, OUT, *job): job for job in jobs}
    for future in as_completed(futures):
        job = futures[future]
        try:
            row = future.result()
            rows.append(row)
            print(
                f"trial {row['trial_id']} attack={row['attack']['name']} "
                f"defense={row['defense']['name']} succeeded={row['attack_succeeded']} "
                f"complete={row['complete']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - 记录失败格，不让整个战役崩掉
            data["failures"].append({"job": list(job), "error": f"{type(exc).__name__}: {exc}"})
            print("trial", job, "ERROR", exc, flush=True)

if data["failures"]:
    (OUT / "transport_failures.json").write_text(json.dumps(data["failures"], ensure_ascii=False, indent=2))

rows.sort(key=lambda row: tuple(int(v) for v in row["trial_id"].split("-")))
comparison = campaign.summarize(PROTOCOL, protocol_hash, OUT, rows)
(OUT / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2))

# 学习版自己的证据层：密钥不泄漏扫描 + 汇总 + sha256
leaked = []
for path in sorted(OUT.rglob("*")):
    if path.is_file():
        if KEY in path.read_text(encoding="utf-8", errors="ignore"):
            leaked.append(str(path.relative_to(OUT)))
data["credential_scan_findings_deepseek"] = leaked
data["protocol"] = PROTOCOL
data["comparison"] = comparison
data["cells"] = [
    {
        "trial_id": r["trial_id"],
        "attack": r["attack"]["name"],
        "defense": r["defense"]["name"],
        "attack_succeeded": r["attack_succeeded"],
        "complete": r["complete"],
        "memory_poison_persisted": r.get("memory_poison_persisted"),
        "fresh_session_used": r.get("fresh_session_used"),
        "n_provider_calls": len(r["provider_calls"]),
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
rates = comparison["attack_success_rates"]
print("\n攻击成功率矩阵（学习版，DeepSeek）", flush=True)
for attack, defenses in rates.items():
    for defense, cell in defenses.items():
        print(f"  {attack} x {defense}: {cell['successes']}/{cell['trials']}")
print("DONE", len(rows), "cells,", comparison["usage"]["total_tokens"], "tokens", flush=True)
