# 📊 BÁO CÁO THU HOẠCH NGHIỆM THU BÀI LAB 3 (BƯỚC 3 — SUBMISSION ARTIFACT)

> **Họ và Tên Học viên:** [Điền Họ và Tên]  
> **Mã Sinh Viên / Mã Học viên:** [Điền MSSV]  
> **Chủ đề Lựa chọn:** Trợ lý Điều phối Tải và Kiểm tra Khả dụng Trạm Sạc VinFast (Đề tài Mở)

---

## 1. BẢNG CHẤM ĐIỂM AGENTIC FIT SCORING MATRIX (ĐÁNH GIÁ CHỦ ĐỀ)

| Tiêu chí Đánh giá | Mức độ (1 - 5) | Giải trình chi tiết lý do chọn điểm |
| :--- | :---: | :--- |
| **1. Multi-step Reasoning** | 4 / 5 | Agent cần tách nhu cầu sạc thành đầu sạc, vị trí, thời điểm và thời lượng; tra cứu trạm theo đúng khung giờ, so sánh quan sát rồi mới đề xuất hoặc đặt chỗ. |
| **2. Tool Interaction** | 5 / 5 | Bài toán cần tối thiểu hai công cụ qua MCP: tra cứu khả dụng trạm sạc và tạo đặt chỗ; có thể mở rộng bằng tra cứu trạng thái xe hoặc cập nhật tải trạm. |
| **3. Dynamic Decision** | 5 / 5 | Trạm được chọn dựa trên Observation: cổng tương thích, công suất, tải và số cổng còn trống trong khung giờ yêu cầu. Demo `race` còn mô phỏng trạm hết chỗ giữa lúc tra cứu và đặt: Agent nhận `UNAVAILABLE`, tra cứu lại và đổi sang trạm khác. |
| **4. Long Horizon Goal** | 4 / 5 | Agent giữ mục tiêu phục vụ nhu cầu sạc đến khi có một trạm và khung giờ phù hợp, sau đó xác nhận đặt chỗ thành công hoặc nêu rõ lý do không thể đáp ứng. |
| **TỔNG ĐIỂM AGENTIC FIT** | **18 / 20** | *Nếu tổng điểm > 12/20: Bài toán rất phù hợp triển khai Agentic System.* |

Điểm 18/20 là đánh giá độ phù hợp của chủ đề, không phải điểm chất lượng triển khai. Demo dùng tải tĩnh và dữ liệu trong bộ nhớ, nhưng đã kiểm tra sức chứa theo khoảng thời gian chồng lấn; chưa có dự báo tải hoặc lưu booking bền vững. Chi tiết kiểm thử và giới hạn: [TESTING.md](TESTING.md).

---

## 2. TRÍCH XUẤT KẾT QUẢ WATERFALL TRACE LOG (SAU KHI CHẠY TEST SUITE TRÊN API THẬT)

> **Trạng thái phiên bản:** Trace bên dưới và kết quả 5/5 thuộc bản trước khi nâng cấp native function response. Bản native mới đã qua **20 kiểm thử offline/contract** (gồm đa tool, function-response/call ID, lỗi tool, slot chồng lấn, retry, tương thích schema Gemini và đổi trạm). Probe API đã xác nhận hết lỗi schema, nhưng gặp 429 quota. Cần chạy lại nghiệm thu API trước khi dùng để chứng nhận bản mới. Xem `TESTING.md`.

> ⚠️ **YÊU CẦU NGHIỆM THU:** Mở tệp `.env` điền `GEMINI_API_KEY` (hoặc `OPENAI_API_KEY`) để kết nối LLM thật trước khi thực thi `python src/app.py --all`. Bài nộp chỉ dùng Mock Offline Provider sẽ không đạt điểm nghiệm thực tế.

Trích xuất TC04 từ lần chạy Gemini API thật ngày 13/09/2026. Không fallback Mock; khi gặp 429, chương trình chờ rồi retry. Các dữ liệu trạm/booking vẫn là mô phỏng của bài lab.

