"""Công cụ MCP và lớp dữ liệu mô phỏng cho Trợ lý Trạm Sạc VinFast."""

import json
import copy
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


TOOLS_SCHEMA = [
    {
        "name": "check_charging_availability",
        "description": "Tra cứu khả dụng của các trạm sạc VinFast theo khu vực, loại đầu sạc hoặc mã trạm.",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "minLength": 2, "description": "Khu vực cần tìm trạm, ví dụ: VinUni Ocean Park."},
                "connector_type": {"type": "string", "enum": ["CCS2", "Type 2"], "description": "Loại đầu sạc yêu cầu."},
                "station_id": {"type": "string", "pattern": "^VF-[A-Z0-9-]+$", "description": "Mã trạm nếu đã biết, ví dụ: VF-OP01."},
                "start_time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d [0-3]\\d/[01]\\d/\\d{4}$", "description": "Tùy chọn: giờ bắt đầu HH:MM DD/MM/YYYY."},
                "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 240, "description": "Tùy chọn: thời lượng cần sạc, 1–240 phút."}
            },
            "required": ["connector_type"],
            "additionalProperties": False
        }
    },
    {
        "name": "reserve_charging_slot",
        "description": "Đặt một khung giờ sạc tại trạm VinFast sau khi đã xác nhận trạm còn cổng phù hợp.",
        "parameters": {
            "type": "object",
            "properties": {
                "station_id": {"type": "string", "pattern": "^VF-[A-Z0-9-]+$", "description": "Mã trạm sạc cần đặt, ví dụ: VF-OP01."},
                "vehicle_id": {"type": "string", "pattern": "^\\d{2}[A-Z]-\\d{3}\\.\\d{2}$", "description": "Biển số xe theo dạng 30H-123.45; phải sao chép chính xác từ yêu cầu người dùng."},
                "start_time": {"type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d [0-3]\\d/[01]\\d/\\d{4}$", "description": "Thời điểm bắt đầu, HH:MM DD/MM/YYYY."},
                "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 240, "description": "Thời lượng đặt chỗ, 1–240 phút."},
                "connector_type": {"type": "string", "enum": ["CCS2", "Type 2"], "description": "Loại đầu sạc cần dùng."}
            },
            "required": ["station_id", "vehicle_id", "start_time", "duration_minutes", "connector_type"],
            "additionalProperties": False
        }
    }
]


MOCK_STATIONS = {
    "VF-OP01": {
        "station_id": "VF-OP01", "name": "Trạm VinFast Ocean Park A", "location": "VinUni Ocean Park",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 2, "load_percent": 55},
            "Type 2": {"total_ports": 2, "available_ports": 1, "load_percent": 40}
        }
    },
    "VF-OP02": {
        "station_id": "VF-OP02", "name": "Trạm VinFast Ocean Park B", "location": "VinUni Ocean Park",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 1, "load_percent": 70},
            "Type 2": {"total_ports": 2, "available_ports": 0, "load_percent": 100}
        }
    },
    "VF-TC01": {
        "station_id": "VF-TC01", "name": "Trạm VinFast Times City A", "location": "Times City",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 0, "load_percent": 100},
            "Type 2": {"total_ports": 4, "available_ports": 3, "load_percent": 25}
        }
    },
    "VF-TC02": {
        "station_id": "VF-TC02", "name": "Trạm VinFast Times City B", "location": "Times City",
        "connectors": {
            "CCS2": {"total_ports": 6, "available_ports": 3, "load_percent": 30},
            "Type 2": {"total_ports": 2, "available_ports": 0, "load_percent": 100}
        }
    },
    "VF-HT01": {
        "station_id": "VF-HT01", "name": "Trạm VinFast Hồ Tây", "location": "Hồ Tây",
        "connectors": {
            "CCS2": {"total_ports": 2, "available_ports": 1, "load_percent": 50},
            "Type 2": {"total_ports": 2, "available_ports": 2, "load_percent": 0}
        }
    },
    "VF-MD01": {
        "station_id": "VF-MD01", "name": "Trạm VinFast Mỹ Đình", "location": "Mỹ Đình",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 0, "load_percent": 100},
            "Type 2": {"total_ports": 2, "available_ports": 0, "load_percent": 100}
        }
    },
    "VF-CG01": {
        "station_id": "VF-CG01", "name": "Trạm VinFast Cầu Giấy A", "location": "Cầu Giấy",
        "connectors": {
            "CCS2": {"total_ports": 6, "available_ports": 4, "load_percent": 20},
            "Type 2": {"total_ports": 4, "available_ports": 2, "load_percent": 50}
        }
    },
    "VF-CG02": {
        "station_id": "VF-CG02", "name": "Trạm VinFast Cầu Giấy B", "location": "Cầu Giấy",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 1, "load_percent": 75},
            "Type 2": {"total_ports": 2, "available_ports": 2, "load_percent": 0}
        }
    },
    "VF-LB01": {
        "station_id": "VF-LB01", "name": "Trạm VinFast Long Biên A", "location": "Long Biên",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 2, "load_percent": 50},
            "Type 2": {"total_ports": 4, "available_ports": 1, "load_percent": 75}
        }
    },
    "VF-LB02": {
        "station_id": "VF-LB02", "name": "Trạm VinFast Long Biên B", "location": "Long Biên",
        "connectors": {
            "CCS2": {"total_ports": 2, "available_ports": 0, "load_percent": 100},
            "Type 2": {"total_ports": 2, "available_ports": 1, "load_percent": 50}
        }
    },
    "VF-TX01": {
        "station_id": "VF-TX01", "name": "Trạm VinFast Thanh Xuân A", "location": "Thanh Xuân",
        "connectors": {
            "CCS2": {"total_ports": 6, "available_ports": 3, "load_percent": 50},
            "Type 2": {"total_ports": 4, "available_ports": 4, "load_percent": 0}
        }
    },
    "VF-TX02": {
        "station_id": "VF-TX02", "name": "Trạm VinFast Thanh Xuân B", "location": "Thanh Xuân",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 1, "load_percent": 75},
            "Type 2": {"total_ports": 2, "available_ports": 0, "load_percent": 100}
        }
    },
    "VF-HD01": {
        "station_id": "VF-HD01", "name": "Trạm VinFast Hà Đông A", "location": "Hà Đông",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 2, "load_percent": 50},
            "Type 2": {"total_ports": 2, "available_ports": 2, "load_percent": 0}
        }
    },
    "VF-HD02": {
        "station_id": "VF-HD02", "name": "Trạm VinFast Hà Đông B", "location": "Hà Đông",
        "connectors": {
            "CCS2": {"total_ports": 6, "available_ports": 5, "load_percent": 17},
            "Type 2": {"total_ports": 4, "available_ports": 1, "load_percent": 75}
        }
    },
    "VF-BD01": {
        "station_id": "VF-BD01", "name": "Trạm VinFast Ba Đình A", "location": "Ba Đình",
        "connectors": {
            "CCS2": {"total_ports": 4, "available_ports": 1, "load_percent": 75},
            "Type 2": {"total_ports": 2, "available_ports": 2, "load_percent": 0}
        }
    },
    "VF-BD02": {
        "station_id": "VF-BD02", "name": "Trạm VinFast Ba Đình B", "location": "Ba Đình",
        "connectors": {
            "CCS2": {"total_ports": 2, "available_ports": 0, "load_percent": 100},
            "Type 2": {"total_ports": 4, "available_ports": 3, "load_percent": 25}
        }
    }
}

