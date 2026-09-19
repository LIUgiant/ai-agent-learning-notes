"""Task2 / 实验 2-10 上下文压缩学习版：课程 run_all_strategies 六策略套件，跑在 DeepSeek 上。

不修改课程代码：复用 StrategyRunner / ResearchAgent / ContextCompressor 全部原逻辑，
仅注入四处——
1. Config.resolve_llm 改指 DeepSeek（task1 同款补丁；.env 的 LLM_PROVIDER=deepseek 会让
   MODEL_NAME 默认错配 kimi-k3，因此显式覆写）；
2. WebTools.search_web / fetch_webpage 换成合成语料（事实沿用课程 mock 的 2024 快照，
   每页加长到约 4K 字符的填充噪声；无 SERPER_API_KEY 时课程本来就回退 mock 语料，
   学习版只是把这个回退语料加大到足以呈现压缩对照）；
3. Config.CONTEXT_WINDOW_SIZE 128000 -> 16000：学习缩尺。溢出判定、80% 阈值、
   windowed 压缩的触发机制全部不变，只是预算缩小（DeepSeek 真实窗口 128K 远大于此，
   缩尺不会触发真实 API 限制）；
4. ResearchAgent 强制 enable_streaming=False（记录层需要非流式响应的完整 usage；
   课程 StrategyRunner 硬编码 True，流式分支由参数透传覆盖）。
"""
import hashlib
import importlib.util
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
KEY = os.getenv("DEEPSEEK_API_KEY", "")
if not KEY:
    raise SystemExit("DEEPSEEK_API_KEY missing; no calls made")
MODEL = "deepseek-flash"
WINDOW = 16000  # 学习缩尺：书方 128K 预算的 1/8
OUT = ROOT / "learning/task2/runs/2-10_context_compression" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT.mkdir(parents=True, exist_ok=False)

data = {
    "experiment": "2-10 context-compression learning variant",
    "note": "course StrategyRunner reused verbatim; DeepSeek provider; synthetic enriched corpus (no SERPER_API_KEY); context budget 128K->16K learning scale",
    "model": MODEL,
    "context_window": WINDOW,
    "source_hashes": {},
    "calls": [],
}

logging.disable(logging.INFO)  # 课程 INFO 日志极多，保留 WARNING+


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


