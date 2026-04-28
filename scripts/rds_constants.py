#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 常量定义
"""

# 地域代码到中文名称的映射（与 ECS 共用）
REGION_CODE_TO_NAME = {
    "cn-qingdao": "华北 1（青岛）",
    "cn-beijing": "华北 2（北京）",
    "cn-zhangjiakou": "华北 3（张家口）",
    "cn-huhehaote": "华北 5（呼和浩特）",
    "cn-wulanchabu": "华北 6（乌兰察布）",
    "cn-hangzhou": "华东 1（杭州）",
    "cn-shanghai": "华东 2（上海）",
    "cn-nanjing": "华东 5（南京）",
    "cn-fuzhou": "华东 6（福州）",
    "cn-guangzhou": "华南 3（广州）",
    "cn-shenzhen": "华南 1（深圳）",
    "cn-heyuan": "华南 2（河源）",
    "cn-chengdu": "西南 1（成都）",
    "cn-hongkong": "中国香港",
    "ap-southeast-1": "新加坡",
    "ap-southeast-2": "悉尼",
    "ap-southeast-3": "吉隆坡",
    "ap-southeast-5": "雅加达",
    "ap-southeast-6": "马尼拉",
    "ap-southeast-7": "曼谷",
    "ap-southeast-8": "胡志明",
    "ap-northeast-1": "东京",
    "ap-northeast-2": "首尔",
    "ap-south-1": "孟买",
    "us-west-1": "硅谷",
    "us-east-1": "弗吉尼亚",
    "eu-central-1": "法兰克福",
    "eu-west-1": "伦敦",
    "me-east-1": "迪拜",
}

# 内地地域列表
INLAND_REGIONS = [
    "cn-qingdao", "cn-beijing", "cn-zhangjiakou", "cn-huhehaote", "cn-wulanchabu",
    "cn-hangzhou", "cn-shanghai", "cn-nanjing", "cn-fuzhou",
    "cn-guangzhou", "cn-shenzhen", "cn-heyuan", "cn-chengdu"
]

# 数据库引擎映射（CSV 中的 Engine 值到 API 参数）
ENGINE_MAP = {
    "mysql": "MySQL",
    "mssql": "SQLServer",
    "postgresql": "PostgreSQL",
    "mariadb": "MariaDB",
}

# 存储类型映射
STORAGE_TYPE_MAP = {
    "general_essd": "高性能云盘",
    "local_ssd": "高性能本地盘",
    "cloud_ssd": "SSD 云盘",
    "cloud_essd": "ESSD PL1 云盘",
    "cloud_essd2": "ESSD PL2 云盘",
    "cloud_essd3": "ESSD PL3 云盘",
}

# SQLServer 版本后缀映射
MSSQL_EDITION_MAP = {
    "_ent": "企业集群版",
    "_ent_ha": "企业版",
    "_std_ha": "标准版",
    "_web": "Web 版",
}

# 产品系列映射（根据规格代码前缀判断）
SERIES_MAP = {
    "rds.mysql": "高可用系列",
    "rds.pg": "高可用系列",
    "rds.mssql": "高可用系列",
    "rds.mariadb": "高可用系列",
    "rds.sharding": "集群系列",
    "mysql.n": "基础系列",
    "pg.n": "基础系列",
}

# 产品架构映射（部分引擎有）
ARCHITECTURE_MAP = {
    "rds.mysql.c": "标准版",
    "rds.mysql.t": "倚天版",
}
