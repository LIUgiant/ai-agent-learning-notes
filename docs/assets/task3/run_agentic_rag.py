"""Task3 / 实验 3-8 agentic-rag 学习版：课程 campaign.py 全量 7 案例，DeepSeek 答题 + DashScope qwen 独立评审。

不修改课程代码：import campaign 后打三处补丁——
1. campaign.HERE 重定向到本运行目录，并把 laws/ 与 evaluation/ 复制过去
   （HERE 既是数据根也是输出根；直接跑会覆盖课程 validation/latest.json）；
2. campaign.OpenAI 换 provider 感知工厂（deepseek 关 thinking、dashscope 关 enable_thinking）；
3. 凭据按课程读取习惯注入：ARK_API_KEY=DeepSeek（答题臂）、MOONSHOT_API_KEY=DashScope（评审）。
   注意：receipts 里 provider 标签沿用课程硬编码的 "ark"/"moonshot"，真实端点见 endpoint 字段。

检索侧零改动：OfflineRetriever（本地法条 BM25）与数据集、金标法条全部课程原样。
"""
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DASHSCOPE_KEY = os.getenv("DASHSCOPE_API_KEY", "")
if not DEEPSEEK_KEY or not DASHSCOPE_KEY:
    raise SystemExit("DEEPSEEK_API_KEY and DASHSCOPE_API_KEY are both required")
ANSWER_MODEL = "deepseek-flash"
JUDGE_MODEL = "qwen3.7-plus"
ANSWER_ENDPOINT = "https://api.deepseek.com"
JUDGE_ENDPOINT = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OUT = ROOT / "learning/task3/runs/3-8_agentic_rag" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

# 课程模块
sys.path.insert(0, str(ROOT / "chapter3"))
sys.path.insert(0, str(ROOT / "chapter3/agentic-rag"))
import campaign as rag_campaign  # noqa: E402

data = {
    "experiment": "3-8 agentic-rag learning variant",
    "note": "course campaign reused verbatim, full 7-case dataset; answer=deepseek-flash, judge=dashscope qwen3.7-plus (cross-vendor); receipt provider labels keep course tags ark/moonshot, real endpoints in endpoint field",
    "answer": {"provider": "deepseek", "endpoint": ANSWER_ENDPOINT, "model": ANSWER_MODEL},
    "judge": {"provider": "dashscope", "endpoint": JUDGE_ENDPOINT, "model": JUDGE_MODEL},
    "source_hashes": {
        "chapter3/agentic-rag/campaign.py": hashlib.sha256(
            (ROOT / "chapter3/agentic-rag/campaign.py").read_bytes()
        ).hexdigest(),
        "chapter3/agentic-rag/evaluation/offline_qa.json": hashlib.sha256(
            (ROOT / "chapter3/agentic-rag/evaluation/offline_qa.json").read_bytes()
        ).hexdigest(),
    },
}

# --- 注入 1：HERE 重定向 + 数据复制 ---------------------------------------------
SRC = ROOT / "chapter3/agentic-rag"
shutil.copytree(SRC / "laws", OUT / "laws")
shutil.copytree(SRC / "evaluation", OUT / "evaluation")
shutil.copy2(SRC / "campaign.py", OUT / "campaign.py")
shutil.copy2(SRC / "offline_retriever.py", OUT / "offline_retriever.py")
rag_campaign.HERE = OUT

# --- 注入 2：provider 感知 OpenAI 工厂 ------------------------------------------
_real_openai = OpenAI


class _NoThinkingCompletions:
    def __init__(self, inner, mode):
        self._inner = inner
        self._mode = mode

    def create(self, **req):
        if self._mode == "deepseek":
            req.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
        elif self._mode == "dashscope":
            req.setdefault("extra_body", {})["enable_thinking"] = False
        return self._inner.create(**req)


class _ProviderAwareOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        base = str(kwargs.get("base_url") or "")
        mode = "deepseek" if "deepseek" in base else ("dashscope" if "dashscope" in base else None)
        self.chat = SimpleNamespace(completions=_NoThinkingCompletions(inner.chat.completions, mode))


rag_campaign.OpenAI = _ProviderAwareOpenAI

# --- 注入 3：凭据注入 ------------------------------------------------------------
os.environ["ARK_API_KEY"] = DEEPSEEK_KEY
os.environ["MOONSHOT_API_KEY"] = DASHSCOPE_KEY

sys.argv = [
    "campaign.py",
    "--answer-endpoint", ANSWER_ENDPOINT,
    "--answer-model", ANSWER_MODEL,
    "--judge-endpoint", JUDGE_ENDPOINT,
    "--judge-model", JUDGE_MODEL,
    "--workers", "3",
]

print("Output:", OUT, flush=True)
print(f"answer={ANSWER_MODEL} @ deepseek | judge={JUDGE_MODEL} @ dashscope | cases: 7 (full)", flush=True)
exit_code = rag_campaign.main()

# --- 学习版证据层 ----------------------------------------------------------------
latest = json.loads((OUT / "validation/latest.json").read_text())
run_dir = OUT / "validation/runs" / latest["run_id"]
evidence = json.loads((run_dir / "evidence.json").read_text())

leaked = []
for key_name, key in (("deepseek", DEEPSEEK_KEY), ("dashscope", DASHSCOPE_KEY)):
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path in {OUT / "evidence.json"}:
            continue
        if path.is_file() and key in path.read_text(errors="ignore"):
            leaked.append(f"{key_name}:{path.relative_to(OUT)}")
data["credential_scan_findings"] = leaked
data["course_evidence"] = {
    "status": evidence.get("status"),
    "scope": evidence.get("scope"),
    "acceptance": evidence.get("acceptance"),
    "hypothesis_outcome": evidence.get("hypothesis_outcome"),
    "summary": evidence.get("summary"),
    "per_case": [
        {
            "id": r["case"]["id"],
            "complexity": r["case"]["complexity"],
            "arms": {
                arm: {
                    "recall": a["evidence"]["recall"],
                    "search_count": a["search_count"],
                    "latency_ms": a["latency_ms"],
                    "judge_correctness": a["judge"].get("correctness"),
                    "has_valid_citation": a["citations"]["has_valid_citation"],
                }
                for arm, a in r["arms"].items()
            },
        }
        for r in evidence.get("results", [])
    ],
}
data["completed"] = not leaked
payload = json.dumps(data, ensure_ascii=False, indent=2)
assert DEEPSEEK_KEY not in payload and DASHSCOPE_KEY not in payload
(OUT / "evidence.json").write_text(payload)
(OUT / "evidence.sha256").write_text(
    hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
)
print("\n基线 vs Agentic（DeepSeek 学习版）", flush=True)
for arm, groups in (evidence.get("summary", {}).get("metrics") or {}).items():
    for group, m in groups.items():
        print(
            f"  {arm:<9} {group:<8} recall={m['evidence_recall']:.2f} "
            f"correctness={m['judge_correctness']:.2f} searches={m['mean_search_count']:.1f} "
            f"latency={m['mean_latency_ms']:.0f}ms",
            flush=True,
        )
print("hypothesis:", evidence.get("hypothesis_outcome"), flush=True)
print("DONE. course status:", evidence.get("status"), "| leak scan:", leaked or "clean", flush=True)