cfg = load("config", "chapter2/context-compression/config.py")
cfg.Config.resolve_llm = classmethod(lambda cls: (KEY, os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"), MODEL))
cfg.Config.MODEL_NAME = MODEL
cfg.Config.CONTEXT_WINDOW_SIZE = WINDOW
cfg.Config.MAX_ITERATIONS = 20

web_tools = load("web_tools", "chapter2/context-compression/web_tools.py")
comp_mod = load("compression_strategies", "chapter2/context-compression/compression_strategies.py")
agent_mod = load("agent", "chapter2/context-compression/agent.py")

# --- 注入 1：记录型 OpenAI 工厂（关 thinking + 记录回执）------------------------
_real_openai = OpenAI


class _RecordingCompletions:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **req):
        req["extra_body"] = {"thinking": {"type": "disabled"}}
        start = time.monotonic()
        resp = self._inner.create(**req)
        data["calls"].append(
            {
                "elapsed_s": round(time.monotonic() - start, 3),
                "model": getattr(resp, "model", None),
                "id": getattr(resp, "id", None),
                "finish_reason": resp.choices[0].finish_reason,
                "stream": bool(req.get("stream")),
                "tool_calls": [
                    tc.function.name for tc in (resp.choices[0].message.tool_calls or [])
                ],
                "usage": resp.usage.model_dump() if resp.usage else {},
            }
        )
        save()
        return resp


class _RecordingOpenAI:
    def __init__(self, **kwargs):
        inner = _real_openai(**kwargs)
        self.chat = _ChatShim(inner)


class _ChatShim:
    def __init__(self, inner):
        self.completions = _RecordingCompletions(inner.chat.completions)


agent_mod.OpenAI = _RecordingOpenAI
comp_mod.OpenAI = _RecordingOpenAI

# --- 注入 2：非流式（记录层需要完整 usage；流式分块不含逐 call 的回执形状）-------
_orig_agent_init = agent_mod.ResearchAgent.__init__


def _init_no_stream(self, api_key, compression_strategy=None, verbose=False, enable_streaming=True):
    _orig_agent_init(
        self,
        api_key,
        compression_strategy=compression_strategy or agent_mod.CompressionStrategy.NO_COMPRESSION,
        verbose=verbose,
        enable_streaming=False,
    )


agent_mod.ResearchAgent.__init__ = _init_no_stream

# --- 注入 3：合成语料（事实 = 课程 mock 的 2024 快照；每页加长填充噪声）---------
_NOISE_PARAS = [
    "The design review covered button colors, illustration spacing and onboarding video length. "
    "Attendees agreed to defer typography changes to the next quarter. ",
    "Operations reported that the quarterly offsite planning is underway, with catering options "
    "and accessibility accommodations still under discussion. No decisions were recorded. ",
    "The newsletter draft mentioned community meetups, a photography contest and several book "
    "recommendations. Editors asked for shorter paragraphs and more concrete dates. ",
    "Facilities noted that the third-floor meeting rooms will be repainted. The color palette "
    "was debated at length without a final choice. ",
    "A retrospective summary listed what went well, what could improve, and action items that "
    "were later postponed. Attendance was recorded in the shared calendar. ",
]


def _page(core: str, noise_blocks: int) -> str:
    noise = "".join(_NOISE_PARAS[i % len(_NOISE_PARAS)] for i in range(noise_blocks))
    return core + "\n\nBackground and unrelated sections:\n" + noise


_CORPUS = {
    "openai": [
        (
            "OpenAI - Wikipedia",
            "https://example.invalid/openai-wikipedia",
            "OpenAI was founded in December 2015 by Sam Altman, Elon Musk, Ilya Sutskever, Greg Brockman, Wojciech Zaremba, and John Schulman...",
            "OpenAI was founded in December 2015 by Sam Altman, Elon Musk, Ilya Sutskever, Greg Brockman, Wojciech Zaremba, and John Schulman.\n"
            "Current status of co-founders (as of 2024): Sam Altman is CEO of OpenAI (returned after a brief departure in November 2023). "
            "Elon Musk left the OpenAI board in 2018 and founded xAI in 2023. Ilya Sutskever, former Chief Scientist, left OpenAI in May 2024 "
            "and co-founded Safe Superintelligence Inc. Greg Brockman is President and Chairman of OpenAI. Wojciech Zaremba is Head of Language "
            "and Code Generation at OpenAI. John Schulman left OpenAI in August 2024 to join Anthropic. Early members Andrej Karpathy is now "
            "independent; Dario and Daniela Amodei left in 2021 to co-found Anthropic.",
        ),
        (
            "History of OpenAI - founding team",
            "https://example.invalid/openai-history",
            "The founding team announced the lab in December 2015...",
            "The founding team announced the lab in December 2015 with the stated goal of advancing digital intelligence in a way that benefits "
            "humanity. The initial backers pledged significant funding. Over the following years several co-founders departed: Musk in 2018, "
            "the Amodei siblings in 2021, Sutskever in May 2024, and Schulman in August 2024. Altman, Brockman and Zaremba remain at the company "
            "as of 2024, with Altman as CEO, Brockman as President, and Zaremba leading language and code generation research.",
        ),
    ],
    "sam altman": [
        (
            "Sam Altman - CEO of OpenAI",
            "https://example.invalid/sam-altman",
            "Sam Altman is the CEO of OpenAI...",
            "Sam Altman is currently the CEO of OpenAI. He briefly left the company in November 2023 but returned after employee protests. "
            "Before OpenAI he was president of Y Combinator, and he is also known for investments in energy, chip and fusion startups.",
        ),
        (
            "Sam Altman profile and career",
            "https://example.invalid/sam-altman-profile",
            "Career overview of Sam Altman...",
            "Sam Altman co-founded OpenAI in 2015 and served as co-chairman before becoming CEO. In November 2023 he was removed and then "
            "reinstated as CEO within days. As of 2024 he continues as CEO of OpenAI.",
        ),
    ],
    "elon musk": [
        (
            "Elon Musk launches xAI",
            "https://example.invalid/elon-musk-xai",
            "Elon Musk founded xAI in 2023...",
            "Elon Musk, who co-founded OpenAI in 2015, left the board in 2018 citing conflicts of interest with Tesla's AI development. "
            "In 2023 he founded xAI, an AI company focused on understanding the universe. He is also CEO of Tesla and SpaceX and owner of X.",
        ),
    ],
    "ilya sutskever": [
        (
            "Ilya Sutskever launches Safe Superintelligence",
            "https://example.invalid/ilya-sutskever",
            "Ilya Sutskever left OpenAI to start SSI...",
            "Ilya Sutskever, former Chief Scientist at OpenAI, left the company in May 2024 after nearly a decade. He co-founded Safe "
            "Superintelligence Inc. (SSI) with Daniel Gross and Daniel Levy, focusing on building safe AGI.",
        ),
    ],
    "greg brockman": [
        (
            "Greg Brockman - President of OpenAI",
            "https://example.invalid/greg-brockman",
            "Greg Brockman is President of OpenAI...",
            "Greg Brockman co-founded OpenAI in 2015 and serves as its President and Chairman. He previously was CTO of Stripe. As of 2024 "
            "he remains at OpenAI in the President role.",
        ),
    ],
    "wojciech zaremba": [
        (
            "Wojciech Zaremba - OpenAI research lead",
            "https://example.invalid/wojciech-zaremba",
            "Wojciech Zaremba leads language and code generation at OpenAI...",
            "Wojciech Zaremba co-founded OpenAI in 2015. As of 2024 he is Head of Language and Code Generation at OpenAI, working on "
            "codex-style models and programming assistants.",
        ),
    ],
    "john schulman": [
        (
            "John Schulman joins Anthropic",
            "https://example.invalid/john-schulman",
            "John Schulman left OpenAI for Anthropic in August 2024...",
            "John Schulman co-founded OpenAI and led the PPO and ChatGPT alignment work. He left OpenAI in August 2024 to join Anthropic, "
            "where he works on reinforcement learning from human feedback.",
        ),
    ],
}


def _synthetic_search(self, query: str, num_results: int = 5):
    q = (query or "").lower()
    pages = next((v for k, v in _CORPUS.items() if k in q), None)
    if pages is None:
        pages = [("Mock Search Result", "https://example.invalid/generic", "Generic mock result",
                  "No specific co-founder information matched this query.")]
    results = []
    for title, url, snippet, core in pages[: max(1, num_results)]:
        content = _page(core, noise_blocks=11)
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "content": content,
                "content_length": len(content),
                "fetch_success": True,
            }
        )
    return {
        "query": query,
        "num_results": len(results),
        "results": results,
        "timestamp": time.time(),
        "mock": True,
        "corpus": "task2-synthetic",
    }


