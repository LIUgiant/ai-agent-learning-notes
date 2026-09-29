"""Course CodingAgent.run on a disposable two-file fixture, Read/Edit/RunTests only.
Model edits policy.py; fixed test file and evaluator are outside its write scope.
Not a production sandbox. No course files or business code are modified.
"""

import json, os, sys, subprocess, hashlib
from pathlib import Path
from types import SimpleNamespace
from common import ROOT, CLIENT, MODEL, Recorder, write

COURSE = ROOT / "chapter5/coding-agent"
sys.path.insert(0, str(COURSE))
from agent import CodingAgent
from tools.base import ToolResult

rec = Recorder("coding")
workspace = rec.out / "workspace"
workspace.mkdir()
(workspace / "policy.py").write_text(
    "def refundable(hours, flexible=False):\n    return flexible or hours < 24\n"
)
(workspace / "test_policy.py").write_text(
    "import unittest\nfrom policy import refundable\nclass PolicyTests(unittest.TestCase):\n    def test_inside(self): self.assertTrue(refundable(5))\n    def test_boundary(self): self.assertTrue(refundable(24))\n    def test_outside(self): self.assertFalse(refundable(24.1))\n    def test_flexible(self): self.assertTrue(refundable(72, True))\n"
)


def test():
    r = subprocess.run(
        [sys.executable, "-m", "unittest", "-v"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=15,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
    )
    return {"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr}


before = test()
original = (workspace / "policy.py").read_text()
test_hash = hashlib.sha256((workspace / "test_policy.py").read_bytes()).hexdigest()
os.chdir(workspace)
a = CodingAgent(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    model=MODEL,
    base_url=str(CLIENT.base_url),
    provider="openai",
)
a.tools = [t for t in a.tools if t["name"] in ["Read", "Edit"]]
a.tools.append(
    {
        "name": "RunTests",
        "description": "运行固定 unittest 测试；无参数。",
        "input_schema": {"type": "object", "properties": {}},
    }
)
a.system_prompt = "你在一个教学工作区修复一个边界错误。先读取源码和测试，再运行测试，最小修改 policy.py，运行测试验证后汇报。只使用提供的三个工具；不能修改测试。工具返回是事实，不能声称未做过的验证。"
registry = a.tool_registry


class Restricted:
    def get_tool(self, name, state):
        class Tool:
            def execute(self, params):
                if name == "RunTests":
                    return ToolResult(success=True, data=test())
                path = Path(params.get("file_path", "")).resolve()
                allowed = (
                    [workspace / "policy.py", workspace / "test_policy.py"]
                    if name == "Read"
                    else [workspace / "policy.py"]
                )
                if name not in ["Read", "Edit"] or path not in allowed:
                    return ToolResult(success=False, data={"error": "outside learning allowlist"})
                return registry.get_tool(name, state).execute(params)

        return Tool()


a.tool_registry = Restricted()


def create(**kw):
    kw.update(
        model=MODEL,
        max_tokens=1500,
        temperature=0,
        extra_body={"thinking": {"type": "disabled"}},
        stream_options={"include_usage": True},
    )
    chunks = []
    s = CLIENT.chat.completions.create(**kw)
    try:
        for ch in s:
            chunks.append(ch.model_dump(mode="json"))
            yield ch
    finally:
        s.close()
        rec.calls.append(
            {
                "request": kw,
                "chunks": chunks,
                "response": {
                    "usage": next((x["usage"] for x in reversed(chunks) if x.get("usage")), {})
                },
            }
        )
        write(rec.out / "calls.json", rec.calls)


a.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
events = []
for event in a.run(
    f"请修复 {workspace}/policy.py：24 小时内含正好 24 小时可退，超过 24 小时仅 flexible=True 可退。测试在 {workspace}/test_policy.py。",
    max_iterations=8,
):
    events.append(event)
    write(rec.out / "events.json", events)
    print(event["type"], flush=True)
after = test()
final = (workspace / "policy.py").read_text()
rec.finish(
    {
        "before": before,
        "after": after,
        "original": original,
        "final": final,
        "tests_unchanged": test_hash
        == hashlib.sha256((workspace / "test_policy.py").read_bytes()).hexdigest(),
        "events": events,
        "messages": a.messages,
        "completed": before["returncode"] != 0
        and after["returncode"] == 0
        and test_hash == hashlib.sha256((workspace / "test_policy.py").read_bytes()).hexdigest(),
    },
    [
        COURSE / f
        for f in [
            "agent.py",
            "tool_registry.py",
            "system_state.py",
            "tools/read_tool.py",
            "tools/edit_tool.py",
            "tools/base.py",
        ]
    ],
)
