"""5-5: eight frozen cases, original course two-arm loop + independent guard probes."""

import sys
from dataclasses import asdict
from common import ROOT, MODEL, Recorder, write

COURSE = ROOT / "chapter5/small-model-codified-rules"
sys.path.insert(0, str(COURSE))
import agent, airline_env, demo, tasks

rec = Recorder("rules")
agent._make_client = lambda model, provider: (None, MODEL, "deepseek-learning")
agent._chat_with_retry = lambda client, messages, tools, model=None: rec.create(
    "rules", messages=messages, tools=tools
)
selected = [
    tasks.TASKS[i] for i in [0, 4, 8, 9, 11, 19, 20, 40]
]  # cover <=24h, >24h, exceptions, flexible/business
rows = []
for task in selected:
    for mode in ["control", "codified"]:
        env = airline_env.AirlineEnv(task.reservation)
        out = agent.run_agent(env, task.user_message, mode, model=MODEL, provider="openai")
        row = {
            "mode": mode,
            "task_id": task.task_id,
            "input": task.user_message,
            "initial": asdict(task.reservation),
            "final": asdict(env.res),
            "verdict": demo.judge(task, env, out["final_text"]),
            "run": out,
        }
        rows.append(row)
        write(rec.out / "rows.json", rows)
        print(task.task_id, mode, row["verdict"]["success"], flush=True)
# Explicit injected wrong expectations: independent of model errors occurring naturally.
probes = []
for task in selected:
    env = airline_env.AirlineEnv(task.reservation)
    response = env.cancel_reservation_codified(
        env.res.reservation_id,
        expected_refundable=not task.expect_refundable,
        expected_reason="airline_caused",
    )
    probes.append(
        {
            "task_id": task.task_id,
            "truth": task.expect_refundable,
            "injected_expected": not task.expect_refundable,
            "response": response,
            "refund": env.res.refund_issued,
            "matches_policy": bool(env.res.refund_issued) == task.expect_refundable,
        }
    )
rec.finish(
    {
        "rows": rows,
        "guard_probes": probes,
        "summary": {
            m: demo.summarize([r["verdict"] for r in rows if r["mode"] == m])
            for m in ["control", "codified"]
        },
        "completed": len(rows) == 16,
    },
    [COURSE / f for f in ["agent.py", "airline_env.py", "demo.py", "tasks.py"]],
)
