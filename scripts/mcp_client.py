#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 OpenAPI MCP 客户端
使用 JSON-RPC 2.0 协议调用 MCP Server
支持 OAuth PKCE 认证
"""

import os
import json
import time
import hashlib
import base64
import secrets
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

# OAuth Token 刷新端点
OAUTH_TOKEN_URL = "https://oauth.aliyun.com/v1/token"


@dataclass
class PriceResult:
    """价格查询结果"""
    success: bool
    price_1y_list: Optional[float] = None      # 官网目录价（1 年）
    price_1y_discount: Optional[float] = None  # 官网折扣价（1 年）
    price_3y_list: Optional[float] = None      # 官网目录价（3 年）
    price_3y_discount: Optional[float] = None  # 官网折扣价（3 年）
    remark_1y: str = ""                         # 1 年折扣说明
    remark_3y: str = ""                         # 3 年折扣说明
    remark: str = ""                            # 备注（合并显示）
    error_message: str = ""                     # 错误信息
    detail_info: Dict = field(default_factory=dict)  # 详细信息
    is_spec_error: bool = False                 # 是否是规格错误


class MCPClient:
    """
    阿里云 OpenAPI MCP 客户端
    
    使用 JSON-RPC 2.0 协议调用 MCP Server
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
        
        self.config_dir = config_dir
        
        # 统一从 config.json 读取所有配置
        self.config = self._load_config("config.json")
        
        # 从统一配置中提取各部分
        mcp_config = self.config.get("mcp", {})
        self.endpoint = mcp_config.get("endpoint", "")
        
        self.session_id: Optional[str] = None
        self.token_data: Optional[Dict] = self.config.get("token")
    
    def _load_config(self, filename: str) -> Dict:
        """加载配置文件"""
        config_path = os.path.join(self.config_dir, filename)
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_config(self, filename: str, data: Dict) -> None:
        """保存配置文件"""
        config_path = os.path.join(self.config_dir, filename)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _get_access_token(self) -> str:
        """获取 Access Token，过期时自动刷新"""
        if not self.token_data or "access_token" not in self.token_data:
            raise ValueError("未找到 Access Token，请先完成 OAuth 授权")

        # 检查是否过期（预留 5 分钟缓冲）
        expires_at = self.token_data.get("expires_at", 0)
        if expires_at and time.time() >= expires_at - 300:
            # Token 已过期或即将过期，尝试自动刷新
            self._auto_refresh_token()

        return self.token_data["access_token"]

    def _auto_refresh_token(self) -> None:
        """使用 refresh_token 自动刷新 access_token"""
        refresh_token = self.token_data.get("refresh_token")
        if not refresh_token:
            raise ValueError("未找到 Refresh Token，无法自动刷新，请重新完成 OAuth 授权")

        app_id = self.config.get("oauth", {}).get("app_id", "")
        if not app_id:
            raise ValueError("未配置 app_id，无法刷新 Token")

        # 调用 OAuth Token 刷新端点
        post_data = urllib.parse.urlencode({
            "grant_type": "refresh_token",
            "client_id": app_id,
            "refresh_token": refresh_token,
        }).encode("utf-8")

        req = urllib.request.Request(
            OAUTH_TOKEN_URL,
            data=post_data,
            method="POST",
        )
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

        # 更新内存中的 token 数据
        self.token_data["access_token"] = token_resp["access_token"]
        self.token_data["expires_at"] = time.time() + token_resp.get("expires_in", 3600)

        # 如果返回了新的 refresh_token，一并保存（阿里云可能轮换）
        if "refresh_token" in token_resp:
            self.token_data["refresh_token"] = token_resp["refresh_token"]

        # 持久化到 config.json
        self.config["token"] = self.token_data
        self._save_config("config.json", self.config)
    
    def _init_session(self) -> str:
        """
        初始化 MCP Session
        
        Returns:
            Session ID
        """
        if self.session_id:
            return self.session_id
        
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "aliyun-price-query",
                    "version": "1.0.0"
                }
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
    
    def _call_tool(self, tool_name: str, arguments: Dict) -> Dict:
        """
        调用 MCP Tool
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            调用结果
        """
        session_id = self._init_session()
        
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
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
                result = json.loads(response.read().decode('utf-8'))
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            return {"error": f"HTTP {e.code}", "details": error_body}
    
    def _build_cli_command(self, region: str, instance_spec: str,
                           system_disk_type: str = "cloud_essd",
                           system_disk_size: int = 40,
                           system_disk_pl: str = "PL0",
                           data_disk_type: str = None,
                           data_disk_size: int = 0,
                           data_disk_pl: str = "PL0",
                           data_disks: list = None,  # 新增：多数据盘 [{'category': 'cloud_essd', 'size': 500, 'pl': 'PL1'}, ...]
                           bandwidth: int = 0,
                           bandwidth_charge_type: str = "PayByBandwidth",
                           image_id: str = None,
                           period: int = 1,
                           price_unit: str = "Year") -> str:
        """
        构建 ECS 价格查询 CLI 命令
        
        Args:
            region: 地域代码
            instance_spec: 实例规格
            system_disk_type: 系统盘类型
            system_disk_size: 系统盘大小（GiB）
            system_disk_pl: 系统盘性能等级
            data_disk_type: 数据盘类型（兼容旧参数）
            data_disk_size: 数据盘大小（GiB）（兼容旧参数）
            data_disk_pl: 数据盘性能等级（兼容旧参数）
            data_disks: 多数据盘列表 [{'category': 'cloud_essd', 'size': 500, 'pl': 'PL1'}, ...]
            bandwidth: 公网带宽（Mbps）
            bandwidth_charge_type: 带宽计费方式
            image_id: 镜像 ID
            period: 购买时长
            price_unit: 价格单位（Year/Month/Hour）
            
        Returns:
            CLI 命令字符串
        """
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
        
        # 数据盘（支持多数据盘）
        if data_disks:
            # 新格式：多数据盘列表
            for i, disk in enumerate(data_disks, 1):
                disk_category = disk.get('category', 'cloud_essd')
                disk_size = disk.get('size', 0)
                disk_pl = disk.get('pl', 'PL0')
                cmd_parts.extend([
                    f"--DataDisk.{i}.Category {disk_category}",
                    f"--DataDisk.{i}.Size {disk_size}"
                ])
                # 只有 ESSD 才有 PerformanceLevel
                if disk_category == 'cloud_essd' and disk_pl:
                    cmd_parts.append(f"--DataDisk.{i}.PerformanceLevel {disk_pl}")
        elif data_disk_type and data_disk_size > 0:
            # 兼容旧格式：单个数据盘
            cmd_parts.extend([
                f"--DataDisk.1.Category {data_disk_type}",
                f"--DataDisk.1.Size {data_disk_size}",
                f"--DataDisk.1.PerformanceLevel {data_disk_pl}"
            ])
        
        # 公网带宽
        if bandwidth > 0:
            cmd_parts.extend([
                f"--InternetChargeType {bandwidth_charge_type}",
                f"--InternetMaxBandwidthOut {bandwidth}"
            ])
        
        # 镜像
        if image_id:
            cmd_parts.append(f"--ImageId {image_id}")
        
        return " \\\n  ".join(cmd_parts)
    
    def _parse_price_result(self, response_text: str) -> Dict:
        """
        解析价格查询结果
        
        Args:
            response_text: API 响应文本
            
        Returns:
            解析后的价格信息
        """
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
        
        # 解析明细
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
                        data_disks: list = None,  # 新增：多数据盘
                        bandwidth: int = 0,
                        bandwidth_charge_type: str = "PayByBandwidth",
                        image_id: str = None) -> PriceResult:
        """
        查询 ECS 价格（1 年和 3 年）
        
        Args:
            region: 地域代码（如 cn-hangzhou）
            instance_spec: 实例规格代码（如 ecs.u1-c1m2.xlarge）
            system_disk_type: 系统盘类型
            system_disk_size: 系统盘容量（GiB）
            system_disk_pl: 系统盘性能等级（PL0/PL1）
            data_disk_type: 数据盘类型（兼容旧参数）
            data_disk_size: 数据盘容量（GiB）（兼容旧参数）
            data_disk_pl: 数据盘性能等级（兼容旧参数）
            data_disks: 多数据盘列表 [{'category': 'cloud_essd', 'size': 500, 'pl': 'PL1'}, ...]
            bandwidth: 公网带宽（Mbps）
            bandwidth_charge_type: 带宽计费方式
            image_id: 镜像 ID
            
        Returns:
            PriceResult 价格查询结果
        """
        results = {}
        errors = []
        
        # 查询 1 年价格
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
                period=1,
                price_unit="Year"
            )
            
            response = self._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd})
            
            content = response.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    data = json.loads(text)
                    
                    if "code" in data and data["code"] < 0:
                        errors.append(f"1年价格查询失败: {data.get('message', '未知错误')}")
                    else:
                        results["1y"] = self._parse_price_result(text)
                        
        except Exception as e:
            errors.append(f"1年价格查询异常: {str(e)}")
        
        # 查询 3 年价格
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
                period=3,
                price_unit="Year"
            )
            
            response = self._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd})
            
            content = response.get("result", {}).get("content", [])
            for item in content:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    data = json.loads(text)
                    
                    if "code" in data and data["code"] < 0:
                        errors.append(f"3年价格查询失败: {data.get('message', '未知错误')}")
                    else:
                        results["3y"] = self._parse_price_result(text)
                        
        except Exception as e:
            errors.append(f"3年价格查询异常: {str(e)}")
        
        # 构建返回结果
        if errors and not results:
            return PriceResult(
                success=False,
                error_message="; ".join(errors)
            )
        
        result = PriceResult(success=True)
        
        if "1y" in results:
            result.price_1y_list = results["1y"].get("original_price")
            result.price_1y_discount = results["1y"].get("trade_price")
            result.detail_info["1y"] = results["1y"]
            # 1 年折扣说明
            if results["1y"].get("rules"):
                result.remark_1y = "；".join(results["1y"]["rules"])
        
        if "3y" in results:
            result.price_3y_list = results["3y"].get("original_price")
            result.price_3y_discount = results["3y"].get("trade_price")
            result.detail_info["3y"] = results["3y"]
            # 3 年折扣说明
            if results["3y"].get("rules"):
                result.remark_3y = "；".join(results["3y"]["rules"])
        
        # 合并折扣规则到备注
        remarks = []
        if result.remark_1y:
            remarks.append(f"【1年】{result.remark_1y}")
        if result.remark_3y:
            remarks.append(f"【3年】{result.remark_3y}")
        result.remark = "\n".join(remarks) if remarks else ""
        
        if errors:
            result.remark += f"\n(部分失败: {'; '.join(errors)})"
        
        return result
    
    def list_tools(self) -> List[Dict]:
        """
        列出可用的 MCP 工具
        
        Returns:
            工具列表
        """
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


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("阿里云 OpenAPI MCP 客户端测试")
    print("=" * 60)
    
    client = MCPClient()
    
    # 列出工具
    print("\n可用工具:")
    tools = client.list_tools()
    for tool in tools:
        print(f"  - {tool.get('name')}")
    
    # 测试价格查询
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