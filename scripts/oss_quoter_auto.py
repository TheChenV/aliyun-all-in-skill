#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSS 统计自动发送 wrapper
调用 oss_stat.py 分析 OSS，自动发送到飞书对话并清理本地文件
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

# 输出目录
OUTPUT_DIR = "/root/.openclaw/workspace/download/"

# 允许的媒体目录（OpenClaw 限制）
ALLOWED_MEDIA_DIR = "/root/.openclaw/workspace/"


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


def send_via_openclaw(file_path, message, target):
    """通过 openclaw message send 发送文件"""
    import json

    # 检查文件是否在允许的目录
    if not file_path.startswith(ALLOWED_MEDIA_DIR):
        import shutil
        safe_path = os.path.join(ALLOWED_MEDIA_DIR, os.path.basename(file_path))
        shutil.copy2(file_path, safe_path)
        file_path = safe_path
        print(f"文件已复制到允许目录：{file_path}")

    # 获取 feishu account：优先环境变量，其次 config.json
    feishu_account = os.environ.get("FEISHU_ACCOUNT")
    if not feishu_account:
        try:
            config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
            config_path = os.path.abspath(os.path.join(config_dir, "config.json"))
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                feishu_account = config.get("feishu_account")
        except Exception:
            pass

    # 构建命令
    cmd = [
        "openclaw", "message", "send",
        "--channel", "feishu",
        "--target", target,
        "--message", message,
        "--media", file_path
    ]
    if feishu_account:
        idx = cmd.index("--target")
        cmd.insert(idx, "--account")
        cmd.insert(idx + 1, feishu_account)

    print(f"发送文件：{file_path}")
    print(f"消息：{message}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if "✅ Sent via Feishu" in result.stdout or "✅ Sent via Feishu" in result.stderr:
        print("✅ 文件发送成功")
        return True
    else:
        print(f"❌ 文件发送失败")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        return False


def cleanup_file(file_path):
    """清理本地文件"""
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
    parser = argparse.ArgumentParser(description="OSS 资源统计自动发送")
    parser.add_argument("ak", help="AccessKey ID")
    parser.add_argument("sk", help="AccessKey Secret")
    parser.add_argument("-m", "--message", help="自定义发送消息")
    parser.add_argument("-t", "--target", help="目标用户 open_id")
    
    args = parser.parse_args()
    
    # 获取 target
    target = args.target
    if not target:
        target = os.environ.get("FEISHU_TARGET")
    if not target:
        print("❌ 未指定目标用户 open_id，请通过 --target 参数或 FEISHU_TARGET 环境变量传入")
        sys.exit(1)
    
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
    
    print(f"Excel 文件已生成：{excel_path}")
    
    # 生成消息
    if args.message:
        message = args.message
    else:
        message = "OSS 资源统计报告已生成，请查收。"
    
    # 发送文件
    print(f"\n发送文件到飞书...")
    send_success = send_via_openclaw(excel_path, message, target)
    
    # 清理文件
    print(f"\n清理本地文件...")
    cleanup_file(excel_path)
    
    # 删除 AK 配置
    print(f"\n删除 AK 配置...")
    cleanup_ak_config()
    
    if send_success:
        print("\n✅ OSS 统计报告已发送并清理完成")
    else:
        print(f"\n⚠️ 发送失败，但文件已保留在：{excel_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()