#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 公共模块 — 场景一和场景二共用
包含：引擎映射、存储类型、地域映射、价格解析、6折策略等
"""

import os
import json
import re
from typing import Dict, List, Optional

# ============================================================
# 常量定义
# ============================================================

# 引擎标准化映射
ENGINE_MAP: Dict[str, str] = {
    "mysql": "MySQL",
    "mssql": "SQLServer",
    "sqlserver": "SQLServer",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "pg": "PostgreSQL",
    "pgsql": "PostgreSQL",
    "mariadb": "MariaDB",
}

# 引擎默认最高版本
ENGINE_DEFAULT_VERSIONS: Dict[str, str] = {
    "MySQL": "8.0",
    "SQLServer": "2022",
    "PostgreSQL": "18.0",
    "MariaDB": "10.6",
}

# MariaDB 仅支持的版本
MARIADB_SUPPORTED_VERSIONS = {"10.3", "10.6"}

# MariaDB 默认存储类型（ESSD PL1）
MARIADB_DEFAULT_STORAGE_TYPE = "cloud_essd"

# 支持的引擎列表
SUPPORTED_ENGINES = {"MySQL", "SQLServer", "PostgreSQL", "MariaDB"}

# ClassCode 前缀推导 Engine
CLASSCODE_ENGINE_MAP: Dict[str, str] = {
    "mysql": "MySQL", "rds.mysql": "MySQL",
    "pg": "PostgreSQL",
    "mssql": "SQLServer",
    "mariadb": "MariaDB",
}

# 存储类型映射
STORAGE_TYPE_MAP: Dict[str, str] = {
    "general_essd": "高性能云盘",
    "local_ssd": "高性能本地盘",
    "cloud_ssd": "SSD 云盘",
    "cloud_essd": "ESSD PL1 云盘",
    "cloud_essd2": "ESSD PL2 云盘",
    "cloud_essd3": "ESSD PL3 云盘",
}

# 存储类型关键词反向映射（用户输入 → 代码）
# ⚠️ 使用有序列表，更具体的关键词必须排在前面
STORAGE_KEYWORD_LIST: List[tuple] = [
    ("essd pl3", "cloud_essd3"),
    ("essd pl2", "cloud_essd2"),
    ("essd pl1", "cloud_essd"),
    ("cloud_essd3", "cloud_essd3"),
    ("cloud_essd2", "cloud_essd2"),
    ("cloud_essd", "cloud_essd"),
    ("高性能本地盘", "local_ssd"),
    ("local_ssd", "local_ssd"),
    ("本地盘", "local_ssd"),
    ("ssd云盘", "cloud_ssd"),
    ("cloud_ssd", "cloud_ssd"),
    ("高性能云盘", "general_essd"),
    ("general_essd", "general_essd"),
]

# 系列显示名称
CATEGORY_DISPLAY: Dict[str, str] = {
    "Basic": "基础系列",
    "HighAvailability": "高可用系列",
    "Cluster": "集群系列",
    "Finance": "金融云系列",
}

# 用户输入关键词 → category 代码
CATEGORY_INPUT_MAP: Dict[str, str] = {
    "基础系列": "Basic",
    "基础": "Basic",
    "Basic": "Basic",
    "单机": "Basic",
    "高可用系列": "HighAvailability",
    "高可用": "HighAvailability",
    "HighAvailability": "HighAvailability",
    "HA": "HighAvailability",
    "集群系列": "Cluster",
    "集群": "Cluster",
    "Cluster": "Cluster",
}

# 地域代码 → 中文名称
REGION_CODE_TO_NAME: Dict[str, str] = {
    "cn-qingdao": "华北 1（青岛）",
    "cn-beijing": "华北 2（北京）",
    "cn-zhangjiakou": "华北 3（张家口）",
    "cn-huhehaote": "华北 5（呼和浩特）",
    "cn-wulanchabu": "华北 6（乌兰察布）",
    "cn-hangzhou": "华东 1（杭州）",
    "cn-shanghai": "华东 2（上海）",
    "cn-nanjing": "华东 5（南京）",
    "cn-fuzhou": "华东 6（福州）",
    "cn-guangzhou": "华南 3（广州）",
    "cn-shenzhen": "华南 1（深圳）",
    "cn-heyuan": "华南 2（河源）",
    "cn-chengdu": "西南 1（成都）",
    "cn-hongkong": "中国香港",
    "ap-southeast-1": "新加坡",
    "ap-southeast-2": "悉尼",
    "ap-southeast-3": "吉隆坡",
    "ap-southeast-5": "雅加达",
    "ap-northeast-1": "东京",
    "ap-northeast-2": "首尔",
    "us-west-1": "硅谷",
    "us-east-1": "弗吉尼亚",
    "eu-central-1": "法兰克福",
    "me-east-1": "迪拜",
}

# 地域关键词 → 代码
REGION_KEYWORD_TO_CODE: Dict[str, str] = {
    "杭州": "cn-hangzhou", "华东1": "cn-hangzhou", "华东 1": "cn-hangzhou",
    "上海": "cn-shanghai", "华东2": "cn-shanghai", "华东 2": "cn-shanghai",
    "北京": "cn-beijing", "华北2": "cn-beijing", "华北 2": "cn-beijing",
    "深圳": "cn-shenzhen", "华南1": "cn-shenzhen", "华南 1": "cn-shenzhen",
    "广州": "cn-guangzhou", "华南3": "cn-guangzhou", "华南 3": "cn-guangzhou",
    "成都": "cn-chengdu", "西南1": "cn-chengdu", "西南 1": "cn-chengdu",
    "青岛": "cn-qingdao", "华北1": "cn-qingdao", "华北 1": "cn-qingdao",
    "张家口": "cn-zhangjiakou", "华北3": "cn-zhangjiakou", "华北 3": "cn-zhangjiakou",
    "呼和浩特": "cn-huhehaote", "华北5": "cn-huhehaote", "华北 5": "cn-huhehaote",
    "乌兰察布": "cn-wulanchabu", "华北6": "cn-wulanchabu", "华北 6": "cn-wulanchabu",
    "南京": "cn-nanjing", "华东5": "cn-nanjing", "华东 5": "cn-nanjing",
    "福州": "cn-fuzhou", "华东6": "cn-fuzhou", "华东 6": "cn-fuzhou",
    "河源": "cn-heyuan", "华南2": "cn-heyuan", "华南 2": "cn-heyuan",
    "香港": "cn-hongkong", "中国香港": "cn-hongkong",
    "新加坡": "ap-southeast-1",
    "东京": "ap-northeast-1",
    "首尔": "ap-northeast-2",
    "硅谷": "us-west-1",
    "弗吉尼亚": "us-east-1",
    "法兰克福": "eu-central-1",
}

# SQLServer 后缀 → 默认系列
MSSQL_SUFFIX_SERIES_MAP: Dict[str, Optional[str]] = {
    "e1": "Basic",
    "w1": "Basic",
    "s1": "Basic",
    "s2": "HighAvailability",
    "s2b": "HighAvailability",
    "2": "HighAvailability",
    "e2b": "HighAvailability",
    "e2": None,  # 模糊，运行时判断
}

# ClassGroup 优先级（越小越优先）
CLASS_GROUP_PRIORITY: Dict[str, int] = {
    "通用型": 1,
    "独享套餐": 2,
    "独享型": 2,
    "独享规格": 2,
    "共享型": 3,
    "经济型": 4,
    "独占物理机": 5,
}
DEFAULT_CLASS_GROUP_PRIORITY = 99

# 用户输入关键词 → storageType（模糊匹配）
# "Local" = 高性能本地盘
# "Cloud" = 高性能云盘、ESSD PL1/PL2/PL3（默认值）
STORAGE_TYPE_RAW_MAP: List[tuple] = [
    ("本地盘", "Local"),
    ("高性能本地盘", "Local"),
    ("local_ssd", "Local"),
    ("local", "Local"),
    ("高性能云盘", "Cloud"),
    ("general_essd", "Cloud"),
    ("essd pl1", "Cloud"),
    ("essd pl2", "Cloud"),
    ("essd pl3", "Cloud"),
    ("cloud_essd", "Cloud"),
    ("cloud_essd2", "Cloud"),
    ("cloud_essd3", "Cloud"),
    ("cloud_ssd", "Cloud"),
    ("ssd", "Cloud"),
    ("cloud", "Cloud"),
]


def resolve_storage_type_raw(text: str) -> str:
    """
    从用户输入文本解析 storageType（Local 或 Cloud）
    用户未提供时返回空字符串（默认 Cloud）
    """
    if not text:
        return ""
    text_lower = text.lower()
    for keyword, st in STORAGE_TYPE_RAW_MAP:
        if keyword.lower() in text_lower:
            return st
    return ""

# 用户输入关键词 → ClassGroup（模糊匹配）
CLASS_GROUP_KEYWORD_MAP: List[tuple] = [
    ("通用型", "通用型"),
    ("通用", "通用型"),
    ("独享套餐", "独享套餐"),
    ("独享型", "独享套餐"),
    ("独享规格", "独享套餐"),
    ("独享", "独享套餐"),
    ("共享型", "共享型"),
    ("共享", "共享型"),
    ("经济型", "经济型"),
    ("经济", "经济型"),
    ("独占物理机", "独占物理机"),
    ("独占", "独占物理机"),
    ("物理机", "独占物理机"),
]


def resolve_class_group(text: str) -> str:
    """
    从用户输入文本解析 ClassGroup
    """
    if not text:
        return ""
    text_lower = text.lower()
    for keyword, group in CLASS_GROUP_KEYWORD_MAP:
        if keyword.lower() in text_lower:
            return group
    return ""

# ============================================================
# 公共函数
# ============================================================


def normalize_engine(text: str) -> str:
    """
    引擎标准化
    例：'mysql' → 'MySQL', 'SQLServer' → 'SQLServer'
    """
    if not text:
        return "MySQL"
    key = text.lower().strip()
    return ENGINE_MAP.get(key, text.strip())


def extract_memory_from_memoryclass(memory_class: str) -> int:
    """
    从 MemoryClass 提取内存 GB 数
    例：" 8GB（独享型）" → 8, "384GB(独享型)" → 384
    """
    if not memory_class:
        return 0
    match = re.search(r'(\d+)\s*G(?:B)?', memory_class, re.IGNORECASE)
    return int(match.group(1)) if match else 0


def extract_cpu_from_memoryclass(memory_class: str) -> Optional[int]:
    """
    从 MemoryClass 提取 CPU 核数（如果包含的话）
    例："4核 8GB（独享型）" → 4
    注意：通常 Cpu 字段已单独提供，此函数用于补充校验
    """
    if not memory_class:
        return None
    match = re.search(r'(\d+)\s*核', memory_class)
    return int(match.group(1)) if match else None


def normalize_engine_version(engine: str, version: str) -> str:
    """
    版本标准化
    """
    if not version:
        return ENGINE_DEFAULT_VERSIONS.get(engine, "")

    version = version.strip()
    engine_lower = engine.lower()

    # SQLServer 特殊处理
    if engine_lower in ('mssql', 'sqlserver'):
        match = re.search(r'(\d{4})', version)
        if match:
            year = match.group(1)
            edition = ""
            version_lower = version.lower()
            if '_ent' in version_lower:
                edition = " 企业集群版" if 'cluster' in version_lower else " 企业版"
            elif '_ent_ha' in version_lower:
                edition = " 企业版"
            elif '_std_ha' in version_lower:
                edition = " 标准版"
            elif '_web' in version_lower:
                edition = " Web 版"
            elif '集群' in version:
                edition = " 企业集群版"
            elif '企业' in version:
                edition = " 企业版"
            elif '标准' in version:
                edition = " 标准版"
            elif 'web' in version_lower:
                edition = " Web 版"
            return f"{year}{edition}"
        return version

    # 其他引擎直接返回清理后的版本
    return version


def format_engine_version_for_api(engine: str, version: str) -> str:
    """
    格式化引擎版本为 API 需要的格式
    PostgreSQL: "14" → "14.0", "18" → "18.0"
    MySQL: "8.0" → "8.0" (保持不变)
    SQLServer: "2022" → "2022" (保持不变)
    """
    if not version:
        return ENGINE_DEFAULT_VERSIONS.get(engine, "")
    
    engine_lower = engine.lower()
    # PostgreSQL 纯数字版本 → 添加 .0
    if engine_lower == 'postgresql' and '.' not in version:
        return f"{version}.0"
    
    return version


def get_region_name(code: str) -> str:
    """地域代码转中文名称"""
    if not code:
        return "华东 1（杭州）"
    if '(' in code or '（' in code:
        return code
    return REGION_CODE_TO_NAME.get(code, code)


def get_storage_type_name(code: str) -> str:
    """存储类型代码转中文名称"""
    if not code:
        return "高性能云盘"
    return STORAGE_TYPE_MAP.get(code, code)


def get_category_display(category: str) -> str:
    """系列代码转中文显示名"""
    if not category:
        return ""
    return CATEGORY_DISPLAY.get(category, category)


def resolve_storage_type(text: str) -> str:
    """
    从用户输入文本解析存储类型代码
    用户未提供时返回空字符串，由验证器根据 JSON 推导
    """
    if not text:
        return ""
    text_lower = text.lower()
    for keyword, code in STORAGE_KEYWORD_LIST:
        if keyword in text_lower:
            return code
    return ""


def resolve_region(text: str) -> str:
    """
    从用户输入文本解析地域代码
    优先匹配 cn-xxx 格式，其次匹配中文关键词
    """
    if not text:
        return "cn-hangzhou"

    # 直接匹配地域代码
    code_match = re.match(r'^(cn-\w+|ap-\w+-\d+|us-\w+-\d+|eu-\w+-\d+|me-\w+-\d+)$', text.strip())
    if code_match:
        return code_match.group(1)

    # 匹配中文关键词
    for keyword, code in REGION_KEYWORD_TO_CODE.items():
        if keyword in text:
            return code

    return "cn-hangzhou"


def resolve_category(text: str) -> str:
    """
    从用户输入文本解析产品系列
    """
    if not text:
        return ""
    for keyword, cat in CATEGORY_INPUT_MAP.items():
        if keyword in text:
            return cat
    return ""


def resolve_storage(text: str) -> int:
    """
    从用户输入文本解析存储大小（GB）
    """
    if not text:
        return 100

    # 匹配 TB
    tb_match = re.search(r'(\d+(?:\.\d+)?)\s*[tT][bB]?', text)
    if tb_match:
        return int(float(tb_match.group(1)) * 1024)

    # 匹配 GB
    gb_match = re.search(r'(\d+)\s*[gG][bB]?', text)
    if gb_match:
        return int(gb_match.group(1))

    return 100


def resolve_engine_version_raw(text: str) -> str:
    """
    从用户输入中提取版本号的原始文本（保留"企业集群版"等中文描述）
    """
    if not text:
        return ""
    # 匹配数字版本号（包含后续中文描述）
    match = re.search(r'(\d+(?:\.\d+)*(?:\s*[\u4e00-\u9fff]+(?:版)?)*)', text)
    return match.group(1).strip() if match else ""


def resolve_engine_version_for_api(version_raw: str) -> str:
    """
    将用户原始版本文本转为 API 需要的版本号
    """
    if not version_raw:
        return ""
    # 提取纯数字版本
    match = re.match(r'(\d+(?:\.\d+)*)', version_raw)
    return match.group(1) if match else version_raw


def get_class_group_priority(class_group: str) -> int:
    """
    获取 ClassGroup 优先级数字（越小越优先）
    """
    if not class_group:
        return DEFAULT_CLASS_GROUP_PRIORITY
    return CLASS_GROUP_PRIORITY.get(class_group, DEFAULT_CLASS_GROUP_PRIORITY)


def derive_engine_from_classcode(class_code: str) -> str:
    """
    从 ClassCode 前缀推导数据库引擎类型
    """
    if not class_code:
        return ""
    cc_lower = class_code.lower()

    # 按最长前缀优先匹配
    for prefix, engine in sorted(CLASSCODE_ENGINE_MAP.items(), key=lambda x: -len(x[0])):
        if cc_lower.startswith(prefix):
            return engine

    return ""


def parse_price_response(content: list, period: str) -> dict:
    """
    解析 DescribePrice API 响应

    Args:
        content: MCP 返回的 content 数组
        period: "1y" 或 "3y"

    Returns:
        {
            "price_list": float or None,
            "price_discount": float or None,
            "activity_name": str or None,
            "stand_price": float or None,
            "module_instances": list,
            "success": bool,
            "error_reason": str or None
        }
    """
    result = {
        "price_list": None,
        "price_discount": None,
        "activity_name": None,
        "stand_price": None,
        "module_instances": [],
        "success": False,
        "error_reason": None,
    }

    for item in content:
        if item.get("type") == "text":
            text = item.get("text", "")
            try:
                data = json.loads(text)
                if "code" in data and data["code"] < 0:
                    result["error_reason"] = data.get('message', '未知错误')
                    return result

                price_info = data.get("PriceInfo", {})
                order_lines = price_info.get("OrderLines", {})
                order_line = order_lines.get("0", {})
                depreciate_info = order_line.get("depreciateInfo", {})
                final_activity = depreciate_info.get("finalActivity", {})

                result["price_list"] = price_info.get("OriginalPrice")
                result["price_discount"] = final_activity.get("finalFee") if final_activity else None
                result["activity_name"] = final_activity.get("activityName") if final_activity else None
                result["stand_price"] = order_line.get("standPrice")
                result["module_instances"] = order_line.get("moduleInstance", [])

                if result["price_list"] is None:
                    result["error_reason"] = "缺少 PriceInfo.OriginalPrice"
                elif result["price_discount"] is None:
                    result["error_reason"] = "缺少 finalActivity.finalFee"
                elif result["activity_name"] is None:
                    result["error_reason"] = "缺少 finalActivity.activityName"
                else:
                    result["success"] = True

                return result

            except json.JSONDecodeError as e:
                result["error_reason"] = f"JSON 解析失败：{e}"
                return result

    result["error_reason"] = "无有效响应数据"
    return result


def build_rds_price_command(region: str, engine: str, engine_version: str,
                            db_instance_class: str, db_instance_storage: int,
                            db_instance_storage_type: str, period: int) -> str:
    """
    构建 RDS DescribePrice CLI 命令
    """
    return " ".join([
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


def apply_six_discount_policy(all_results: list):
    """
    6 折分配策略：
    - 筛选命中"新客首购云数据库 RDS 1年享6折优惠"的实例
    - 选 1 年目录价最高的 1 台应用 6 折（finalFee）
    - 其余命中 6 折的使用 standPrice
    """
    six_discount_candidates = [
        idx for idx, result in enumerate(all_results)
        if result.get("activity_name_1y") and
           "新客首购云数据库 RDS 1年享6折优惠，限1次，限1件" in result["activity_name_1y"]
    ]

    if len(six_discount_candidates) > 0:
        best_index = max(
            six_discount_candidates,
            key=lambda idx: all_results[idx].get("price_1y_list") or 0
        )
        all_results[best_index]["is_promotion_applied"] = True

    for idx, result in enumerate(all_results):
        if not result.get("is_promotion_applied"):
            if result.get("activity_name_1y") and \
               "新客首购云数据库 RDS 1年享6折优惠，限1次，限1件" in result["activity_name_1y"]:
                result["use_stand_price"] = True
