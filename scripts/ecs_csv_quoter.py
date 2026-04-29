#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECS 实例清单 CSV 自动报价
解析阿里云控制台导出的实例清单 CSV 文件，自动生成报价单
"""

import os
import sys
import csv
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field

# 添加脚本目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from ecs_excel_generator import ExcelGenerator
from mcp_client import MCPClient
from ecs_constants import REGION_CODE_TO_NAME, INLAND_REGIONS


@dataclass
class InstanceConfig:
    """实例配置"""
    instance_name: str = ""
    instance_id: str = ""
    spec: str = ""
    vcpu: int = 0
    memory: str = ""
    memory_gb: int = 0  # 内存大小（数字，GiB）
    os: str = ""
    system_disk: str = ""
    system_disk_type: str = ""  # 系统盘类型
    system_disk_size: int = 0   # 系统盘大小（GiB）
    data_disk: str = ""
    data_disks: List[dict] = field(default_factory=list)  # 所有数据盘
    bandwidth: str = ""
    bandwidth_type: str = ""  # PayByTraffic 或 PayByBandwidth
    region: str = ""
    zone: str = ""


def parse_disk_info(disk_str: str) -> tuple:
    """
    解析磁盘信息
    
    Args:
        disk_str: 磁盘信息字符串，如 "d-xxx(ESSD Entry 80GiB)"
        
    Returns:
        (disk_type, disk_size)
    """
    if not disk_str or disk_str.strip() == '':
        return None, 0
    
    # 提取括号内的内容
    match = re.search(r'\(([^)]+)\)', disk_str)
    if not match:
        return None, 0
    
    disk_info = match.group(1)
    
    # 提取磁盘大小
    size_match = re.search(r'(\d+)\s*GiB', disk_info)
    disk_size = int(size_match.group(1)) if size_match else 0
    
    # 提取磁盘类型
    if 'ESSD Entry' in disk_info:
        disk_type = 'ESSD Entry 云盘'
    elif 'ESSD AutoPL' in disk_info or 'ESSD Auto' in disk_info:
        disk_type = 'ESSD AutoPL 云盘'
    elif re.search(r'ESSD.*PL0', disk_info):
        disk_type = 'ESSD 云盘 PL0'
    elif re.search(r'ESSD.*PL1', disk_info):
        disk_type = 'ESSD 云盘 PL1'
    elif re.search(r'ESSD.*PL2', disk_info):
        disk_type = 'ESSD 云盘 PL2'
    elif re.search(r'ESSD.*PL3', disk_info):
        disk_type = 'ESSD 云盘 PL3'
    elif 'ESSD' in disk_info:
        disk_type = 'ESSD 云盘 PL0'
    elif 'SSD' in disk_info:
        disk_type = 'SSD 云盘'
    elif '高效' in disk_info:
        disk_type = '高效云盘'
    elif '普通' in disk_info:
        disk_type = '普通云盘'
    else:
        disk_type = 'ESSD 云盘 PL0'
    
    return disk_type, disk_size


def parse_memory(memory_str: str) -> int:
    """
    解析内存字符串，提取数字
    
    Args:
        memory_str: 内存字符串，如 "32 GiB"
        
    Returns:
        内存大小（GiB）
    """
    if not memory_str:
        return 0
    match = re.search(r'(\d+)', memory_str)
    return int(match.group(1)) if match else 0


def parse_csv(csv_path: str) -> List[InstanceConfig]:
    """
    解析 CSV 文件
    
    Args:
        csv_path: CSV 文件路径
        
    Returns:
        实例配置列表
    """
    instances = []
    
    # 尝试多种编码
    encodings = ['utf-8', 'gbk', 'gb2312', 'iso-8859-1']
    rows = []
    
    for encoding in encodings:
        try:
            with open(csv_path, 'r', encoding=encoding) as f:
                reader = csv.DictReader(f)
                # 去除 BOM 等不可见字符
                if reader.fieldnames:
                    reader.fieldnames = [name.lstrip('\ufeff').strip() for name in reader.fieldnames]
                rows = list(reader)
                if rows and '实例规格' in reader.fieldnames:
                    break
        except:
            continue
    
    for row in rows:
        # 解析系统盘
        sys_disk_str = row.get('系统盘', '')
        sys_disk_type, sys_disk_size = parse_disk_info(sys_disk_str)
        
        # 解析数据盘（可能有多个）
        data_disk_str = row.get('数据盘', '')
        data_disks = []
        
        if data_disk_str:
            # 按换行分隔多个数据盘
            disk_lines = data_disk_str.split('\n') if '\n' in data_disk_str else [data_disk_str]
            
            for disk_line in disk_lines:
                disk_line = disk_line.strip()
                if disk_line:
                    dtype, dsize = parse_disk_info(disk_line)
                    if dtype and dsize > 0:
                        data_disks.append({'type': dtype, 'size': dsize})
        
        # 解析内存
        memory_str = row.get('内存', '')
        memory_gb = parse_memory(memory_str)
        
        # 解析带宽
        bandwidth_str = row.get('带宽', '0')
        bandwidth = int(bandwidth_str) if bandwidth_str.isdigit() else 0
        
        # 带宽计费方式
        bandwidth_type = row.get('带宽计费方式', '')
        
        # 解析地域
        region = row.get('地域', '')
        
        # 创建实例配置
        instance = InstanceConfig(
            instance_name=row.get('实例名称', ''),
            instance_id=row.get('实例 ID', ''),
            spec=row.get('实例规格', ''),
            vcpu=int(row.get('CPU', 0)) if row.get('CPU', '').isdigit() else 0,
            memory=memory_str,
            memory_gb=memory_gb,
            os=row.get('操作系统', ''),
            system_disk=f"{sys_disk_type} {sys_disk_size}GiB" if sys_disk_type else "",
            system_disk_type=sys_disk_type,
            system_disk_size=sys_disk_size,
            data_disk=f"{data_disks[0]['type']} {data_disks[0]['size']}GiB" if data_disks else "",
            data_disks=data_disks,
            bandwidth=f"{bandwidth}Mbps" if bandwidth > 0 else "",
            bandwidth_type=bandwidth_type,
            region=region,
            zone=row.get('所在可用区', '')
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
    if '（' in region_code:
        return region_code
    
    # 查找映射
    return REGION_CODE_TO_NAME.get(region_code, region_code)


def is_paid_mirror(os_name: str, region: str) -> bool:
    """
    判断是否为收费镜像
    
    根据 REQUIREMENTS.md：
    - Red Hat / RHEL：全球收费
    - SUSE：全球收费
    - Alibaba Cloud Linux 3 Pro：全球收费
    - Windows Server：中国香港及海外地域收费，内地免费
    
    Args:
        os_name: 操作系统名称
        region: 地域代码
        
    Returns:
        True: 收费镜像，不报价
        False: 免费镜像，正常报价
    """
    if not os_name:
        return False
    
    os_lower = os_name.lower()
    
    # 全球收费镜像
    if 'red hat' in os_lower or 'rhel' in os_lower:
        return True
    if 'suse' in os_lower:
        return True
    if 'alibaba cloud linux 3 pro' in os_lower or 'alibaba cloud linux  pro' in os_lower:
        return True
    
    # Windows：仅中国香港及海外地域收费
    if 'windows' in os_lower:
        # 内地地域免费，其他地域收费
        if region not in INLAND_REGIONS:
            return True
    
    return False


def get_disk_mcp_params(disk_type: str, disk_size: int) -> dict:
    """
    根据磁盘类型获取 MCP 参数
    
    Args:
        disk_type: 磁盘类型字符串
        disk_size: 磁盘大小（GiB）
        
    Returns:
        {'category': 'cloud_essd', 'pl': 'PL0', 'size': 100}
    """
    params = {'size': disk_size}
    
    if 'ESSD Entry' in disk_type:
        params['category'] = 'cloud_essd_entry'
        params['pl'] = None
    elif 'ESSD AutoPL' in disk_type or 'ESSD Auto' in disk_type:
        params['category'] = 'cloud_auto'
        params['pl'] = None
    elif 'PL0' in disk_type:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL0'
    elif 'PL1' in disk_type:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL1'
    elif 'PL2' in disk_type:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL2'
    elif 'PL3' in disk_type:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL3'
    elif 'ESSD' in disk_type:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL0'
    elif '高效' in disk_type:
        params['category'] = 'cloud_efficiency'
        params['pl'] = None
    elif 'SSD' in disk_type:
        params['category'] = 'cloud_ssd'
        params['pl'] = None
    else:
        params['category'] = 'cloud_essd'
        params['pl'] = 'PL0'
    
    return params


def quote_instances(instances: List[InstanceConfig]) -> Optional[str]:
    """
    对实例列表进行报价（支持多数据盘）
    
    Args:
        instances: 实例配置列表
        
    Returns:
        Excel 文件路径
    """
    # 初始化 MCP 客户端
    client = MCPClient()
    
    # 初始化 Excel 生成器
    generator = ExcelGenerator(include_instance_id=True)
    
    success_count = 0
    for i, instance in enumerate(instances, 1):
        print(f"正在查询 {i}/{len(instances)}: {instance.spec}...")
        
        # 解析系统盘 MCP 参数
        sys_params = get_disk_mcp_params(instance.system_disk_type, instance.system_disk_size)
        sys_disk_category = sys_params['category']
        sys_disk_pl = sys_params['pl']
        sys_disk_size = sys_params['size']
        
        # 解析数据盘 MCP 参数
        data_disks = None
        if instance.data_disks:
            data_disks = []
            for disk in instance.data_disks:
                disk_params = get_disk_mcp_params(disk.get('type', ''), disk.get('size', 0))
                data_disks.append({
                    'category': disk_params['category'],
                    'size': disk_params['size'],
                    'pl': disk_params['pl']
                })
        
        # 解析带宽计费方式
        # 关键修复：使用精确匹配，而不是字符串包含
        if instance.bandwidth_type == 'PayByTraffic':
            bw_charge_type = 'PayByTraffic'
        else:
            bw_charge_type = 'PayByBandwidth'
        
        # 解析带宽大小
        bw = 0
        if instance.bandwidth:
            bw_match = re.search(r'(\d+)', instance.bandwidth)
            if bw_match:
                bw = int(bw_match.group(1))
        
        # 解析地域代码
        region_code = instance.region if instance.region else 'cn-beijing'
        # 获取地域中文名称
        region_name = get_region_name(region_code)
        
        # 判断是否为收费镜像
        if is_paid_mirror(instance.os, region_code):
            # 收费镜像，不调用 MCP，直接生成错误行
            print(f"  ⚠️ 收费镜像，跳过报价")
            
            # 构建产品描述（保留原镜像名称）
            desc_parts = [f"实例规格：{instance.spec} ({instance.vcpu} vCPU {instance.memory_gb} GiB)"]
            desc_parts.append(f"镜像：{instance.os}")
            if instance.system_disk:
                desc_parts.append(f"系统盘：{instance.system_disk}")
            if instance.data_disks:
                for idx, d in enumerate(instance.data_disks, 1):
                    desc_parts.append(f"数据盘{idx}：{d.get('type', '')} {d.get('size', 0)}GiB")
            if bw > 0:
                bw_desc = "按流量计费" if bw_charge_type == 'PayByTraffic' else "按固定带宽"
                desc_parts.append(f"公网带宽：{bw_desc} {bw}Mbps")
            
            generator.add_data_row(
                product_name="ECS",
                instance_id=instance.instance_id,
                product_desc="\n".join(desc_parts),
                region=region_name,
                quantity=1,
                remark="涉及收费镜像，请人工确认",
                is_error=True
            )
            continue
        
        try:
            # 调用 MCP 查询价格
            price_result = client.query_ecs_price(
                region=region_code,
                instance_spec=instance.spec,
                system_disk_type=sys_disk_category,
                system_disk_size=sys_disk_size,
                system_disk_pl=sys_disk_pl,
                data_disks=data_disks,
                bandwidth=bw,
                bandwidth_charge_type=bw_charge_type
            )
            
            if price_result.success:
                # 构建产品描述
                # 修复：实例规格格式包含 CPU/内存
                desc_parts = [f"实例规格：{instance.spec} ({instance.vcpu} vCPU {instance.memory_gb} GiB)"]
                
                # 镜像
                desc_parts.append("镜像：公共免费镜像")
                
                # 系统盘
                if instance.system_disk:
                    desc_parts.append(f"系统盘：{instance.system_disk}")
                
                # 数据盘
                if instance.data_disks:
                    for idx, d in enumerate(instance.data_disks, 1):
                        desc_parts.append(f"数据盘{idx}：{d.get('type', '')} {d.get('size', 0)}GiB")
                
                # 带宽
                if bw > 0:
                    bw_desc = "按流量计费" if bw_charge_type == 'PayByTraffic' else "按固定带宽"
                    desc_parts.append(f"公网带宽：{bw_desc} {bw}Mbps")
                
                product_desc = "\n".join(desc_parts)
                
                generator.add_data_row(
                    product_name="ECS",
                    instance_id=instance.instance_id,
                    product_desc=product_desc,
                    region=region_name,
                    quantity=1,
                    price_1y_list=price_result.price_1y_list,
                    price_1y_discount=price_result.price_1y_discount,
                    price_3y_list=price_result.price_3y_list,
                    price_3y_discount=price_result.price_3y_discount,
                    remark=price_result.remark if price_result.remark else ""
                )
                success_count += 1
                print(f"  ✅ 1年折扣价: ￥{price_result.price_1y_discount:.2f}")
            else:
                print(f"  ❌ 查询失败: {price_result.error_message}")
                generator.add_data_row(
                    product_name="ECS",
                    instance_id=instance.instance_id,
                    product_desc=f"实例规格：{instance.spec} ({instance.vcpu} vCPU {instance.memory_gb} GiB)",
                    region=region_name,
                    quantity=1,
                    remark=price_result.error_message,
                    is_error=True
                )
        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")
            generator.add_data_row(
                product_name="ECS",
                instance_id=instance.instance_id,
                product_desc=f"实例规格：{instance.spec} ({instance.vcpu} vCPU {instance.memory_gb} GiB)",
                region=region_name,
                quantity=1,
                remark=str(e),
                is_error=True
            )
    
    # 生成 Excel
    print(f"\n生成 Excel 文件...")
    file_path = generator.generate()
    print(f"✅ 报价单已生成：{file_path}（成功 {success_count}/{len(instances)}）")
    
    return file_path


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法：python csv_quoter.py <csv_file_path>")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    
    if not os.path.exists(csv_path):
        print(f"文件不存在：{csv_path}")
        sys.exit(1)
    
    # 解析 CSV
    print(f"解析 CSV 文件：{csv_path}")
    instances = parse_csv(csv_path)
    print(f"找到 {len(instances)} 台实例")
    
    # 报价
    print("开始报价...")
    file_path = quote_instances(instances)
    
    if file_path:
        print(f"✅ 报价单已生成：{file_path}")
    else:
        print("❌ 报价失败")


if __name__ == "__main__":
    main()