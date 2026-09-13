"""Native wire-contract and failure-path tests using SDK models, without network."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from app import run_react_agent
from mcp_server import MCPChargingServer
from native_transport import gemini_contents, gemini_tool_declarations, openai_messages
from providers import GeminiProvider, OpenAIProvider, MockOfflineProvider, call_with_retry
from tools import MOCK_STATIONS, RESERVATIONS, reset_demo_state, TOOLS_SCHEMA


class NativeTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()

    def run_agent(self, provider, server=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return run_react_agent('Tra cứu', provider, server or MCPChargingServer())

    def test_gemini_preserves_signature_and_native_response(self):
        from google.genai import types
        content = types.Content(role='model', parts=[types.Part(
            function_call=types.FunctionCall(name='check_charging_availability', args={'connector_type': 'CCS2'}, id='call1'),
            thought_signature=b'opaque-signature')])
        provider = GeminiProvider(api_key='fixture')
        provider._client = NS(models=Mock())
        provider._client.models.generate_content.return_value = NS(candidates=[NS(content=content)])
        first = provider.generate_with_tools('hi', TOOLS_SCHEMA)
        self.assertIs(first['native_message']['gemini_content'], content)
        messages = [{'role': 'user', 'content': 'hi'}, first['native_message'],
                    {'role': 'tool', 'name': 'check_charging_availability', 'native_call_id': 'call1',
                     'tool_call_id': 'call1', 'observation': {'status': 'SUCCESS'}}]
        provider.generate_with_tools(messages, TOOLS_SCHEMA)
        sent = provider._client.models.generate_content.call_args.kwargs['contents']
        self.assertEqual(sent[1].parts[0].thought_signature, b'opaque-signature')
        self.assertEqual(sent[2].parts[0].function_response.id, 'call1')
        self.assertEqual(sent[2].parts[0].function_response.response, {'status': 'SUCCESS'})

    def test_openai_tool_call_id_roundtrip(self):
        provider = OpenAIProvider(api_key='fixture')
        create = Mock(return_value=NS(choices=[NS(message=NS(content=None, tool_calls=[
            NS(id='call-17', function=NS(name='check_charging_availability', arguments='{"connector_type":"CCS2"}'))]))]))
        provider._client = NS(chat=NS(completions=NS(create=create)))
        first = provider.generate_with_tools('hi', TOOLS_SCHEMA)
        messages = [{'role': 'user', 'content': 'hi'}, first['native_message'],
                    {'role': 'tool', 'name': 'check_charging_availability', 'tool_call_id': 'call-17',
                     'observation': {'status': 'SUCCESS'}}]
        provider.generate_with_tools(messages, TOOLS_SCHEMA)
        wire = create.call_args.kwargs['messages']
        self.assertEqual(wire[-1]['role'], 'tool')
        self.assertEqual(wire[-1]['tool_call_id'], wire[-2]['tool_calls'][0]['id'])

    def test_gemini_schema_removes_only_unsupported_additional_properties(self):
        declarations = gemini_tool_declarations(TOOLS_SCHEMA)
        self.assertNotIn('additionalProperties', declarations[0]['parameters'])
        self.assertEqual(declarations[1]['parameters']['properties']['duration_minutes']['maximum'], 240)
        self.assertIn('additionalProperties', TOOLS_SCHEMA[0]['parameters'])

    def test_alternate_station_from_observation(self):
        MOCK_STATIONS['VF-OP01']['connectors']['CCS2']['available_ports'] = 0
        with contextlib.redirect_stdout(io.StringIO()):
            logs = run_react_agent('Tôi cần sạc CCS2 tại VinUni Ocean Park, hãy tìm và đặt chỗ.', MockOfflineProvider(), MCPChargingServer())
        booking = next(e for e in logs if e.get('tool_name') == 'reserve_charging_slot' and e['action_type'] == 'TOOL_EXECUTION')
        self.assertEqual(booking['arguments']['station_id'], 'VF-OP02')
        decision = next(e for e in logs if e['action_type'] == 'DECISION' and e.get('tool_name') == 'reserve_charging_slot')
        self.assertEqual(decision['decision_basis']['selected_station']['station_id'], 'VF-OP02')

    def test_multiple_calls_get_corresponding_observations(self):
        class Provider:
            model_name = 'fixture'
            turn = 0
            def generate_with_tools(self, messages, *args, **kwargs):
                self.turn += 1
                if self.turn == 1:
                    return {'type': 'tool_call', 'calls': [
                        {'id': 'a', 'tool_name': 'unknown', 'arguments': {}},
                        {'id': 'b', 'tool_name': 'check_charging_availability', 'arguments': None}]}
                results = [m for m in messages if m['role'] == 'tool']
                assert [m['tool_call_id'] for m in results] == ['a', 'b']
                assert [m['observation']['status'] for m in results] == ['UNKNOWN_TOOL', 'INVALID_ARGUMENTS']
                return {'type': 'text', 'content': 'Không đặt chỗ.'}
        logs = self.run_agent(Provider())
        self.assertEqual(logs[-1]['action_type'], 'FINAL_ANSWER')
        self.assertFalse(RESERVATIONS)

    def test_tool_exception_is_native_observation(self):
        class BrokenServer(MCPChargingServer):
            def call_tool(self, *args):
                raise RuntimeError('backend unavailable')
        class Provider:
            model_name = 'fixture'
            def generate_with_tools(self, messages, *args, **kwargs):
                if messages[-1]['role'] == 'tool':
                    assert messages[-1]['observation']['status'] == 'TOOL_ERROR'
                    return {'type': 'text', 'content': 'Công cụ gặp lỗi.'}
                return {'type': 'tool_call', 'calls': [{'id': 'a', 'tool_name': 'check_charging_availability', 'arguments': {}}]}
        logs = self.run_agent(Provider(), BrokenServer())
        self.assertEqual(logs[-1]['action_type'], 'FINAL_ANSWER')

    def test_max_iterations_is_error(self):
        class Loop:
            model_name = 'fixture'
            def generate_with_tools(self, *args, **kwargs):
                return {'type': 'tool_call', 'calls': [{'id': 'x', 'tool_name': 'unknown', 'arguments': {}}]}
        logs = self.run_agent(Loop())
        self.assertEqual(logs[-1]['status'], 'MAX_ITERATIONS')
        self.assertEqual(logs[-1]['action_type'], 'ERROR')

    def test_empty_response_is_error(self):
        class Empty:
            model_name = 'fixture'
            def generate_with_tools(self, *args, **kwargs):
                return {'type': 'text', 'content': ''}
        self.assertEqual(self.run_agent(Empty())[-1]['status'], 'EMPTY_RESPONSE')

    def test_race_recovers_by_querying_again(self):
        from demo_dynamic import run_scenario
        with contextlib.redirect_stdout(io.StringIO()):
            logs, passed = run_scenario(MockOfflineProvider(), 'race')
        self.assertTrue(passed)
        calls = [e for e in logs if e['action_type'] == 'TOOL_EXECUTION']
        self.assertEqual([e['tool_name'] for e in calls], ['check_charging_availability', 'reserve_charging_slot', 'check_charging_availability', 'reserve_charging_slot'])
        self.assertEqual([e['observation']['status'] for e in calls], ['SUCCESS', 'UNAVAILABLE', 'SUCCESS', 'SUCCESS'])
        self.assertTrue(all('llm_latency_ms' in e and 'tool_latency_ms' in e and 'retry_wait_ms' in e for e in logs))

    def test_retry_timing_is_separate(self):
        class Provider:
            n = 0
            def generate_with_tools(self, *args, **kwargs):
                self.n += 1
                if self.n == 1:
                    raise RuntimeError('429 retry in 55s')
                return {'type': 'text', 'content': 'ok'}
        events = []
        with patch('providers.time.perf_counter', side_effect=[0, 2, 2, 59, 59, 62]), patch('providers.time.sleep'):
            result = call_with_retry(Provider(), '', [], '', events.append)
        self.assertEqual(result['llm_latency_ms'], 5000)
        self.assertEqual(result['retry_wait_ms'], 57000)
        self.assertEqual(events[0]['retry_wait_ms'], 57000)


if __name__ == '__main__':
    unittest.main()
