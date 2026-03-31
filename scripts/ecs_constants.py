#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECS 公共常量模块
统一管理地域映射、磁盘类型、镜像类型等常量
"""

# ==================== 地域映射 ====================

# 地域代码到中文名称（ECS/OSS 通用）
REGION_CODE_TO_NAME = {
    # 中国内地
    "cn-hangzhou": "华东 1（杭州）",
    "cn-shanghai": "华东 2（上海）",
    "cn-qingdao": "华北 1（青岛）",
    "cn-beijing": "华北 2（北京）",
    "cn-zhangjiakou": "华北 3（张家口）",
    "cn-huhehaote": "华北 5（呼和浩特）",
    "cn-wulanchabu": "华北 6（乌兰察布）",
    "cn-shenzhen": "华南 1（深圳）",
    "cn-heyuan": "华南 2（河源）",
    "cn-guangzhou": "华南 3（广州）",
    "cn-chengdu": "西南 1（成都）",
    # 中国香港、澳门、台湾
    "cn-hongkong": "中国香港",
    "mo-yamate": "中国澳门",
    "cn-taipei": "中国台湾",
    # 亚太地区
    "ap-southeast-1": "新加坡",
    "ap-southeast-2": "澳大利亚（悉尼）",
    "ap-southeast-3": "马来西亚（吉隆坡）",
    "ap-southeast-5": "印度尼西亚（雅加达）",
    "ap-southeast-6": "菲律宾（马尼拉）",
    "ap-southeast-7": "泰国（曼谷）",
    "ap-southeast-8": "越南（胡志明）",
    "ap-northeast-1": "日本（东京）",
    "ap-northeast-2": "韩国（首尔）",
    "ap-south-1": "印度（孟买）",
    "ap-south-2": "印度（海德拉巴）",
    # 欧洲地区
    "eu-central-1": "德国（法兰克福）",
    "eu-west-1": "英国（伦敦）",
    "eu-west-2": "瑞士（苏黎世）",
    # 中东地区
    "me-east-1": "阿联酋（迪拜）",
    "me-central-1": "沙特（利雅得）",
    # 美洲地区
    "us-west-1": "美国（硅谷）",
    "us-east-1": "美国（弗吉尼亚）",
    "sa-east-1": "巴西（圣保罗）",
    "mx-central-1": "墨西哥（克雷塔罗）",
}

# 中文名称到地域代码
REGION_NAME_TO_CODE = {v: k for k, v in REGION_CODE_TO_NAME.items()}

# 地域关键词到地域代码（用于文本解析识别地域）
REGION_KEYWORDS_TO_CODE = {
    # 中国内地
    '杭州': 'cn-hangzhou',
    '华东1': 'cn-hangzhou',
    '华东 1': 'cn-hangzhou',
    '上海': 'cn-shanghai',
    '华东2': 'cn-shanghai',
    '华东 2': 'cn-shanghai',
    '北京': 'cn-beijing',
    '华北2': 'cn-beijing',
    '华北 2': 'cn-beijing',
    '青岛': 'cn-qingdao',
    '华北1': 'cn-qingdao',
    '华北 1': 'cn-qingdao',
    '深圳': 'cn-shenzhen',
    '华南1': 'cn-shenzhen',
    '华南 1': 'cn-shenzhen',
    '广州': 'cn-guangzhou',
    '华南3': 'cn-guangzhou',
    '华南 3': 'cn-guangzhou',
    '成都': 'cn-chengdu',
    '西南1': 'cn-chengdu',
    '西南 1': 'cn-chengdu',
    '张家口': 'cn-zhangjiakou',
    '华北3': 'cn-zhangjiakou',
    '华北 3': 'cn-zhangjiakou',
    '呼和浩特': 'cn-huhehaote',
    '华北5': 'cn-huhehaote',
    '华北 5': 'cn-huhehaote',
    '乌兰察布': 'cn-wulanchabu',
    '华北6': 'cn-wulanchabu',
    '华北 6': 'cn-wulanchabu',
    '河源': 'cn-heyuan',
    '华南2': 'cn-heyuan',
    '华南 2': 'cn-heyuan',
    # 中国香港、澳门、台湾
    '香港': 'cn-hongkong',
    '澳门': 'mo-yamate',
    '台湾': 'cn-taipei',
    # 亚太地区
    '新加坡': 'ap-southeast-1',
    '日本': 'ap-northeast-1',
    '东京': 'ap-northeast-1',
    '日本东京': 'ap-northeast-1',
    '韩国': 'ap-northeast-2',
    '首尔': 'ap-northeast-2',
    '韩国首尔': 'ap-northeast-2',
    '马来西亚': 'ap-southeast-3',
    '吉隆坡': 'ap-southeast-3',
    '印度尼西亚': 'ap-southeast-5',
    '雅加达': 'ap-southeast-5',
    '印度': 'ap-south-1',
    '孟买': 'ap-south-1',
    '澳大利亚': 'ap-southeast-2',
    '悉尼': 'ap-southeast-2',
    '菲律宾': 'ap-southeast-6',
    '马尼拉': 'ap-southeast-6',
    '泰国': 'ap-southeast-7',
    '曼谷': 'ap-southeast-7',
    '越南': 'ap-southeast-8',
    '胡志明': 'ap-southeast-8',
    # 欧洲地区
    '德国': 'eu-central-1',
    '法兰克福': 'eu-central-1',
    '英国': 'eu-west-1',
    '伦敦': 'eu-west-1',
    '瑞士': 'eu-west-2',
    '苏黎世': 'eu-west-2',
    # 中东地区
    '阿联酋': 'me-east-1',
    '迪拜': 'me-east-1',
    '阿联酋迪拜': 'me-east-1',
    '中东': 'me-east-1',
    '沙特': 'me-central-1',
    '利雅得': 'me-central-1',
    # 美洲地区
    '美国': 'us-west-1',
    '硅谷': 'us-west-1',
    '美国硅谷': 'us-west-1',
    '弗吉尼亚': 'us-east-1',
    '美国弗吉尼亚': 'us-east-1',
    '巴西': 'sa-east-1',
    '圣保罗': 'sa-east-1',
    '墨西哥': 'mx-central-1',
    # 英文/代码关键词（直接匹配）
    'cn-hangzhou': 'cn-hangzhou',
    'cn-shanghai': 'cn-shanghai',
    'cn-beijing': 'cn-beijing',
    'cn-qingdao': 'cn-qingdao',
    'cn-shenzhen': 'cn-shenzhen',
    'cn-guangzhou': 'cn-guangzhou',
    'cn-chengdu': 'cn-chengdu',
    'cn-hongkong': 'cn-hongkong',
    'cn-zhangjiakou': 'cn-zhangjiakou',
    'cn-huhehaote': 'cn-huhehaote',
    'cn-wulanchabu': 'cn-wulanchabu',
    'cn-heyuan': 'cn-heyuan',
    'ap-southeast-1': 'ap-southeast-1',
    'ap-northeast-1': 'ap-northeast-1',
    'ap-northeast-2': 'ap-northeast-2',
    'ap-southeast-2': 'ap-southeast-2',
    'ap-southeast-3': 'ap-southeast-3',
    'ap-southeast-5': 'ap-southeast-5',
    'ap-southeast-6': 'ap-southeast-6',
    'ap-southeast-7': 'ap-southeast-7',
    'ap-southeast-8': 'ap-southeast-8',
    'ap-south-1': 'ap-south-1',
    'eu-central-1': 'eu-central-1',
    'eu-west-1': 'eu-west-1',
    'eu-west-2': 'eu-west-2',
    'us-west-1': 'us-west-1',
    'us-east-1': 'us-east-1',
    'sa-east-1': 'sa-east-1',
    'mx-central-1': 'mx-central-1',
    'me-east-1': 'me-east-1',
    'me-central-1': 'me-central-1',
}

# 中国内地地域列表（Windows 在这些地域免费）
INLAND_REGIONS = [
    'cn-hangzhou', 'cn-shanghai', 'cn-qingdao', 'cn-beijing',
    'cn-zhangjiakou', 'cn-huhehaote', 'cn-wulanchabu',
    'cn-shenzhen', 'cn-heyuan', 'cn-guangzhou', 'cn-chengdu'
]

# OSS 地域名称（带 oss- 前缀）
OSS_REGION_NAMES = {
    'oss-cn-hangzhou': '华东1（杭州）',
    'oss-cn-shanghai': '华东2（上海）',
    'oss-cn-qingdao': '华北1（青岛）',
    'oss-cn-beijing': '华北2（北京）',
    'oss-cn-zhangjiakou': '华北3（张家口）',
    'oss-cn-huhehaote': '华北5（呼和浩特）',
    'oss-cn-wulanchabu': '华北6（乌兰察布）',
    'oss-cn-shenzhen': '华南1（深圳）',
    'oss-cn-heyuan': '华南2（河源）',
    'oss-cn-guangzhou': '华南3（广州）',
    'oss-cn-chengdu': '西南1（成都）',
    'oss-cn-hongkong': '中国（香港）',
    'oss-us-west-1': '美国西部1（硅谷）',
    'oss-us-east-1': '美国东部1（弗吉尼亚）',
    'oss-ap-southeast-1': '亚太东南1（新加坡）',
    'oss-ap-southeast-2': '亚太东南2（悉尼）',
    'oss-ap-southeast-3': '亚太东南3（吉隆坡）',
    'oss-ap-southeast-5': '亚太东南5（雅加达）',
    'oss-ap-northeast-1': '亚太东北1（东京）',
    'oss-ap-south-1': '亚太南部1（孟买）',
    'oss-eu-central-1': '欧洲中部1（法兰克福）',
    'oss-eu-west-1': '英国（伦敦）',
    'oss-me-east-1': '中东东部1（迪拜）',
}


# ==================== 磁盘类型 ====================

# 磁盘类型映射（显示名称 -> MCP 参数）
DISK_TYPES = {
    # ESSD 系列
    "ESSD 云盘 PL0": {"category": "cloud_essd", "pl": "PL0"},
    "ESSD 云盘 PL1": {"category": "cloud_essd", "pl": "PL1"},
    "ESSD 云盘 PL2": {"category": "cloud_essd", "pl": "PL2"},
    "ESSD 云盘 PL3": {"category": "cloud_essd", "pl": "PL3"},
    "ESSD Entry 云盘": {"category": "cloud_essd_entry", "pl": None},
    "ESSD AutoPL 云盘": {"category": "cloud_auto", "pl": None},
    # SSD
    "SSD 云盘": {"category": "cloud_ssd", "pl": None},
    # 高效云盘
    "高效云盘": {"category": "cloud_efficiency", "pl": None},
    # 普通云盘
    "普通云盘": {"category": "cloud", "pl": None},
}

# 默认磁盘类型
DEFAULT_DISK_TYPE = "ESSD 云盘 PL0"


# ==================== 存储类型名称 ====================

# 存储类型英文 -> 中文
STORAGE_CLASS_NAMES = {
    'Standard': '标准存储',
    'IA': '低频存储',
    'Archive': '归档存储',
    'ColdArchive': '冷归档存储',
    'DeepColdArchive': '深度冷归档存储',
}

# 冗余类型英文 -> 中文
REDUNDANCY_TYPE_NAMES = {
    'LRS': '本地冗余',
    'ZRS': '同城冗余',
}


# ==================== 工具函数 ====================

def get_region_name(region_code: str) -> str:
    """
    根据地域代码获取中文名称
    
    Args:
        region_code: 地域代码（如 cn-hangzhou）
        
    Returns:
        中文名称
    """
    return REGION_CODE_TO_NAME.get(region_code, region_code)


def get_region_code(region_name: str) -> str:
    """
    根据中文名称获取地域代码
    
    Args:
        region_name: 中文名称
        
    Returns:
        地域代码
    """
    return REGION_NAME_TO_CODE.get(region_name, region_name)