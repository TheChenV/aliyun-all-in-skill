#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 场景二：文字配置解析器
"""

import re
from typing import List, Optional
from dataclasses import dataclass

from rds_common import (
    resolve_region, resolve_category,
    resolve_storage, resolve_storage_type,
    resolve_engine_version_for_api, resolve_class_group,
    resolve_storage_type_raw,
    ENGINE_DEFAULT_VERSIONS
)

# 不支持的引擎关键词（用于检测并报错）
UNSUPPORTED_ENGINES = {
    "oracle": "Oracle",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
}


@dataclass
class RDSTextConfig:
    index: int
    raw_text: str = ""
    region_id: str = "cn-hangzhou"
    engine: str = "MySQL"
    engine_version_raw: str = ""
    engine_version: str = ""
    db_instance_class: str = ""
    cpu: int = 0
    memory: int = 0
    category: str = ""
    class_group: str = ""
    storage_type_raw: str = ""
    db_instance_storage: int = 100
    db_instance_storage_type: str = ""  # 由验证器根据 JSON 推导或使用用户提供的值


class RDSTextParser:
    def __init__(self, text: str):
        self.text = text.strip()
        self.items: List[RDSTextConfig] = []

    def parse(self) -> List[RDSTextConfig]:
        segments = self._split_by_index(self.text)
        for idx, segment in enumerate(segments, 1):
            config = self._parse_single(idx, segment)
            self.items.append(config)
        return self.items

    def _split_by_index(self, text: str) -> List[str]:
        pattern = r'(?:(?:^|\n)\s*(\d+)\s*[、.）)]\s*)'
        splits = [m.start() for m in re.finditer(pattern, text)]
        if not splits:
            return [text.strip()] if text.strip() else []
        segments = []
        for i, pos in enumerate(splits):
            end = splits[i + 1] if i + 1 < len(splits) else len(text)
            segments.append(text[pos:end].strip())
        return segments

    def _parse_single(self, index: int, text: str) -> RDSTextConfig:
        config = RDSTextConfig(index=index, raw_text=text)
        config.db_instance_class = self._extract_classcode(text)
        config.engine = self._extract_engine(text)
        config.cpu, config.memory = self._extract_cpu_memory(text)
        config.engine_version_raw = self._extract_version_raw(text, config.engine)
        config.engine_version = resolve_engine_version_for_api(config.engine_version_raw)
        config.category = self._extract_category(text)
        config.region_id = self._extract_region(text)
        config.db_instance_storage = self._extract_storage(text)
        config.db_instance_storage_type = self._extract_storage_type(text)
        config.class_group = self._extract_class_group(text)
        config.storage_type_raw = self._extract_storage_type_raw(text)
        if not config.engine_version:
            config.engine_version = ENGINE_DEFAULT_VERSIONS.get(config.engine, "")
        return config

    def _extract_classcode(self, text: str) -> str:
        match = re.search(r'([a-zA-Z][\w]*\.[\w]+\.[\w]+(?:\.[\w]+)?)', text)
        return match.group(1) if match else ""

    def _extract_engine(self, text: str) -> str:
        t = text.lower()
        if 'sqlserver' in t or 'mssql' in t:
            return "SQLServer"
        if 'postgresql' in t or 'postgres' in t or 'pgsql' in t:
            return "PostgreSQL"
        if 'mariadb' in t:
            return "MariaDB"
        if 'mysql' in t:
            return "MySQL"
        # 检测不支持的引擎
        if 'oracle' in t:
            return "Oracle"
        if 'mongodb' in t or 'mongo' in t:
            return "MongoDB"
        return "MySQL"  # 默认

    def _extract_version_raw(self, text: str, engine: str) -> str:
        if engine == "SQLServer":
            match = re.search(r'(\d{4})\s*([\u4e00-\u9fff]+(?:版)?)?', text)
            if match:
                year = match.group(1)
                desc = match.group(2) or ""
                return f"{year}{desc}" if desc else year
            return ""
        classcode = self._extract_classcode(text)
        clean_text = text.replace(classcode, '') if classcode else text
        engine_patterns = {
            "MySQL": r'(?:mysql)\s*([\d.]+)',
            "PostgreSQL": r'(?:postgresql|postgres|pgsql)\s*([\d.]+)',
            "MariaDB": r'(?:mariadb)\s*([\d.]+)',
        }
        pattern = engine_patterns.get(engine)
        if pattern:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                return match.group(1)
        return ""

    def _extract_cpu_memory(self, text: str) -> tuple:
        # 优先匹配"X核YG"格式
        match = re.search(r'(\d+)\s*核\s*(\d+)\s*[gG]', text)
        if match:
            return int(match.group(1)), int(match.group(2))
        # "XcYG"格式：先移除 ClassCode 再匹配，避免".2c 1000G"误匹配
        clean = re.sub(r'[a-zA-Z][\w]*\.[\w]+\.[\w]+(?:\.[\w]+)?', '', text)
        match = re.search(r'(\d+)\s*[cC]\s*(\d+)\s*[gG]', clean)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0

    def _extract_category(self, text: str) -> str:
        return resolve_category(text)

    def _extract_region(self, text: str) -> str:
        return resolve_region(text)

    def _extract_storage(self, text: str) -> int:
        clean = text
        clean = re.sub(r'[a-zA-Z][\w]*\.[\w]+\.[\w]+(?:\.[\w]+)?', '', clean)
        clean = re.sub(r'^\s*\d+\s*[、.）)]\s*', '', clean)
        clean = re.sub(r'\d+\s*核\s*\d+\s*[gG]', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\d+\s*[cC]\s*\d+\s*[gG]', '', clean)
        clean = re.sub(r'(?:mysql|postgresql|postgres|pg|mariadb|mssql|sqlserver)\s*[\d.]+', '', clean, flags=re.IGNORECASE)
        # 只移除 SQLServer 年份（如 2022、2019），不移除任意 4 位数字（如 1000）
        clean = re.sub(r'\b(20[0-9]{2})\b', '', clean)
        return resolve_storage(clean)

    def _extract_storage_type(self, text: str) -> str:
        return resolve_storage_type(text)

    def _extract_class_group(self, text: str) -> str:
        return resolve_class_group(text)

    def _extract_storage_type_raw(self, text: str) -> str:
        return resolve_storage_type_raw(text)


if __name__ == "__main__":
    test_cases = [
        "1、杭州，4核8G，MySQL 8.0，高可用系列，500GB，ESSD PL1",
        "2、4核16G，PostgreSQL 14，基础系列，200G",
        "3、上海，mysql.x4.large.2c，100GB",
        "4、8核32G，SQLServer 2022企业版",
        "5、2核4G，MariaDB，100G",
    ]
    for tc in test_cases:
        parser = RDSTextParser(tc)
        configs = parser.parse()
        for c in configs:
            print(f"[{c.index}] {c.raw_text}")
            print(f"  engine={c.engine}, ver={c.engine_version_raw!r}/{c.engine_version!r}")
            print(f"  classcode={c.db_instance_class!r}, cpu={c.cpu}, mem={c.memory}")
            print(f"  cat={c.category!r}, storage={c.db_instance_storage}GB, type={c.db_instance_storage_type}")
            print()
