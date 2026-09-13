# Kiểm thử và đọc trace

## Các lệnh chính

```bash
.venv/bin/python -m unittest discover -s tests -v
LLM_PROVIDER=mock .venv/bin/python src/app.py --all
.venv/bin/python src/demo_dynamic.py --scenario alternate
.venv/bin/python src/demo_dynamic.py --scenario race
```

`alternate`: VF-OP01 hết cổng ngay từ đầu → chọn VF-OP02.
`race`: VF-OP01 còn cổng khi tra cứu nhưng hết cổng lúc đặt → nhận UNAVAILABLE → tra cứu lại → chọn VF-OP02.

Các tình huống trên mặc định dùng Mock. Chạy với LLM thật khi có quota:

```bash
.venv/bin/python src/app.py --all --no-retry
.venv/bin/python src/demo_dynamic.py --scenario race --live --no-retry
.venv/bin/python src/app.py --interactive
```

Mặc định retry 3 lần; `--no-retry` dừng ngay khi API lỗi. Không tự chuyển từ API sang Mock. Không chạy nhiều phiên API đồng thời khi quota thấp. Hết quota ngày không được giải quyết bằng chờ vài giây.

## Bằng chứng và đường dẫn

| File | Ý nghĩa |
| --- | --- |
| `docs/trace_waterfall.json`, `docs/test_results_api.json` | Bằng chứng Gemini 5/5 của bản trước native-response; giữ nguyên |
| `docs/trace_native_api.json`, `docs/test_results_native_api.json` | Bằng chứng chỉ được dùng khi bộ 5 test API trên bản native mới đều PASS |
| `artifacts/trace_offline.json`, `artifacts/test_results_offline.json` | Bộ test Mock mới nhất |
| `artifacts/trace_alternate_offline.json`, `artifacts/trace_race_offline.json` | Quyết định linh hoạt bằng Mock |
| `artifacts/trace_race_native_api.json` | Tình huống race chạy với `--live` |
| `artifacts/trace_interactive.json`, `artifacts/trace_demo.json` | Chat có lịch sử / tra cứu đơn lẻ |
| `artifacts/previous/` | Log chạy thử trước khi dọn repo, giữ để đối chiếu |

Chỉ thay trace nộp bài sau khi đã xác nhận bộ native API mới đạt. `artifacts/` được bỏ qua bởi Git; không phải bằng chứng nghiệm thu mặc định.

## Cách đọc trace mới

- `run_id`, `event_id`, `call_id`: liên kết phiên, sự kiện và cặp gọi/kết quả tool.
- `LLM_RESPONSE`: loại phản hồi và `llm_latency_ms` — tổng thời gian các lần request trong bước, không gồm ngủ retry.
- `DECISION`: `decision_summary` là câu lý do công khai nếu model trả về; `rationale_source` chỉ rõ nguồn. Nếu không có, ghi `not_provided`, không tạo suy nghĩ giả.
- `decision_basis`: ID các Observation trước và dữ liệu trạm được chọn, do ứng dụng ghi để đối chiếu, không phải suy nghĩ của model.
- `ACTION`: tên tool, arguments và call ID.
- `TOOL_EXECUTION`: Observation/status và `tool_latency_ms`, chỉ tính thời gian chạy tool.
- `RETRY`: mã lỗi 429, số lần, thời gian chờ yêu cầu và `retry_wait_ms` thực đo.
- `FINAL_ANSWER` / `ERROR`: kết thúc thành công hoặc lỗi/giới hạn vòng lặp.
- `timestamp` UTC và `elapsed_ms`: vị trí sự kiện trên trục thời gian.

Tổng thời gian LLM lấy từ LLM_RESPONSE (hoặc ERROR nếu request thất bại hoàn toàn), tool từ TOOL_EXECUTION, chờ từ RETRY. `total_retry_wait_ms` trên ERROR chỉ là tổng đối chiếu, không cộng lần nữa. SDK được tắt retry tự động để tránh đếm thiếu thời gian chờ.

## Test hội thoại

Nhập lần lượt: “Tìm trạm CCS2 tại Ocean Park 1 cho xe 30H-456.78”, “Đặt lúc 17:00 ngày 15/09/2026”, “Trong 60 phút”. Chỉ đặt khi đủ dữ liệu. `/reset` xóa lịch sử nhưng giữ booking trong phiên; `exit` thoát.

## Trạng thái kiểm chứng

Bản native đã qua 20 kiểm thử offline/contract: giữ chữ ký Gemini, đúng OpenAI call ID, nhiều tool calls, lỗi tool, arguments sai, giới hạn vòng lặp, đo retry, kiểm tra slot chồng lấn và schema. JSON Schema vẫn chặt chẽ cho OpenAI/nội bộ; khi gửi Gemini, adapter bỏ riêng `additionalProperties` vì API Gemini không nhận trường đó. Hai tình huống đổi trạm đã chạy Mock. Lượt probe Gemini thật của bản mới đã qua lỗi schema nhưng gặp 429 quota; chưa có bằng chứng mới cho native API hoặc hội thoại nhiều lượt thật. Bộ 5/5 API cũ chỉ chứng minh phiên bản cũ.
