"""5-11: real loopback HTTP + live model diagnosis/tests. No external Issue creation.
Uses course HTTP orchestration, validators and evaluator. Corrected implementation is
pre-existing course code, NOT a patch produced by the diagnosis model.
"""

import json, sys, subprocess, time
from common import ROOT, Recorder, write

COURSE = ROOT / "chapter5/log-diagnosis"
sys.path.insert(0, str(COURSE))
import campaign as c

rec = Recorder("diagnosis")
port = c._free_port()
base = f"http://127.0.0.1:{port}"
log = (rec.out / "service.log").open("w")
proc = subprocess.Popen(
    [sys.executable, str(COURSE / "http_service.py"), "--port", str(port)], stdout=log, stderr=log
)
try:
    for _ in range(50):
        if c._http_call(base, "GET", "/health", timeout=0.2)["status"] == "success":
            break
        time.sleep(0.05)
    else:
        raise RuntimeError("local service not healthy")
    source_tasks = {
        "HTTP-RF-001": {"intent": "refund", "order_id": "ORD-58-A"},
        "HTTP-INV-001": {"intent": "order_status", "order_id": "ORD-58-B", "sku": "SKU-42"},
    }
    sources = {
        tid: c._trajectory(base, t, tid, inject_regressions=True) for tid, t in source_tasks.items()
    }
    write(rec.out / "sources.json", sources)
    prompts = {
        "diagnosis": f"{c.ARCHITECTURE}\n{c.PRD}\nObserved logs: {json.dumps(sources)}\nReturn JSON with problems list. Each problem has title,priority,module,description,suggestion,prd_ref,trajectory_ids,focus_turns,suggested_assignee. Only diagnose evidenced R1 and R2 violations. Use source IDs HTTP-RF-001 and HTTP-INV-001 (not ::buggy IDs), and exact observed turn indexes.",
    }
    feedback = ""
    problems = None
    for attempt in range(3):
        r = rec.create(
            f"diagnosis-{attempt}",
            messages=[
                {
                    "role": "system",
                    "content": "Diagnose only evidenced defects. Return a JSON object.",
                },
                {
                    "role": "user",
                    "content": prompts["diagnosis"] + "\nValidation feedback: " + feedback,
                },
            ],
            response_format={"type": "json_object"},
        )
        try:
            problems = c._validate_diagnosis(json.loads(r.choices[0].message.content), sources)
            break
        except (ValueError, KeyError) as e:
            feedback = str(e)
    if problems is None:
        raise RuntimeError("diagnosis invalid: " + feedback)
    prompt = f"""{c.PRD}\nProblems: {json.dumps(problems)}\nSources: {json.dumps(sources)}
Return JSON test_cases list. Each test has test_id,trajectory_id,focus_turn,description,assertion.
Allowed assertions: {{"type":"step_present","params":{{"tool":"verify_refund_eligibility"}}}}, {{"type":"latency_under","params":{{"tool":"check_stock","threshold_ms":250}}}}, {{"type":"final_status_is","params":{{"value":"success"}}}}.
Cover both R1 and R2. Use exact source IDs without ::buggy and observed focus_turn. Express correct fixed behavior; every test must fail on buggy and pass on fixed. Do not invent tools."""
    attempts = []
    feedback = ""
    passed = False
    for attempt in range(3):
        r = rec.create(
            f"tests-{attempt}",
            messages=[
                {"role": "system", "content": "Generate executable regression assertions as JSON."},
                {"role": "user", "content": prompt + "\nPrevious feedback: " + feedback},
            ],
            response_format={"type": "json_object"},
        )
        tests_payload = json.loads(r.choices[0].message.content)
        try:
            tests = c._validate_tests(tests_payload, sources)
            records = []
            for test in tests:
                tid = test["trajectory_id"]
                task = sources[tid]["task_input"]
                pair = {}
                for mode in ["buggy", "fixed"]:
                    trace = c._trajectory(base, task, tid, inject_regressions=mode == "buggy")
                    ok, detail = c._evaluate(test["assertion"], trace)
                    pair[mode] = {"passed": ok, "detail": detail, "trajectory": trace}
                records.append({"test": test, **pair})
            passed = all(not v["buggy"]["passed"] and v["fixed"]["passed"] for v in records)
            feedback = json.dumps(
                [
                    {
                        "test": v["test"],
                        "buggy": v["buggy"]["detail"],
                        "fixed": v["fixed"]["detail"],
                    }
                    for v in records
                ]
            )
            attempts.append({"attempt": attempt, "passed": passed, "records": records})
            write(rec.out / "attempts.json", attempts)
            if passed:
                break
        except (ValueError, KeyError) as e:
            feedback = str(e)
            attempts.append({"attempt": attempt, "error": feedback, "payload": tests_payload})
    # Verifier-strength probe: presence alone doesn't establish ordering.
    malformed = {"turns": [{"tool": "process_refund"}, {"tool": "verify_refund_eligibility"}]}
    weak, _ = c._evaluate(
        {"type": "step_present", "params": {"tool": "verify_refund_eligibility"}}, malformed
    )
    rec.finish(
        {
            "sources": sources,
            "problems": problems,
            "test_attempts": attempts,
            "completed": passed,
            "external_issue_created": False,
            "fix_author": "pre-existing course orchestrator",
            "verifier_probe": {
                "refund_before_check": True,
                "course_step_present_passes": weak,
                "meaning": "presence is weaker than ordering",
            },
        },
        [COURSE / f for f in ["campaign.py", "http_service.py"]],
    )
finally:
    proc.terminate()
    proc.wait(timeout=5)
    log.close()
