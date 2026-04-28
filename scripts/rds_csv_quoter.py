#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 实例清单 CSV 自动报价
解析阿里云控制台导出的 RDS 实例清单 CSV 文件，自动生成报价单
"""

import os
import sys
import csv
import re
import json
from typing import List, Dict, Optional
from dataclasses import dataclass

# 添加脚本目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from rds_constants import REGION_CODE_TO_NAME, STORAGE_TYPE_MAP
from rds_excel_generator import RDSExcelGenerator, create_rds_product_desc
from mcp_client import MCPClient


@dataclass
class RDSInstanceConfig:
    """RDS 实例配置"""
    region_id: str = ""
    engine: str = ""
    engine_version: str = ""
    db_instance_class: str = ""
    db_instance_storage: int = 0
    db_instance_storage_type: str = ""
    db_instance_type: str = ""
    category: str = ""  # 系列：cluster, HighAvailability, Basic


def parse_csv(csv_path: str) -> List[RDSInstanceConfig]:
    """
    解析 RDS CSV 文件
    
    Args:
        csv_path: CSV 文件路径
        
    Returns:
        RDS 实例配置列表
    """
    instances = []
    
    # 尝试多种编码
    encodings = ['utf-8', 'gbk', 'gb2312', 'iso-8859-1']
    rows = []
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                # 检查是否有必需字段
                if rows and 'DBInstanceClass(实例规格)' in reader.fieldnames:
                    break
        except UnicodeDecodeError:
            continue
    
    if not rows:
        print("⚠️ 无法解析 CSV 文件，请检查文件格式")
        return instances
    
    for row in rows:
        # 解析存储大小
        storage_str = row.get('DBInstanceStorage(存储（GB）)', '0')
        try:
            storage = int(storage_str) if storage_str.isdigit() else 0
        except ValueError:
            storage = 0
        
        # 创建实例配置
        instance = RDSInstanceConfig(
            region_id=row.get('RegionId(地域)', ''),
            engine=row.get('Engine(数据库类型)', ''),
            engine_version=row.get('EngineVersion(数据库版本)', ''),
            db_instance_class=row.get('DBInstanceClass(实例规格)', ''),
            db_instance_storage=storage,
            db_instance_storage_type=row.get('DBInstanceStorageType(存储类型)', ''),
            db_instance_type=row.get('DBInstanceType(实例类型)', ''),
            category=row.get('Category(系列)', '')  # 集群系列需要 DBNode 参数
        )
        instances.append(instance)
    
    return instances


def get_region_name(region_code: str) -> str:
    """
    根据地域代码获取中文名称
    
    Args:
        region_code: 地域代码，如 "cn-beijing"
        
    Returns:
        中文名称，如 "华北 2（北京）"
    """
    if not region_code:
        return "华北 2（北京）"
    
    # 如果已经是中文名称，直接返回
    if '(' in region_code or '（' in region_code:
        return region_code
    
    # 查找映射
    return REGION_CODE_TO_NAME.get(region_code, region_code)


def normalize_engine(engine: str) -> str:
    """
    标准化引擎名称（用于 API 调用，需要正确的大小写）
    
    Args:
        engine: 原始引擎名称
        
    Returns:
        标准化后的引擎名称（首字母大写）
    """
    if not engine:
        return "MySQL"
    
    engine_lower = engine.lower().strip()
    
    if engine_lower in ['mysql']:
        return "MySQL"
    elif engine_lower in ['mssql', 'sqlserver', 'sql server']:
        return "SQLServer"
    elif engine_lower in ['postgresql', 'postgres']:
        return "PostgreSQL"
    elif engine_lower in ['mariadb']:
        return "MariaDB"
    
    return engine.capitalize()


def normalize_engine_version(engine: str, version: str) -> str:
    """
    标准化引擎版本
    
    Args:
        engine: 引擎类型
        version: 原始版本号
        
    Returns:
        标准化后的版本号
    """
    if not version:
        return ""
    
    # 清理版本号
    version = version.strip()
    
    # SQLServer 特殊处理
    if engine.lower() == 'mssql':
        # 提取年份
        match = re.search(r'(\d{4})', version)
        if match:
            year = match.group(1)
            # 检查版本后缀
            edition = ""
            if '_ent' in version.lower():
                edition = " 企业集群版"
            elif '_ent_ha' in version.lower():
                edition = " 企业版"
            elif '_std_ha' in version.lower():
                edition = " 标准版"
            elif '_web' in version.lower():
                edition = " Web 版"
            return f"{year}{edition}"
        return version
    
    # 其他引擎直接返回清理后的版本
    return version


def get_storage_type_name(storage_type: str) -> str:
    """
    根据存储类型代码获取中文名称
    
    Args:
        storage_type: 存储类型代码
        
    Returns:
        中文名称
    """
    if not storage_type:
        return "高性能云盘"
    
    return STORAGE_TYPE_MAP.get(storage_type, "高性能云盘")


def get_series(engine: str, instance_class: str, category: str = "") -> str:
    """
    根据引擎和规格代码获取产品系列
    
    Args:
        engine: 引擎类型
        instance_class: 实例规格代码
        category: CSV 中的 Category 字段（如果有）
        
    Returns:
        产品系列
    """
    engine_lower = engine.lower()
    instance_class_lower = instance_class.lower()
    
    # 判断产品系列
    if category:
        if category.lower() == "cluster":
            return "集群系列"
        elif category.lower() == "highavailability":
            return "高可用系列"
        elif category.lower() == "basic":
            return "基础系列"
        else:
            # 根据规格代码判断
            if 'sharding' in instance_class_lower:
                return "集群系列"
            elif instance_class_lower.startswith('mysql.n') or instance_class_lower.startswith('pg.n'):
                return "基础系列"
            else:
                return "高可用系列"
    else:
        # 没有 category 字段，根据规格代码判断
        if 'sharding' in instance_class_lower:
            return "集群系列"
        elif instance_class_lower.startswith('mysql.n') or instance_class_lower.startswith('pg.n'):
            return "基础系列"
        else:
            return "高可用系列"


def get_spec_description(module_instances: list) -> str:
    """
    从 moduleInstance 获取规格描述
    
    Args:
        module_instances: MCP 返回的 moduleInstance 列表
        
    Returns:
        规格描述，如 "4 核 16GB（独享型）"
    """
    if not module_instances:
        return ""
    
    # 从 rds_class 模块获取规格描述
    for mi in module_instances:
        if mi.get("moduleCode") == "rds_class":
            module_attrs = mi.get("moduleAttrs", [])
            for attr in module_attrs:
                if attr.get("code") == "rds_class":
                    name = attr.get("name", "")
                    if name:
                        return name
    
    return ""


def build_rds_price_command(region: str, engine: str, engine_version: str,
                            db_instance_class: str, db_instance_storage: int,
                            db_instance_storage_type: str, instance_used_type: str,
                            period: int) -> str:
    """
    构建 RDS 价格查询 CLI 命令
    
    Args:
        region: 地域代码
        engine: 数据库引擎
        engine_version: 数据库版本
        db_instance_class: 实例规格
        db_instance_storage: 存储大小（GB）
        db_instance_storage_type: 存储类型
        instance_used_type: 实例类型（0 主实例、3 只读实例）
        period: 购买时长（1 或 3）
        
    Returns:
        CLI 命令字符串
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
        f"--InstanceUsedType {instance_used_type}",
        f"--OrderType BUY",
        f"--DBInstanceStorageType {db_instance_storage_type}"
    ])


