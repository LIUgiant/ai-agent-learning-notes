"""Task2 / 实验 2-3 KV Cache 学习版：课程 KVCacheAgent 六种上下文构造模式 x DeepSeek。

不修改课程代码：加载 chapter2/kv-cache/agent.py 后仅注入两处——
1. agentbook.providers.resolve_backend 打补丁，把 agent 硬编码的 kimi/openrouter
   二选一改指 DeepSeek 后端（与 task1 的 Config.resolve_llm 注入同思路）；
2. 模块级 OpenAI 符号替换为记录工厂：透传请求，但记录每次调用的原始 usage
   （含 DeepSeek 的 prompt_cache_hit_tokens / prompt_cache_miss_tokens）、
   消息指纹与耗时，并统一关闭 thinking 以降低延迟测量的方差。
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import logging
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not KEY:
    raise SystemExit("DEEPSEEK_API_KEY missing; no calls made")
MODEL = os.getenv("TASK2_MODEL", "deepseek-v4-flash")
OUT = ROOT / "learning/task2/runs/2-3_kv_cache" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)
(OUT / "logs").mkdir()

logging.disable(logging.CRITICAL)

data = {
    "experiment": "2-3 kv-cache learning variant",
    "note": "six context-construction modes of the course KVCacheAgent, run on DeepSeek; not the book's Kimi K2.6 campaign",
    "model": MODEL,
    "modes": [],
    "calls": [],
    "source_hashes": {},
}


def save():
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    assert KEY not in payload
    (OUT / "evidence.json").write_text(payload)


def load(name, rel):
    p = ROOT / rel
    data["source_hashes"][rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


# --- 注入 1：provider 解析改指 DeepSeek ------------------------------------
import agentbook.providers as providers

_real_resolve = providers.resolve_backend


def _deepseek_backend(provider, model=None, api_key=None, **kwargs):
    return _real_resolve("deepseek", model=MODEL, api_key=KEY)


providers.resolve_backend = _deepseek_backend

# --- 注入 2：记录型 OpenAI 工厂 --------------------------------------------
_real_openai = OpenAI


def _message_digest(messages):
    """每条消息的紧凑指纹：角色、内容长度、内容哈希、工具调用概况。"""
    rows = []
    for msg in messages:
        content = msg.get("content") or ""
        row = {
            "role": msg.get("role"),
            "chars": len(content) if isinstance(content, str) else -1,
            "sha": hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()[:12],
        }
        tcs = msg.get("tool_calls") or []
        if tcs:
            row["tool_calls"] = [tc.get("function", {}).get("name", "?") for tc in tcs]
        rows.append(row)
    return rows


def _common_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x.get("sha") != y.get("sha") or x.get("role") != y.get("role"):
            break
        n += 1
    return n


class _RecordingCompletions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **req):
        req["extra_body"] = {"thinking": {"type": "disabled"}}
        start = time.monotonic()
        resp = self._inner.create(**req)
        elapsed = time.monotonic() - start
        usage = resp.usage.model_dump() if resp.usage else {}
        record = {
            "elapsed_s": round(elapsed, 3),
            "model": resp.model,
            "finish_reason": resp.choices[0].finish_reason,
            "tool_calls": [tc.function.name for tc in (resp.choices[0].message.tool_calls or [])],
            "usage": usage,
            "tools_order": [t["function"]["name"] for t in req.get("tools", [])],
            "messages_digest": _message_digest(req["messages"]),
            "n_messages": len(req["messages"]),
        }
        data["calls"].append(record)
        save()
        return resp


class _RecordingOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        self.chat = SimpleNamespace(completions=_RecordingCompletions(inner.chat.completions))
        global _LAST_BASE_URL
        _LAST_BASE_URL = str(kwargs.get("base_url", ""))


_LAST_BASE_URL = ""
agent_mod = load("kv_agent", "chapter2/kv-cache/agent.py")
agent_mod.OpenAI = _RecordingOpenAI

FIXTURE = ROOT / "learning/task2/work/kv_fixture"
TASK = """Analyze the Python project in this directory.
1. First use the find tool to discover all files.
2. Then read every Python file to understand its purpose.
3. Use grep if you need to trace how modules reference each other.
4. Finally summarize what each module does and how they work together."""

print("Output:", OUT, flush=True)
data["base_url_host"] = urlparse(_deepseek_backend("kimi").base_url).hostname

for mode in agent_mod.KVCacheMode:
    call_base = len(data["calls"])
    log_path = OUT / "logs" / f"{mode.value}.txt"
    with open(log_path, "w") as log, contextlib.redirect_stdout(log):
        agent = agent_mod.KVCacheAgent(
            api_key=KEY, mode=mode, model=MODEL, root_dir=str(FIXTURE), verbose=False
        )
        result = agent.execute_task(TASK, max_iterations=30)
    mode_calls = data["calls"][call_base:]
    # 逐次调用与前一次的消息公共前缀长度：证明前缀稳定（correct）或被重建/改写
    prefix_trace = []
    for i, call in enumerate(mode_calls):
        if i == 0:
            prefix_trace.append(0)
        else:
            prev = mode_calls[i - 1]["messages_digest"]
            cur = call["messages_digest"]
            prefix_trace.append(_common_prefix_len(prev, cur))
    hit = [c["usage"].get("prompt_cache_hit_tokens", 0) for c in mode_calls]
    miss = [c["usage"].get("prompt_cache_miss_tokens", 0) for c in mode_calls]
    mode_record = {
        "mode": mode.value,
        "course_metrics": asdict(result["metrics"]),
        "iterations": result["iterations"],
        "n_calls": len(mode_calls),
        "success": result["success"],
        "final_answer_chars": len(result["final_answer"] or ""),
        "tool_call_names": [c["tool_calls"] for c in mode_calls],
        "per_call_elapsed_s": [c["elapsed_s"] for c in mode_calls],
        "per_call_prompt_tokens": [c["usage"].get("prompt_tokens", 0) for c in mode_calls],
        "per_call_cache_hit_tokens": hit,
        "per_call_cache_miss_tokens": miss,
        "per_call_tools_order": [c["tools_order"] for c in mode_calls],
        "per_call_n_messages": [c["n_messages"] for c in mode_calls],
        "prefix_common_len_with_previous": prefix_trace,
        "usage_field_names": sorted(mode_calls[0]["usage"].keys()) if mode_calls else [],
        "checks": {
            "made_real_calls": len(mode_calls) >= 2,
            "usage_reports_cache_fields": bool(
                mode_calls and "prompt_cache_hit_tokens" in mode_calls[0]["usage"]
            ),
            "hit_plus_miss_equals_prompt": all(
                h + m == p
                for h, m, p in zip(
                    hit, miss, [c["usage"].get("prompt_tokens", 0) for c in mode_calls]
                )
            ),
        },
    }
    data["modes"].append(mode_record)
    save()
    print(
        f"{mode.value:<17} calls={len(mode_calls)} iters={result['iterations']} "
        f"hit={sum(hit)} miss={sum(miss)} ok={result['success']}",
        flush=True,
    )

data["completed"] = True
data["total_prompt_tokens"] = sum(c["usage"].get("prompt_tokens", 0) for c in data["calls"])
data["total_completion_tokens"] = sum(c["usage"].get("completion_tokens", 0) for c in data["calls"])
save()
(OUT / "evidence.sha256").write_text(
    hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
)
print("DONE", len(data["calls"]), "calls", data["total_prompt_tokens"], "prompt tokens", flush=True)