def _synthetic_fetch(self, url: str):
    for pages in _CORPUS.values():
        for title, page_url, snippet, core in pages:
            if page_url == url:
                content = _page(core, noise_blocks=11)
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "content_length": len(content),
                    "fetch_success": True,
                    "timestamp": time.time(),
                }
    return {
        "url": url,
        "title": "Error",
        "content": f"Failed to fetch webpage: unknown synthetic url {url}",
        "content_length": 0,
        "success": False,
        "error": "unknown synthetic url",
        "timestamp": time.time(),
    }


web_tools.WebTools.search_web = _synthetic_search
web_tools.WebTools.fetch_webpage = _synthetic_fetch

# --- 运行课程 StrategyRunner ----------------------------------------------------
runner_mod = load("run_all_strategies", "chapter2/context-compression/run_all_strategies.py")
print("Output:", OUT, flush=True)
print("model:", MODEL, "| window:", WINDOW, "| strategies: 6", flush=True)

runner = runner_mod.StrategyRunner(log_dir=str(OUT))
runner.run_all_strategies(list(runner_mod.ALL_STRATEGIES))

results = json.loads(Path(runner.json_file).read_text())

names = ["Altman", "Musk", "Sutskever", "Brockman", "Zaremba", "Schulman"]
affiliations = {"Altman": ["CEO"], "Musk": ["xAI"], "Sutskever": ["Superintelligence", "SSI"],
                "Brockman": ["President"], "Zaremba": ["OpenAI"], "Schulman": ["Anthropic"]}
for r in results["results"]:
    answer = r.get("final_answer") or ""
    r["learning_checks"] = {
        "names_present": {n: n in answer for n in names},
        "affiliation_keywords": {k: any(w in answer for w in v) for k, v in affiliations.items()},
        "all_names": all(n in answer for n in names),
    }
data["strategy_results"] = results
data["n_calls"] = len(data["calls"])
data["completed"] = True
save()
(OUT / "evidence.sha256").write_text(
    hashlib.sha256((OUT / "evidence.json").read_bytes()).hexdigest() + "  evidence.json\n"
)
print("\n六策略结果（DeepSeek 学习版，16K 窗口）", flush=True)
for r in results["results"]:
    m = r.get("metrics", {})
    print(
        f"  {r['strategy']:<40} success={r['success']} overflow={m.get('context_overflows')} "
        f"tokens={m.get('total_tokens')} ratio={m.get('compression_ratio')} names={r['learning_checks']['all_names']}",
        flush=True,
    )
print("DONE", data["n_calls"], "model calls", flush=True)
