"""
🔌 MODEL CONTEXT PROTOCOL (MCP) SERVER MODULE
Mô phỏng kiến trúc MCP Server cho Trợ lý Trạm Sạc VinFast.
"""

import json
import sys
from typing import Dict, Any, List
from tools import TOOLS_SCHEMA, dispatch_tool_call

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

class MCPChargingServer:
    """
    Giả lập MCP Server tuân thủ chuẩn giao thức Model Context Protocol cho dữ liệu trạm sạc.
    """
    def __init__(self, server_name: str = "vinfast-charging-mcp-server"):
        self.server_name = server_name
        self.version = "2026.1.0"
        
    def list_tools(self) -> List[Dict[str, Any]]:
        """Trả về danh sách các Tools chuẩn giao thức MCP"""
        return TOOLS_SCHEMA
        
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Thực thi tool và đóng gói response theo giao diện mô phỏng của lab."""
        content = json.loads(dispatch_tool_call(tool_name, arguments))
        return {
            "jsonrpc": "2.0",
            "server": self.server_name,
            "tool": tool_name,
            "result": content
        }


if __name__ == "__main__":
    print("==========================================================")
    print("🔌 KIỂM THỬ ĐỘC LẬP MCP SERVER (vinfast-charging-mcp-server)")
    print("==========================================================")
    
    server = MCPChargingServer()
    tools = server.list_tools()
    print(f"✅ Khởi tạo thành công MCP Server: {server.server_name} (Version: {server.version})")
    print(f"📦 Số lượng Tools công bố: {len(tools)}")
    
    for tool in tools:
        assert tool.get("parameters", {}).get("properties"), f"Schema thiếu properties: {tool['name']}"
    print("✅ Tool schemas đã có đầy đủ properties.")

    test_result = server.call_tool("check_charging_availability", {
        "location": "VinUni Ocean Park", "connector_type": "CCS2"
    })
    print("✅ Test dispatch tool 'check_charging_availability' thành công:")
    print(f"   Phản hồi JSON-RPC: {json.dumps(test_result, ensure_ascii=False)}")
