#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 OpenAPI MCP 客户端
使用 JSON-RPC 2.0 协议调用 MCP Server
通过 alibabacloud.mcp-proxy 子进程(STDIO)通信,使用 AK 静态凭证认证
"""

import os
import sys
import json
import time
import subprocess
import threading
import atexit
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# OAuth Token 刷新端点(OAuth 模式)
OAUTH_TOKEN_URL = "https://oauth.aliyun.com/v1/token"


@dataclass
class PriceResult:
    """价格查询结果"""
    success: bool
    price_1y_list: Optional[float] = None      # 官网目录价(1 年)
    price_1y_discount: Optional[float] = None  # 官网折扣价(1 年)
    price_3y_list: Optional[float] = None      # 官网目录价(3 年)
    price_3y_discount: Optional[float] = None  # 官网折扣价(3 年)
    remark_1y: str = ""                         # 1 年折扣说明
    remark_3y: str = ""                         # 3 年折扣说明
    remark: str = ""                            # 备注(合并显示)
    error_message: str = ""                     # 错误信息
    detail_info: Dict = field(default_factory=dict)  # 详细信息
    is_spec_error: bool = False                 # 是否是规格错误


class MCPClient:
    """
    阿里云 OpenAPI MCP 客户端

    通过 alibabacloud.mcp-proxy 子进程(STDIO)与 MCP Server 通信。
    使用 AK 静态凭证认证,无需 OAuth 刷新。
    """

    def __init__(self, config_dir: str = None):
        """
        初始化 MCP 客户端

        Args:
            config_dir: 配置文件目录路径
        """
        if config_dir is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(script_dir, "..", "config")

        self.config_dir = os.path.abspath(config_dir)
        self.config_path = os.path.join(self.config_dir, "config.json")
        self.config = self._load_config()

        mcp_config = self.config.get("mcp", {})
        self.endpoint = mcp_config.get("endpoint", "")

        # AK 凭证
        ak_config = self.config.get("ak", {})
        self.access_key_id = ak_config.get("access_key_id", "")
        self.access_key_secret = ak_config.get("access_key_secret", "")

        # 子进程管理
        # AK 子进程模式
        self._mode = "oauth"  # 默认 OAuth,有 AK 时切换
        self._proxy_proc: Optional[subprocess.Popen] = None
        self._proxy_stdin = None
        self._proxy_stdout = None
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._initialized = False

        # OAuth HTTP 模式(向后兼容)
        self.token_data: Optional[Dict] = self.config.get("token")
        self.session_id: Optional[str] = None

        # 优先使用 AK 模式(如果凭证已配置且不是占位符)
        if (self.access_key_id and self.access_key_secret and
                self.access_key_id != "YOUR_AK_ID_HERE" and
                self.access_key_secret != "YOUR_AK_SECRET_HERE"):
            self._mode = "ak"
        elif self.token_data and "access_token" in self.token_data:
            # 检查是否需要刷新
            expires_at = self.token_data.get("expires_at", 0)
            if expires_at and time.time() >= expires_at - 300:
                try:
                    self._auto_refresh_token()
                except Exception:
                    pass  # 刷新失败也不阻塞,后续调用时会重试

        # 注册退出时清理
        atexit.register(self.close)

    def _load_config(self) -> Dict:
        """加载配置文件"""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_config(self, data: Dict) -> None:
        """原子保存配置文件"""
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.rename(tmp_path, self.config_path)
        self.config = data

    def _validate_ak(self) -> None:
        """验证 AK 凭证是否配置"""
        if not self.access_key_id or not self.access_key_secret:
            raise ValueError(
                "未配置 AK 凭证。请在 config.json 中添加 ak.access_key_id 和 ak.access_key_secret。\n"
                "或者使用 OAuth 模式(保留 token 配置)。"
            )

    def _get_access_token(self) -> str:
        """OAuth 模式:获取 Access Token,过期时自动刷新"""
        if not self.token_data or "access_token" not in self.token_data:
            raise ValueError("未找到 Access Token,请先完成 OAuth 授权")

        expires_at = self.token_data.get("expires_at", 0)
        if expires_at and time.time() >= expires_at - 300:
            self._auto_refresh_token()

        return self.token_data["access_token"]

    def _auto_refresh_token(self) -> None:
        """OAuth 模式:使用 refresh_token 自动刷新 access_token"""
        refresh_token = self.token_data.get("refresh_token")
        if not refresh_token:
            raise ValueError("未找到 Refresh Token,无法自动刷新,请重新完成 OAuth 授权")

        app_id = self.config.get("oauth", {}).get("app_id", "")
        if not app_id:
            raise ValueError("未配置 app_id,无法刷新 Token")

        post_data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": app_id,
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(OAUTH_TOKEN_URL, data=post_data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                token_resp = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise ValueError(
                f"Token 刷新失败 (HTTP {e.code}): {error_body[:300]}\n"
                f"请重新运行 oauth_local_server.py 完成授权"
            )
        except Exception as e:
            raise ValueError(f"Token 刷新请求异常: {e}")

        if "access_token" not in token_resp:
            error_msg = token_resp.get("error_description", json.dumps(token_resp, ensure_ascii=False))
            raise ValueError(
                f"Token 刷新失败: {error_msg[:300]}\n"
                f"请重新运行 oauth_local_server.py 完成授权"
            )

        self.token_data["access_token"] = token_resp["access_token"]
        self.token_data["expires_at"] = time.time() + token_resp.get("expires_in", 3600)
        if "refresh_token" in token_resp:
            self.token_data["refresh_token"] = token_resp["refresh_token"]

        self.config["token"] = self.token_data
        self._save_config(self.config)

    # ========== 子进程管理 ==========

    def _ensure_proxy(self) -> None:
        """确保 proxy 子进程已启动且存活"""
        if self._proxy_proc is not None and self._proxy_proc.poll() is None:
            return  # 子进程还在运行

        # 清理旧进程
        self._close_proxy()

        self._validate_ak()

        env = os.environ.copy()
        env["ALIBABA_CLOUD_ACCESS_KEY_ID"] = self.access_key_id
        env["ALIBABA_CLOUD_ACCESS_KEY_SECRET"] = self.access_key_secret
        env["ALIBABACLOUD_MCP_SERVER_URL"] = self.endpoint
        env["ALIBABACLOUD_MCP_SITE_TYPE"] = "CN"

        # 查找 uvx 路径(优先 .local/bin)
        uvx_path = os.path.expanduser("~/.local/bin/uvx")
        if not os.path.exists(uvx_path):
            uvx_path = "uvx"  # fallback to PATH

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
        """关闭 proxy 子进程"""
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
        """关闭客户端,释放子进程"""
        self._close_proxy()

    def __del__(self):
        self.close()

    # ========== STDIO JSON-RPC 通信 ==========

    def _send_request(self, method: str, params: Optional[Dict] = None,
                      request_id: Optional[int] = None) -> Dict:
        """
        通过 STDIO 发送 JSON-RPC 请求并等待响应。
        使用 NDJSON (JSON Lines) 格式：每行一个 JSON 对象。
        返回完整的 JSON-RPC 响应（包含 result 字段）。
        """
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

            # 发送
            self._proxy_stdin.write(msg.encode("utf-8"))
            self._proxy_stdin.flush()

            # 读取响应
            result = self._read_response(request_id)
            # 返回完整的 JSON-RPC 响应格式，与 OAuth 模式保持一致
            return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _read_response(self, request_id: int, timeout: float = 60) -> Dict:
        """
        从 stdout 按行读取 NDJSON，找到匹配 request_id 的响应。
        跳过 notifications（没有 id 的消息）。
        """
        import select
        deadline = time.time() + timeout

        while time.time() < deadline:
            readable, _, _ = select.select([self._proxy_stdout], [], [], 1)
            if not readable:
                continue

            chunk = self._proxy_stdout.read(1)
            if not chunk:
                raise RuntimeError("Proxy 子进程意外退出")

            # 读取完整一行
            line = chunk
            while line[-1:] != b"\n":
                more = self._proxy_stdout.read(1)
                if not more:
                    raise RuntimeError("Proxy 子进程意外退出")
                line += more

            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue  # 跳过非 JSON 行

            # 如果是响应且 id 匹配，返回
            if msg.get("id") == request_id:
                if "error" in msg:
                    err = msg["error"]
                    raise RuntimeError(
                        f"MCP 调用失败: {err.get('message', 'unknown')} "
                        f"(code={err.get('code', 'n/a')})"
                    )
                return msg.get("result", {})

            # notifications 或其他响应，忽略

        raise RuntimeError(f"等待 MCP 响应超时（{timeout}s）")

    def _send_notification(self, method: str, params: Optional[Dict] = None) -> None:
        """发送 JSON-RPC 通知（无响应）"""
        msg = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }, ensure_ascii=False) + "\n"

        with self._request_lock:
            self._ensure_proxy()
            self._proxy_stdin.write(msg.encode("utf-8"))
            self._proxy_stdin.flush()

    # ========== MCP 协议 ==========

    def _ensure_initialized(self) -> None:
        """确保 MCP 会话已初始化"""
        if self._initialized:
            return

        self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "aliyun-skill", "version": "2.0.0"},
        })

        self._send_notification("notifications/initialized")
        self._initialized = True

    def _call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """调用 MCP Tool(支持 AK 和 OAuth 双模式)"""
        if self._mode == "ak":
            self._ensure_initialized()
            return self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments,
            })
        else:
            return self._call_tool_http(tool_name, arguments)

    def _call_tool_http(self, tool_name: str, arguments: Dict) -> Dict:
        """OAuth 模式:通过 HTTP 调用 MCP Tool"""
        session_id = self._init_session()

        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            method='POST'
        )
        req.add_header('Authorization', f'Bearer {self._get_access_token()}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('mcp-session-id', session_id)

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            return {"error": f"HTTP {e.code}", "details": error_body}

    def list_tools(self) -> List[Dict]:
        """列出可用的 MCP 工具(支持 AK 和 OAuth 双模式)"""
        if self._mode == "ak":
            self._ensure_initialized()
            response = self._send_request("tools/list")
            return response.get("result", {}).get("tools", [])
        else:
            return self._list_tools_http()

    def _list_tools_http(self) -> List[Dict]:
        """OAuth 模式:通过 HTTP 列出工具"""
        session_id = self._init_session()

        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
            "params": {}
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            method='POST'
        )
        req.add_header('Authorization', f'Bearer {self._get_access_token()}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('mcp-session-id', session_id)

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("result", {}).get("tools", [])

    def _init_session(self) -> str:
        """OAuth 模式:初始化 MCP Session"""
        if self.session_id:
            return self.session_id

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aliyun-price-query", "version": "1.0.0"}
            }
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            method='POST'
        )
        req.add_header('Authorization', f'Bearer {self._get_access_token()}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json, text/event-stream')

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                self.session_id = response.headers.get('mcp-session-id')
                return self.session_id
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            raise Exception(f"MCP 初始化失败: HTTP {e.code} - {error_body}")

        payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/list",
            "params": {}
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode('utf-8'),
            method='POST'
        )
        req.add_header('Authorization', f'Bearer {self._get_access_token()}')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json')
        req.add_header('mcp-session-id', session_id)

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("result", {}).get("tools", [])

    # ========== 业务方法(保持不变) ==========

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
        """构建 ECS 价格查询 CLI 命令"""
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
        """解析价格查询结果"""
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
        """查询 ECS 价格(1 年和 3 年)"""
        results = {}
        errors = []

        for period, label in [(1, "1y"), (3, "3y")]:
            try:
                cli_cmd = self._build_cli_command(
                    region=region,
                    instance_spec=instance_spec,
                    system_disk_type=system_disk_type,
                    system_disk_size=system_disk_size,
                    system_disk_pl=system_disk_pl,
                    data_disk_type=data_disk_type,
                    data_disk_size=data_disk_size,
                    data_disk_pl=data_disk_pl,
                    data_disks=data_disks,
                    bandwidth=bandwidth,
                    bandwidth_charge_type=bandwidth_charge_type,
                    image_id=image_id,
                    period=period,
                    price_unit="Year"
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
                result.remark_1y = ";".join(results["1y"]["rules"])

        if "3y" in results:
            result.price_3y_list = results["3y"].get("original_price")
            result.price_3y_discount = results["3y"].get("trade_price")
            result.detail_info["3y"] = results["3y"]
            if results["3y"].get("rules"):
                result.remark_3y = ";".join(results["3y"]["rules"])

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
        """RDS 价格查询"""
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
                    result.error_message = f"JSON 解析失败:{e}"
                    return result

        result.error_message = "无有效响应数据"
        return result


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("阿里云 OpenAPI MCP 客户端测试(AK 模式)")
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
        print(f"   1 年目录价: ¥{result.price_1y_list:.2f}")
        print(f"   1 年折扣价: ¥{result.price_1y_discount:.2f}")
        print(f"   3 年目录价: ¥{result.price_3y_list:.2f}")
        print(f"   3 年折扣价: ¥{result.price_3y_discount:.2f}")
        if result.remark:
            print(f"   折扣规则: {result.remark}")
    else:
        print(f"\n❌ 查询失败: {result.error_message}")

    client.close()
