#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里云 Skill 共享配置读取工具
所有入口脚本在启动时调用 setup_output_dir()，统一从 config.json 读取输出目录。
"""

import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "config.json")
DEFAULT_OUTPUT_DIR = "/root/.openclaw/workspace/download/"


def load_config():
    """读取 config.json，返回 dict"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_output_dir():
    """从 config.json 获取 output_dir，失败则返回默认值"""
    cfg = load_config()
    return cfg.get("output_dir", DEFAULT_OUTPUT_DIR)


def setup_output_dir():
    """读取 config.json 中的 output_dir，写入环境变量，供生成器类读取"""
    output_dir = get_output_dir()
    os.environ["ALIYUN_SKILL_OUTPUT_DIR"] = output_dir
    return output_dir
