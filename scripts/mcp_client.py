#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 OpenAPI MCP 客户端
使用 JSON-RPC 2.0 协议调用 MCP Server
通过 alibabacloud.mcp-proxy 子进程（STDIO）通信，使用 AK 静态凭证认证
"""

import os
import json
import time
import subprocess
import threading
import atexit
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class PriceResult:
    """价格查询结果"""
    success: bool
    price_1y_list: Optional[float] = None
    price_1y_discount: Optional[float] = None
    price_3y_list: Optional[float] = None
    price_3y_discount: Optional[float] = None
    remark_1y: str = ""
    remark_3y: str = ""
    remark: str = ""
    error_message: str = ""
    detail_info: Dict = field(default_factory=dict)
    is_spec_error: bool = False


class MCPClient:
    """
    阿里云 OpenAPI MCP 客户端

    通过 alibabacloud.mcp-proxy 子进程（STDIO）与 MCP Server 通信。
    使用 AK 静态凭证认证，永不过期。
    """

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(script_dir, "..", "config")

        self.config_dir = os.path.abspath(config_dir)
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.config = self._load_config()

        mcp_config = self.config.get("mcp", {})
        self.endpoint = mcp_config.get("endpoint", "")

        ak_config = self.config.get("ak", {})
        self.access_key_id = ak_config.get("access_key_id", "")
        self.access_key_secret = ak_config.get("access_key_secret", "")

        self._proxy_proc: Optional[subprocess.Popen] = None
        self._proxy_stdin = None
        self._proxy_stdout = None
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._initialized = False

        atexit.register(self.close)

    def _load_config(self) -> Dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _ensure_proxy(self) -> None:
        if self._proxy_proc is not None and self._proxy_proc.poll() is None:
            return

        self._close_proxy()

        if not self.access_key_id or not self.access_key_secret:
            raise ValueError(
                "未配置 AK 凭证。请在 config.json 中添加 ak.access_key_id 和 ak.access_key_secret。"
            )

        env = os.environ.copy()
        env["ALIBABA_CLOUD_ACCESS_KEY_ID"] = self.access_key_id
        env["ALIBABA_CLOUD_ACCESS_KEY_SECRET"] = self.access_key_secret
        env["ALIBABACLOUD_MCP_SERVER_URL"] = self.endpoint
        env["ALIBABACLOUD_MCP_SITE_TYPE"] = "CN"

        uvx_path = os.path.expanduser("~/.local/bin/uvx")
        if not os.path.exists(uvx_path):
            uvx_path = "uvx"

        self._proxy_proc = subprocess.Popen(
            [uvx_path, "alibabacloud.mcp-proxy@latest", "--server-url", self.endpoint],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            bufsize=0,
        )

        self._proxy_stdin = self._proxy_proc.stdin
        self._proxy_stdout = self._proxy_proc.stdout
        self._initialized = False

    def _close_proxy(self) -> None:
        try:
            if self._proxy_stdin:
                self._proxy_stdin.close()
        except Exception:
            pass
        try:
            if self._proxy_proc and self._proxy_proc.poll() is None:
                self._proxy_proc.terminate()
                try:
                    self._proxy_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proxy_proc.kill()
        except Exception:
            pass
        self._proxy_proc = None
        self._proxy_stdin = None
        self._proxy_stdout = None

    def close(self) -> None:
        self._close_proxy()

    def __del__(self):
        self.close()

    def _send_request(self, method: str, params: Optional[Dict] = None,
                      request_id: Optional[int] = None) -> Dict:
        if request_id is None:
            self._request_id += 1
            request_id = self._request_id

        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }, ensure_ascii=False) + "\n"

        with self._request_lock:
            self._ensure_proxy()
            self._proxy_stdin.write(msg.encode("utf-8"))
            self._proxy_stdin.flush()
            result = self._read_response(request_id)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _read_response(self, request_id: int, timeout: float = 60) -> Dict:
        import select
        deadline = time.time() + timeout

        while time.time() < deadline:
            readable, _, _ = select.select([self._proxy_stdout], [], [], 1)
            if not readable:
                continue

            chunk = self._proxy_stdout.read(1)
            if not chunk:
                raise RuntimeError("Proxy 子进程意外退出")

            line = chunk
            while line[-1:] != b"\n":
                more = self._proxy_stdout.read(1)
                if not more:
                    raise RuntimeError("Proxy 子进程意外退出")
                line += more

            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            if msg.get("id") == request_id:
                if "error" in msg:
                    err = msg["error"]
                    raise RuntimeError(
                        f"MCP 调用失败: {err.get('message', 'unknown')} "
                        f"(code={err.get('code', 'n/a')})"
                    )
                return msg.get("result", {})

        raise RuntimeError(f"等待 MCP 响应超时（{timeout}s）")

    def _send_notification(self, method: str, params: Optional[Dict] = None) -> None:
        msg = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }, ensure_ascii=False) + "\n"

        with self._request_lock:
            self._ensure_proxy()
            self._proxy_stdin.write(msg.encode("utf-8"))
            self._proxy_stdin.flush()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return

        self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "aliyun-skill", "version": "2.0.0"},
        })
        self._send_notification("notifications/initialized")
        self._initialized = True

    def list_tools(self) -> List[Dict]:
        self._ensure_initialized()
        response = self._send_request("tools/list")
        return response.get("result", {}).get("tools", [])

    def _call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        self._ensure_initialized()
        return self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

    # ========== 业务方法 ==========

    def _build_cli_command(self, region: str, instance_spec: str,
                           system_disk_type: str = "cloud_essd",
                           system_disk_size: int = 40,
                           system_disk_pl: str = "PL0",
                           data_disk_type: str = None,
                           data_disk_size: int = 0,
                           data_disk_pl: str = "PL0",
                           data_disks: list = None,
                           bandwidth: int = 0,
                           bandwidth_charge_type: str = "PayByBandwidth",
                           image_id: str = None,
                           period: int = 1,
                           price_unit: str = "Year") -> str:
        cmd_parts = [
            "aliyun ecs DescribePrice",
            f"--RegionId {region}",
            f"--InstanceType {instance_spec}",
            f"--SystemDisk.Category {system_disk_type}",
            f"--SystemDisk.Size {system_disk_size}",
            f"--SystemDisk.PerformanceLevel {system_disk_pl}",
            f"--PriceUnit {price_unit}",
            f"--Period {period}"
        ]

        if data_disks:
            for i, disk in enumerate(data_disks, 1):
                disk_category = disk.get('category', 'cloud_essd')
                disk_size = disk.get('size', 0)
                disk_pl = disk.get('pl', 'PL0')
                cmd_parts.extend([
                    f"--DataDisk.{i}.Category {disk_category}",
                    f"--DataDisk.{i}.Size {disk_size}"
                ])
                if disk_category == 'cloud_essd' and disk_pl:
                    cmd_parts.append(f"--DataDisk.{i}.PerformanceLevel {disk_pl}")
        elif data_disk_type and data_disk_size > 0:
            cmd_parts.extend([
                f"--DataDisk.1.Category {data_disk_type}",
                f"--DataDisk.1.Size {data_disk_size}",
                f"--DataDisk.1.PerformanceLevel {data_disk_pl}"
            ])

        if bandwidth > 0:
            cmd_parts.extend([
                f"--InternetChargeType {bandwidth_charge_type}",
                f"--InternetMaxBandwidthOut {bandwidth}"
            ])

        if image_id:
            cmd_parts.append(f"--ImageId {image_id}")

        return " \\\n  ".join(cmd_parts)

    def _parse_price_result(self, response_text: str) -> Dict:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            return {"error": "无法解析响应数据"}

        if "code" in data and data["code"] < 0:
            return {"error": data.get("message", "未知错误")}

        price_info = data.get("PriceInfo", {}).get("Price", {})
        rules = data.get("PriceInfo", {}).get("Rules", {}).get("Rule", [])

        result = {
            "original_price": price_info.get("OriginalPrice", 0),
            "discount_price": price_info.get("DiscountPrice", 0),
            "trade_price": price_info.get("TradePrice", 0),
            "currency": price_info.get("Currency", "CNY"),
            "rules": [r.get("Description", "") for r in rules],
            "details": []
        }

        detail_infos = price_info.get("DetailInfos", {}).get("DetailInfo", [])
        for detail in detail_infos:
            if detail.get("OriginalPrice", 0) > 0:
                result["details"].append({
                    "resource": detail.get("Resource", ""),
                    "original_price": detail.get("OriginalPrice", 0),
                    "trade_price": detail.get("TradePrice", 0)
                })

        return result

    def query_ecs_price(self, region: str, instance_spec: str,
                        system_disk_type: str = "cloud_essd",
                        system_disk_size: int = 40,
                        system_disk_pl: str = "PL0",
                        data_disk_type: str = None,
                        data_disk_size: int = 0,
                        data_disk_pl: str = "PL0",
                        data_disks: list = None,
                        bandwidth: int = 0,
                        bandwidth_charge_type: str = "PayByBandwidth",
                        image_id: str = None) -> PriceResult:
        results = {}
        errors = []

        for period, label in [(1, "1y"), (3, "3y")]:
            try:
                cli_cmd = self._build_cli_command(
                    region=region, instance_spec=instance_spec,
                    system_disk_type=system_disk_type, system_disk_size=system_disk_size,
                    system_disk_pl=system_disk_pl, data_disk_type=data_disk_type,
                    data_disk_size=data_disk_size, data_disk_pl=data_disk_pl,
                    data_disks=data_disks, bandwidth=bandwidth,
                    bandwidth_charge_type=bandwidth_charge_type, image_id=image_id,
                    period=period, price_unit="Year"
                )

                response = self._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd})
                content = response.get("result", {}).get("content", [])

                for item in content:
                    if item.get("type") == "text":
                        text = item.get("text", "")
                        data = json.loads(text)
                        if "code" in data and data["code"] < 0:
                            errors.append(f"{label}价格查询失败: {data.get('message', '未知错误')}")
                        else:
                            results[label] = self._parse_price_result(text)
            except Exception as e:
                errors.append(f"{label}价格查询异常: {str(e)}")

        if errors and not results:
            return PriceResult(success=False, error_message="; ".join(errors))

        result = PriceResult(success=True)

        if "1y" in results:
            result.price_1y_list = results["1y"].get("original_price")
            result.price_1y_discount = results["1y"].get("trade_price")
            result.detail_info["1y"] = results["1y"]
            if results["1y"].get("rules"):
                result.remark_1y = "；".join(results["1y"]["rules"])

        if "3y" in results:
            result.price_3y_list = results["3y"].get("original_price")
            result.price_3y_discount = results["3y"].get("trade_price")
            result.detail_info["3y"] = results["3y"]
            if results["3y"].get("rules"):
                result.remark_3y = "；".join(results["3y"]["rules"])

        remarks = []
        if result.remark_1y:
            remarks.append(f"【1年】{result.remark_1y}")
        if result.remark_3y:
            remarks.append(f"【3年】{result.remark_3y}")
        result.remark = "\n".join(remarks) if remarks else ""

        if errors:
            result.remark += f"\n(部分失败: {'; '.join(errors)})"

        return result

    def query_rds_price(self, region: str, engine: str, engine_version: str,
                        db_instance_class: str, db_instance_storage: int,
                        db_instance_storage_type: str, period: int = 1) -> PriceResult:
        cli_cmd = " ".join([
            "aliyun rds DescribePrice",
            f"--RegionId {region}",
            f"--CommodityCode rds",
            f"--Engine {engine}",
            f"--EngineVersion {engine_version}",
            f"--DBInstanceClass {db_instance_class}",
            f"--DBInstanceStorage {db_instance_storage}",
            f"--PayType Prepaid",
            f"--UsedTime {period}",
            f"--TimeType Year",
            f"--Quantity 1",
            f"--InstanceUsedType 0",
            f"--OrderType BUY",
            f"--DBInstanceStorageType {db_instance_storage_type}"
        ])

        response = self._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd})
        content = response.get("result", {}).get("content", [])
        result = PriceResult(success=False)

        for item in content:
            if item.get("type") == "text":
                text = item.get("text", "")
                try:
                    data = json.loads(text)
                    if "code" in data and data["code"] < 0:
                        result.error_message = data.get('message', '未知错误')
                        return result

                    price_info = data.get("PriceInfo", {})
                    order_lines = price_info.get("OrderLines", {})
                    order_line = order_lines.get("0", {})
                    depreciate_info = order_line.get("depreciateInfo", {})
                    final_activity = depreciate_info.get("finalActivity", {})

                    result.success = True
                    result.price_1y_list = price_info.get("OriginalPrice")
                    result.price_1y_discount = final_activity.get("finalFee") if final_activity else None
                    result.remark_1y = final_activity.get("activityName", "") if final_activity else ""
                    result.detail_info["1y"] = {
                        "original_price": price_info.get("OriginalPrice"),
                        "discount_price": final_activity.get("finalFee") if final_activity else None,
                        "rules": [final_activity.get("activityName", "")] if final_activity else [],
                    }
                    return result
                except json.JSONDecodeError as e:
                    result.error_message = f"JSON 解析失败：{e}"
                    return result

        result.error_message = "无有效响应数据"
        return result


if __name__ == "__main__":
    print("=" * 60)
    print("阿里云 OpenAPI MCP 客户端测试（AK 模式）")
    print("=" * 60)

    client = MCPClient()

    print("\n可用工具:")
    tools = client.list_tools()
    for tool in tools:
        print(f"  - {tool.get('name')}")

    print("\n测试 ECS 价格查询...")
    result = client.query_ecs_price(
        region="cn-hangzhou",
        instance_spec="ecs.u1-c1m2.xlarge",
        system_disk_size=40,
        system_disk_pl="PL0"
    )

    if result.success:
        print(f"\n✅ 查询成功!")
        print(f"   1 年目录价: ￥{result.price_1y_list:.2f}")
        print(f"   1 年折扣价: ￥{result.price_1y_discount:.2f}")
        print(f"   3 年目录价: ￥{result.price_3y_list:.2f}")
        print(f"   3 年折扣价: ￥{result.price_3y_discount:.2f}")
        if result.remark:
            print(f"   折扣规则: {result.remark}")
    else:
        print(f"\n❌ 查询失败: {result.error_message}")

    client.close()
