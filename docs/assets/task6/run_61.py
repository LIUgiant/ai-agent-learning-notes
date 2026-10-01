"""6-1 learning harness: reuse the course loop, replace only the producer/handler.
Python standard library only. No LLM, Redis, HTTP, or messaging channel.
"""
import argparse
import hashlib
import json
import logging
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course', type=Path, required=True)
    parser.add_argument('--hold', type=float, default=0.15)
    args = parser.parse_args()
    if not 0 <= args.hold <= 1:
        parser.error('--hold must be between 0 and 1 second')
    source = args.course.resolve() / 'chapter6/agent-with-event-trigger'
    sys.path.insert(0, str(source))
    from event_loop_demo import EventLoop, TriggerSource
    from event_types import Event, EventType
    logging.getLogger().setLevel(logging.ERROR)
    output = Path(__file__).resolve().parent / 'runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True)
    report = {'kind': 'offline mechanism experiment', 'hold_seconds': args.hold,
              'python': sys.version, 'course_root': str(args.course.resolve()),
              'course_head': subprocess.check_output(['git', '-C', str(args.course), 'rev-parse', 'HEAD'], text=True).strip(),
              'sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [source / 'event_loop_demo.py', source / 'event_types.py', Path(__file__)]},
              'cases': []}

    # Run the unmodified course CLI first, retaining both output streams.
    command = [sys.executable, str(source / 'event_loop_demo.py'), '--mock',
               '--trigger', 'timer', '--delay', '0.1', '--duration', '0.3']
    timer = subprocess.run(command, capture_output=True, text=True, timeout=10)
    (output / 'course-timer.log').write_text(timer.stdout + timer.stderr)
    report['timer'] = {'command': command, 'returncode': timer.returncode,
                       'passed': timer.returncode == 0 and '共处理 1 个事件' in timer.stdout}

    for case in ['burst', 'slow', 'failure', 'duplicate']:
        start = time.monotonic()
        trace, deliveries, errors = [], [], []
        lock = threading.Lock()
        active = threading.Event()
        release = threading.Event()

        def record(stage, event, **extra):
            with lock:
                trace.append({'seq': len(trace) + 1, 'ms': round((time.monotonic() - start) * 1000, 3),
                              'stage': stage, 'id': event.event_id, **extra})

        class RecordedQueue(queue.Queue):
            # These hooks run under Queue's mutex. The consumer cannot get an
            # item between insertion and its enqueue trace record.
            def _put(self, event):
                super()._put(event)
                record('enqueue', event, pending=[e.event_id for e in self.queue])

            def _get(self):
                event = super()._get()
                record('dequeue', event, pending=[e.event_id for e in self.queue])
                return event

        def dispatch(event):
            record('start', event, model_input=event.to_user_message())
            if event.event_id == 'A' and case == 'slow':
                active.set()
                if not release.wait(2):
                    raise TimeoutError('producer did not release A')
            if event.event_id == 'B' and case == 'failure':
                record('error', event, reason='injected handler failure')
                raise ValueError('intentional B failure')
            deliveries.append(event.event_id)
            record('local_delivery', event)  # Local receipt, not a real send.

        loop = EventLoop(dispatch)
        loop.event_queue = RecordedQueue()
        emitter = TriggerSource('synthetic-parent', loop.event_queue)
        messages = [Event(EventType.IM_MESSAGE, '查一下课程', {'sender': 'demo-parent'}, event_id='A'),
                    Event(EventType.IM_MESSAGE, '补充：只看周末', {'sender': 'demo-parent'}, event_id='B'),
                    Event(EventType.SYSTEM_ALERT, '后台查询完成：演示数据', {'alert_type': 'query_done'}, event_id='C')]

        def produce():
            try:
                emitter.emit(messages[0])
                if case == 'slow' and not active.wait(2):
                    raise TimeoutError('A never started')
                emitter.emit(messages[1])
                if case == 'duplicate':
                    emitter.emit(messages[1])
                emitter.emit(messages[2])
                if case == 'slow':
                    time.sleep(args.hold)  # Teaching delay, not model latency.
            except Exception as exc:
                errors.append(str(exc))
            finally:
                release.set()

        producer = threading.Thread(target=produce, daemon=True)
        producer.start()
        loop.run(duration=0.4 + args.hold)
        producer.join(timeout=3)
        ids = lambda stage: [r['id'] for r in trace if r['stage'] == stage]
        expected = ['A', 'B', 'B', 'C'] if case == 'duplicate' else ['A', 'B', 'C']
        checks = {'all_input_consumed_in_order': ids('dequeue') == expected,
                  'local_receipts_match': deliveries == (['A', 'C'] if case == 'failure' else expected),
                  'processed_counts_attempts': loop.processed == len(expected),
                  'producer_finished': not producer.is_alive() and not errors,
                  'expected_errors_only': ids('error') == (['B'] if case == 'failure' else [])}
        if case == 'slow':
            pos = lambda stage, eid: next(r['seq'] for r in trace if r['stage'] == stage and r['id'] == eid)
            checks['B_arrives_while_A_active'] = pos('start', 'A') < pos('enqueue', 'B') < pos('local_delivery', 'A')
            checks['B_waits_for_A'] = pos('local_delivery', 'A') < pos('start', 'B')
        (output / f'{case}.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
        report['cases'].append({'case': case, 'checks': checks, 'deliveries': deliveries,
                                'processed': loop.processed, 'errors': errors})
    report['passed'] = report['timer']['passed'] and all(all(c['checks'].values()) for c in report['cases'])
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': report['passed'], 'output': str(output), 'cases': report['cases']}, ensure_ascii=False, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
