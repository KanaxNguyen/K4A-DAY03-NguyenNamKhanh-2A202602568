"""
🔌 MULTI-PROVIDER LLM ADAPTER (Google Gemini, OpenAI & Offline Mock)
Hỗ trợ Native Tool Calling và chuyển đổi linh hoạt qua biến môi trường LLM_PROVIDER.
"""

import os
import sys
import json
import re
import time
from typing import Dict, Any, List
from dotenv import load_dotenv

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

load_dotenv()

class BaseLLMProvider:
    """Interface cơ sở cho các LLM Provider hỗ trợ Native Tool Calling"""
    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return self.generate_with_tools(prompt, [], system_prompt)['content']

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        raise NotImplementedError


class MockOfflineProvider(BaseLLMProvider):
    """Offline Mock Provider dùng để chạy thử mà không tốn API Key"""
    def __init__(self):
        self.model_name = "Offline-Mock-Model-2026"

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        return f"[Mock Chatbot Response]: Xin chào! Tôi đã nhận được câu hỏi '{prompt}'. (Chế độ Chatbot không có Tool tra cứu dữ liệu thời gian thực)."

    def generate_with_tools(self, prompt: str, tools_schema: List[Dict[str, Any]], system_prompt: str = "") -> Dict[str, Any]:
        if isinstance(prompt, list):
            messages = prompt
            user_parts = [m['content'] for m in messages if m['role'] == 'user']
            prompt = '\n'.join(user_parts)
            if messages and messages[-1]['role'] == 'tool':
                last = messages[-1]
                prompt += '\nObservation từ công cụ ' + last['name'] + ': ' + json.dumps(last['observation'], ensure_ascii=False)
        prompt_lower = prompt.lower()
        requested_slot = {}
        if '14:00' in prompt and '15/09/2026' in prompt:
            requested_slot = {'start_time': '14:00 15/09/2026', 'duration_minutes': 60}
        observation = {}
        if 'Observation từ công cụ ' in prompt:
            tail = prompt.rsplit('Observation từ công cụ ', 1)[1]
            observation = json.JSONDecoder().raw_decode(tail[tail.index('{'):])[0]

        if "observation" not in prompt_lower and any(keyword in prompt_lower for keyword in ["giới thiệu", "hỗ trợ gì", "cách sử dụng"]):
            return {
                "type": "text",
                "content": "[Mock Agent Response]: Tôi có thể tra cứu trạm sạc còn cổng, đề xuất trạm phù hợp và hỗ trợ đặt chỗ sạc.",
                "thought": "Câu hỏi thông tin chung, trả lời trực tiếp không cần gọi Tool."
            }

        # Observation của lượt trước: quyết định bước tiếp theo dựa trên dữ liệu Tool thực tế.
        if "observation" in prompt_lower:
            if '"booking_id"' in prompt_lower:
                return {
                    "type": "text",
                    "content": observation.get('message', '') + ' Mã đặt chỗ: ' + observation.get('booking', {}).get('booking_id', ''),
                    "thought": "Tool đã tạo booking thành công, tôi xác nhận kết quả cho người dùng."
                }
            if observation.get('status') not in (None, 'SUCCESS'):
                if observation.get('status') == 'UNAVAILABLE' and 'Observation từ công cụ reserve_charging_slot:' in prompt:
                    return {'type': 'tool_call', 'tool_name': 'check_charging_availability',
                            'arguments': {'location': 'VinUni Ocean Park', 'connector_type': 'CCS2', **requested_slot},
                            'decision_summary': 'Đặt chỗ vừa thất bại vì hết cổng; tra cứu lại trước khi chọn trạm khác (Mock fixture).'}
                return {
                    "type": "text",
                    "content": observation.get('message', 'Không thể hoàn tất yêu cầu.'),
                    "thought": "Observation không cho phép đặt chỗ, tôi trả lời dựa trên lỗi Tool."
                }
            if '"status": "success"' in prompt_lower and "recommended_station" in prompt_lower and "đặt" in prompt_lower:
                return {
                    "type": "tool_call",
                    "tool_name": "reserve_charging_slot",
                    "arguments": {
                        "station_id": observation['recommended_station']['station_id'], "vehicle_id": "30H-123.45",
                        "start_time": "14:00 15/09/2026", "duration_minutes": 60, "connector_type": "CCS2"
                    },
                    "thought": "Mock chọn trạm được đề xuất trong Observation để đặt chỗ theo fixture."
                }
            if '"status": "success"' in prompt_lower:
                return {
                    "type": "text",
                    "content": "Tôi đã tìm thấy trạm sạc còn cổng phù hợp. Chi tiết trạm và mức tải nằm trong kết quả tra cứu.",
                    "thought": "Observation thành công và người dùng chỉ yêu cầu tra cứu, nên tôi tổng hợp kết quả."
                }
        if "vf-khongtontai" in prompt_lower:
            return {
                "type": "tool_call",
                "tool_name": "check_charging_availability",
                "arguments": {"location": "VinUni Ocean Park", "connector_type": "CCS2", "station_id": "VF-KHONGTONTAI"},
                "thought": "Tôi cần xác minh mã trạm mà người dùng nêu trước khi có thể đặt chỗ."
            }
        if "đặt chỗ" in prompt_lower and "vf-op01" in prompt_lower:
            return {
                "type": "tool_call",
                "tool_name": "reserve_charging_slot",
                "arguments": {
                    "station_id": "VF-OP01", "vehicle_id": "30H-123.45",
                    "start_time": "14:00 15/09/2026", "duration_minutes": 60, "connector_type": "CCS2"
                },
                "thought": "Người dùng đã cung cấp trạm, xe, khung giờ và loại đầu sạc; tôi sẽ tạo đặt chỗ."
            }
        if any(keyword in prompt_lower for keyword in ["trạm sạc", "cổng ccs2", "cần sạc", "khả dụng"]):
            return {
                "type": "tool_call",
                "tool_name": "check_charging_availability",
                "arguments": {"location": "VinUni Ocean Park", "connector_type": "CCS2", **requested_slot},
                "thought": "Tôi cần tra cứu số cổng CCS2 còn trống tại khu vực được hỏi."
            }
        return {
            "type": "text",
            "content": "[Mock Agent Response]: Tôi có thể tra cứu trạm sạc còn cổng, đề xuất trạm phù hợp và hỗ trợ đặt chỗ sạc.",
            "thought": "Câu hỏi thông tin chung, trả lời trực tiếp không cần gọi Tool."
        }


