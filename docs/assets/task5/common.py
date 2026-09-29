"""Learning-only recording adapter. Never records authentication headers."""

import copy, hashlib, json, os, subprocess, time
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MODEL = os.getenv("TASK5_MODEL", "deepseek-flash")
CLIENT = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    timeout=90,
    max_retries=1,
)


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n")


class Recorder:
    def __init__(self, name):
        self.out = (
            ROOT
            / "learning/task5/runs"
            / name
            / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        )
        self.out.mkdir(parents=True)
        self.calls = []

    def create(self, label, **kw):
        kw.update(model=MODEL, extra_body={"thinking": {"type": "disabled"}})
        kw.setdefault("max_tokens", 2200)
        kw.setdefault("temperature", 0)
        snapshot = copy.deepcopy(kw)  # freeze before course loop appends more messages
        start = time.monotonic()
        response = CLIENT.chat.completions.create(**kw)
        self.calls.append(
            {
                "label": label,
                "request": snapshot,
                "response": response.model_dump(mode="json"),
                "seconds": round(time.monotonic() - start, 3),
            }
        )
        write(self.out / "calls.json", self.calls)
        return response

    def finish(self, data, files):
        data.update(
            model_requested=MODEL,
            course_commit=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            source_sha256={
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
            },
            calls=len(self.calls),
            tokens=sum(
                (c["response"].get("usage") or {}).get("total_tokens", 0) for c in self.calls
            ),
            scope="learning variant; not full canonical campaign",
        )
        write(self.out / "evidence.json", data)
        (self.out / "evidence.sha256").write_text(
            hashlib.sha256((self.out / "evidence.json").read_bytes()).hexdigest()
            + "  evidence.json\n"
        )
        print("RESULT", self.out, flush=True)
