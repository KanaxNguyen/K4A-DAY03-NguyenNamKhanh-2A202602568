"""
🚀 CORE AGENT APPLICATION (DAY 03: CHATBOT VS REACT AGENT)
Thực thi so sánh giữa Chatbot Baseline (Cấp 2) và ReAct Agent kết nối MCP Server (Cấp 3).
"""

import json
import os
import argparse
from pathlib import Path
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from mcp_server import MCPChargingServer
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS
)
from providers import get_llm_provider, call_with_retry, MockOfflineProvider
from tools import reset_demo_state

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]


def load_test_cases():
    path = ROOT / 'config' / 'test_cases.json'
    if not path.exists():
        path = ROOT / 'config' / 'test_cases.example.json'
    return json.loads(path.read_text(encoding='utf-8'))


def save_waterfall_trace(trace_data: list, filename='trace_native_api.json'):
    # Only live-suite evidence lives under docs; transient runs are separate.
    folder = ROOT / ('docs' if filename in {'trace_native_api.json', 'test_results_native_api.json'} else 'artifacts')
    folder.mkdir(exist_ok=True)
    path = folder / filename
    path.write_text(json.dumps(trace_data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'[TRACE] {len(trace_data)} events: {path}')


def run_baseline_chatbot(user_query: str, provider):
    """Chạy Chatbot gốc (Cấp 2) không có công cụ gọi Tool"""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot phản hồi:\n{response}")


def run_react_agent(user_query: str, provider, mcp_server: MCPChargingServer, history=None, max_retries=3) -> list:
    """Native conversation loop with auditable, separately timed events."""
    import uuid
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    history = history if history is not None else []
    history.append({'role': 'user', 'content': user_query})
    logs = []
    run_id = uuid.uuid4().hex
    origin = 'mock' if isinstance(provider, MockOfflineProvider) else (
        'live_api' if provider.__class__.__name__ in ('GeminiProvider', 'OpenAIProvider', 'OpenRouterProvider') else 'test_double')
    started = time.perf_counter()
    step = 0
    def record(kind, **fields):
        event = dict(run_id=run_id, event_id=len(logs) + 1, step=step, query=user_query,
                     timestamp=datetime.now(ZoneInfo('UTC')).isoformat(),
                     elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                     action_type=kind, source=origin, provider=provider.__class__.__name__,
                     model=provider.model_name, llm_latency_ms=0, tool_latency_ms=0,
                     retry_wait_ms=0, retry_count=0)
        event.update(fields)
        logs.append(event)
        return event

    system = REACT_AGENT_SYSTEM_PROMPT + '\nThời gian Việt Nam: ' + datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat()
    for step in range(1, MAX_ITERATIONS + 1):
        print(f"--- ReAct step {step}/{MAX_ITERATIONS} ---")
        try:
            result = call_with_retry(provider, history, mcp_server.list_tools(), system,
                                     on_retry=lambda data: record('RETRY', **data), max_retries=max_retries)
        except Exception as error:
            metrics = dict(getattr(error, 'metrics', {}))
            metrics['total_retry_wait_ms'] = metrics.pop('retry_wait_ms', 0)
            record('ERROR', status='API_ERROR', output=str(error), **metrics)
            print(f'[ERROR] {error}')
            break
        record('LLM_RESPONSE', llm_latency_ms=result['llm_latency_ms'],
               retry_count=result['retry_count'],
               response_type=result.get('type'))
        if result.get('type') == 'text':
            output = result.get('content', '').strip()
            if not output:
                record('ERROR', status='EMPTY_RESPONSE', output='LLM trả về nội dung rỗng.')
                break
            history.append(result.get('native_message') or {'role': 'assistant', 'content': output})
            record('FINAL_ANSWER', output=output, status='COMPLETED')
            print('[Final Answer] ' + output)
            break
        if result.get('type') != 'tool_call':
            record('ERROR', status='INVALID_RESPONSE', output='Kiểu phản hồi LLM không hợp lệ.')
            break
        calls = result.get('calls')
        if calls is None:  # Legacy Mock fixture only.
            calls = [dict(id=uuid.uuid4().hex, tool_name=result.get('tool_name'), arguments=result.get('arguments'))]
        if not calls:
            record('ERROR', status='EMPTY_TOOL_CALL', output='Không có lời gọi công cụ.')
            break
        # Preserve every provider call and return one result per call, including invalid calls.
        history.append(result.get('native_message') or {
            'role': 'assistant', 'content': result.get('decision_summary', ''),
            'tool_calls': [{'id': c['id'], 'type': 'function',
                            'function': {'name': c['tool_name'], 'arguments': json.dumps(c['arguments'])}} for c in calls]})
        prior = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
        for call in calls:
            call_id, name, arguments = call['id'], call['tool_name'], call['arguments']
            basis = {'previous_observation_event_ids': [e['event_id'] for e in prior[-2:]]}
            if name == 'reserve_charging_slot' and isinstance(arguments, dict):
                available = [e for e in prior if e['tool_name'] == 'check_charging_availability']
                if available:
                    stations = available[-1]['observation'].get('stations', [])
                    basis['selected_station'] = next((s for s in stations if s['station_id'] == arguments.get('station_id')), None)
            summary = result.get('decision_summary', '')
            record('DECISION', call_id=call_id, tool_name=name, decision_summary=summary or
                   'Model không trả lý do dạng văn bản; xem decision_basis để đối chiếu dữ liệu.',
                   rationale_source=('mock_fixture' if origin == 'mock' else 'model_visible_text') if summary else 'not_provided',
                   decision_basis=basis)
            record('ACTION', call_id=call_id, tool_name=name, arguments=arguments)
            tool_start = time.perf_counter()
            try:
                if not isinstance(arguments, dict):
                    observation = {'status': 'INVALID_ARGUMENTS', 'message': 'Arguments phải là JSON object.'}
                else:
                    observation = mcp_server.call_tool(name, arguments).get('result')
                    if not isinstance(observation, dict) or not observation.get('status'):
                        observation = {'status': 'INVALID_TOOL_RESPONSE', 'message': 'Tool không trả observation hợp lệ.'}
            except Exception:
                observation = {'status': 'TOOL_ERROR', 'message': 'Công cụ thất bại; không xác nhận đặt chỗ thành công.'}
            tool_ms = round((time.perf_counter() - tool_start) * 1000, 3)
            record('TOOL_EXECUTION', call_id=call_id, tool_name=name, arguments=arguments,
                   observation=observation, tool_latency_ms=tool_ms, status=observation['status'])
            history.append({'role': 'tool', 'name': name, 'tool_call_id': call_id,
                            'native_call_id': call.get('native_call_id'), 'observation': observation})
            print(f"[Observation] {name}: {json.dumps(observation, ensure_ascii=False)}")
    else:
        record('ERROR', status='MAX_ITERATIONS', output='Đạt giới hạn vòng lặp, chưa hoàn tất yêu cầu.')
    return logs


def evaluate_case(tc, logs):
    calls = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
    names = [e['tool_name'] for e in calls]
    if not logs or logs[-1]['action_type'] != 'FINAL_ANSWER' or not logs[-1].get('output'):
        return False
    if any(e['action_type'] == 'ERROR' for e in logs):
        return False
    if tc['id'] == 'TC01':
        return not calls
    if tc['id'] == 'TC05':
        return names == ['check_charging_availability'] and calls[0]['observation'].get('status') == 'NOT_FOUND'
    if any(e['observation'].get('status') != 'SUCCESS' for e in calls):
        return False
    if tc['id'] == 'TC02':
        return names == ['check_charging_availability'] and calls[0]['arguments'].get('connector_type', '').upper() == 'CCS2'
    if tc['id'] == 'TC04' and names != ['check_charging_availability', 'reserve_charging_slot']:
        return False
    if tc['id'] == 'TC03' and names not in [['reserve_charging_slot'], ['check_charging_availability', 'reserve_charging_slot']]:
        return False
    booking = calls[-1]['observation'].get('booking', {}) if calls else {}
    return all(booking.get(k) == v for k, v in {'vehicle_id': '30H-123.45', 'start_time': '14:00 15/09/2026', 'duration_minutes': 60, 'connector_type': 'CCS2'}.items()) and bool(booking.get('booking_id'))


def main():
    parser = argparse.ArgumentParser(description='Trợ lý trạm sạc — demo ReAct/native tool calling')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--all', action='store_true', help='Chạy và chấm 5 test độc lập')
    mode.add_argument('--interactive', action='store_true', help='Chat có lịch sử')
    mode.add_argument('--baseline', metavar='QUESTION', help='So sánh với chatbot không có tool')
    parser.add_argument('--no-retry', action='store_true', help='Không chờ thử lại khi API lỗi')
    args = parser.parse_args()
    provider = get_llm_provider()
    server = MCPChargingServer()
    limit = 0 if args.no_retry else 3
    print(f'[PROVIDER] {provider.__class__.__name__} | {provider.model_name}')
    tests = load_test_cases()
    if args.baseline:
        run_baseline_chatbot(args.baseline, provider)
        return 0
    if args.interactive:
        history, session = [], []
        print('Nhập yêu cầu; exit để thoát, /reset để xóa lịch sử (booking vẫn giữ trong phiên).')
        while True:
            try:
                query = input('👤 Người dùng hỏi: ').strip()
                if query.lower() in ('exit', 'quit'):
                    break
                if not query:
                    continue
                if query == '/reset':
                    history.clear()
                    continue
                session.extend(run_react_agent(query, provider, server, history, max_retries=limit))
                save_waterfall_trace(session, 'trace_interactive.json')
            except (KeyboardInterrupt, EOFError):
                print('Đã dừng chat.')
                break
        return 0
    if args.all:
        traces, results = [], []
        for tc in tests:
            reset_demo_state()
            logs = run_react_agent(tc['question'], provider, server, max_retries=limit)
            for event in logs:
                event['test_id'] = tc['id']
            passed = evaluate_case(tc, logs)
            results.append({'test_id': tc['id'], 'passed': passed, 'source': logs[0]['source']})
            traces.extend(logs)
            print(f"[{tc['id']}] {'PASS' if passed else 'FAIL'}")
        offline = isinstance(provider, MockOfflineProvider)
        save_waterfall_trace(traces, 'trace_offline.json' if offline else 'trace_native_api.json')
        save_waterfall_trace(results, 'test_results_offline.json' if offline else 'test_results_native_api.json')
        print(f"PASS: {sum(r['passed'] for r in results)}/{len(tests)}")
        return 0 if results and all(r['passed'] for r in results) else 1
    logs = run_react_agent(tests[1]['question'], provider, server, max_retries=limit)
    save_waterfall_trace(logs, 'trace_demo.json')
    return 1 if logs[-1]['action_type'] == 'ERROR' else 0


if __name__ == '__main__':
    raise SystemExit(main())
