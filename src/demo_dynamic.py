"""Reproducible fixture for adaptive decisions. --live uses the configured real LLM."""
import argparse
from app import run_react_agent, save_waterfall_trace, load_test_cases
from providers import MockOfflineProvider, get_llm_provider
from mcp_server import MCPChargingServer
from tools import reset_demo_state, MOCK_STATIONS


class RaceServer(MCPChargingServer):
    """Simulate another car taking the last available ports between query and booking."""
    triggered = False

    def call_tool(self, name, arguments):
        if name == 'reserve_charging_slot' and arguments.get('station_id') == 'VF-OP01' and not self.triggered:
            self.triggered = True
            MOCK_STATIONS['VF-OP01']['connectors']['CCS2']['available_ports'] = 0
        return super().call_tool(name, arguments)


def run_scenario(provider, scenario, max_retries=3):
    reset_demo_state()
    if scenario == 'alternate':
        MOCK_STATIONS['VF-OP01']['connectors']['CCS2']['available_ports'] = 0
    server = RaceServer() if scenario == 'race' else MCPChargingServer()
    query = next(tc['question'] for tc in load_test_cases() if tc['id'] == 'TC04')
    logs = run_react_agent(query, provider, server, max_retries=max_retries)
    calls = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
    bookings = [e['observation'].get('booking', {}) for e in calls if e['tool_name'] == 'reserve_charging_slot' and e['observation']['status'] == 'SUCCESS']
    passed = bool(bookings) and bookings[-1].get('station_id') == 'VF-OP02' and logs[-1]['action_type'] == 'FINAL_ANSWER'
    if scenario == 'race':
        passed = passed and any(e['tool_name'] == 'reserve_charging_slot' and e['observation']['status'] == 'UNAVAILABLE' for e in calls)
    for event in logs:
        event['scenario'] = scenario
    return logs, passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', choices=['alternate', 'race'], default='alternate')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--no-retry', action='store_true')
    args = parser.parse_args()
    provider = get_llm_provider() if args.live else MockOfflineProvider()
    if args.live and isinstance(provider, MockOfflineProvider):
        parser.error('--live requires Gemini or OpenAI, not Mock')
    logs, passed = run_scenario(provider, args.scenario, max_retries=0 if args.no_retry else 3)
    save_waterfall_trace(logs, f"trace_{args.scenario}_{'native_api' if args.live else 'offline'}.json")
    print(f"{args.scenario}: {'PASS' if passed else 'FAIL'} ({logs[0]['source']})")
    raise SystemExit(0 if passed else 1)