def parse_price_response(content: list, period: str) -> dict:
    """
    解析价格响应
    
    Args:
        content: MCP 返回的 content 数组
        period: 时间段（"1 年"或"3 年"）
        
    Returns:
        {
            "price_list": float or None,
            "price_discount": float or None,
            "activity_name": str or None,
            "stand_price": float or None,  # 仅 1 年需要
            "module_instances": list,      # 仅 1 年需要
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
        "error_reason": None
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
                
                # 严格按照要求的字段映射
                result["price_list"] = price_info.get("OriginalPrice")
                result["price_discount"] = final_activity.get("finalFee") if final_activity else None
                result["activity_name"] = final_activity.get("activityName") if final_activity else None
                result["stand_price"] = order_line.get("standPrice")
                result["module_instances"] = order_line.get("moduleInstance", [])
                
                # 检查必需字段
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


def quote_instances(instances: List[RDSInstanceConfig]) -> Optional[str]:
    """
    对 RDS 实例列表进行报价
    
    Args:
        instances: RDS 实例配置列表
        
    Returns:
        Excel 文件路径
    """
    # 初始化 MCP 客户端
    client = MCPClient()
    
    # 初始化 Excel 生成器
    generator = RDSExcelGenerator()
    
    # 保存所有实例的报价结果（用于后续选择最贵的一台给 6 折优惠）
    all_results = []
    
    success_count = 0
    for i, instance in enumerate(instances, 1):
        print(f"正在查询 {i}/{len(instances)}: {instance.db_instance_class}...")
        
        # 标准化引擎名称
        engine = normalize_engine(instance.engine)
        
        # 标准化版本号
        engine_version = normalize_engine_version(engine, instance.engine_version)
        
        # 获取存储类型中文名称
        storage_type_name = get_storage_type_name(instance.db_instance_storage_type)
        
        # 获取产品系列（传入 category 参数）
        series = get_series(engine, instance.db_instance_class, instance.category)
        
        # 解析实例类型（0 主实例、3 只读实例）
        instance_used_type = "0"  # 默认主实例
        if instance.db_instance_type:
            if '只读' in instance.db_instance_type or 'ReadOnly' in instance.db_instance_type:
                instance_used_type = "3"
        
        # 解析地域代码
        region_code = instance.region_id if instance.region_id else 'cn-hangzhou'
        region_name = get_region_name(region_code)
        
        # 检查是否为集群系列（目前 DBNode 参数有格式问题，无法自动询价）
        is_cluster = instance.category.lower() == "cluster" if instance.category else False
        
        if is_cluster:
            print(f"  ⚠️ 集群系列实例，DBNode 参数格式问题，需要人工确认")
            # 构建产品描述
            series = get_series(engine, instance.db_instance_class)
            storage_type_name = get_storage_type_name(instance.db_instance_storage_type)
            product_desc = create_rds_product_desc(
                engine=engine,
                engine_version=engine_version,
                series="集群系列",
                storage_type=storage_type_name,
                spec_desc="",
                instance_class=instance.db_instance_class,
                storage=instance.db_instance_storage
            )
            generator.add_data_row(
                product_name="RDS",
                product_desc=product_desc,
                region=region_name,
                quantity=1,
                remark="⚠️ 集群系列实例，DBNode 参数格式问题，需要人工确认价格",
                is_error=True
            )
            continue
        
        try:
            # 查询 1 年价格
            cli_cmd_1y = build_rds_price_command(
                region=region_code,
                engine=engine,
                engine_version=engine_version,
                db_instance_class=instance.db_instance_class,
                db_instance_storage=instance.db_instance_storage,
                db_instance_storage_type=instance.db_instance_storage_type,
                instance_used_type=instance_used_type,
                period=1
            )
            
            response_1y = client._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd_1y})
            content_1y = response_1y.get("result", {}).get("content", [])
            
            # 解析 1 年价格
            result_1y = parse_price_response(content_1y, "1 年")
            if result_1y["success"]:
                print(f"  ✅ 1 年价格解析成功：listPrice={result_1y['price_list']}, discountPrice={result_1y['price_discount']}, activity={result_1y['activity_name'][:50]}...")
            else:
                print(f"  ❌ 1 年价格解析失败：{result_1y['error_reason']}")
            
            # 查询 3 年价格
            cli_cmd_3y = build_rds_price_command(
                region=region_code,
                engine=engine,
                engine_version=engine_version,
                db_instance_class=instance.db_instance_class,
                db_instance_storage=instance.db_instance_storage,
                db_instance_storage_type=instance.db_instance_storage_type,
                instance_used_type=instance_used_type,
                period=3
            )
            
            response_3y = client._call_tool("AlibabaCloud___CallCLI", {"command": cli_cmd_3y})
            content_3y = response_3y.get("result", {}).get("content", [])
            
            # 解析 3 年价格
            result_3y = parse_price_response(content_3y, "3 年")
            if result_3y["success"]:
                print(f"  ✅ 3 年价格解析成功：listPrice={result_3y['price_list']}, discountPrice={result_3y['price_discount']}, activity={result_3y['activity_name'][:50]}...")
            else:
                print(f"  ❌ 3 年价格解析失败：{result_3y['error_reason']}")
            
            # 检查是否成功获取价格
            if result_1y["success"] and result_3y["success"]:
                # 获取规格描述（从 moduleInstances 中获取）
                spec_desc = get_spec_description(result_1y["module_instances"])
                
                # 构建产品描述（不需要 architecture 参数）
                product_desc = create_rds_product_desc(
                    engine=engine,
                    engine_version=engine_version,
                    series=series,
                    storage_type=storage_type_name,
                    spec_desc=spec_desc,
                    instance_class=instance.db_instance_class,
                    storage=instance.db_instance_storage
                )
                
                # 保存结果（用于后续选择最贵的一台）
                all_results.append({
                    "index": len(all_results),
                    "product_desc": product_desc,
                    "region_name": region_name,
                    "price_1y_list": result_1y["price_list"],
                    "price_1y_discount": result_1y["price_discount"],
                    "activity_name_1y": result_1y["activity_name"],
                    "stand_price_1y": result_1y["stand_price"],
                    "price_3y_list": result_3y["price_list"],
                    "price_3y_discount": result_3y["price_discount"],
                    "activity_name_3y": result_3y["activity_name"],
                    "is_promotion_applied": False,
                    "use_stand_price": False
                })
                
                success_count += 1
                print(f"  ✅ 1 年折扣价：￥{result_1y['price_discount']:.2f}")
            else:
                # 构建失败原因
                missing_fields = []
                if not result_1y["success"]:
                    missing_fields.append(f"1 年：{result_1y['error_reason']}")
                if not result_3y["success"]:
                    missing_fields.append(f"3 年：{result_3y['error_reason']}")
                
                reason = "询价失败：缺少必要字段 (" + ", ".join(missing_fields) + ")"
                print(f"  ❌ {reason}")
                generator.add_data_row(
                    product_name="RDS",
                    product_desc=f"引擎：{engine} {engine_version}\n实例规格：{instance.db_instance_class}",
                    region=region_name,
                    quantity=1,
                    remark=reason,
                    is_error=True
                )
                
        except Exception as e:
            print(f"  ❌ 异常：{str(e)}")
            generator.add_data_row(
                product_name="RDS",
                product_desc=f"引擎：{engine} {engine_version}\n实例规格：{instance.db_instance_class}",
                region=region_name,
                quantity=1,
                remark=f"询价异常：{str(e)}",
                is_error=True
            )
    
    # 选择 1 年目录价最高的一台应用 6 折优惠
    # 筛选命中"新客首购 6 折"活动的实例
    six_discount_candidates = [
        (idx, result) for idx, result in enumerate(all_results)
        if result.get("activity_name_1y") and 
           "新客首购云数据库 RDS 1 年享 6 折优惠，限 1 次，限 1 件" in result["activity_name_1y"]
    ]
    
    if len(six_discount_candidates) > 0:
        # 选择 1 年官网目录价最高的一台
        best_index, _ = max(six_discount_candidates, key=lambda x: x[1]["price_1y_list"] or 0)
        all_results[best_index]["is_promotion_applied"] = True
        print(f"  🎯 选择第{best_index+1}台应用 6 折优惠（1 年目录价￥{all_results[best_index]['price_1y_list']}）")
    
    # 处理其他命中 6 折但未被选中的实例
    for idx, result in enumerate(all_results):
        if not result["is_promotion_applied"]:
            if result.get("activity_name_1y") and \
               "新客首购云数据库 RDS 1 年享 6 折优惠，限 1 次，限 1 件" in result["activity_name_1y"]:
                # 命中 6 折但未被选中 → 使用 standPrice
                result["use_stand_price"] = True
                print(f"  📌 第{idx+1}台命中 6 折但未被选中，使用 standPrice={result.get('stand_price_1y')}")
    
    # 将所有结果添加到 Excel
    for idx, result in enumerate(all_results, 1):
        # 确定 1 年价格和备注
        if result["is_promotion_applied"]:
            # 被选中的 6 折实例
            final_price_1y = result["price_1y_discount"]  # finalFee
            remark_1y = result["activity_name_1y"]
        elif result["use_stand_price"]:
            # 命中 6 折但未被选中 → 使用 standPrice
            final_price_1y = result.get("stand_price_1y")
            remark_1y = "1 年默认折扣价"
        else:
            # 其他实例
            final_price_1y = result["price_1y_discount"]  # finalFee
            remark_1y = result["activity_name_1y"]
        
        # 3 年价格直接使用 finalFee
        final_price_3y = result["price_3y_discount"]
        remark_3y = result["activity_name_3y"]
        
        # 合并备注：1 年优惠说明 | 3 年优惠说明
        remark = f"{remark_1y} | {remark_3y}"
        
        generator.add_data_row(
            product_name="RDS",
            product_desc=result["product_desc"],
            region=result["region_name"],
            quantity=1,
            price_1y_list=result["price_1y_list"],
            price_1y_discount=final_price_1y,
            price_3y_list=result["price_3y_list"],
            price_3y_discount=final_price_3y,
            remark=remark
        )
    
    # 生成 Excel
    print(f"\n生成 Excel 文件...")
    file_path = generator.generate()
    print(f"✅ 报价单已生成：{file_path}（成功 {success_count}/{len(instances)}）")
    
    return file_path


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法：python rds_csv_quoter.py <csv_file_path>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    
    if not os.path.exists(csv_path):
        print(f"文件不存在：{csv_path}")
        sys.exit(1)
    
    # 解析 CSV
    print(f"解析 CSV 文件：{csv_path}")
    instances = parse_csv(csv_path)
    print(f"找到 {len(instances)} 台 RDS 实例")
    
    if not instances:
        print("❌ 未找到有效的 RDS 实例配置")
        sys.exit(1)
    
    # 报价
    print("开始报价...")
    file_path = quote_instances(instances)
    
    if file_path:
        print(f"✅ 报价单已生成：{file_path}")
    else:
        print("❌ 报价失败")


if __name__ == "__main__":
    main()
