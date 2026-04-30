#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSS 统计入口
调用 oss_stat.py 分析 OSS，输出文件路径供 AI 发送
"""

import os
import sys
import subprocess
import argparse

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OSS_STAT = os.path.join(SCRIPT_DIR, "oss_stat.py")

# venv Python（优先使用，确保 oss2 等依赖可用）
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python3")
PYTHON = VENV_PYTHON if os.path.exists(VENV_PYTHON) else "python3"

# 从 config.json 读取输出目录
from skill_config import setup_output_dir

OUTPUT_DIR = setup_output_dir()


def get_latest_excel():
    """获取最新生成的 Excel 文件"""
    if not os.path.exists(OUTPUT_DIR):
        return None
    
    files = [f for f in os.listdir(OUTPUT_DIR) if f.startswith("OSS 使用统计") and f.endswith(".xlsx")]
    if not files:
        return None
    
    # 按修改时间排序，返回最新的
    files.sort(key=lambda f: os.path.getmtime(os.path.join(OUTPUT_DIR, f)), reverse=True)
    return os.path.join(OUTPUT_DIR, files[0])


def cleanup_ak_config(account_id: str = "oss_account"):
    """删除本地保存的 AK 配置"""
    try:
        from config_store import ConfigStore
        store = ConfigStore()
        store.delete_account(account_id)
        print(f"✅ 已删除 AK 配置：{account_id}")
    except Exception as e:
        print(f"⚠️ 删除 AK 配置失败：{e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="OSS 资源统计")
    parser.add_argument("ak", help="AccessKey ID")
    parser.add_argument("sk", help="AccessKey Secret")
    parser.add_argument("-m", "--message", help="自定义消息（可选）")
    
    args = parser.parse_args()
    
    # 调用 oss_stat.py 分析
    print(f"开始 OSS 资源统计...")
    
    result = subprocess.run(
        [PYTHON, OSS_STAT, args.ak, args.sk],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    print(result.stdout)
    
    if result.returncode != 0:
        print(f"❌ OSS 统计失败：{result.stderr}")
        sys.exit(1)
    
    # 获取最新生成的 Excel 文件
    excel_path = get_latest_excel()
    if not excel_path:
        print("❌ 未找到生成的 Excel 文件")
        sys.exit(1)
    
    print(f"\n✅ OSS 统计报告已生成：{excel_path}")
    print(f"FILE_PATH:{excel_path}")
    
    # 删除 AK 配置
    cleanup_ak_config()


if __name__ == "__main__":
    main()