```json
[
  {
    "step": 1,
    "query": "Xe VF 8 biển 30H-123.45 của tôi cần sạc CCS2 tại VinUni Ocean Park vào 14:00 ngày 15/09/2026. Hãy tìm trạm còn chỗ và đặt khung giờ một tiếng phù hợp nhất.",
    "action_type": "TOOL_EXECUTION",
    "tool_name": "check_charging_availability",
    "arguments": {
      "connector_type": "CCS2",
      "location": "VinUni Ocean Park"
    },
    "observation": {
      "status": "SUCCESS",
      "location": "VinUni Ocean Park",
      "connector_type": "CCS2",
      "stations": [
        {
          "station_id": "VF-OP01",
          "station_name": "Trạm VinFast Ocean Park A",
          "location": "VinUni Ocean Park",
          "connector_type": "CCS2",
          "total_ports": 4,
          "available_ports": 2,
          "load_percent": 55
        },
        {
          "station_id": "VF-OP02",
          "station_name": "Trạm VinFast Ocean Park B",
          "location": "VinUni Ocean Park",
          "connector_type": "CCS2",
          "total_ports": 4,
          "available_ports": 1,
          "load_percent": 70
        }
      ],
      "recommended_station": {
        "station_id": "VF-OP01",
        "station_name": "Trạm VinFast Ocean Park A",
        "location": "VinUni Ocean Park",
        "connector_type": "CCS2",
        "total_ports": 4,
        "available_ports": 2,
        "load_percent": 55
      }
    },
    "thought": "Gemini quyết định gọi công cụ 'check_charging_availability' với tham số: {\"connector_type\": \"CCS2\", \"location\": \"VinUni Ocean Park\"}",
    "latency_ms": 2593.62,
    "provider": "GeminiProvider",
    "model": "gemini-2.5-flash",
    "source": "live_api",
    "test_id": "TC04"
  },
  {
    "step": 2,
    "query": "Xe VF 8 biển 30H-123.45 của tôi cần sạc CCS2 tại VinUni Ocean Park vào 14:00 ngày 15/09/2026. Hãy tìm trạm còn chỗ và đặt khung giờ một tiếng phù hợp nhất.",
    "action_type": "TOOL_EXECUTION",
    "tool_name": "reserve_charging_slot",
    "arguments": {
      "connector_type": "CCS2",
      "duration_minutes": 60,
      "start_time": "14:00 15/09/2026",
      "station_id": "VF-OP01",
      "vehicle_id": "30H-123.45"
    },
    "observation": {
      "status": "SUCCESS",
      "booking": {
        "booking_id": "CHG-001",
        "station_id": "VF-OP01",
        "station_name": "Trạm VinFast Ocean Park A",
        "vehicle_id": "30H-123.45",
        "start_time": "14:00 15/09/2026",
        "duration_minutes": 60,
        "connector_type": "CCS2"
      },
      "message": "Đã đặt chỗ sạc CCS2 tại Trạm VinFast Ocean Park A từ 14:00 15/09/2026 trong 60 phút."
    },
    "thought": "Gemini quyết định gọi công cụ 'reserve_charging_slot' với tham số: {\"connector_type\": \"CCS2\", \"duration_minutes\": 60, \"start_time\": \"14:00 15/09/2026\", \"station_id\": \"VF-OP01\", \"vehicle_id\": \"30H-123.45\"}",
    "latency_ms": 54133.06,
    "provider": "GeminiProvider",
    "model": "gemini-2.5-flash",
    "source": "live_api",
    "test_id": "TC04"
  },
  {
    "step": 3,
    "query": "Xe VF 8 biển 30H-123.45 của tôi cần sạc CCS2 tại VinUni Ocean Park vào 14:00 ngày 15/09/2026. Hãy tìm trạm còn chỗ và đặt khung giờ một tiếng phù hợp nhất.",
    "action_type": "FINAL_ANSWER",
    "thought": "Gemini phản hồi trực tiếp bằng văn bản (không cần gọi công cụ).",
    "output": "Bạn đã đặt chỗ sạc thành công với mã đặt chỗ CHG-001 tại Trạm VinFast Ocean Park A vào 14:00 ngày 15/09/2026 trong 60 phút.",
    "latency_ms": 1826.06,
    "provider": "GeminiProvider",
    "model": "gemini-2.5-flash",
    "source": "live_api",
    "test_id": "TC04"
  }
]
```

---

## 3. TỔNG KẾT KẾT QUẢ NGHIỆM THU & NỘP BÀI

- [x] Bằng chứng lịch sử: bản trước đã chạy 5 / 5 test Gemini API thật.
- [x] Bản hiện tại: đã qua 20 kiểm thử offline/contract và các scenario đổi trạm; schema Gemini đã tương thích, nhưng chưa có API live PASS mới vì quota Gemini 429.
- **Tổng số Test Cases API của bản hiện tại:** Chưa nghiệm thu lại — không được ghi là 5/5 cho tới khi file native API mới đều PASS.
- **Số lượt gọi Tool qua MCP Server (bằng chứng API lịch sử):** 5 lượt trong bộ 5 test; có 1 lượt trả về NOT_FOUND đúng kỳ vọng TC05.
- **Kết quả đẩy Repo nộp bài:** [ ] Đã Commit và Push mã nguồn thành công lên GitHub cá nhân.

---

> ✅ **HOÀN TẤT NỘP BÀI:** Sao chép đường link GitHub Repository cá nhân của bạn và dán vào ô nộp bài trên hệ thống LMS VLearn để hoàn tất Bài Lab 3!
