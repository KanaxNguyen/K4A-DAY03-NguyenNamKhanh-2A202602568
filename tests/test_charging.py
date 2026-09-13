"""Regression checks; no API key or network required."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from tools import TOOLS_SCHEMA, MOCK_STATIONS, dispatch_tool_call, reset_demo_state, RESERVATIONS
from providers import call_with_retry
from app import run_react_agent, evaluate_case
from mcp_server import MCPChargingServer


class ChargingTests(unittest.TestCase):
    def setUp(self):
        reset_demo_state()

    def lookup(self, **args):
        arguments = {'connector_type': 'CCS2'}
        arguments.update(args)
        return json.loads(dispatch_tool_call('check_charging_availability', arguments))

    def test_alias_and_unknown_area(self):
        for name in ['ocean park', 'Ocean Park 1', 'oceanpark1', 'VinUni Ocean Park']:
            self.assertEqual(self.lookup(location=name)['status'], 'SUCCESS')
        self.assertEqual(self.lookup(location='Ocean Park 2')['status'], 'LOCATION_NOT_FOUND')

    def test_dataset_covers_multiple_locations_connectors_and_full_station(self):
        self.assertEqual(len(MOCK_STATIONS), 16)
        times_ccs2 = self.lookup(location='Times City')
        self.assertEqual(times_ccs2['recommended_station']['station_id'], 'VF-TC02')
        times_type2 = self.lookup(location='Times City', connector_type='Type 2')
        self.assertEqual(times_type2['recommended_station']['station_id'], 'VF-TC01')
        self.assertEqual(self.lookup(location='Hồ Tây', connector_type='Type 2')['status'], 'SUCCESS')
        self.assertEqual(self.lookup(location='Mỹ Đình')['status'], 'UNAVAILABLE')
        self.assertEqual(self.lookup(station_id='VF-TC01')['status'], 'UNAVAILABLE')
        self.assertEqual(self.lookup(location='Cầu Giấy')['recommended_station']['station_id'], 'VF-CG01')
        self.assertEqual(self.lookup(location='Hà Đông')['recommended_station']['station_id'], 'VF-HD02')

    def test_missing_station_needs_no_invented_location(self):
        self.assertEqual(self.lookup(station_id='VF-KHONGTONTAI')['status'], 'NOT_FOUND')

    def test_booking_validation_and_idempotence(self):
        args = dict(station_id='VF-OP01', vehicle_id='30H-456.78', connector_type='CCS2', start_time='17:00 15/09/2026', duration_minutes=60)
        for _ in range(2):
            self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', args))['status'], 'SUCCESS')
        self.assertEqual(len(RESERVATIONS), 1)
        args['duration_minutes'] = -5
        self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', args))['status'], 'INVALID_ARGUMENTS')
        args['duration_minutes'] = 60
        args['vehicle_id'] = '3H-123.45'
        self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', args))['status'], 'INVALID_ARGUMENTS')

    def test_time_window_capacity_and_non_overlapping_slots(self):
        first = dict(station_id='VF-OP02', vehicle_id='30H-001.01', connector_type='CCS2', start_time='14:00 15/09/2026', duration_minutes=60)
        self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', first))['status'], 'SUCCESS')
        same_slot = dict(first, vehicle_id='30H-002.02')
        self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', same_slot))['status'], 'UNAVAILABLE')
        later_slot = dict(first, vehicle_id='30H-003.03', start_time='15:00 15/09/2026')
        self.assertEqual(json.loads(dispatch_tool_call('reserve_charging_slot', later_slot))['status'], 'SUCCESS')
        lookup = json.loads(dispatch_tool_call('check_charging_availability', {
            'location': 'VinUni Ocean Park', 'connector_type': 'CCS2', 'start_time': '14:30 15/09/2026', 'duration_minutes': 30
        }))
        self.assertNotIn('VF-OP02', [station['station_id'] for station in lookup['stations']])
        op01 = next(station for station in lookup['stations'] if station['station_id'] == 'VF-OP01')
        self.assertEqual(op01['availability_window']['duration_minutes'], 30)

    def test_time_window_arguments_must_be_given_together(self):
        result = json.loads(dispatch_tool_call('check_charging_availability', {
            'location': 'VinUni Ocean Park', 'connector_type': 'CCS2', 'start_time': '14:00 15/09/2026'
        }))
        self.assertEqual(result['status'], 'INVALID_ARGUMENTS')

    def test_unknown_station_takes_priority_over_incomplete_time_window(self):
        result = json.loads(dispatch_tool_call('check_charging_availability', {
            'station_id': 'VF-KHONGTONTAI', 'connector_type': 'CCS2', 'start_time': '14:00 15/09/2026'
        }))
        self.assertEqual(result['status'], 'NOT_FOUND')

    def test_schema_declares_backend_constraints(self):
        lookup, reservation = TOOLS_SCHEMA
        self.assertEqual(lookup['parameters']['properties']['connector_type']['enum'], ['CCS2', 'Type 2'])
        self.assertEqual(reservation['parameters']['properties']['duration_minutes']['maximum'], 240)
        self.assertTrue(reservation['parameters']['additionalProperties'] is False)

    def test_rate_limit_retry_and_no_fallback(self):
        class Provider:
            count = 0
            def generate_with_tools(self, *args, **kwargs):
                self.count += 1
                if self.count == 1:
                    raise RuntimeError('429 retry in 55s')
                return dict(type='text', content='ok')
        with patch('providers.time.sleep') as sleep:
            self.assertEqual(call_with_retry(Provider(), '', [], '')['retry_count'], 1)
            sleep.assert_called_once_with(57)
        class Broken:
            def generate_with_tools(self, *args, **kwargs):
                raise RuntimeError('401 invalid key')
        with self.assertRaises(RuntimeError):
            call_with_retry(Broken(), '', [], '')

    def test_retry_is_bounded(self):
        class Broken:
            def generate_with_tools(self, *args, **kwargs):
                raise RuntimeError('429')
        with patch('providers.time.sleep') as sleep, self.assertRaises(RuntimeError):
            call_with_retry(Broken(), '', [], '')
        self.assertEqual(sleep.call_count, 3)

    def test_history_reaches_next_turn(self):
        class Recorder:
            model_name = 'test-double'
            prompts = []
            def generate_with_tools(self, prompt, *args, **kwargs):
                self.prompts.append(prompt)
                return dict(type='text', content='Bạn muốn sạc lúc nào?')
        provider, history = Recorder(), []
        with contextlib.redirect_stdout(io.StringIO()):
            run_react_agent('Xe 30H-456.78 tại Ocean Park 1, CCS2', provider, MCPChargingServer(), history)
            run_react_agent('17:00 hôm nay trong 60 phút', provider, MCPChargingServer(), history)
        messages = json.dumps(provider.prompts[-1], ensure_ascii=False)
        self.assertIn('30H-456.78', messages)
        self.assertIn('CCS2', messages)
        self.assertIn('17:00 hôm nay', messages)

    def test_error_is_not_a_pass(self):
        self.assertFalse(evaluate_case({'id': 'TC01'}, [{'action_type': 'ERROR'}]))


if __name__ == '__main__':
    unittest.main()
