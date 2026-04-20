#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECS 文本配置报价（场景二）
解析文本配置，调用规格验证，查询价格，生成 Excel

三种规格验证场景：
- 场景1：有标准格式实例规格名称（ecs.<规格族>.<规格大小>）→ 字典精确匹配
- 场景2：有规格族但没有标准规格名称 → 字典精确匹配
- 场景3：只有几核几G → 默认优先级匹配（u1 > u2i > c9i > g9i > r9i）
"""

import os
import sys
import re
import argparse
import subprocess
from typing import List, Optional
from dataclasses import dataclass, field

# 添加脚本目录到路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from ecs_excel_generator import ExcelGenerator
from mcp_client import MCPClient
from ecs_spec_validator import SpecValidator
from ecs_constants import REGION_CODE_TO_NAME, REGION_KEYWORDS_TO_CODE


# 默认地域
DEFAULT_REGION = "cn-hangzhou"
DEFAULT_REGION_NAME = "华东 1（杭州）"


@dataclass
class TextInstanceConfig:
    """文本配置解析结果"""
    name: str = ""
    spec: str = ""
    vcpu: int = 0
    memory: int = 0
    system_disk_type: str = "ESSD 云盘 PL0"
    system_disk_size: int = 40
    data_disks: List[dict] = field(default_factory=list)
    bandwidth: int = 0
    bandwidth_charge_type: str = "PayByBandwidth"
    region: str = DEFAULT_REGION
    region_name: str = DEFAULT_REGION_NAME
    # 原始输入（用于验证失败时保留配置）
    raw_spec_input: str = ""  # 用户输入的规格描述
    raw_series_input: str = ""  # 用户输入的规格族


def parse_disk_type(disk_str: str) -> tuple:
    """
    解析磁盘类型
    
    Returns:
        (display_name, category, pl)
    """
    disk_str_lower = disk_str.lower()
    
    # ESSD Entry
    if 'entry' in disk_str_lower:
        return "ESSD Entry 云盘", "cloud_essd_entry", None
    # ESSD AutoPL
    if 'auto' in disk_str_lower or 'autopl' in disk_str_lower:
        return "ESSD AutoPL 云盘", "cloud_auto", None
    # ESSD PLx
    if 'essd' in disk_str_lower:
        pl_match = re.search(r'pl\s*(\d)', disk_str_lower)
        if pl_match:
            pl = f'PL{pl_match.group(1)}'
            return f"ESSD 云盘 {pl}", "cloud_essd", pl
        return "ESSD 云盘 PL0", "cloud_essd", "PL0"
    # SSD
    if 'ssd' in disk_str_lower and 'essd' not in disk_str_lower:
        return "SSD 云盘", "cloud_ssd", None
    # 高效云盘
    if '高效' in disk_str:
        return "高效云盘", "cloud_efficiency", None
    # 普通云盘
    if '普通' in disk_str:
        return "普通云盘", "cloud", None
    
    # 默认 ESSD PL0
    return "ESSD 云盘 PL0", "cloud_essd", "PL0"


def extract_region(text: str) -> tuple:
    """
    从文本中提取地域信息
    
    Args:
        text: 配置文本
        
    Returns:
        (region_code, region_name)
    """
    # 使用 ecs_constants.py 中的统一地域关键词映射
    region_keywords = REGION_KEYWORDS_TO_CODE
    
    text_lower = text.lower()
    
    for keyword, region_code in region_keywords.items():
        if keyword.lower() in text_lower:
            region_name = REGION_CODE_TO_NAME.get(region_code, region_code)
            return region_code, region_name
    
    # 未找到，返回默认值（杭州）
    return DEFAULT_REGION, DEFAULT_REGION_NAME


def parse_text_instances(text: str, default_region: str = DEFAULT_REGION) -> List[TextInstanceConfig]:
    """
    解析文本配置，提取实例列表
    
    支持两种格式：
    1. 单行格式：1. 实例规格：ecs.c7.xlarge 系统盘：100GiB 带宽：10Mbps
    2. 多行格式：
       1. 华东1（杭州）
       - 实例规格：ecs.c7.xlarge (4 vCPU 8 GiB)
       - 系统盘：ESSD PL0 100GiB
       - 带宽：按使用流量 10Mbps
    
    Args:
        text: 用户输入的配置文本
        default_region: 默认地域
        
    Returns:
        实例配置列表
    """
    instances = []
    
    # 提取全局地域（如果有的话）
    global_region, global_region_name = extract_region(text)
    
    # 检测是否是多行格式（序号后跟地域名）
    # 多行格式特征：^\d+\.\s*[^\n]+\n\s*-\s*实例规格 或 Markdown 格式 **数字. 地域**
    multiline_pattern = r'^(\*\*)?\d+\.\s*[\u4e00-\u9fa5\(\）\(\)]+.*?(\*\*)?\n\s*[-－—]\s*实例规格'
    is_multiline = bool(re.search(multiline_pattern, text, re.MULTILINE | re.IGNORECASE))
    
    if is_multiline:
        # 多行格式解析
        # 按 "数字. " 或 "**数字. **" 开头分割（保留分隔符）
        parts = re.split(r'(?=^(?:\*\*)?\d+\.\s)', text, flags=re.MULTILINE)
        
        for part in parts:
            part = part.strip()
            if not part or '实例规格' not in part:
                continue
            
            config = TextInstanceConfig()
            
            # 提取序号（支持 Markdown 格式）
            num_match = re.match(r'^\*\*(\d+)\.\s', part) or re.match(r'^(\d+)\.\s', part)
            if num_match:
                config.name = f"实例{num_match.group(1)}"
            else:
                config.name = f"实例{len(instances) + 1}"
            
            # 提取地域（从第一行）
            first_line = part.split('\n')[0] if '\n' in part else part
            instance_region, instance_region_name = extract_region(first_line)
            config.region = instance_region
            config.region_name = instance_region_name
            
            # 提取实例规格代码（ecs.xxx.xxx 格式）
            spec_match = re.search(r'(ecs\.[a-z0-9\-]+\.[a-z0-9]+)', part, re.IGNORECASE)
            if spec_match:
                config.spec = spec_match.group(1).lower()
                config.raw_spec_input = config.spec
            
            # 提取 vCPU 和内存
            cpu_mem_patterns = [
                r'\((\d+)\s*vCPU\s*(\d+)\s*GiB\)',
                r'(\d+)\s*vCPU\s*(\d+)\s*GiB',
                r'(\d+)\s*核\s*(\d+)\s*[GGBiB]*',
                r'(\d+)\s*[核 v]*CPU\s*(\d+)\s*[GGBiB]*',
            ]
            for pattern in cpu_mem_patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    config.vcpu = int(match.group(1))
                    config.memory = int(match.group(2))
                    break
            
            # 提取规格族关键词（用于场景2）
            if not config.spec:
                # 尝试匹配 "计算型 c9i"、"通用型 g9i" 等格式
                series_name_match = re.search(r'(?:计算型|通用型|内存型)\s*([a-z]\d+[a-z]?)', part, re.IGNORECASE)
                if series_name_match:
                    config.raw_series_input = series_name_match.group(1).lower()
                else:
                    # 尝试匹配 "c9i系列"、"g9i系列" 等格式
                    series_name_match = re.search(r'(u\d+i?|g\d+i?a?|c\d+i?a?|r\d+i?a?|e-c\d+m\d+)(?:规格|系列)?', part, re.IGNORECASE)
                    if series_name_match:
                        config.raw_series_input = series_name_match.group(1).lower()
            
            # 提取系统盘（支持：系统盘：500GiB / 系统盘500G / 系统盘 500G）
            sys_disk_match = re.search(r'系统盘[：:]?\s*(.+?)(?=\n|\s*[-－—]|\s*数据盘|\s*公网带宽|\s*带宽|$)', part, re.IGNORECASE)
            if sys_disk_match:
                disk_text = sys_disk_match.group(1).strip()
                # 支持 GiB/G/GB 等多种单位
                size_match = re.search(r'(\d+)\s*[Gg][iI]?[bB]?', disk_text)
                if size_match:
                    config.system_disk_size = int(size_match.group(1))
                dtype, dcategory, dpl = parse_disk_type(disk_text)
                config.system_disk_type = dtype
            
            # 提取数据盘
            data_disk_match = re.search(r'数据盘[：:]?\s*(.+?)(?=\n|\s*[-－—]|\s*公网带宽|\s*带宽|$)', part, re.IGNORECASE)
            if data_disk_match:
                disk_text = data_disk_match.group(1).strip()
                size_match = re.search(r'(\d+)\s*[Gg][iI]?[bB]?', disk_text)
                disk_size = int(size_match.group(1)) if size_match else 0
                dtype, dcategory, dpl = parse_disk_type(disk_text)
                if disk_size > 0:
                    config.data_disks.append({
                        'type': dtype,
                        'category': dcategory,
                        'pl': dpl,
                        'size': disk_size
                    })
            
            # 提取带宽（支持 2Mbps / 2M / 固定宽带2M / 带宽2M 等格式）
            bw_match = re.search(r'(?:带宽|宽带|按固定|按流量|Mbps|Mbps)[^\d]*(\d+)\s*[Mm]?(?:[Bb]ps?)?', part, re.IGNORECASE)
            if not bw_match:
                # 备用：数字+Mbps 格式
                bw_match = re.search(r'(\d+)\s*[Mm][Bb]ps', part, re.IGNORECASE)
            if not bw_match:
                # 备用：(固定)宽带X M 格式
                bw_match = re.search(r'宽[带帯][^\d]*(\d+)', part)
            if bw_match:
                config.bandwidth = int(bw_match.group(1))
            
            # 提取带宽计费方式
            if '按流量' in part or '按使用流量' in part:
                config.bandwidth_charge_type = "PayByTraffic"
            elif '按固定带宽' in part or '按带宽' in part:
                config.bandwidth_charge_type = "PayByBandwidth"
            else:
                if config.bandwidth > 20:
                    config.bandwidth_charge_type = "PayByTraffic"
                else:
                    config.bandwidth_charge_type = "PayByBandwidth"
            
            instances.append(config)
    else:
        # 单行格式解析
        # 按序号分割：支持 1. / 1、/ **1.** 等多种分隔符（不强制要求后跟空格）
        parts = re.split(r'(?=^(?:\*\*)?\d+[\.、．])', text, flags=re.MULTILINE)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 宽松匹配：只要有 CPU/内存 或 系统盘 关键词即可
            if not re.search(r'(\d+\s*核|\d+\s*vCPU|系统盘)', part, re.IGNORECASE):
                continue
            
            config = TextInstanceConfig()
            
            # 提取序号（支持 1. / 1、/ **1.** 等格式）
            num_match = re.match(r'^(?:\*\*)?(\d+)[\.、．]', part)
            if num_match:
                config.name = f"实例{num_match.group(1)}"
            else:
                config.name = f"实例{len(instances) + 1}"
            
            # 提取实例规格代码（ecs.xxx.xxx 格式）
            spec_match = re.search(r'(ecs\.[a-z0-9\-]+\.[a-z0-9]+)', part, re.IGNORECASE)
            if spec_match:
                config.spec = spec_match.group(1).lower()
                config.raw_spec_input = config.spec
            
            # 提取 vCPU 和内存
            cpu_mem_patterns = [
                r'(\d+)\s*vCPU\s*(\d+)\s*GiB',
                r'(\d+)\s*核\s*(\d+)\s*[GGBiB]*',
                r'(\d+)\s*[核 v]*CPU\s*(\d+)\s*[GGBiB]*',
            ]
            for pattern in cpu_mem_patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    config.vcpu = int(match.group(1))
                    config.memory = int(match.group(2))
                    break
            
            # 提取规格族关键词（用于场景2）
            # 规格族格式：字母+数字+可选后缀，如 g6, c7, r7, u1, u2i, g9a 等
            # 支持：g7规格、g7系列、g7 等格式
            if not config.spec:
                # 先尝试匹配 "g7规格"、"g7系列"、"c7系列" 等格式
                series_name_match = re.search(r'(u\d+i?|g\d+i?a?|c\d+i?a?|r\d+i?a?)(?:规格|系列)?', part, re.IGNORECASE)
                if series_name_match:
                    config.raw_series_input = series_name_match.group(1).lower()
            
            # 提取地域（每个实例可以有独立地域）
            instance_region, instance_region_name = extract_region(part)
            if instance_region != DEFAULT_REGION:
                # 该实例有独立地域
                config.region = instance_region
                config.region_name = instance_region_name
            else:
                # 使用全局地域
                config.region = global_region
                config.region_name = global_region_name
            
            # 提取系统盘（支持：系统盘：500GiB / 系统盘500G / 系统盘 500G）
            sys_disk_match = re.search(
                r'系统盘[：:]?\s*(.+?)(?=\s*\||\s*数据盘|\s*公网带宽|\s*镜像|\s*地域|$)',
                part, re.IGNORECASE
            )
            if sys_disk_match:
                disk_text = sys_disk_match.group(1).strip()
                # 支持 GiB/G/GB 等多种单位
                size_match = re.search(r'(\d+)\s*[Gg][iI]?[bB]?', disk_text)
                if size_match:
                    config.system_disk_size = int(size_match.group(1))
                # 提取类型
                dtype, dcategory, dpl = parse_disk_type(disk_text)
                config.system_disk_type = dtype
            
            # 提取数据盘（支持多个）
            data_disk_pattern = r'数据盘\s*(?:\d+)?\s*[：:]?\s*([\s\S]+?)(?=\s*\||\s*数据盘\d*\s*[：:]|\s*公网带宽|\s*镜像|\s*地域|\s*带宽|$)'
            data_disk_matches = list(re.finditer(data_disk_pattern, part, re.IGNORECASE))
            
            if data_disk_matches:
                for dm in data_disk_matches:
                    disk_text = dm.group(1).strip()
                    # 提取大小（支持 GiB/G/GB）
                    size_match = re.search(r'(\d+)\s*[Gg][iI]?[bB]?', disk_text)
                    disk_size = int(size_match.group(1)) if size_match else 0
                    # 提取类型
                    dtype, dcategory, dpl = parse_disk_type(disk_text)
                    if disk_size > 0:
                        config.data_disks.append({
                            'type': dtype,
                            'category': dcategory,
                            'pl': dpl,
                            'size': disk_size
                        })
            
            # 提取带宽（支持 2Mbps / 固定宽带2M / 带宽10M 等格式）
            bw_match = re.search(r'(\d+)\s*[Mm][Bb]ps', part, re.IGNORECASE)
            if bw_match:
                config.bandwidth = int(bw_match.group(1))
            else:
                # 备用匹配：固定宽带2M、带宽10M 等格式
                bw_match2 = re.search(r'(?:固定)?[宽带带宽]+[^\d]*(\d+)\s*[Mm]?', part, re.IGNORECASE)
                if bw_match2:
                    config.bandwidth = int(bw_match2.group(1))
            
            # 提取带宽计费方式（用户明确指定优先）
            if '按流量' in part:
                config.bandwidth_charge_type = "PayByTraffic"
            elif '按固定带宽' in part or '按带宽' in part:
                config.bandwidth_charge_type = "PayByBandwidth"
            else:
                # 用户未指定，根据带宽大小判断
                if config.bandwidth > 20:
                    config.bandwidth_charge_type = "PayByTraffic"
                else:
                    config.bandwidth_charge_type = "PayByBandwidth"
            
            instances.append(config)
    
    return instances


def build_product_desc(config: TextInstanceConfig) -> str:
    """
    构建产品描述
    
    Args:
        config: 实例配置
        
    Returns:
        产品描述文本
    """
    parts = []
    
    # 实例规格
    if config.spec and config.vcpu > 0 and config.memory > 0:
        parts.append(f"实例规格：{config.spec} ({config.vcpu} vCPU {config.memory} GiB)")
    elif config.spec:
        parts.append(f"实例规格：{config.spec}")
    elif config.raw_series_input:
        parts.append(f"规格族：{config.raw_series_input} ({config.vcpu} vCPU {config.memory} GiB)")
    elif config.vcpu > 0 and config.memory > 0:
        parts.append(f"配置：{config.vcpu} vCPU {config.memory} GiB")
    
    # 镜像
    parts.append("镜像：公共免费镜像")
    
    # 系统盘
    parts.append(f"系统盘：{config.system_disk_type} {config.system_disk_size}GiB")
    
    # 数据盘
    for i, disk in enumerate(config.data_disks, 1):
        parts.append(f"数据盘{i}：{disk['type']} {disk['size']}GiB")
    
    # 带宽
    if config.bandwidth > 0:
        bw_type = "按流量计费" if config.bandwidth_charge_type == "PayByTraffic" else "按固定带宽"
        parts.append(f"公网带宽：{bw_type} {config.bandwidth}Mbps")
    
    return "\n".join(parts)


def quote_text_instances(
    instances: List[TextInstanceConfig], 
    validator: SpecValidator,
    default_region: str = DEFAULT_REGION
) -> Optional[str]:
    """
    对实例列表进行报价
    
    Args:
        instances: 实例配置列表
        validator: 规格验证器
        default_region: 默认地域
        
    Returns:
        Excel 文件路径
    """
    # 初始化 MCP 客户端
    client = MCPClient()
    
    # 初始化 Excel 生成器
    generator = ExcelGenerator()
    
    success_count = 0
    error_count = 0
    
    for i, instance in enumerate(instances, 1):
        # 获取地域名称
        region_name = REGION_CODE_TO_NAME.get(instance.region, instance.region_name)
        
        print(f"正在验证 {i}/{len(instances)}: {instance.spec or instance.raw_series_input or f'{instance.vcpu}核{instance.memory}G'}...")
        
        # ========== 规格验证 ==========
        # 判断是哪种场景
        if instance.spec:
            # 场景1：有标准规格名称
            validation_result = validator.validate(
                spec_code=instance.spec,
                vcpu=instance.vcpu if instance.vcpu > 0 else None,
                memory=instance.memory if instance.memory > 0 else None
            )
        elif instance.raw_series_input:
            # 场景2：有规格族但没有标准规格名称
            validation_result = validator.validate(
                series=instance.raw_series_input,
                vcpu=instance.vcpu if instance.vcpu > 0 else None,
                memory=instance.memory if instance.memory > 0 else None
            )
        elif instance.vcpu > 0 and instance.memory > 0:
            # 场景3：只有几核几G
            validation_result = validator.validate(
                vcpu=instance.vcpu,
                memory=instance.memory
            )
        else:
            # 无法识别
            validation_result = type('obj', (object,), {
                'valid': False,
                'error_message': '无法识别的规格描述'
            })()
        
        # 验证失败
        if not validation_result.valid:
            print(f"  ❌ 验证失败: {validation_result.error_message}")
            product_desc = build_product_desc(instance)
            generator.add_data_row(
                product_name="ECS",
                product_desc=product_desc,
                region=region_name,
                quantity=1,
                remark=validation_result.error_message,
                is_error=True
            )
            error_count += 1
            continue
        
        # 验证成功，更新配置
        print(f"  ✅ 验证通过: {validation_result.spec_code}")
        instance.spec = validation_result.spec_code
        instance.vcpu = validation_result.vcpu
        instance.memory = int(validation_result.memory)
        
        # 解析系统盘 MCP 参数
        _, sys_category, sys_pl = parse_disk_type(instance.system_disk_type)
        
        # 解析数据盘 MCP 参数
        data_disks_mcp = []
        for disk in instance.data_disks:
            data_disks_mcp.append({
                'category': disk['category'],
                'size': disk['size'],
                'pl': disk['pl']
            })
        
        # ========== 调用 MCP 报价 ==========
        print(f"  正在查询价格...")
        try:
            price_result = client.query_ecs_price(
                region=instance.region,
                instance_spec=instance.spec,
                system_disk_type=sys_category,
                system_disk_size=instance.system_disk_size,
                system_disk_pl=sys_pl,
                data_disks=data_disks_mcp if data_disks_mcp else None,
                bandwidth=instance.bandwidth,
                bandwidth_charge_type=instance.bandwidth_charge_type
            )
            
            if price_result.success:
                product_desc = build_product_desc(instance)
                
                generator.add_data_row(
                    product_name="ECS",
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
                print(f"  ❌ 价格查询失败: {price_result.error_message}")
                product_desc = build_product_desc(instance)
                generator.add_data_row(
                    product_name="ECS",
                    product_desc=product_desc,
                    region=region_name,
                    quantity=1,
                    remark=price_result.error_message,
                    is_error=True
                )
                error_count += 1
        except Exception as e:
            print(f"  ❌ 异常: {str(e)}")
            product_desc = build_product_desc(instance)
            generator.add_data_row(
                product_name="ECS",
                product_desc=product_desc,
                region=region_name,
                quantity=1,
                remark=str(e),
                is_error=True
            )
            error_count += 1
    
    # 生成 Excel
    print(f"\n生成 Excel 文件...")
    file_path = generator.generate()
    print(f"✅ 报价单已生成：{file_path}")
    print(f"   成功: {success_count}/{len(instances)}, 失败: {error_count}/{len(instances)}")
    
    return file_path


def get_feishu_account() -> str:
    """获取飞书账号名称：优先环境变量，其次 config.json"""
    account = os.environ.get("FEISHU_ACCOUNT")
    if not account:
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
            config_path = os.path.abspath(os.path.join(config_dir, "config.json"))
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                account = config.get("feishu_account")
        except Exception:
            pass
    return account


def send_file(file_path: str, message: str, target: str) -> bool:
    """发送文件到飞书"""
    cmd = [
        "openclaw", "message", "send",
        "--channel", "feishu",
        "--target", target,
        "--message", message,
        "--media", file_path
    ]
    account = get_feishu_account()
    if account:
        idx = cmd.index("--target")
        cmd.insert(idx, "--account")
        cmd.insert(idx + 1, account)
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return "✅ Sent via Feishu" in result.stdout or "✅ Sent via Feishu" in result.stderr


def main(args=None):
    """主函数"""
    parser = argparse.ArgumentParser(description="文本配置报价（场景二）")
    parser.add_argument("text", nargs='?', help="配置文本")
    parser.add_argument("-f", "--file", help="配置文件路径")
    parser.add_argument("-t", "--target", help="目标用户 open_id")
    parser.add_argument("-r", "--region", default=DEFAULT_REGION, help="地域代码（默认：cn-hangzhou）")
    
    # 支持外部传入参数
    if args is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(args)
    
    # 获取配置文本
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        parser.error("需要提供配置文本或文件路径")
    
    # 解析配置
    print("解析配置文本...")
    instances = parse_text_instances(text, args.region)
    print(f"找到 {len(instances)} 台实例")
    
    if not instances:
        print("未找到有效配置")
        sys.exit(1)
    
    # 初始化规格验证器
    print("\n初始化规格验证器...")
    validator = SpecValidator()
    
    # 报价
    print("\n开始报价...")
    file_path = quote_text_instances(instances, validator, args.region)
    
    if file_path:
        # 发送文件
        target = args.target
        if not target:
            target = os.environ.get("FEISHU_TARGET")
        if not target:
            print("❌ 未指定目标用户 open_id，请通过 --target 参数或 FEISHU_TARGET 环境变量传入")
            sys.exit(1)
        
        message = f"ECS 报价单已生成，共 {len(instances)} 台实例。"
        
        print("\n发送文件到飞书...")
        if send_file(file_path, message, target):
            print("✅ 文件发送成功")
            # 清理
            os.remove(file_path)
            print(f"✅ 已删除本地文件")
        else:
            print("❌ 文件发送失败")


if __name__ == "__main__":
    main()