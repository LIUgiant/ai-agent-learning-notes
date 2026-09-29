"""Targeted follow-up after observed exact-24h failure; not a new accuracy benchmark."""

import sys
from common import ROOT, MODEL, Recorder

COURSE = ROOT / "chapter5/small-model-codified-rules"
sys.path.insert(0, str(COURSE))
import agent, airline_env, demo, tasks

rec = Recorder("boundary")
agent._make_client = lambda model, provider: (None, MODEL, "deepseek-learning")
agent._chat_with_retry = lambda client, messages, tools, model=None: rec.create(
    "boundary", messages=messages, tools=tools
)
clarification = "\n边界澄清：24 小时内包含正好 24.0 小时，即 hours_since_booking <= 24；24.1 小时不在窗口内。请以此规则执行。"
agent.CONTROL_SYSTEM += clarification
agent.CODIFIED_SYSTEM += clarification
rows = []
for mode in ["control", "codified"]:
    task = tasks.TASKS[4]
    env = airline_env.AirlineEnv(task.reservation)
    out = agent.run_agent(env, task.user_message, mode, model=MODEL, provider="openai")
    rows.append(
        {
            "mode": mode,
            "task_id": task.task_id,
            "verdict": demo.judge(task, env, out["final_text"]),
            "run": out,
        }
    )
rec.finish(
    {
        "clarification": clarification,
        "rows": rows,
        "completed": True,
        "selection": "post-hoc exact-24h failure follow-up, one case x two arms",
    },
    [COURSE / "agent.py", COURSE / "airline_env.py"],
)
