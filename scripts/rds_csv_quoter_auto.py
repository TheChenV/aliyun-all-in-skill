#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 RDS 报价技能 - CSV 自动报价入口
调用 rds_csv_quoter.py 生成报价单，输出文件路径供 AI 发送
"""

import os
import sys
import subprocess

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_QUOTER = os.path.join(SCRIPT_DIR, "rds_csv_quoter.py")
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python")

# 从 config.json 读取输出目录
from skill_config import setup_output_dir

OUTPUT_DIR = setup_output_dir()


def get_latest_excel():
    """获取最新生成的 Excel 文件"""
    if not os.path.exists(OUTPUT_DIR):
        return None
    
    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("阿里云资源清单") and f.endswith(".xlsx")]
    if not files:
        return None
    
    # 按修改时间排序，返回最新的
    files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)), reverse=True)
    return os.path.join(OUTPUT_DIR, files[0])


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="RDS 报价单自动生成（CSV 场景）")
    parser.add_argument("csv_path", help="RDS 实例清单 CSV 文件路径")
    parser.add_argument("-m", "--message", help="自定义消息（可选）")
    
    args = parser.parse_args()
    
    csv_path = args.csv_path
    
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在：{csv_path}")
        sys.exit(1)
    
    # 调用 rds_csv_quoter.py 生成报价单
    print(f"解析 CSV 文件：{csv_path}")
    result = subprocess.run(
        [VENV_PYTHON, CSV_QUOTER, csv_path],
        capture_output=True,
        text=True,
        timeout=300  # RDS 报价可能需要更长时间
    )
    
    # 检查报价是否成功
    if result.returncode != 0:
        print(f"❌ 报价失败：{result.stderr}")
        sys.exit(1)
    
    print(result.stdout)
    
    # 获取最新生成的 Excel 文件
    excel_path = get_latest_excel()
    if not excel_path:
        print("❌ 未找到生成的 Excel 文件")
        sys.exit(1)
    
    # 解析 CSV 获取实例数量（尝试多种编码）
    instance_count = 0
    try:
        import csv
        for encoding in ['utf-8', 'gbk', 'gb2312']:
            try:
                with open(csv_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    instance_count = sum(1 for _ in reader)
                    if instance_count > 0:
                        break
            except UnicodeDecodeError:
                continue
    except Exception:
        pass
    
    # 输出结果（供 AI 读取）
    if instance_count > 0:
        print(f"\n✅ 报价单已生成：{excel_path}（共 {instance_count} 台 RDS 实例）")
    else:
        print(f"\n✅ 报价单已生成：{excel_path}")
    
    # 输出文件路径（AI 会读取此路径来发送文件）
    print(f"FILE_PATH:{excel_path}")


if __name__ == "__main__":
    main()
