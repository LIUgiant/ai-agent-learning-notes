#!/usr/bin/env python3
"""Task4 / 实验 4-1 主动工具发现学习版：课程 run_exact_experiment.py 的机制原样复用，模型换 DeepSeek。

课程原版用本地 Ollama qwen3:4b 暴露「50K 全量 schema 下小模型指令遵循退化」。学习版保留同一
对照设计（control = 全量 schema 注入；treatment = web_search/code_interpreter + discover_tools
元工具 + 本地嵌入检索注入 + 状态栏），只把模型换成 deepseek-flash，用来回答一个不同的问题：
**当模型足够强时，主动工具发现还剩多少价值**。

零改动复用（import 课程模块，直接调用）：
  canonical_json / sha256_bytes / write_json / _server_info / schema_dict / render_schemas /
  count_tokens / extract_json / parse_action / grade_plan / parse_payload / simulation_markers /
  substantive_payload / mcp_receipt / compact_tool_data / arxiv_ids / visualization_code /
  _task_artifacts / _finalize_execution / _call_real_tool / append_history /
  LocalEmbeddingIndex / safe_summary / _history_chain_valid / _required_receipts_real / build_manifest

按学习版重写（模型身份/回执/门禁/输出目录）：
  1. ollama_chat → deepseek_chat：OpenAI 兼容端点、thinking 关闭、带 usage 与缓存命中字段；
  2. 系统提示词中的 "Qwen3-4B" → "DeepSeek"（对照组横幅同步改写）；
  3. 门禁 `exact_model_with_qwen_response_receipts` → `exact_model_with_deepseek_response_receipts`；
  4. VALIDATION_ROOT 重定向到 learning/task4/runs/4-1_active_tool_discovery/<UTC 时间戳>，
     课程 validation/ 目录不被触碰。

目录结构（每次运行）：
  protocol.json                     课程协议原样落盘
  catalog.schemas.json.gz           127 个真实 MCP schema（哈希入收据）
  catalog_receipt.json              schema 目录收据（token 数、哈希、必需工具）
  embedding_receipt.json            本地 all-MiniLM-L6-v2 索引收据
  index/embeddings-*.json           工具向量缓存（含 texts/vectors 哈希）
  control/<task>/receipt.json       对照组逐轮轨迹 + 真实 MCP 观测 + 工件
  treatment/<task>/receipt.json     实验组逐轮轨迹（含 discover_tools 注入与状态栏）
  summary.json                      对照汇总 + 全部门禁
  manifest.json                     全目录 sha256
  evidence.json / evidence.sha256   学习版证据层
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
if not DEEPSEEK_KEY:
    raise SystemExit("DEEPSEEK_API_KEY is required for the learning variant")

# 课程用 tiktoken o200k_base 统计 schema token；该编码首次使用要从境外拉 3.6MB BPE 文件
# （本机实测 151 秒，看起来像卡死）。先把缓存固定到仓库内，避免每次重跑都重新下载。
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(__file__).resolve().parent / ".cache/tiktoken"))

CHAPTER4 = ROOT / "chapter4"
sys.path.insert(0, str(CHAPTER4 / "active-tool-discovery"))
import run_exact_experiment as course  # noqa: E402

# --- 学习版常量 ---------------------------------------------------------------
MODEL = "deepseek-flash"
LEARNING_BANNER = "DeepSeek"
RUNTIME = {
    "name": "deepseek-openai-compatible",
    "model": MODEL,
    "endpoint": DEEPSEEK_BASE,
    "temperature": 0,
    "thinking": "disabled",
    "max_tokens": 1400,
    "max_turns": 12,
}
OUT_ROOT = ROOT / "learning/task4/runs/4-1_active_tool_discovery"
OUT = OUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
_AGENT_PROTOCOL = course._AGENT_PROTOCOL

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=DEEPSEEK_KEY, base_url=DEEPSEEK_BASE, timeout=900.0)
    return _client


async def deepseek_chat(messages: list[dict[str, str]], *, timeout: float = 900.0) -> dict:
    """课程 ollama_chat 的 DeepSeek 等价物：同样的返回形状，外加 usage 与缓存命中。"""
    request = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0,
        "max_tokens": RUNTIME["max_tokens"],
        "extra_body": {"thinking": {"type": "disabled"}},
    }
    started = time.perf_counter()
    response = await _get_client().chat.completions.create(**request, timeout=timeout)
    latency = round(time.perf_counter() - started, 3)
    choice = response.choices[0]
    usage = response.usage
    extra = getattr(usage, "model_extra", None) or {}
    return {
        "response_model": response.model,
        "created_at": str(response.created),
        "done": choice.finish_reason is not None,
        "done_reason": choice.finish_reason,
        "content": choice.message.content or "",
        "thinking": "",
        "prompt_eval_count": getattr(usage, "prompt_tokens", None),
        "eval_count": getattr(usage, "completion_tokens", None),
        "total_duration_ns": int(latency * 1e9),
        "latency_seconds": latency,
        "request_hash": course.sha256_bytes(course.canonical_json(request).encode()),
        "usage": {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "prompt_cache_hit_tokens": extra.get("prompt_cache_hit_tokens"),
            "prompt_cache_miss_tokens": extra.get("prompt_cache_miss_tokens"),
        },
    }


async def run_agent_task(session, schemas, index, strategy: str, task: dict, task_dir: Path) -> dict:
    """课程 run_agent_task 的同构重写：唯一差异是模型横幅、聊天后端与 runtime 回执。"""
    by_name = {schema["name"]: schema for schema in schemas}
    if strategy == "control":
        system = (f"You are {LEARNING_BANNER} in the full-schema control. The perception MCP server "
                  f"exposed {len(schemas)} complete tools.\n\n{course.render_schemas(schemas)}\n\n"
                  f"{_AGENT_PROTOCOL}")
        available = set(by_name)
    else:
        base_schemas = [by_name[name] for name in sorted(course.BASE_TOOL_NAMES)]
        system = (f"You are {LEARNING_BANNER} in the active-discovery treatment. Initially only the "
                  "three schemas below exist. Discover a specialist only when you encounter that "
                  "capability gap. Previously discovered schema blocks stay at their original "
                  "history position.\n\n" + course.TREATMENT_GUIDANCE + "\n\n" +
                  course.render_schemas(base_schemas + [course.DISCOVER_SCHEMA]) + "\n\n" +
                  _AGENT_PROTOCOL)
        available = set(course.BASE_TOOL_NAMES)
    initial_schema_names = sorted(
        available | ({"discover_tools"} if strategy == "treatment" else set())
    )
    messages: list[dict[str, str]] = []
    history: list[dict] = []
    course.append_history(messages, history, "system", system, turn=0,
                          event="initial_system_prompt", available=available,
                          extra={"schema_names": initial_schema_names})
    course.append_history(
        messages, history, "user",
        f"Task: {task['prompt']}\n[STATUS BAR: available tools = {sorted(available)}]",
        turn=0, event="task_prompt", available=available,
    )
    state: dict = {"receipts": [], "search_payload": None, "contributors": []}
    actions: list[dict] = []
    discoveries: list[dict] = []
    interactions: list[dict] = []
    parse_errors: list[str] = []
    final_answer = ""
    started = time.perf_counter()
    for turn in range(1, RUNTIME["max_turns"] + 1):
        response = await deepseek_chat(messages)
        action, parse_error = course.parse_action(response)
        interactions.append({"turn": turn, "response": response,
                             "action": action, "parse_error": parse_error})
        course.append_history(messages, history, "assistant", response["content"], turn=turn,
                              event="model_response", available=available)
        if parse_error or action is None:
            parse_errors.append(parse_error or "unknown parse error")
            course.append_history(
                messages, history, "user",
                f"Protocol error: {parse_error}. Return exactly one valid JSON action. "
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="protocol_error", available=available,
            )
            continue
        if action["action"] == "finish":
            completion_probe = course._finalize_execution(task, state, task_dir)
            if not completion_probe["task_complete"]:
                successful = {receipt.get("tool") for receipt in state["receipts"]
                              if receipt.get("success") is True}
                missing_count = sum(not bool(successful & slot) for slot in task["slots"])
                course.append_history(
                    messages, history, "user",
                    "Finish rejected: one or more requested subtasks still lack "
                    f"a successful specialist observation or required artifact "
                    f"(missing capability slots: {missing_count}). "
                    "Use discover_tools for each remaining capability gap, then "
                    "execute the discovered specialist before finishing. "
                    f"[STATUS BAR: available tools = {sorted(available)}]",
                    turn=turn, event="premature_finish_rejected", available=available,
                    extra={"missing_capability_slots": missing_count},
                )
                continue
            final_answer = action["answer"]
            break
        if action["action"] == "discover_tools":
            if strategy != "treatment":
                course.append_history(
                    messages, history, "user",
                    "discover_tools is unavailable in the control; choose a listed tool.",
                    turn=turn, event="control_discovery_error", available=available,
                )
                continue
            hits = index.search(action["need"], course.DISCOVERY_TOP_K)
            hit_schemas = [hit["schema"] for hit in hits]
            block = course.render_schemas(hit_schemas)
            names = [schema["name"] for schema in hit_schemas]
            available.update(names)
            discovery = {"turn": turn, "need": action["need"], "top_k": len(hits),
                         "matches": [{"name": hit["schema"]["name"], "score": hit["score"]}
                                     for hit in hits],
                         "schemas_sha256": course.sha256_bytes(block.encode()),
                         "schema_tokens": course.count_tokens(block)}
            discoveries.append(discovery)
            course.append_history(
                messages, history, "user",
                f"discover_tools returned these {len(hits)} complete MCP schemas:\n{block}\n\n"
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="schema_injection", available=available,
                extra={"schema_names": names, "schema_count": len(hit_schemas),
                       "schemas_sha256": discovery["schemas_sha256"],
                       "schema_tokens": discovery["schema_tokens"]},
            )
            continue
        name = action["tool"]
        actions.append(action)
        if name not in available:
            state["receipts"].append({"tool": name, "success": False,
                                      "error": "tool was not available at this turn"})
            hint = ("Call discover_tools for this missing capability first."
                    if strategy == "treatment" else "Choose an exact name from the full catalog.")
            course.append_history(
                messages, history, "user",
                f"Tool error: {name} is unavailable. {hint} "
                f"[STATUS BAR: available tools = {sorted(available)}]",
                turn=turn, event="unavailable_tool", available=available,
            )
            continue
        observation = await course._call_real_tool(session, task, action, task_dir, state)
        course.append_history(
            messages, history, "user",
            "Real MCP observation:\n" +
            json.dumps(observation, ensure_ascii=False, default=str)[:50000] +
            f"\n[STATUS BAR: available tools = {sorted(available)}]",
            turn=turn, event="mcp_observation", available=available,
            extra={"tool": name, "success": bool(observation.get("success"))},
        )
    grade = course.grade_plan(task, actions)
    execution = course._finalize_execution(task, state, task_dir)
    execution["agent_finished"] = bool(final_answer.strip())
    execution["task_complete"] = execution["task_complete"] and execution["agent_finished"]
    return {
        "task": task["id"], "strategy": strategy, "model": MODEL,
        "prompt": task["prompt"], "actions": actions, "parse_errors": parse_errors,
        "discoveries": discoveries, "grade": grade, "execution": execution,
        "final_answer": final_answer, "interactions": interactions,
        "history_receipt": {
            "events": history,
            "event_count": len(history),
            "final_chain_sha256": history[-1]["chain_sha256"],
            "dynamic_schema_injection_tokens": sum(
                row.get("schema_tokens", 0) for row in history
                if row["event"] == "schema_injection"
            ),
        },
        "initial_schema_names": initial_schema_names,
        "catalog_sha256": course.sha256_bytes(course.canonical_json(schemas).encode()),
        "runtime": RUNTIME,
        "system_prompt_sha256": course.sha256_bytes(system.encode()),
        "system_prompt_tokens": course.count_tokens(system),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


_AGENT_PROTOCOL = course._AGENT_PROTOCOL


async def run_group(session, schemas, index, strategy: str, campaign_dir: Path) -> list[dict]:
    records = []
    for task in course.TASKS:
        task_dir = campaign_dir / strategy / task["id"]
        task_dir.mkdir(parents=True, exist_ok=True)
        record = await run_agent_task(session, schemas, index, strategy, task, task_dir)
        course.write_json(task_dir / "receipt.json", record)
        records.append(record)
        print(f"  [{strategy}] {task['id']}: complete={record['execution']['task_complete']} "
              f"accuracy={record['grade']['accuracy']:.2f} turns={len(record['interactions'])} "
              f"{record['elapsed_seconds']:.1f}s", flush=True)
    return records


def derive_acceptance(records, schemas, catalog, protocol, comparison, embedding) -> dict:
    """课程 derive_acceptance 的门禁结构，把 qwen 专属项换成 DeepSeek 回执项。"""
    task_by_id = {task["id"]: task for task in course.TASKS}
    expected_pairs = {(strategy, task["id"])
                      for strategy in ("control", "treatment") for task in course.TASKS}
    actual_pairs = [(row.get("strategy"), row.get("task")) for row in records]
    exact_six = len(actual_pairs) == 6 and set(actual_pairs) == expected_pairs \
        and len(set(actual_pairs)) == len(actual_pairs)
    schema_by_name = {schema["name"]: schema for schema in schemas}
    catalog_hash = course.sha256_bytes(course.canonical_json(schemas).encode())

    deepseek_receipts = bool(records) and all(
        row.get("model") == MODEL
        and row.get("runtime", {}).get("name") == RUNTIME["name"]
        and row.get("runtime", {}).get("model") == MODEL
        and bool(row.get("interactions"))
        and all(
            interaction.get("response", {}).get("response_model") == MODEL
            and interaction.get("response", {}).get("done") is True
            and bool(interaction.get("response", {}).get("request_hash"))
            and bool(interaction.get("response", {}).get("content", "").strip())
            and (interaction.get("response", {}).get("usage") or {}).get("prompt_tokens")
            for interaction in row.get("interactions", [])
        )
        for row in records
    )
    real_execution = exact_six and all(
        row.get("task") in task_by_id
        and course._required_receipts_real(row, task_by_id[row["task"]])
        for row in records
    )
    completed_with_artifacts = exact_six and all(
        row.get("execution", {}).get("task_complete") is True
        and row.get("execution", {}).get("agent_finished") is True
        and bool(row.get("final_answer", "").strip())
        for row in records
    )
    treatment_rows = [row for row in records if row.get("strategy") == "treatment"]
    treatment_discovery = len(treatment_rows) == 3
    dynamic_token_totals = []
    for row in treatment_rows:
        discoveries = row.get("discoveries", [])
        events = [event for event in row.get("history_receipt", {}).get("events", [])
                  if event.get("event") == "schema_injection"]
        dynamic_tokens = row.get("history_receipt", {}).get("dynamic_schema_injection_tokens", -1)
        dynamic_token_totals.append(dynamic_tokens)
        if not discoveries or len(events) != len(discoveries) or not course._history_chain_valid(row):
            treatment_discovery = False
            continue
        if set(row.get("initial_schema_names", [])) != {
            "web_search", "code_interpreter", "discover_tools"
        }:
            treatment_discovery = False
        cumulative = {"web_search", "code_interpreter"}
        for discovery, event in zip(discoveries, events):
            names = [match.get("name") for match in discovery.get("matches", [])]
            resolved = [schema_by_name.get(name) for name in names]
            if any(schema is None for schema in resolved):
                treatment_discovery = False
                continue
            expected_block = course.render_schemas(resolved)
            cumulative.update(names)
            conditions = [
                3 <= discovery.get("top_k", 0) <= 5,
                discovery.get("top_k") == len(names),
                event.get("role") == "user",
                event.get("turn") == discovery.get("turn"),
                event.get("schema_names") == names,
                event.get("schema_count") == len(names),
                event.get("schemas_sha256") == course.sha256_bytes(expected_block.encode()),
                discovery.get("schemas_sha256") == course.sha256_bytes(expected_block.encode()),
                event.get("schema_tokens") == course.count_tokens(expected_block),
                discovery.get("schema_tokens") == course.count_tokens(expected_block),
                event.get("status_bar_present") is True,
                set(event.get("available_tools") or []) == cumulative,
            ]
            if not all(conditions):
                treatment_discovery = False
        if dynamic_tokens != sum(item.get("schema_tokens", 0) for item in discoveries) \
                or dynamic_tokens <= 0:
            treatment_discovery = False

    control_rows = [row for row in records if row.get("strategy") == "control"]
    full_control_catalog = len(control_rows) == 3 and all(
        set(row.get("initial_schema_names", [])) == set(schema_by_name)
        and row.get("system_prompt_tokens", 0) > protocol["minimum_control_schema_tokens"]
        for row in control_rows
    )
    identical_runtime = exact_six and all(
        row.get("catalog_sha256") == catalog_hash
        and row.get("runtime") == records[0].get("runtime")
        and row.get("model") == records[0].get("model") == MODEL
        and row.get("prompt") == next(
            task["prompt"] for task in course.TASKS if task["id"] == row.get("task")
        )
        for row in records
    )
    comparison_present = set(comparison) == {"control", "treatment"} and all(
        set(comparison[strategy]) >= {
            "tasks", "mean_tool_selection_accuracy",
            "tasks_with_all_required_capabilities", "tasks_completed", "elapsed_seconds"
        } and comparison[strategy]["tasks"] == 3
        for strategy in ("control", "treatment")
    )
    embedding_real = (
        embedding.get("model") == "sentence-transformers/all-MiniLM-L6-v2"
        and embedding.get("backend") == "local-transformers-mean-pooling"
        and embedding.get("local_files_only") is True
        and embedding.get("catalog_text_count") == len(schemas)
        and embedding.get("vector_count") == len(schemas)
        and embedding.get("vector_dimensions", 0) > 0
        and bool(embedding.get("texts_sha256"))
        and bool(embedding.get("cache_sha256"))
    )
    gates = {
        "exact_model_with_deepseek_response_receipts": deepseek_receipts,
        "catalog_from_mcp_and_hash_matches": (
            catalog.get("transport") == "mcp-stdio"
            and catalog.get("tools_list_received") is True
            and catalog.get("schema_sha256") == catalog_hash
            and catalog.get("tool_count") == len(schemas)
            and catalog.get("unique_tool_count") == len(schema_by_name)
            and all(catalog.get("required_tools_present", {}).values())
            and catalog.get("catalog_gzip_bytes", 0) > 0
            and len(catalog.get("catalog_gzip_sha256", "")) == 64
            and catalog.get("catalog_gzip_content_sha256") == catalog_hash
        ),
        "tool_count_at_least_120": len(schemas) >= protocol["minimum_mcp_tools"],
        "control_over_50k_complete_schema_tokens": (
            catalog.get("schema_tokens_o200k", 0) > protocol["minimum_control_schema_tokens"]
            and full_control_catalog
        ),
        "three_tasks_each_group": exact_six,
        "real_mcp_execution_only": real_execution,
        "all_tasks_completed_with_required_artifacts": completed_with_artifacts,
        "treatment_discovery_history_and_status_verified": treatment_discovery,
        "identical_tasks_model_runtime_and_catalog": identical_runtime,
        "local_embedding_index_receipted": embedding_real,
        "dynamic_schema_injection_tokens_recorded": (
            len(dynamic_token_totals) == 3 and all(value > 0 for value in dynamic_token_totals)
        ),
        "comparison_metrics_present_for_both_arms": comparison_present,
    }
    return {"status": "passed" if all(gates.values()) else "failed", "gates": gates}


async def run() -> Path:
    protocol = json.loads((CHAPTER4 / "active-tool-discovery/experiment_protocol.json")
                          .read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=False)
    course.write_json(OUT / "protocol.json", protocol)
    params = course.StdioServerParameters(
        command=sys.executable,
        args=[str(CHAPTER4 / "perception-tools/src/main.py")],
        env=os.environ.copy(),
    )
    async with course.stdio_client(params) as (read, write):
        async with course.ClientSession(read, write) as session:
            initialize = await session.initialize()
            listed = await session.list_tools()
            schemas = [course.schema_dict(tool) for tool in listed.tools]
            schema_bytes = course.canonical_json(schemas).encode()
            schema_text = course.render_schemas(schemas)
            catalog = {
                "transport": "mcp-stdio",
                "server": str(CHAPTER4 / "perception-tools/src/main.py"),
                "tools_list_received": True,
                "server_name": course._server_info(initialize).name,
                "server_version": course._server_info(initialize).version,
                "tool_count": len(schemas),
                "unique_tool_count": len({s["name"] for s in schemas}),
                "schema_tokens_o200k": course.count_tokens(schema_text),
                "schema_bytes": len(schema_bytes),
                "schema_sha256": course.sha256_bytes(schema_bytes),
                "required_tools_present": {
                    name: name in {schema["name"] for schema in schemas}
                    for name in ["web_search", "code_interpreter", "yfinance_quote", "search_news",
                                 "arxiv_search", "arxiv_download", "github_list_contributors"]
                },
            }
            print(f"MCP catalog: {catalog['tool_count']} tools, "
                  f"{catalog['schema_tokens_o200k']} schema tokens", flush=True)
            if catalog["tool_count"] < protocol["minimum_mcp_tools"]:
                raise RuntimeError(f"MCP catalog too small: {catalog['tool_count']}")
            if catalog["schema_tokens_o200k"] <= protocol["minimum_control_schema_tokens"]:
                raise RuntimeError(f"control schema prompt too small: {catalog['schema_tokens_o200k']}")
            if not all(catalog["required_tools_present"].values()):
                raise RuntimeError("required task tools missing from MCP catalog")
            gzip_path = OUT / "catalog.schemas.json.gz"
            with gzip.open(gzip_path, "wt", encoding="utf-8") as stream:
                json.dump(schemas, stream, ensure_ascii=False)
            catalog["catalog_gzip_bytes"] = gzip_path.stat().st_size
            catalog["catalog_gzip_sha256"] = course.sha256_bytes(gzip_path.read_bytes())
            with gzip.open(gzip_path, "rt", encoding="utf-8") as stream:
                gzip_schemas = json.load(stream)
            catalog["catalog_gzip_content_sha256"] = course.sha256_bytes(
                course.canonical_json(gzip_schemas).encode()
            )
            course.write_json(OUT / "catalog_receipt.json", catalog)

            index = await asyncio.to_thread(course.LocalEmbeddingIndex, schemas, OUT / "index")
            embedding_receipt = index.receipt()
            course.write_json(OUT / "embedding_receipt.json", embedding_receipt)

            print(f"running control arm with {MODEL} ...", flush=True)
            control = await run_group(session, schemas, index, "control", OUT)
            print(f"running treatment arm with {MODEL} ...", flush=True)
            treatment = await run_group(session, schemas, index, "treatment", OUT)
            records = control + treatment
            comparison = course.safe_summary(records)
            acceptance = derive_acceptance(records, schemas, catalog, protocol,
                                           comparison, embedding_receipt)
            summary = {
                "experiment": "4-1",
                "campaign_id": OUT.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "learning_variant": {
                    "model": MODEL, "runtime": RUNTIME,
                    "note": "course mechanism reused verbatim; model replaced Ollama qwen3:4b with "
                            "deepseek-flash to test whether active discovery still pays off for a "
                            "strong model",
                },
                "catalog": catalog,
                "embedding": embedding_receipt,
                "comparison": comparison,
                "dynamic_schema_injection_tokens": {
                    row["task"]: row["history_receipt"]["dynamic_schema_injection_tokens"]
                    for row in treatment
                },
                "token_usage": {
                    strategy: {
                        "prompt_tokens": sum(
                            (interaction.get("response", {}).get("usage") or {}).get("prompt_tokens") or 0
                            for row in records if row["strategy"] == strategy
                            for interaction in row["interactions"]
                        ),
                        "completion_tokens": sum(
                            (interaction.get("response", {}).get("usage") or {}).get("completion_tokens") or 0
                            for row in records if row["strategy"] == strategy
                            for interaction in row["interactions"]
                        ),
                        "cache_hit_tokens": sum(
                            (interaction.get("response", {}).get("usage") or {})
                            .get("prompt_cache_hit_tokens") or 0
                            for row in records if row["strategy"] == strategy
                            for interaction in row["interactions"]
                        ),
                    }
                    for strategy in ("control", "treatment")
                },
                "acceptance": acceptance,
                "status": acceptance["status"],
            }
            course.write_json(OUT / "summary.json", summary)
    course.write_json(OUT / "manifest.json", course.build_manifest(OUT))
    return OUT


def write_evidence() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    leak = []
    for name, key in (("deepseek", DEEPSEEK_KEY),):
        for path in sorted(OUT.rglob("*")):
            if path.is_file() and key and key in path.read_bytes().decode("utf-8", "ignore"):
                leak.append(f"{name}:{path.relative_to(OUT)}")
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    evidence = {
        "experiment": "4-1 active tool discovery (learning variant)",
        "run_dir": str(OUT.relative_to(ROOT)),
        "run_dir_sha256_manifest": hashlib.sha256(
            (OUT / "manifest.json").read_bytes()).hexdigest(),
        "manifest_file_count": len(manifest["files"]),
        "model": MODEL,
        "runtime": RUNTIME,
        "catalog": summary["catalog"],
        "embedding_receipt": summary["embedding"],
        "comparison": summary["comparison"],
        "token_usage": summary["token_usage"],
        "dynamic_schema_injection_tokens": summary["dynamic_schema_injection_tokens"],
        "acceptance": summary["acceptance"],
        "course_evidence": {
            "source": "chapter4/active-tool-discovery/run_exact_experiment.py (control loop, "
                      "receipts, gates, MCP execution and embedding index reused verbatim)",
            "status": summary["status"],
            "gates": summary["acceptance"]["gates"],
        },
        "source_hashes": {
            rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
            for rel in [
                "chapter4/active-tool-discovery/run_exact_experiment.py",
                "chapter4/active-tool-discovery/experiment_protocol.json",
                "chapter4/perception-tools/src/main.py",
                "learning/task4/run_4_1_tool_discovery.py",
            ]
        },
        "credential_scan_findings": leak,
        "completed": summary["status"] == "passed" and not leak,
    }
    payload = json.dumps(evidence, ensure_ascii=False, indent=2)
    assert DEEPSEEK_KEY not in payload
    (OUT / "evidence.json").write_text(payload, encoding="utf-8")
    (OUT / "evidence.sha256").write_text(
        hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print("output:", OUT, flush=True)
    path = asyncio.run(run())
    write_evidence()
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    print("\n对照结果（DeepSeek 学习版）", flush=True)
    for strategy, row in summary["comparison"].items():
        print(f"  {strategy:<9} accuracy={row['mean_tool_selection_accuracy']:.2f} "
              f"all_caps={row['tasks_with_all_required_capabilities']}/3 "
              f"complete={row['tasks_completed']}/3 elapsed={row['elapsed_seconds']:.0f}s", flush=True)
    print("runtime:", summary["status"], "| gates:",
          sum(summary["acceptance"]["gates"].values()), "/",
          len(summary["acceptance"]["gates"]), flush=True)
    print("DONE", path, flush=True)


if __name__ == "__main__":
    main()