RESERVATIONS = []
INITIAL_STATIONS = copy.deepcopy(MOCK_STATIONS)


def reset_demo_state():
    MOCK_STATIONS.clear()
    MOCK_STATIONS.update(copy.deepcopy(INITIAL_STATIONS))
    RESERVATIONS.clear()


def normalize_location(value):
    compact = re.sub(r'\s+', '', value.lower())
    if compact in {'oceanpark', 'oceanpark1', 'vinunioceanpark', 'vinhomes ocean park'.replace(' ', '')}:
        return 'vinuni ocean park'
    return value.strip().lower()


def _normalize_connector(connector_type: str) -> str:
    return connector_type.strip().upper().replace("TYPE 2", "Type 2")


def _parse_slot(start_time: str, duration_minutes: int):
    start = datetime.strptime(start_time, "%H:%M %d/%m/%Y")
    return start, start + timedelta(minutes=duration_minutes)


def _overlapping_reservations(station_id: str, connector_type: str, start_time: str, duration_minutes: int):
    requested_start, requested_end = _parse_slot(start_time, duration_minutes)
    matches = []
    for booking in RESERVATIONS:
        if booking["station_id"] != station_id or booking["connector_type"] != connector_type:
            continue
        booking_start, booking_end = _parse_slot(booking["start_time"], booking["duration_minutes"])
        if requested_start < booking_end and booking_start < requested_end:
            matches.append(booking)
    return matches


