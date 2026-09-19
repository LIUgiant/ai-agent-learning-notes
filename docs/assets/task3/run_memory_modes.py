"""Task3 / 实验 3-1+3-2 用户记忆学习版：课程 run_evaluation.py 的四记忆模式战役。

不修改课程代码、不触碰课程 validation/ 目录：import run_evaluation 后打三处补丁——
1. run_eval.HERE 重定向到本运行目录（write_campaign_evidence 会写 HERE/validation/，
   原样运行会覆盖书方的规范证据 latest.json；重定向后检查点与证据全落在学习目录）；
2. run_eval.OpenAI 换 provider 感知工厂：DeepSeek 调用关 thinking
   （extra_body thinking），DashScope/qwen 调用关思考（enable_thinking=False）；
3. 环境变量 ARK_API_KEY/MOONSHOT_API_KEY 按课程代码的读取习惯注入
   （writer=DeepSeek、judge=DashScope qwen，端点与模型全部由 CLI 参数指定，
   真正异厂商独立评审；provenance 里 key 存在性显示为真，实际指向在学习协议里写明）。

规模：课程默认 smoke（每层 2 案例 × 4 模式 = 24 评估），不是权威 60×4 全量。
"""
import hashlib
import json
import os
import sys
import time
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
WRITER_MODEL = "deepseek-flash"
JUDGE_MODEL = "qwen3.7-plus"
WRITER_ENDPOINT = "https://api.deepseek.com"
JUDGE_ENDPOINT = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
OUT = ROOT / "learning/task3/runs/3-1_3-2_memory_modes" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

# 课程模块（run_evaluation 自己会把 chapter3 根加进 sys.path 以导入 experiment_utils）
sys.path.insert(0, str(ROOT / "chapter3/user-memory"))
import run_evaluation as run_eval  # noqa: E402

data = {
    "experiment": "3-1/3-2 memory modes learning variant",
    "note": "course run_evaluation reused verbatim; writer=deepseek-flash, judge=dashscope qwen3.7-plus (cross-vendor); smoke scale 2 cases/layer x 4 modes, not the authoritative 60x4",
    "writer": {"provider": "deepseek", "endpoint": WRITER_ENDPOINT, "model": WRITER_MODEL},
    "judge": {"provider": "dashscope", "endpoint": JUDGE_ENDPOINT, "model": JUDGE_MODEL},
    "source_hashes": {
        "chapter3/user-memory/run_evaluation.py": hashlib.sha256(
            (ROOT / "chapter3/user-memory/run_evaluation.py").read_bytes()
        ).hexdigest(),
    },
}

# --- 注入 1：输出目录重定向（保护课程 validation/）------------------------------
# write_campaign_evidence 的 input_paths 会引用 HERE/run_evaluation.py，
# 因此把入口脚本也复制一份到运行目录（哈希与课程原文一致）。
import shutil

shutil.copy2(ROOT / "chapter3/user-memory/run_evaluation.py", OUT / "run_evaluation.py")
run_eval.HERE = OUT
# CHAPTER 保持课程目录不变：test_cases 默认路径指向课程评测集（只读）

# --- 注入 2：provider 感知的 OpenAI 工厂 -----------------------------------------
_real_openai = OpenAI


class _NoThinkingCompletions:
    def __init__(self, inner, disable_thinking):
        self._inner = inner
        self._disable = disable_thinking

    def create(self, **req):
        if self._disable == "deepseek":
            req.setdefault("extra_body", {})["thinking"] = {"type": "disabled"}
        elif self._disable == "dashscope":
            req.setdefault("extra_body", {})["enable_thinking"] = False
        return self._inner.create(**req)


class _ProviderAwareOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        base = str(kwargs.get("base_url") or "")
        mode = "deepseek" if "deepseek" in base else ("dashscope" if "dashscope" in base else None)
        self.chat = SimpleNamespace(completions=_NoThinkingCompletions(inner.chat.completions, mode))


run_eval.OpenAI = _ProviderAwareOpenAI

# --- 注入 3：凭据按课程读取习惯注入（指向不同厂商的端点）-----------------------
os.environ["ARK_API_KEY"] = DEEPSEEK_KEY      # Campaign 以此作为 writer key
os.environ["MOONSHOT_API_KEY"] = DASHSCOPE_KEY  # Campaign 以此作为 judge key

sys.argv = [
    "run_evaluation.py",
    "--writer-endpoint", WRITER_ENDPOINT,
    "--writer-model", WRITER_MODEL,
    "--judge-endpoint", JUDGE_ENDPOINT,
    "--judge-model", JUDGE_MODEL,
    "--workers", "4",
]

print("Output:", OUT, flush=True)
print(f"writer={WRITER_MODEL} @ deepseek | judge={JUDGE_MODEL} @ dashscope", flush=True)
exit_code = run_eval.main()

# --- 学习版证据层：定位产物、密钥扫描、汇总 -------------------------------------
runs_dir = OUT / "validation" / "runs"
latest = json.loads((OUT / "validation" / "latest.json").read_text())
run_dir = runs_dir / latest["run_id"]
evidence = json.loads((run_dir / "evidence.json").read_text())

leaked = []
for key_name, key in (("deepseek", DEEPSEEK_KEY), ("dashscope", DASHSCOPE_KEY)):
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and key in path.read_text(errors="ignore"):
            leaked.append(f"{key_name}:{path.relative_to(OUT)}")
data["credential_scan_findings"] = leaked
data["course_evidence"] = {
    "status": evidence.get("status"),
    "scope": evidence.get("scope"),
    "acceptance": evidence.get("acceptance"),
    "summary": evidence.get("summary"),
    "results": [
        {
            "test_id": r["test_id"],
            "layer": r["layer"],
            "mode": r["mode"],
            "judge": r["judge"],
            "answer_chars": len(r.get("answer") or ""),
            "session_count": r["session_count"],
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
print("\n四模式 x 三层（DeepSeek 学习版）", flush=True)
for mode, layers in (evidence.get("summary", {}).get("aggregate") or {}).items():
    overall = layers.get("overall", {})
    print(
        f"  {mode:<22} pass={overall.get('pass_rate', 0):.2f} "
        f"reward={overall.get('mean_reward', 0):.3f} halluc={overall.get('hallucination_rate', 0):.2f}",
        flush=True,
    )
print("DONE. course status:", evidence.get("status"), "| leak scan:", leaked or "clean", flush=True)
