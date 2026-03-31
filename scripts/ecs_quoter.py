#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECS 报价统一入口
自动判断场景，调用对应处理器

场景判断：
- 场景一：文件名匹配 ecs_instance_list_**_YYYY-MM-DD.csv → 直接报价
- 场景二：其他所有形式 → 先分析确认，再报价

使用方式：
    python ecs_quoter.py <input> [--target <open_id>] [--region <region>]
    
    input: CSV 文件路径或文本配置
    --target: 目标用户 open_id（飞书发送用）
    --region: 地域代码（默认 cn-beijing）
"""

import os
import sys
import re
import argparse
from typing import Optional, Tuple

# 场景一：CSV 文件名正则
CSV_PATTERN = re.compile(r'ecs_instance_list_.*\d{4}-\d{2}-\d{2}.*\.csv$', re.IGNORECASE)


def is_csv_file(input_str: str) -> bool:
    """
    判断是否为场景一（标准 CSV 文件）
    
    Args:
        input_str: 输入内容（文件路径或文本）
        
    Returns:
        是否为场景一
    """
    # 检查是否为文件路径
    if not os.path.exists(input_str):
        return False
    
    # 检查文件名是否匹配
    filename = os.path.basename(input_str)
    return bool(CSV_PATTERN.match(filename))


def quote_csv(csv_path: str, target: str = None) -> Tuple[bool, str]:
    """
    场景一：CSV 文件报价
    
    Args:
        csv_path: CSV 文件路径
        target: 目标用户 open_id
        
    Returns:
        (success, message)
    """
    from ecs_csv_quoter_auto import main as csv_main
    
    # 构建参数
    args = ['ecs_csv_quoter_auto.py', csv_path]
    if target:
        args.extend(['-t', target])
    
    # 调用
    sys.argv = args
    try:
        csv_main()
        return True, "报价完成"
    except Exception as e:
        return False, f"报价失败: {str(e)}"


def quote_text(text: str, target: str = None, region: str = "cn-beijing") -> Tuple[bool, str]:
    """
    场景二：文本配置报价
    
    Args:
        text: 配置文本
        target: 目标用户 open_id
        region: 地域代码
        
    Returns:
        (success, message)
    """
    from ecs_text_quoter import main as text_main
    
    # 构建参数
    args = ['ecs_text_quoter.py', text, '-r', region]
    if target:
        args.extend(['-t', target])
    
    # 调用
    sys.argv = args
    try:
        text_main()
        return True, "报价完成"
    except Exception as e:
        return False, f"报价失败: {str(e)}"


def analyze_text(text: str) -> dict:
    """
    分析文本配置（场景二预处理）
    
    在报价前先分析统计，供用户确认
    
    Args:
        text: 配置文本
        
    Returns:
        {
            'instance_count': int,
            'instances': [{'name', 'spec', 'vcpu', 'memory', ...}],
            'need_confirm': bool
        }
    """
    from ecs_text_quoter import parse_text_instances
    
    instances = parse_text_instances(text)
    
    return {
        'instance_count': len(instances),
        'instances': [
            {
                'name': inst.name,
                'spec': inst.spec,
                'vcpu': inst.vcpu,
                'memory': inst.memory,
                'system_disk': f"{inst.system_disk_type} {inst.system_disk_size}GiB",
                'data_disks': len(inst.data_disks),
                'bandwidth': f"{inst.bandwidth}Mbps"
            }
            for inst in instances
        ],
        'need_confirm': True  # 场景二需要用户确认
    }


def quote(input_str: str, target: str = None, region: str = "cn-beijing", 
          skip_confirm: bool = False) -> Tuple[bool, str, Optional[dict]]:
    """
    统一报价入口
    
    自动判断场景，调用对应处理器
    
    Args:
        input_str: 输入内容（CSV 文件路径或文本配置）
        target: 目标用户 open_id
        region: 地域代码
        skip_confirm: 是否跳过确认（场景二用）
        
    Returns:
        (success, message, analysis)
    """
    # 判断场景
    if is_csv_file(input_str):
        # 场景一：直接报价
        print(f"[场景一] 检测到标准 CSV 文件：{os.path.basename(input_str)}")
        success, msg = quote_csv(input_str, target)
        return success, msg, None
    else:
        # 场景二：先分析
        print(f"[场景二] 检测到文本配置")
        analysis = analyze_text(input_str)
        
        if skip_confirm:
            # 直接报价
            success, msg = quote_text(input_str, target, region)
            return success, msg, analysis
        else:
            # 返回分析结果，等待确认
            return True, "需要用户确认", analysis


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="ECS 报价统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 场景一：CSV 文件报价
  python ecs_quoter.py ecs_instance_list_cn-beijing_2026-02-08.csv -t ou_xxx
  
  # 场景二：文本配置报价
  python ecs_quoter.py "ecs.g6.xlarge 4核16G" -t ou_xxx
  
  # 场景二：从文件读取配置
  python ecs_quoter.py -f config.txt -t ou_xxx
  
  # 场景二：跳过确认直接报价
  python ecs_quoter.py "ecs.g6.xlarge 4核16G" -t ou_xxx --skip-confirm
"""
    )
    
    parser.add_argument("input", nargs='?', help="CSV 文件路径或文本配置")
    parser.add_argument("-f", "--file", help="配置文件路径")
    parser.add_argument("-t", "--target", help="目标用户 open_id")
    parser.add_argument("-r", "--region", default="cn-beijing", help="地域代码")
    parser.add_argument("--skip-confirm", action="store_true", help="跳过确认直接报价")
    
    args = parser.parse_args()
    
    # 获取输入内容
    if args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            input_str = f.read()
    elif args.input:
        input_str = args.input
    else:
        parser.error("需要提供输入内容或文件路径")
    
    # 调用统一入口
    success, msg, analysis = quote(
        input_str, 
        args.target, 
        args.region,
        args.skip_confirm
    )
    
    # 输出分析结果（如果有）
    if analysis:
        print(f"\n检测到 {analysis['instance_count']} 台实例：")
        for inst in analysis['instances']:
            print(f"  {inst['name']}: {inst['spec']} ({inst['vcpu']}核{inst['memory']}G)")
        
        if analysis['need_confirm'] and not args.skip_confirm:
            print("\n请确认后报价，或使用 --skip-confirm 跳过确认")
    
    if not success:
        print(f"\n❌ {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()