def execute_check_charging_availability(
    connector_type: str,
    location: str = '',
    station_id: Optional[str] = None,
    start_time: Optional[str] = None,
    duration_minutes: Optional[int] = None,
) -> str:
    """Tra cứu trạm và số cổng khả dụng trong khung giờ nếu được cung cấp."""
    normalized_connector = _normalize_connector(connector_type)
    requested_station = station_id.strip().upper() if station_id else None
    # A named station can be resolved independently of an optional time window.
    # This makes a NOT_FOUND response actionable even when a booking request is incomplete.
    if requested_station and requested_station not in MOCK_STATIONS:
        return json.dumps({"status": "NOT_FOUND", "message": f"Không tìm thấy trạm sạc có mã '{requested_station}'."}, ensure_ascii=False)
    if (start_time is None) != (duration_minutes is None):
        return json.dumps({"status": "INVALID_ARGUMENTS", "message": "Cần cung cấp cả start_time và duration_minutes."}, ensure_ascii=False)
    if start_time is not None:
        try:
            _parse_slot(start_time, duration_minutes)
            if type(duration_minutes) is not int or not 1 <= duration_minutes <= 240:
                raise ValueError()
        except (TypeError, ValueError):
            return json.dumps({"status": "INVALID_ARGUMENTS", "message": "Khung giờ phải dùng HH:MM DD/MM/YYYY và thời lượng 1–240 phút."}, ensure_ascii=False)
    candidates = []
    matched = False
    for current_id, station in MOCK_STATIONS.items():
        if requested_station and current_id != requested_station:
            continue
        if not requested_station and (not location.strip() or normalize_location(location) != normalize_location(station['location'])):
            continue
        matched = True
        connector = station["connectors"].get(normalized_connector)
        reserved = _overlapping_reservations(current_id, normalized_connector, start_time, duration_minutes) if start_time else []
        available = max(0, connector["available_ports"] - len(reserved)) if connector else 0
        if connector and available > 0:
            candidates.append({
                "station_id": current_id, "station_name": station["name"], "location": station["location"],
                "connector_type": normalized_connector, "available_ports": available,
                "total_ports": connector["total_ports"], "load_percent": connector["load_percent"],
                "reserved_overlapping_slots": len(reserved), "availability_window": {"start_time": start_time, "duration_minutes": duration_minutes} if start_time else None
            })

    if not candidates:
        return json.dumps({
            "status": "UNAVAILABLE" if matched else "LOCATION_NOT_FOUND",
            "message": f"Không có cổng {normalized_connector} khả dụng tại {location}." if matched else "Chưa nhận diện được khu vực trong dữ liệu mô phỏng; hãy cung cấp mã trạm hoặc VinUni Ocean Park.", "stations": []
        }, ensure_ascii=False)

    candidates.sort(key=lambda item: (-item["available_ports"], item["load_percent"]))
    return json.dumps({
        "status": "SUCCESS", "location": location, "connector_type": normalized_connector,
        "stations": candidates, "recommended_station": candidates[0]
    }, ensure_ascii=False)


def execute_reserve_charging_slot(
    station_id: str, vehicle_id: str, start_time: str, duration_minutes: int, connector_type: str
) -> str:
    """Tạo đặt chỗ khi trạm và loại đầu sạc vẫn còn cổng trống."""
    normalized_station_id = station_id.strip().upper()
    try:
        _parse_slot(start_time, duration_minutes)
        if type(duration_minutes) is not int or not 1 <= duration_minutes <= 240 or not re.fullmatch(r"\d{2}[A-Z]-\d{3}\.\d{2}", vehicle_id.strip()):
            raise ValueError()
    except (ValueError, TypeError):
        return json.dumps({'status': 'INVALID_ARGUMENTS', 'message': 'Cần giờ HH:MM DD/MM/YYYY, biển số dạng 30H-123.45 và thời lượng 1–240 phút.'}, ensure_ascii=False)
    for old in RESERVATIONS:
        if all(old[k] == v for k, v in {'station_id': normalized_station_id, 'vehicle_id': vehicle_id, 'start_time': start_time, 'duration_minutes': duration_minutes, 'connector_type': _normalize_connector(connector_type)}.items()):
            return json.dumps({'status': 'SUCCESS', 'booking': old, 'message': 'Đặt chỗ này đã tồn tại.'}, ensure_ascii=False)
    normalized_connector = _normalize_connector(connector_type)
    station = MOCK_STATIONS.get(normalized_station_id)
    if not station:
        return json.dumps({"status": "NOT_FOUND", "message": f"Không tìm thấy trạm sạc có mã '{normalized_station_id}'."}, ensure_ascii=False)

    connector = station["connectors"].get(normalized_connector)
    reserved = _overlapping_reservations(normalized_station_id, normalized_connector, start_time, duration_minutes)
    if not connector or len(reserved) >= connector["available_ports"]:
        return json.dumps({
            "status": "UNAVAILABLE", "message": f"Trạm {normalized_station_id} không còn cổng {normalized_connector} để đặt chỗ."
        }, ensure_ascii=False)

    booking = {
        "booking_id": f"CHG-{len(RESERVATIONS) + 1:03d}", "station_id": normalized_station_id,
        "station_name": station["name"], "vehicle_id": vehicle_id, "start_time": start_time,
        "duration_minutes": duration_minutes, "connector_type": normalized_connector
    }
    RESERVATIONS.append(booking)
    return json.dumps({
        "status": "SUCCESS", "booking": booking,
        "message": f"Đã đặt chỗ sạc {normalized_connector} tại {station['name']} từ {start_time} trong {duration_minutes} phút."
    }, ensure_ascii=False)


TOOL_ROUTER = {
    "check_charging_availability": execute_check_charging_availability,
    "reserve_charging_slot": execute_reserve_charging_slot
}


def dispatch_tool_call(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Điều phối lệnh gọi công cụ và chuẩn hóa lỗi thực thi thành JSON."""
    if tool_name not in TOOL_ROUTER:
        return json.dumps({"status": "UNKNOWN_TOOL", "error": f"Tool '{tool_name}' không tồn tại!"}, ensure_ascii=False)
    try:
        return TOOL_ROUTER[tool_name](**arguments)
    except Exception as error:
        return json.dumps({"status": "EXECUTION_ERROR", "error": str(error)}, ensure_ascii=False)
