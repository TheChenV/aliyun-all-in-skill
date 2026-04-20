#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSS 统计 - 使用 oss2 SDK 分析 OSS 资源使用情况
支持 GetBucketStat API,获取各存储类型的实际存储量和计费存储量
新增 ECS 快照统计(按地域聚合)
"""

import os
import sys
import hmac
import hashlib
import base64
import uuid
import json
import urllib.request
import urllib.parse
from typing import Dict, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from collections import defaultdict
import oss2
from oss2.models import BucketStat

# 添加脚本目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from ecs_constants import OSS_REGION_NAMES, STORAGE_CLASS_NAMES, REDUNDANCY_TYPE_NAMES


@dataclass
class BucketStats:
    """Bucket 统计信息"""
    bucket_name: str
    region: str
    redundancy_type: str = "LRS"  # 冗余类型 (LRS/ZRS)

    # 标准存储
    standard_storage: float = 0.0       # 实际存储量(字节)
    standard_billing: float = 0.0       # 计费存储量(字节)
    standard_count: int = 0             # 对象数量

    # 低频存储
    ia_storage: float = 0.0             # 实际存储量
    ia_billing: float = 0.0             # 计费存储量(已计算 64KB 最小计量)
    ia_count: int = 0

    # 归档存储
    archive_storage: float = 0.0
    archive_billing: float = 0.0        # 计费存储量(已计算 64KB 最小计量)
    archive_count: int = 0

    # 冷归档存储
    cold_archive_storage: float = 0.0
    cold_archive_billing: float = 0.0   # 计费存储量(已计算 64KB 最小计量)
    cold_archive_count: int = 0

    # 深度冷归档存储
    deep_cold_archive_storage: float = 0.0
    deep_cold_archive_billing: float = 0.0  # 计费存储量(已计算 64KB 最小计量)
    deep_cold_archive_count: int = 0


@dataclass
class AggregatedStats:
    """聚合统计信息"""
    region: str
    storage_class: str
    redundancy_type: str
    real_storage: float = 0.0      # 实际存储量(字节)
    billing_storage: float = 0.0   # 计费存储量(字节)


@dataclass
class ECS_SnapshotStats:
    """ECS 快照统计(按地域聚合)"""
    region: str
    source_disk_gb: float = 0.0    # 源云盘容量(GB)- 对应实际存储
    snapshot_bytes: float = 0.0    # 快照实际占用(字节)- 对应计费存储
    snapshot_count: int = 0


class OSSAnalyzer:
    """OSS 分析器 - 使用 oss2 SDK"""

    def __init__(self, ak: str, sk: str):
        """
        初始化 OSS 分析器

        Args:
            ak: AccessKey ID
            sk: AccessKey Secret
        """
        self.ak = ak
        self.sk = sk
        self.auth = oss2.Auth(ak, sk)

    # ==================== ECS 快照查询 ====================

    def _ecs_sign(self, params: dict) -> str:
        """ECS API 请求签名（HMAC-SHA1）"""
        sorted_params = sorted(params.items())
        qs = '&'.join(f'{urllib.parse.quote(k, safe="")}={urllib.parse.quote(str(v), safe="")}' for k, v in sorted_params)
        string_to_sign = 'GET&%2F&' + urllib.parse.quote(qs, safe='')
        h = hmac.new((self.sk + '&').encode('utf-8'), string_to_sign.encode('utf-8'), hashlib.sha1)
        return base64.b64encode(h.digest()).decode('utf-8')

    def _ecs_call(self, region: str, action: str, **extra) -> dict:
        """调用 ECS API"""
        params = {
            'AccessKeyId': self.ak,
            'Action': action,
            'Format': 'JSON',
            'SignatureMethod': 'HMAC-SHA1',
            'SignatureNonce': str(uuid.uuid4()),
            'SignatureVersion': '1.0',
            'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'Version': '2014-05-26',
            'RegionId': region,
        }
        params.update(extra)
        params['Signature'] = self._ecs_sign(params)
        url = 'https://ecs.aliyuncs.com/?' + urllib.parse.urlencode(params)
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return {}

    def query_ecs_snapshots(self) -> List[ECS_SnapshotStats]:
        """
        查询所有地域的 ECS 快照，按地域聚合
        实际存储 = 源云盘容量（SourceDiskSize，GB）
        计费存储 = 快照容量（DescribeSnapshotsUsage.SnapshotSize，字节）
        """
        print("\n开始查询 ECS 快照...")
        regions_data = self._ecs_call('cn-beijing', 'DescribeRegions')
        regions = [r['RegionId'] for r in regions_data.get('Regions', {}).get('Region', [])]
        print(f"  共 {len(regions)} 个地域")

        # 第一步：用 DescribeSnapshotsUsage 快速筛选有快照的地域
        print("  扫描各地域快照用量...")
        active_regions = []
        total_snaps = 0
        for region in regions:
            try:
                usage = self._ecs_call(region, 'DescribeSnapshotsUsage')
                count = usage.get('SnapshotCount', 0)
                if count > 0:
                    active_regions.append(region)
                    total_snaps += count
            except Exception:
                pass

        if not active_regions:
            print("  未找到任何快照")
            return []

        print(f"  找到 {total_snaps} 个快照，分布在 {len(active_regions)} 个地域")

        # 第二步：对有快照的地域，用 DescribeSnapshots 获取源云盘容量
        # 同时用 DescribeSnapshotsUsage 获取准确的快照容量
        aggregated: Dict[str, ECS_SnapshotStats] = {}

        for region in active_regions:
            try:
                # 获取快照容量（DescribeSnapshotsUsage）
                usage = self._ecs_call(region, 'DescribeSnapshotsUsage')
                snapshot_bytes = usage.get('SnapshotSize', 0)
                snap_count = usage.get('SnapshotCount', 0)

                # 获取源云盘容量（DescribeSnapshots）
                result = self._ecs_call(region, 'DescribeSnapshots', PageSize=100)
                snaps = result.get('Snapshots', {}).get('Snapshot', [])
                source_disk_gb = sum(s.get('SourceDiskSize', 0) for s in snaps)

                aggregated[region] = ECS_SnapshotStats(
                    region=region,
                    source_disk_gb=source_disk_gb,
                    snapshot_bytes=snapshot_bytes,
                    snapshot_count=snap_count
                )
            except Exception as e:
                print(f"  查询 {region} 失败: {e}")

        result_list = sorted(aggregated.values(), key=lambda x: x.region)
        for r in result_list:
            print(f"  {r.region}: 快照数={r.snapshot_count}, "
                  f"源云盘={r.source_disk_gb:.0f}GB, 快照容量={r.snapshot_bytes/1024**3:.2f}GB")
        print(f"  总计: 快照容量 {sum(r.snapshot_bytes for r in result_list)/1024**3:.2f} GB")
        return result_list

    def list_buckets(self) -> List[tuple]:
        """
        列出所有 Bucket

        Returns:
            [(bucket_name, region, extranet_endpoint), ...]
        """
        service = oss2.Service(self.auth, 'oss-cn-hangzhou.aliyuncs.com')
        result = service.list_buckets()

        buckets = []
        for b in result.buckets:
            buckets.append((b.name, b.location, b.extranet_endpoint))

        return buckets

    def get_bucket_redundancy(self, bucket_name: str, endpoint: str) -> str:
        """
        获取 Bucket 冗余类型

        Args:
            bucket_name: Bucket 名称
            endpoint: Endpoint

        Returns:
            冗余类型 (LRS/ZRS)
        """
        try:
            bucket = oss2.Bucket(self.auth, endpoint, bucket_name)
            info = bucket.get_bucket_info()

            # 获取冗余类型
            redundancy = getattr(info, 'data_redundancy_type', 'LRS')
            if redundancy == 'ZRS':
                return 'ZRS'
            return 'LRS'
        except Exception as e:
            print(f"获取 Bucket {bucket_name} 冗余类型失败: {e}")
            return 'LRS'

    def stat_bucket(self, bucket_name: str, endpoint: str) -> Optional[BucketStats]:
        """
        获取 Bucket 统计信息(使用 GetBucketStat API)

        Args:
            bucket_name: Bucket 名称
            endpoint: Endpoint

        Returns:
            BucketStats 或 None
        """
        try:
            bucket = oss2.Bucket(self.auth, endpoint, bucket_name)
            stat: BucketStat = bucket.get_bucket_stat()

            # 获取冗余类型
            redundancy = self.get_bucket_redundancy(bucket_name, endpoint)

            # 提取地域
            region = endpoint.replace('.aliyuncs.com', '').replace('oss-', '')

            return BucketStats(
                bucket_name=bucket_name,
                region=region,
                redundancy_type=redundancy,

                # 标准存储
                standard_storage=stat.standard_storage or 0,
                standard_billing=stat.standard_storage or 0,  # 标准存储按实际大小计费
                standard_count=stat.standard_object_count or 0,

                # 低频存储(计费存储量已自动计算 64KB 最小计量单位)
                ia_storage=stat.infrequent_access_real_storage or 0,
                ia_billing=stat.infrequent_access_storage or 0,  # 已计算 64KB
                ia_count=stat.infrequent_access_object_count or 0,

                # 归档存储
                archive_storage=stat.archive_real_storage or 0,
                archive_billing=stat.archive_storage or 0,  # 已计算 64KB
                archive_count=stat.archive_object_count or 0,

                # 冷归档存储
                cold_archive_storage=stat.cold_archive_real_storage or 0,
                cold_archive_billing=stat.cold_archive_storage or 0,  # 已计算 64KB
                cold_archive_count=stat.cold_archive_object_count or 0,

                # 深度冷归档存储
                deep_cold_archive_storage=getattr(stat, 'deep_cold_archive_real_storage', 0) or 0,
                deep_cold_archive_billing=getattr(stat, 'deep_cold_archive_storage', 0) or 0,
                deep_cold_archive_count=getattr(stat, 'deep_cold_archive_object_count', 0) or 0,
            )
        except oss2.exceptions.NoSuchBucket:
            print(f"Bucket {bucket_name} 不存在")
            return None
        except oss2.exceptions.AccessDenied:
            print(f"无权限访问 Bucket {bucket_name}")
            return None
        except Exception as e:
            print(f"统计 Bucket {bucket_name} 失败: {e}")
            return None

    def aggregate_stats(self, buckets: List[BucketStats]) -> List[AggregatedStats]:
        """
        按地域>存储类型>冗余类型聚合统计
        直接统计每个 Bucket 中实际存储的数据类型和大小

        Args:
            buckets: Bucket 统计列表

        Returns:
            聚合统计列表
        """
        # 使用字典聚合
        aggregated = defaultdict(lambda: AggregatedStats(
            region="",
            storage_class="",
            redundancy_type="",
            real_storage=0.0,
            billing_storage=0.0
        ))

        for bucket in buckets:
            # 为每种存储类型创建聚合记录(统计实际数据类型)
            storage_types = [
                ('Standard', bucket.standard_storage, bucket.standard_billing),
                ('IA', bucket.ia_storage, bucket.ia_billing),
                ('Archive', bucket.archive_storage, bucket.archive_billing),
                ('ColdArchive', bucket.cold_archive_storage, bucket.cold_archive_billing),
                ('DeepColdArchive', bucket.deep_cold_archive_storage, bucket.deep_cold_archive_billing),
            ]

            # 统计有数据的存储类型
            for storage_class, storage, billing in storage_types:
                if storage > 0:
                    key = (bucket.region, storage_class, bucket.redundancy_type)

                    agg = aggregated[key]
                    agg.region = bucket.region
                    agg.storage_class = storage_class
                    agg.redundancy_type = bucket.redundancy_type
                    agg.real_storage += storage
                    agg.billing_storage += billing

        # 转换为列表并排序
        result = sorted(aggregated.values(),
                       key=lambda x: (x.region, x.storage_class, x.redundancy_type))

        return result

    def analyze(self) -> List[AggregatedStats]:
        """
        主入口 - 分析 OSS 使用情况

        Returns:
            聚合统计列表
        """
        print("开始分析 OSS 使用情况...")

        # 获取所有 Bucket
        buckets = self.list_buckets()
        print(f"找到 {len(buckets)} 个 Bucket")

        if not buckets:
            return []

        # 获取每个 Bucket 的详情
        detailed_buckets = []
        for i, (name, region, endpoint) in enumerate(buckets, 1):
            print(f"[{i}/{len(buckets)}] 统计 Bucket: {name} ({region})")
            stat = self.stat_bucket(name, endpoint)
            if stat:
                detailed_buckets.append(stat)

        # 聚合统计
        aggregated = self.aggregate_stats(detailed_buckets)

        print(f"\n聚合完成:{len(aggregated)} 条记录")
        return aggregated


def analyze_oss(ak: str, sk: str) -> Optional[str]:
    """
    分析 OSS 并生成 Excel

    Args:
        ak: AccessKey ID
        sk: AccessKey Secret

    Returns:
        Excel 文件路径,失败返回 None
    """
    from oss_excel import OSSExcelGenerator

    try:
        # 创建分析器
        analyzer = OSSAnalyzer(ak, sk)

        # 分析 OSS
        stats = analyzer.analyze()

        # 查询 ECS 快照
        snapshots = analyzer.query_ecs_snapshots()

        if not stats and not snapshots:
            print("未找到任何 OSS 或 ECS 快照资源")
            return None

        # 生成 Excel
        generator = OSSExcelGenerator()

        for stat in stats:
            generator.add_row(
                region=OSS_REGION_NAMES.get(f'oss-{stat.region}', stat.region),
                storage_class=STORAGE_CLASS_NAMES.get(stat.storage_class, stat.storage_class),
                redundancy_type=REDUNDANCY_TYPE_NAMES.get(stat.redundancy_type, stat.redundancy_type),
                real_storage=stat.real_storage,
                billing_storage=stat.billing_storage
            )

        # 添加 ECS 快照行
        for snap in snapshots:
            region_name = OSS_REGION_NAMES.get(f'oss-{snap.region}', snap.region)
            generator.add_row(
                region=region_name,
                storage_class='ECS 快照',
                redundancy_type='-',
                real_storage=snap.source_disk_gb * (1024 ** 3),  # GB 转字节
                billing_storage=snap.snapshot_bytes
            )

        file_path = generator.generate()
        print(f"Excel 文件已生成:{file_path}")
        return file_path

    except oss2.exceptions.AccessDenied as e:
        raise Exception(f"权限不足:{e}")
    except Exception as e:
        raise Exception(f"统计失败:{e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("用法:python oss_stat.py <AK> <SK>")
        sys.exit(1)

    ak = sys.argv[1]
    sk = sys.argv[2]

    # 分析并生成 Excel
    file_path = analyze_oss(ak, sk)

    if file_path:
        print(f"\n✅ OSS 统计完成:{file_path}")
    else:
        print("\n❌ OSS 统计失败")