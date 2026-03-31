#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSS 统计 - 使用 oss2 SDK 分析 OSS 资源使用情况
支持 GetBucketStat API，获取各存储类型的实际存储量和计费存储量
"""

import os
import sys
from typing import Dict, List, Optional
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
    standard_storage: float = 0.0       # 实际存储量（字节）
    standard_billing: float = 0.0       # 计费存储量（字节）
    standard_count: int = 0             # 对象数量
    
    # 低频存储
    ia_storage: float = 0.0             # 实际存储量
    ia_billing: float = 0.0             # 计费存储量（已计算 64KB 最小计量）
    ia_count: int = 0
    
    # 归档存储
    archive_storage: float = 0.0
    archive_billing: float = 0.0        # 计费存储量（已计算 64KB 最小计量）
    archive_count: int = 0
    
    # 冷归档存储
    cold_archive_storage: float = 0.0
    cold_archive_billing: float = 0.0   # 计费存储量（已计算 64KB 最小计量）
    cold_archive_count: int = 0
    
    # 深度冷归档存储
    deep_cold_archive_storage: float = 0.0
    deep_cold_archive_billing: float = 0.0  # 计费存储量（已计算 64KB 最小计量）
    deep_cold_archive_count: int = 0


@dataclass
class AggregatedStats:
    """聚合统计信息"""
    region: str
    storage_class: str
    redundancy_type: str
    real_storage: float = 0.0      # 实际存储量（字节）
    billing_storage: float = 0.0   # 计费存储量（字节）


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
        获取 Bucket 统计信息（使用 GetBucketStat API）
        
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
                
                # 低频存储（计费存储量已自动计算 64KB 最小计量单位）
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
            # 为每种存储类型创建聚合记录（统计实际数据类型）
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
        
        print(f"\n聚合完成：{len(aggregated)} 条记录")
        return aggregated


def analyze_oss(ak: str, sk: str) -> Optional[str]:
    """
    分析 OSS 并生成 Excel
    
    Args:
        ak: AccessKey ID
        sk: AccessKey Secret
        
    Returns:
        Excel 文件路径，失败返回 None
    """
    from oss_excel import OSSExcelGenerator
    
    try:
        # 创建分析器
        analyzer = OSSAnalyzer(ak, sk)
        
        # 分析
        stats = analyzer.analyze()
        
        if not stats:
            print("未找到任何 OSS 资源")
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
        
        file_path = generator.generate()
        print(f"Excel 文件已生成：{file_path}")
        return file_path
    
    except oss2.exceptions.AccessDenied as e:
        raise Exception(f"权限不足：{e}")
    except Exception as e:
        raise Exception(f"统计失败：{e}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("用法：python oss_stat.py <AK> <SK>")
        sys.exit(1)
    
    ak = sys.argv[1]
    sk = sys.argv[2]
    
    # 分析并生成 Excel
    file_path = analyze_oss(ak, sk)
    
    if file_path:
        print(f"\n✅ OSS 统计完成：{file_path}")
    else:
        print("\n❌ OSS 统计失败")