class GeminiProvider(BaseLLMProvider):
    """Google Gemini Provider (Native Tool Calling với Google GenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"

    def generate_with_tools(self, prompt, tools_schema, system_prompt=""):
        from native_transport import gemini_generate
        return gemini_generate(self, prompt, tools_schema, system_prompt)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI Provider (Native Tool Calling với OpenAI SDK)"""
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model_name = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"

    def generate_with_tools(self, prompt, tools_schema, system_prompt=""):
        from native_transport import openai_generate
        return openai_generate(self, prompt, tools_schema, system_prompt)


def get_llm_provider() -> BaseLLMProvider:
    """Factory function khởi tạo Provider theo LLM_PROVIDER env variable"""
    provider_type = os.getenv("LLM_PROVIDER", "gemini").lower()
    
    if provider_type == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if key and key != "your_gemini_api_key_here":
            return GeminiProvider()
        else:
            raise RuntimeError("Thiếu GEMINI_API_KEY; dùng LLM_PROVIDER=mock cho offline.")
    elif provider_type == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if key and key != "your_openai_api_key_here":
            return OpenAIProvider()
        else:
            raise RuntimeError("Thiếu OPENAI_API_KEY; dùng LLM_PROVIDER=mock cho offline.")
    elif provider_type == "mock":
        return MockOfflineProvider()
    else:
        raise RuntimeError("LLM_PROVIDER phải là mock, gemini hoặc openai.")


def call_with_retry(provider, prompt, schema, system_prompt, on_retry=None, max_retries=3):
    """Bounded rate-limit retries; never replace live evidence with Mock."""
    llm_ms, wait_ms = 0.0, 0.0
    for attempt in range(max_retries + 1):
        started = time.perf_counter()
        try:
            result = provider.generate_with_tools(prompt, schema, system_prompt=system_prompt)
            llm_ms += (time.perf_counter() - started) * 1000
            result['retry_count'] = attempt
            result['llm_latency_ms'] = round(llm_ms, 3)
            result['retry_wait_ms'] = round(wait_ms, 3)
            return result
        except Exception as error:
            llm_ms += (time.perf_counter() - started) * 1000
            message = str(error)
            rate_limited = '429' in message or 'RESOURCE_EXHAUSTED' in message
            if not rate_limited or attempt == max_retries:
                failure = RuntimeError(f"{type(error).__name__}: API thất bại; rate_limited={rate_limited}; không fallback Mock.")
                failure.metrics = {'llm_latency_ms': round(llm_ms, 3), 'retry_wait_ms': round(wait_ms, 3), 'retry_count': attempt}
                raise failure from None
            match = re.search(r'(?:retry in |retryDelay[^0-9]*)([0-9.]+)', message, re.I)
            delay = min(120, float(match.group(1)) + 2) if match else 62
            print(f"[RETRY] API 429: chờ {delay:.0f}s, lần {attempt + 1}/{max_retries}.", flush=True)
            waiting = time.perf_counter()
            time.sleep(delay)
            actual_wait = (time.perf_counter() - waiting) * 1000
            wait_ms += actual_wait
            if on_retry:
                on_retry({'retry_number': attempt + 1, 'status_code': 429,
                          'requested_wait_ms': delay * 1000, 'retry_wait_ms': round(actual_wait, 3)})
