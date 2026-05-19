#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 场景二：文字配置报价入口
接收用户文字描述配置，自动生成 RDS 报价单

用法：
  venv/bin/python3 rds_text_quoter.py '<配置文本>'
"""

import os
import sys

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# 加载公共模块
from rds_common import (
    normalize_engine, get_region_name, get_storage_type_name,
    get_category_display, build_rds_price_command, parse_price_response,
    apply_six_discount_policy, SUPPORTED_ENGINES, CATEGORY_DISPLAY,
    ENGINE_DEFAULT_VERSIONS, format_engine_version_for_api,
)
from rds_text_parser import RDSTextParser, RDSTextConfig
from rds_spec_validator import RDSSpecValidator, SpecMatchResult
from mcp_client import MCPClient

# 输出目录
from skill_config import setup_output_dir
OUTPUT_DIR = setup_output_dir()


def get_latest_excel():
    """获取最新生成的 Excel 文件"""
    if not os.path.exists(OUTPUT_DIR):
        return None
    files = [f for f in os.listdir(OUTPUT_DIR)
             if f.startswith("阿里云资源清单") and f.endswith(".xlsx")]
    if not files:
        return None
    files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)),
               reverse=True)
    return os.path.join(OUTPUT_DIR, files[0])


def build_error_desc(config: RDSTextConfig) -> str:
    """构建错误行的产品描述"""
    parts = []
    if config.engine:
        ver = config.engine_version_raw or ""
        parts.append(f"引擎:{config.engine.lower()}{' ' + ver if ver else ''}")
    if config.db_instance_class:
        parts.append(f"实例规格:{config.db_instance_class}")
    if config.cpu and config.memory:
        parts.append(f"配置:{config.cpu}核{config.memory}G")
    elif config.cpu:
        parts.append(f"配置:{config.cpu}核")
    elif config.memory:
        parts.append(f"配置:{config.memory}G")
    parts.append(f"存储:{config.db_instance_storage}GB")
    return "\n".join(parts)


def format_engine_version(engine: str, version: str) -> str:
    """格式化引擎版本号：PGSQL 显示整数，其他保持原样"""
    if engine.lower() == 'postgresql' and '.' in version:
        try:
            return str(int(float(version)))
        except ValueError:
            pass
    return version

def build_success_desc(match: SpecMatchResult, config: RDSTextConfig) -> str:
    """构建成功行的产品描述"""
    engine_lower = match.engine.lower()
    spec_desc = f"{match.cpu}核 {match.memory_class}"
    category_name = get_category_display(match.category)
    version_display = format_engine_version(match.engine, match.engine_version)

    parts = [
        f"引擎:{engine_lower} {version_display}",
        f"产品系列:{category_name}",
        f"存储类型:{get_storage_type_name(match.storage_type_api)}",
        f"实例规格:{spec_desc} {match.class_code}",
        f"存储空间:{config.db_instance_storage}GB",
    ]
    return "\n".join(parts)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="RDS 报价单自动生成（文字配置场景）")
    parser.add_argument("text_input", help="用户文字配置描述")

    args = parser.parse_args()
    text_input = args.text_input

    # 1. 解析文字输入
    print(f"解析配置文本...")
    configs = RDSTextParser(text_input).parse()
    if not configs:
        print("❌ 未解析到任何有效配置")
        sys.exit(1)
    print(f"找到 {len(configs)} 台实例配置")

    # 2. 加载规格数据库 + 初始化
    series_path = os.path.join(SCRIPT_DIR, "..", "references", "rds_series.json")
    validator = RDSSpecValidator(series_path)

    # 动态导入 Excel 生成器（场景二无实例ID列）
    from rds_excel_generator import RDSExcelGenerator
    generator = RDSExcelGenerator(include_instance_id=False)

    client = MCPClient()
    all_results = []

    # 3. 遍历处理每台实例
    for config in configs:
        print(f"\n处理第 {config.index} 台...")

        # 3a. Engine 校验
        if config.engine not in SUPPORTED_ENGINES:
            print(f"  ❌ 不支持的数据库类型: {config.engine}")
            generator.add_data_row(
                product_name="RDS",
                product_desc=build_error_desc(config),
                region=get_region_name(config.region_id),
                quantity=1,
                remark="该数据库类型暂不支持",
                is_error=True
            )
            continue

        # 3b. 规格匹配验证
        match = validator.validate(config)

        if match.error:
            print(f"  ❌ {match.error}")
            generator.add_data_row(
                product_name="RDS",
                product_desc=build_error_desc(config),
                region=get_region_name(config.region_id),
                quantity=1,
                remark=match.error,
                is_error=True
            )
            continue

        print(f"  ✅ 匹配规格: {match.class_code} | {match.engine} {match.engine_version} | {match.category}")

        # 3c. MCP 询价（1年 + 3年）
        try:
            # API 传参用格式化的版本号（如 PostgreSQL "14" → "14.0"）
            api_version = format_engine_version_for_api(match.engine, match.engine_version)

            # 构建询价命令并调用
            cmd_1y = build_rds_price_command(
                region=config.region_id,
                engine=match.engine,
                engine_version=api_version,
                db_instance_class=match.class_code,
                db_instance_storage=config.db_instance_storage,
                db_instance_storage_type=match.storage_type_api,
                period=1
            )

            response_1y = client._call_tool(
                "AlibabaCloud___CallCLI",
                {"command": cmd_1y}
            )

            content_1y = response_1y.get("result", {}).get("content", [])
            result_1y = parse_price_response(content_1y, "1y")

            if not result_1y["success"]:
                raise Exception(f"1年价格查询失败: {result_1y['error_reason']}")

            # 3年价格
            cmd_3y = build_rds_price_command(
                region=config.region_id,
                engine=match.engine,
                engine_version=api_version,
                db_instance_class=match.class_code,
                db_instance_storage=config.db_instance_storage,
                db_instance_storage_type=match.storage_type_api,
                period=3
            )

            response_3y = client._call_tool(
                "AlibabaCloud___CallCLI",
                {"command": cmd_3y}
            )

            content_3y = response_3y.get("result", {}).get("content", [])
            result_3y = parse_price_response(content_3y, "3y")

            if not result_3y["success"]:
                raise Exception(f"3年价格查询失败: {result_3y['error_reason']}")

            print(f"  ✅ 1年折扣价: ￥{result_1y['price_discount']}")

            all_results.append({
                "product_desc": build_success_desc(match, config),
                "region_name": get_region_name(config.region_id),
                "price_1y_list": result_1y["price_list"],
                "price_1y_discount": result_1y["price_discount"],
                "price_3y_list": result_3y["price_list"],
                "price_3y_discount": result_3y["price_discount"],
                "activity_name_1y": result_1y.get("activity_name"),
                "activity_name_3y": result_3y.get("activity_name"),
                "stand_price_1y": result_1y.get("stand_price"),
                "is_promotion_applied": False,
                "use_stand_price": False,
            })

        except Exception as e:
            print(f"  ❌ MCP 询价失败: {str(e)}")
            generator.add_data_row(
                product_name="RDS",
                product_desc=build_error_desc(config),
                region=get_region_name(config.region_id),
                quantity=1,
                remark="MCP 询价失败，请检查配置或人工询价",
                is_error=True
            )

    # 4. 应用 6 折分配策略
    if all_results:
        apply_six_discount_policy(all_results)

    # 5. 写入 Excel
    for r in all_results:
        if r["is_promotion_applied"]:
            fp1 = r["price_1y_discount"]
            rm1 = r["activity_name_1y"]
        elif r["use_stand_price"]:
            fp1 = r.get("stand_price_1y")
            rm1 = "1 年默认折扣价"
        else:
            fp1 = r["price_1y_discount"]
            rm1 = r["activity_name_1y"]

        fp3 = r["price_3y_discount"]
        rm3 = r["activity_name_3y"]
        remark = f"{rm1} | {rm3}"

        generator.add_data_row(
            product_name="RDS",
            product_desc=r["product_desc"],
            region=r["region_name"],
            quantity=1,
            price_1y_list=r["price_1y_list"],
            price_1y_discount=fp1,
            price_3y_list=r["price_3y_list"],
            price_3y_discount=fp3,
            remark=remark
        )

    # 6. 生成 Excel
    print(f"\n生成 Excel 文件...")
    file_path = generator.generate()
    print(f"✅ 报价单已生成：{file_path}（成功 {len(all_results)}/{len(configs)}）")
    print(f"FILE_PATH:{file_path}")


if __name__ == "__main__":
    main()
