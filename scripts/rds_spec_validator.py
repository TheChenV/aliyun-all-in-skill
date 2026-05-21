#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RDS 场景二：规格匹配验证器
根据用户配置在 rds_series.json 中匹配规格，验证一致性
"""

import json
import os
import re
from typing import List, Dict, Optional
from dataclasses import dataclass

from rds_common import (
    derive_engine_from_classcode, extract_memory_from_memoryclass,
    get_class_group_priority, normalize_engine,
    ENGINE_DEFAULT_VERSIONS, CATEGORY_DISPLAY,
    DEFAULT_CLASS_GROUP_PRIORITY, resolve_class_group,
)


@dataclass
class SpecMatchResult:
    """规格匹配结果"""
    class_code: str = ""           # 匹配的 ClassCode
    engine: str = ""               # 推导的引擎类型
    engine_version: str = ""       # 确定的版本号
    category: str = ""             # 产品系列
    cpu: int = 0                   # 实际 CPU 核数
    memory: int = 0                # 实际内存 GB
    memory_class: str = ""         # 原始 MemoryClass 字符串
    class_group: str = ""          # 原始 ClassGroup 字符串
    reference_price: int = 0       # 参考报价
    storage_type_raw: str = ""     # JSON 原始 storageType（Local/Cloud）
    storage_type_api: str = ""     # 用于询价 API 的存储类型代码
    error: str = ""                # 错误信息（非空表示失败）


class RDSSpecValidator:
    """规格匹配验证器"""

    def __init__(self, series_path_or_data):
        """
        初始化验证器

        Args:
            series_path_or_data: rds_series.json 路径 或 Items 列表
        """
        if isinstance(series_path_or_data, str):
            with open(series_path_or_data, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.items = data.get("Items", [])
        else:
            self.items = series_path_or_data

    def validate(self, config) -> SpecMatchResult:
        """
        验证并匹配规格

        Args:
            config: RDSTextConfig 实例

        Returns:
            SpecMatchResult
        """
        if config.db_instance_class:
            return self._match_by_classcode(config)
        elif config.cpu > 0 and config.memory > 0:
            return self._match_by_cpu_memory(config)
        else:
            return SpecMatchResult(error="未提供实例规格或 CPU/内存配置")

    def _match_by_classcode(self, config) -> SpecMatchResult:
        """
        流程 1：用户提供了 ClassCode
        """
        class_code = config.db_instance_class

        # 1. 精确查找 ClassCode
        matched = self._find_exact_classcode(class_code)
        if not matched:
            return SpecMatchResult(error="提供的数据库规格不存在，请检查")

        # 2. 推导 Engine
        derived_engine = derive_engine_from_classcode(class_code)

        # 3. 校验 Engine 一致性
        # 只有用户显式提供了引擎关键词时才校验冲突
        # 如果用户用的是默认 MySQL，则以 ClassCode 推导的为准
        if config.engine and config.engine != "MySQL":
            if derived_engine != config.engine:
                return SpecMatchResult(error="该数据库规格和提供的数据库类型冲突，请检查")

        # 使用推导出的引擎（覆盖默认的 MySQL）
        engine = derived_engine

        # 4. 校验 CPU/内存一致性（如果用户提供了）
        actual_cpu = int(matched.get("Cpu", "0").strip() or "0")
        actual_memory = extract_memory_from_memoryclass(matched.get("MemoryClass", ""))

        if config.cpu > 0 and actual_cpu != config.cpu:
            return SpecMatchResult(error="该数据库规格和提供的 CPU/内存配置冲突，请检查")
        if config.memory > 0 and actual_memory != config.memory:
            return SpecMatchResult(error="该数据库规格和提供的 CPU/内存配置冲突，请检查")

        # 5. 确定系列（category）并校验
        category = self._resolve_category(matched, config)
        if category == "Cluster":
            return SpecMatchResult(error="集群系列暂不自动报价，请人工确认")

        # 5b. 校验用户提供的 category 与 JSON 是否一致
        if config.category and config.category != category:
            return SpecMatchResult(error="该数据库规格和提供的产品系列冲突，请检查")

        # 6. 校验存储类型（storageType）
        json_storage_type = matched.get("storageType", "")  # Local 或 Cloud
        if config.storage_type_raw and json_storage_type and config.storage_type_raw != json_storage_type:
            return SpecMatchResult(error="该数据库规格和提供的存储类型冲突，请检查")

        # 7. 校验规格族（ClassGroup）
        json_class_group = matched.get("ClassGroup", "")
        if config.class_group and config.class_group != json_class_group:
            return SpecMatchResult(error="该数据库规格和提供的规格族冲突，请检查")

        # 8. 确定 EngineVersion
        if config.engine_version_raw:
            engine_version = self._normalize_version(engine, config.engine_version_raw)
        else:
            engine_version = ENGINE_DEFAULT_VERSIONS.get(engine, "")

        # 8b. MariaDB 版本校验
        if engine.lower() == "mariadb":
            from rds_common import MARIADB_SUPPORTED_VERSIONS
            ver_num = engine_version.split(".")[0] + "." + engine_version.split(".")[1] if "." in engine_version else engine_version
            if ver_num not in MARIADB_SUPPORTED_VERSIONS:
                return SpecMatchResult(error="该数据库版本不支持，MariaDB 仅支持 10.3/10.6 版本")

        # 9. 推导 storage_type_api（用户提供了具体代码则用用户的，否则根据 JSON 推导）
        if engine.lower() == "mariadb":
            # MariaDB 仅支持 ESSD PL1/PL2/PL3，默认 cloud_essd（PL1）
            storage_type_api = config.db_instance_storage_type if config.db_instance_storage_type else "cloud_essd"
        elif config.db_instance_storage_type:
            storage_type_api = config.db_instance_storage_type
        elif json_storage_type == "Local":
            storage_type_api = "local_ssd"
        else:
            storage_type_api = "general_essd"

        return SpecMatchResult(
            class_code=class_code,
            engine=engine,
            engine_version=engine_version,
            category=category,
            cpu=actual_cpu,
            memory=actual_memory,
            memory_class=matched.get("MemoryClass", ""),
            class_group=json_class_group,
            reference_price=int(matched.get("ReferencePrice", "0") or "0"),
            storage_type_raw=json_storage_type,
            storage_type_api=storage_type_api,
        )

    def _match_by_cpu_memory(self, config) -> SpecMatchResult:
        """
        流程 2：用户未提供 ClassCode，但提供了 CPU + 内存
        """
        # 1. 确定 Engine
        engine = config.engine if config.engine else "MySQL"

        # 2. 确定 EngineVersion（提前，SQLServer 版本影响后续过滤）
        if config.engine_version_raw:
            engine_version = self._normalize_version(engine, config.engine_version_raw)
        else:
            engine_version = ENGINE_DEFAULT_VERSIONS.get(engine, "")

        # 2b. MariaDB 版本校验
        if engine.lower() == "mariadb":
            from rds_common import MARIADB_SUPPORTED_VERSIONS
            ver_num = engine_version.split(".")[0] + "." + engine_version.split(".")[1] if "." in engine_version else engine_version
            if ver_num not in MARIADB_SUPPORTED_VERSIONS:
                return SpecMatchResult(error="该数据库版本不支持，MariaDB 仅支持 10.3/10.6 版本")

        # 3. 确定系列（category）
        category = config.category if config.category else "HighAvailability"
        if category == "Cluster":
            return SpecMatchResult(error="集群系列暂不自动报价，请人工确认")

        # 4. 确定 ClassGroup（用户提供了用用户的，否则为空）
        user_class_group = config.class_group if config.class_group else ""

        # 4b. MariaDB 仅支持高可用系列，强制覆盖
        if engine.lower() == "mariadb":
            category = "HighAvailability"

        # 4c. 确定 storageType（用户提供 → Local/Cloud，否则默认 Cloud）
        user_storage_type = config.storage_type_raw if config.storage_type_raw else "Cloud"
        # MariaDB 仅支持 ESSD，强制 Cloud
        if engine.lower() == "mariadb":
            user_storage_type = "Cloud"

        # 5. 筛选匹配（不含 ClassGroup）
        candidates = self._filter_by_cpu_memory(
            engine=engine,
            cpu=config.cpu,
            memory=config.memory,
            category=category,
            storage_type=user_storage_type,
        )

        if not candidates:
            return SpecMatchResult(error="未找到匹配的规格，请检查配置")

        # 5b. 按 ClassGroup 过滤（用户提供了→精确匹配，未提供→按优先级过滤）
        candidates = self._apply_class_group_filter(candidates, user_class_group)

        if not candidates:
            return SpecMatchResult(error="未找到匹配的规格，请检查配置")

        # 6. 匹配结果处理
        if len(candidates) == 1:
            selected = candidates[0]
        elif len(candidates) == 2:
            # 2 条：检查是否有 arm 架构
            arm_item = None
            non_arm_item = None
            for c in candidates:
                isa = c.get("InstructionSetArch", "")
                if isa and isa.strip().lower() == "arm":
                    arm_item = c
                else:
                    non_arm_item = c

            if arm_item and non_arm_item:
                # 存在 arm → 选非 arm 的
                selected = non_arm_item
            else:
                # 两条都不是 arm → 检查是否仅差 "e" 字母（如 pg.n2.2c.1m vs pg.n2e.2c.1m）
                codes = [c["ClassCode"] for c in candidates]
                no_e_codes = [c.replace("e", "") for c in codes]
                if no_e_codes[0] == no_e_codes[1]:
                    # 仅差 e → 选不带 e 的（标准版）
                    for c in candidates:
                        if "e" not in c["ClassCode"]:
                            selected = c
                            break
                    else:
                        # 理论上不会走到这里（两个都带 e 消除后相等不可能）
                        selected = candidates[0]
                else:
                    # 差异不止 e → 不报价
                    codes_sorted = sorted(codes)
                    return SpecMatchResult(
                        error=f"匹配到的规格为：{codes_sorted[0]}、{codes_sorted[1]}，请人工确认"
                    )
        else:
            # 3 条及以上 → 不报价
            codes = sorted([c["ClassCode"] for c in candidates])
            codes_str = "、".join(codes)
            return SpecMatchResult(
                error=f"匹配到的规格为：{codes_str}，请人工确认"
            )

        return SpecMatchResult(
            class_code=selected["ClassCode"],
            engine=engine,
            engine_version=engine_version,
            category=selected.get("category", ""),
            cpu=int(selected.get("Cpu", "0").strip() or "0"),
            memory=extract_memory_from_memoryclass(selected.get("MemoryClass", "")),
            memory_class=selected.get("MemoryClass", ""),
            class_group=selected.get("ClassGroup", ""),
            reference_price=int(selected.get("ReferencePrice", "0") or "0"),
            storage_type_raw=user_storage_type,
            storage_type_api=config.db_instance_storage_type if config.db_instance_storage_type else (
                "cloud_essd" if engine.lower() == "mariadb" else (
                    "local_ssd" if user_storage_type == "Local" else "general_essd"
                )
            ),
        )

    def _find_exact_classcode(self, class_code: str) -> Optional[Dict]:
        """精确查找 ClassCode"""
        for item in self.items:
            if item.get("ClassCode") == class_code:
                return item
        return None

    def _resolve_category(self, item: Dict, config) -> str:
        """
        确定系列（category）
        优先用 JSON 中的 category，无则运行时判断（SQLServer .e2 模糊项）
        """
        if "category" in item:
            return item["category"]

        # 无 category → 只能是 SQLServer .e2 模糊项
        class_code = item.get("ClassCode", "")
        suffix = class_code.split(".")[-1] if "." in class_code else ""

        if suffix == "e2":
            # 根据用户提供的 EngineVersion 判断
            version_raw = config.engine_version_raw or ""
            version_lower = version_raw.lower()
            if "集群" in version_raw or "cluster" in version_lower:
                return "Cluster"
            return "HighAvailability"

        # 其他未知情况：默认高可用
        return "HighAvailability"

    def _normalize_version(self, engine: str, version_raw: str) -> str:
        """
        标准化版本号
        """
        version_raw = version_raw.strip()
        engine_lower = engine.lower()

        if engine_lower in ('mssql', 'sqlserver'):
            match = re.search(r'(\d{4})', version_raw)
            if match:
                year = match.group(1)
                edition = ""
                version_lower = version_raw.lower()
                if '集群' in version_raw or 'cluster' in version_lower:
                    edition = " 企业集群版"
                elif '企业' in version_raw:
                    edition = " 企业版"
                elif '标准' in version_raw:
                    edition = " 标准版"
                elif 'web' in version_lower:
                    edition = " Web 版"
                return f"{year}{edition}"
            return version_raw

        # 其他引擎：提取纯数字版本
        match = re.match(r'(\d+(?:\.\d+)*)', version_raw)
        return match.group(1) if match else version_raw

    def _filter_by_cpu_memory(self, engine: str, cpu: int,
                              memory: int, category: str,
                              class_group: str = "",
                              storage_type: str = "Cloud") -> List[Dict]:
        """
        在 rds_series.json 中按 CPU + 内存筛选匹配项
        """
        # 引擎前缀映射
        engine_prefixes = {
            "MySQL": ["mysql.", "rds.mysql."],
            "PostgreSQL": ["pg."],
            "SQLServer": ["mssql."],
            "MariaDB": ["mariadb."],
        }
        prefixes = engine_prefixes.get(engine, [])

        candidates = []
        for item in self.items:
            class_code = item.get("ClassCode", "")

            # a. 按 ClassCode 前缀过滤
            if not any(class_code.startswith(p) for p in prefixes):
                continue

            # b. 按 Cpu 过滤
            item_cpu_str = item.get("Cpu", "").strip()
            try:
                item_cpu = int(item_cpu_str)
            except (ValueError, TypeError):
                continue
            if item_cpu != cpu:
                continue

            # c. 按 MemoryClass 过滤
            memory_class = item.get("MemoryClass", "")
            item_memory = extract_memory_from_memoryclass(memory_class)
            if item_memory != memory:
                continue

            # d. 按 category 过滤
            item_category = item.get("category")
            if item_category is None:
                # 无 category（SQLServer .e2 模糊项）→ 默认 HighAvailability
                if category == "Cluster":
                    continue
                item_category = "HighAvailability"
            elif item_category == "Cluster":
                # 排除集群系列
                continue
            elif item_category != category:
                continue

            # e. 按 storageType 过滤
            item_storage_type = item.get("storageType")
            if item_storage_type is not None:
                if item_storage_type != storage_type:
                    continue

            candidates.append({**item, "category": item_category})

        return candidates

    def _apply_class_group_filter(self, candidates: List[Dict], user_class_group: str) -> List[Dict]:
        """
        ClassGroup 过滤：
        - 用户提供了 → 按提供的精确匹配
        - 未提供 → 按优先级过滤：通用型(1) > 独享套餐(2) > 共享型(3) > 经济型(4) > 独占物理机(5) > 其他
          只保留优先级最高的所有候选
        """
        if not candidates:
            return candidates

        if user_class_group:
            # 用户提供了 → 精确匹配
            return [c for c in candidates if c.get("ClassGroup", "") == user_class_group]

        # 未提供 → 按优先级过滤
        best_priority = DEFAULT_CLASS_GROUP_PRIORITY
        for c in candidates:
            cg = c.get("ClassGroup", "")
            p = get_class_group_priority(cg)
            if p < best_priority:
                best_priority = p

        return [c for c in candidates if get_class_group_priority(c.get("ClassGroup", "")) == best_priority]

    def _select_best_match(self, candidates: List[Dict]) -> Dict:
        """
        多条匹配时，按 ClassGroup 优先级 → ReferencePrice 选择最优

        优先级：通用型(1) > 独享套餐/独享型/独享规格(2) > 共享型(3) > 经济型(4) > 独占物理机(5)
        同优先级选 ReferencePrice 最低的（性价比最优）
        """
        # 按 ClassGroup 优先级分组
        best_priority = DEFAULT_CLASS_GROUP_PRIORITY
        best_candidates = []

        for c in candidates:
            priority = get_class_group_priority(c.get("ClassGroup", ""))
            if priority < best_priority:
                best_priority = priority
                best_candidates = [c]
            elif priority == best_priority:
                best_candidates.append(c)

        if len(best_candidates) == 1:
            return best_candidates[0]

        # 同优先级多条：选 ReferencePrice 最低
        best_candidates.sort(
            key=lambda x: int(x.get("ReferencePrice", "0") or "0")
        )
        return best_candidates[0]


# 测试
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    series_path = os.path.join(script_dir, "..", "references", "rds_series.json")
    validator = RDSSpecValidator(series_path)

    # 模拟测试
    from rds_text_parser import RDSTextParser, RDSTextConfig

    test_inputs = [
        "1、杭州，4核8G，MySQL 8.0，高可用系列，500GB，ESSD PL1",
        "2、上海，mysql.x4.large.2c，100GB",
        "3、mysql.x4.large.2c，PostgreSQL 14",  # Engine 冲突
        "4、4核8G，MariaDB",
    ]

    for text in test_inputs:
        parser = RDSTextParser(text)
        configs = parser.parse()
        for c in configs:
            result = validator.validate(c)
            print(f"[{c.index}] {c.raw_text}")
            if result.error:
                print(f"  ❌ {result.error}")
            else:
                print(f"  ✅ {result.class_code} | {result.engine} {result.engine_version} | {result.category} | CPU={result.cpu} MEM={result.memory}")
            print()
