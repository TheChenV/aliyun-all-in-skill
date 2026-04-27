#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSS CSV 资源清单统计（场景二）
解析阿里云控制台导出的标准 OSS 资源清单（buckets_YYYYMMDD.csv），按地域>存储类型>冗余类型聚合，
使用与场景一相同的 Excel 模板生成统计报告（不含 ECS 快照）

CSV 列结构：
存储桶名称,地域,存储类型,存储桶创建时间,冗余类型,版本控制,传输加速,
容量,容量（Byte）,标准型存储量,标准型存储量（Byte）,
低频型计费存储量,低频型计费存储量（Byte）,归档型计费存储量,归档型计费存储量（Byte）,
冷归档型计费存储量,冷归档型计费存储量（Byte）,深度冷归档型计费存储量,深度冷归档型计费存储量（Byte）,
本月公网流量,本月公网流量（Byte）,本月请求次数,标签,读写权限
"""

import os
import sys
import csv
import re
import argparse
from collections import defaultdict
from dataclasses import dataclass

# 添加脚本目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from ecs_constants import OSS_REGION_NAMES, STORAGE_CLASS_NAMES, REDUNDANCY_TYPE_NAMES

# 输出目录
OUTPUT_DIR = "/root/.openclaw/workspace/download/"

# CSV 列名映射（阿里云控制台导出格式）
CSV_COLUMNS = {
    'bucket_name': '存储桶名称',
    'region': '地域',
    'storage_class': '存储类型',
    'redundancy_type': '冗余类型（LRS-本地冗余｜ZRS-同城冗余）',
    'total_storage_byte': '容量（Byte）',
    'standard_storage_byte': '标准型存储量（Byte）',
    'ia_billing_byte': '低频型计费存储量（Byte）',
    'archive_billing_byte': '归档型计费存储量（Byte）',
    'cold_archive_billing_byte': '冷归档型计费存储量（Byte）',
    'deep_cold_archive_billing_byte': '深度冷归档型计费存储量（Byte）',
}


@dataclass
class OSSCsvRow:
    """CSV 行数据"""
    bucket_name: str
    region: str          # 如 oss-cn-hangzhou
    storage_class: str   # Standard / IA / Archive / ColdArchive / DeepColdArchive
    redundancy_type: str # LRS / ZRS
    # 各存储类型的计费存储量（字节）
    standard_billing: float = 0.0
    ia_billing: float = 0.0
    archive_billing: float = 0.0
    cold_archive_billing: float = 0.0
    deep_cold_archive_billing: float = 0.0


def parse_redundancy_type(raw: str) -> str:
    """解析冗余类型字段"""
    if 'ZRS' in raw:
        return 'ZRS'
    return 'LRS'


def parse_storage_class(raw: str) -> str:
    """解析存储类型字段"""
    raw_lower = raw.lower().strip()
    if raw_lower in ('standard', '标准'):
        return 'Standard'
    if raw_lower in ('ia', '低频', '低频访问'):
        return 'IA'
    if raw_lower in ('archive', '归档', '归档存储'):
        return 'Archive'
    if raw_lower in ('coldarchive', '冷归档', '冷归档存储'):
        return 'ColdArchive'
    if raw_lower in ('deepcoldarchive', '深度冷归档', '深度冷归档存储'):
        return 'DeepColdArchive'
    # 默认
    return raw.strip()


def safe_float(value) -> float:
    """安全转换为浮点数"""
    if value is None or value == '' or value == '0.0Byte' or value == '0':
        return 0.0
    try:
        # 去除可能的非数字字符
        cleaned = re.sub(r'[^\d.]', '', str(value))
        if cleaned == '':
            return 0.0
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def parse_csv(csv_path: str) -> list:
    """
    解析 buckets_YYYYMMDD.csv 文件

    Args:
        csv_path: CSV 文件路径

    Returns:
        OSSCsvRow 列表
    """
    rows = []

    # 尝试多种编码
    for encoding in ['utf-8', 'gbk', 'gb2312']:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    csv_row = OSSCsvRow(
                        bucket_name=row.get(CSV_COLUMNS['bucket_name'], ''),
                        region=row.get(CSV_COLUMNS['region'], ''),
                        storage_class=parse_storage_class(row.get(CSV_COLUMNS['storage_class'], 'Standard')),
                        redundancy_type=parse_redundancy_type(row.get(CSV_COLUMNS['redundancy_type'], 'LRS')),
                        standard_billing=safe_float(row.get(CSV_COLUMNS['standard_storage_byte'], 0)),
                        ia_billing=safe_float(row.get(CSV_COLUMNS['ia_billing_byte'], 0)),
                        archive_billing=safe_float(row.get(CSV_COLUMNS['archive_billing_byte'], 0)),
                        cold_archive_billing=safe_float(row.get(CSV_COLUMNS['cold_archive_billing_byte'], 0)),
                        deep_cold_archive_billing=safe_float(row.get(CSV_COLUMNS['deep_cold_archive_billing_byte'], 0)),
                    )
                    rows.append(csv_row)
            break  # 成功解析，跳出编码循环
        except UnicodeDecodeError:
            continue

    return rows


@dataclass
class AggregatedStat:
    """聚合统计"""
    region: str
    storage_class: str
    redundancy_type: str
    real_storage: float = 0.0       # 实际存储（字节）
    billing_storage: float = 0.0    # 计费存储（字节）


def aggregate_stats(rows: list) -> list:
    """
    按地域>存储类型>冗余类型聚合统计

    对于每个 Bucket，数据已按存储类型分布在不同列中，
    需要将每个 Bucket 的各存储类型数据分别累加到对应聚合键。

    注意：CSV 中只有计费存储量（Byte），没有实际存储量（Byte）。
    对于标准存储，计费=实际；对于低频/归档等，计费>=实际（含最小计量单位）。
    因此：real_storage = billing_storage（CSV 场景下两者等价）
    """
    aggregated = defaultdict(lambda: AggregatedStat(
        region="", storage_class="", redundancy_type="", real_storage=0.0, billing_storage=0.0
    ))

    for row in rows:
        # 每个 Bucket 的各存储类型分别聚合
        storage_entries = [
            ('Standard', row.standard_billing),
            ('IA', row.ia_billing),
            ('Archive', row.archive_billing),
            ('ColdArchive', row.cold_archive_billing),
            ('DeepColdArchive', row.deep_cold_archive_billing),
        ]

        for storage_class, billing in storage_entries:
            if billing > 0:
                key = (row.region, storage_class, row.redundancy_type)
                agg = aggregated[key]
                agg.region = row.region
                agg.storage_class = storage_class
                agg.redundancy_type = row.redundancy_type
                # CSV 只有计费存储量，实际存储量无法区分，用计费存储量代替
                agg.real_storage += billing
                agg.billing_storage += billing

    # 转换为列表并排序
    result = sorted(aggregated.values(), key=lambda x: (x.region, x.storage_class, x.redundancy_type))
    return result


def generate_excel(stats: list) -> str:
    """
    生成 Excel 报告（使用与场景一相同的模板）

    Args:
        stats: 聚合统计列表

    Returns:
        Excel 文件路径
    """
    from oss_excel import OSSExcelGenerator

    generator = OSSExcelGenerator()

    for stat in stats:
        region_name = OSS_REGION_NAMES.get(stat.region, stat.region)
        storage_name = STORAGE_CLASS_NAMES.get(stat.storage_class, stat.storage_class)
        redundancy_name = REDUNDANCY_TYPE_NAMES.get(stat.redundancy_type, stat.redundancy_type)

        generator.add_row(
            region=region_name,
            storage_class=storage_name,
            redundancy_type=redundancy_name,
            real_storage=stat.real_storage,
            billing_storage=stat.billing_storage
        )

    file_path = generator.generate()
    return file_path


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="OSS CSV 资源清单统计（场景二）")
    parser.add_argument("csv_path", help="OSS 资源清单 CSV 文件路径（buckets_YYYYMMDD.csv）")
    parser.add_argument("-m", "--message", help="自定义消息（可选）")

    args = parser.parse_args()

    csv_path = args.csv_path

    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在：{csv_path}")
        sys.exit(1)

    # 解析 CSV
    print(f"解析 OSS 资源清单：{csv_path}")
    rows = parse_csv(csv_path)
    print(f"找到 {len(rows)} 个 Bucket")

    if not rows:
        print("❌ 未找到有效数据")
        sys.exit(1)

    # 聚合统计
    stats = aggregate_stats(rows)
    print(f"聚合完成：{len(stats)} 条记录")

    # 生成 Excel
    print("生成 Excel 报告...")
    file_path = generate_excel(stats)

    print(f"\n✅ OSS 统计报告已生成：{file_path}（共 {len(rows)} 个 Bucket，{len(stats)} 条聚合记录）")
    print(f"FILE_PATH:{file_path}")


if __name__ == "__main__":
    main()