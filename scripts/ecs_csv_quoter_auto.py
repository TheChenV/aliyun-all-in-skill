#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 ECS 报价技能 - 自动发送 wrapper
调用 ecs_csv_quoter.py 生成报价单，然后自动发送到飞书对话并清理本地文件
"""

import os
import sys
import subprocess
import json

# 脚本目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_QUOTER = os.path.join(SCRIPT_DIR, "ecs_csv_quoter.py")
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python")

# 输出目录
OUTPUT_DIR = "/root/.openclaw/workspace/download/"

# 允许的媒体目录（OpenClaw 限制）
ALLOWED_MEDIA_DIR = "/root/.openclaw/workspace/"


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


def send_via_openclaw(file_path, message, target=None):
    """
    通过 openclaw message send 发送文件
    
    Args:
        file_path: 文件路径
        message: 消息文本
        target: 目标用户 open_id（可选，默认使用环境变量或配置）
    """
    # 检查文件是否在允许的目录
    if not file_path.startswith(ALLOWED_MEDIA_DIR):
        # 需要复制到允许的目录
        import shutil
        safe_path = os.path.join(ALLOWED_MEDIA_DIR, os.path.basename(file_path))
        shutil.copy2(file_path, safe_path)
        file_path = safe_path
        print(f"文件已复制到允许目录：{file_path}")
    
    # 获取 target：必须传入或通过环境变量设置
    if not target:
        target = os.environ.get("FEISHU_TARGET")
    if not target:
        raise ValueError("未指定目标用户 open_id，请通过 --target 参数或 FEISHU_TARGET 环境变量传入")
    
    # 构建命令
    cmd = [
        "openclaw", "message", "send",
        "--channel", "feishu",
        "--account", "yunbao",
        "--target", target,
        "--message", message,
        "--media", file_path
    ]
    
    print(f"发送文件：{file_path}")
    print(f"消息：{message}")
    
    # 执行命令
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    
    # 检查是否发送成功
    if "✅ Sent via Feishu" in result.stdout or "✅ Sent via Feishu" in result.stderr:
        print("✅ 文件发送成功")
        return True
    else:
        print(f"❌ 文件发送失败")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        return False


def cleanup_file(file_path):
    """
    清理本地文件
    
    Args:
        file_path: 文件路径
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"✅ 已删除本地文件：{file_path}")
            
            # 如果文件是复制到允许目录的，也要删除原始文件
            original_file = os.path.join(OUTPUT_DIR, os.path.basename(file_path))
            if original_file != file_path and os.path.exists(original_file):
                os.remove(original_file)
                print(f"✅ 已删除原始文件：{original_file}")
    except Exception as e:
        print(f"❌ 删除文件失败：{e}")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="ECS 报价单自动生成与发送")
    parser.add_argument("csv_path", help="ECS 实例清单 CSV 文件路径")
    parser.add_argument("-m", "--message", help="自定义发送消息")
    parser.add_argument("-t", "--target", help="目标用户 open_id（默认：当前对话用户）")
    
    args = parser.parse_args()
    
    csv_path = args.csv_path
    custom_message = args.message
    target = args.target
    
    if not os.path.exists(csv_path):
        print(f"❌ 文件不存在：{csv_path}")
        sys.exit(1)
    
    # 调用 ecs_csv_quoter.py 生成报价单
    print(f"解析 CSV 文件：{csv_path}")
    result = subprocess.run(
        [VENV_PYTHON, CSV_QUOTER, csv_path],
        capture_output=True,
        text=True,
        timeout=180
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
    
    print(f"Excel 文件已生成：{excel_path}")
    
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
    except Exception as e:
        print(f"⚠️ 无法统计实例数量：{e}")
        instance_count = 0  # 不显示默认值
    
    # 生成消息
    if custom_message:
        message = custom_message
    else:
        if instance_count > 0:
            message = f"ECS 实例报价单已生成，共 {instance_count} 台实例。"
        else:
            message = f"ECS 实例报价单已生成，请查收。"
    
    # 发送文件
    print(f"\n发送文件到飞书...")
    send_success = send_via_openclaw(excel_path, message, target=target)
    
    # 清理文件
    print(f"\n清理本地文件...")
    cleanup_file(excel_path)
    
    if send_success:
        print("\n✅ 报价单已发送并清理完成")
    else:
        print("\n⚠️ 发送失败，但文件已保留在：{excel_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
