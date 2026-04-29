#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECS 规格验证模块（简化版）
直接从 ecs_series.json 加载规格数据，使用字典精确匹配

三种规格判断场景：
- 场景1：有标准格式实例规格名称（ecs.<规格族>.<规格大小>）
- 场景2：有规格族但没有标准规格名称
- 场景3：只有几核几G → 默认优先级匹配（u1 > u2i > c9i > g9i > r9i）
"""

import os
import re
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class SpecValidationResult:
    """规格验证结果"""
    valid: bool
    spec_code: str = ""
    series: str = ""
    vcpu: int = 0
    memory: float = 0.0
    error_message: str = ""


class SpecValidator:
    """ECS 规格验证器"""
    
    # 标准 ECS 规格名称正则：ecs.<规格族>.<规格大小>
    SPEC_CODE_PATTERN = re.compile(r'^ecs\.([a-z0-9\-]+)\.([a-z0-9]+)$', re.IGNORECASE)
    
    # 场景3 默认匹配优先级
    DEFAULT_PRIORITY = ["u1", "u2i", "c9i", "g9i", "r9i"]
    
    def __init__(self):
        """
        初始化验证器
        从 references/ecs_series.json 加载规格数据
        """
        # 规格数据
        self.specs_data = {}       # series -> [spec_info, ...]
        self.spec_code_index = {}  # spec_code -> spec_info
        
        self._load_specs()
    
    def _load_specs(self):
        """从 references/ecs_series.json 加载规格数据"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        ecs_series_path = os.path.join(script_dir, "..", "references", "ecs_series.json")
        
        if not os.path.exists(ecs_series_path):
            print(f"警告：未找到 {ecs_series_path}")
            return
        
        with open(ecs_series_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.specs_data = data.get('specs', {})
            
            # 构建规格代码索引
            for series, specs in self.specs_data.items():
                for spec_info in specs:
                    spec_code = spec_info['spec']
                    self.spec_code_index[spec_code.lower()] = {
                        'spec_code': spec_code,
                        'series': series.lower(),
                        'vcpu': spec_info['vcpu'],
                        'memory': spec_info['memory']
                    }
        
        # 统计信息
        total_specs = len(self.spec_code_index)
        series_count = len(self.specs_data)
        
        # 统计各系列规格数量
        series_stats = {}
        for series in self.DEFAULT_PRIORITY:
            series_stats[series] = len(self.specs_data.get(series, []))
        
        print(f"已加载 {series_count} 个规格族，{total_specs} 个规格")
        for series, count in series_stats.items():
            if count > 0:
                print(f"  {series}: {count} 个规格")
    
    def is_standard_spec(self, spec_code: str) -> bool:
        """检查是否是标准 ECS 规格名称"""
        return bool(self.SPEC_CODE_PATTERN.match(spec_code))
    
    def validate(
        self,
        spec_code: Optional[str] = None,
        series: Optional[str] = None,
        vcpu: Optional[int] = None,
        memory: Optional[float] = None,
        raw_input: str = ""
    ) -> SpecValidationResult:
        """
        验证规格（三种场景）
        
        Args:
            spec_code: 标准规格名称（如 ecs.g6.xlarge）
            series: 规格族（如 g6、u1）
            vcpu: vCPU 数量
            memory: 内存大小（GiB）
            raw_input: 原始输入（用于错误时保留配置）
        """
        
        # ========== 场景1：有标准格式实例规格名称 ==========
        if spec_code and self.is_standard_spec(spec_code):
            return self._validate_scenario1(spec_code, vcpu, memory)
        
        # ========== 场景2：有规格族但没有标准规格名称 ==========
        if series and not spec_code:
            return self._validate_scenario2(series, vcpu, memory)
        
        # ========== 场景3：只有几核几G ==========
        if vcpu is not None and memory is not None and not spec_code and not series:
            return self._validate_scenario3(vcpu, memory)
        
        # 无法识别的情况
        return SpecValidationResult(
            valid=False,
            vcpu=vcpu or 0,
            memory=memory or 0,
            error_message="无法识别的规格描述"
        )
    
    def _validate_scenario1(
        self, spec_code: str, vcpu: Optional[int], memory: Optional[float]
    ) -> SpecValidationResult:
        """
        场景1：有标准格式实例规格名称
        
        步骤：
        1. 字典查找该规格是否存在
        2a. 不存在 -> 不报价，备注"该规格不存在"
        2b. 存在 -> 检查是否提供几核几G
           - 提供了 -> 校验一致性
           - 没提供 -> 直接报价
        """
        
        # 步骤1：查找规格是否存在
        spec_info = self.spec_code_index.get(spec_code.lower())
        
        if not spec_info:
            return SpecValidationResult(
                valid=False,
                spec_code=spec_code,
                error_message="该规格不存在"
            )
        
        # 步骤2：是否提供几核几G
        if vcpu is not None and memory is not None:
            actual_vcpu = spec_info['vcpu']
            actual_memory = spec_info['memory']
            
            if vcpu == actual_vcpu and memory == actual_memory:
                return SpecValidationResult(
                    valid=True,
                    spec_code=spec_code,
                    series=spec_info['series'],
                    vcpu=actual_vcpu,
                    memory=actual_memory
                )
            else:
                return SpecValidationResult(
                    valid=False,
                    spec_code=spec_code,
                    series=spec_info['series'],
                    vcpu=vcpu,
                    memory=memory,
                    error_message=f"ECS 规格和配置描述不一致：{spec_code} 实际为 {actual_vcpu}核{actual_memory}G，描述为 {vcpu}核{memory}G"
                )
        else:
            return SpecValidationResult(
                valid=True,
                spec_code=spec_code,
                series=spec_info['series'],
                vcpu=spec_info['vcpu'],
                memory=spec_info['memory']
            )
    
    def _validate_scenario2(
        self, series: str, vcpu: Optional[int], memory: Optional[float]
    ) -> SpecValidationResult:
        """
        场景2：有规格族但没有标准规格名称
        
        步骤：
        1. 确认规格族是否存在（大小写不敏感）
        2a. 不存在 -> 不报价，备注"该规格族不存在"
        2b. 存在 -> 检查是否提供几核几G
           - 没提供 -> 不报价，备注"没有提供具体的规格要求"
           - 提供了 -> 查找该规格族下是否有对应规格
        """
        
        series_lower = series.lower().strip()
        
        # 步骤1：确认规格族是否存在
        if series_lower not in self.specs_data:
            return SpecValidationResult(
                valid=False,
                series=series,
                error_message="该规格"
            )
        
        # 步骤2：是否提供几核几G
        if vcpu is None or memory is None:
            return SpecValidationResult(
                valid=False,
                series=series,
                error_message="缺少配置要求"
            )
        
        # 步骤3：查找该规格族下是否有对应配置
        specs = self.specs_data.get(series_lower, [])
        for spec in specs:
            if spec['vcpu'] == vcpu and spec['memory'] == memory:
                return SpecValidationResult(
                    valid=True,
                    spec_code=spec['spec'],
                    series=series_lower,
                    vcpu=spec['vcpu'],
                    memory=spec['memory']
                )
        
        return SpecValidationResult(
            valid=False,
            series=series,
            vcpu=vcpu,
            memory=memory,
            error_message="没有提供具体的规格要求"
        )
    
    def _validate_scenario3(self, vcpu: int, memory: float) -> SpecValidationResult:
        """
        场景3：只有几核几G，按默认优先级匹配
        
        优先级：u1 > u2i > c9i > g9i > r9i
        直接使用 ecs_series.json 数据
        """
        
        for series in self.DEFAULT_PRIORITY:
            specs = self.specs_data.get(series, [])
            for spec in specs:
                if spec['vcpu'] == vcpu and spec['memory'] == memory:
                    return SpecValidationResult(
                        valid=True,
                        spec_code=spec['spec'],
                        series=series,
                        vcpu=spec['vcpu'],
                        memory=spec['memory']
                    )
        
        return SpecValidationResult(
            valid=False,
            vcpu=vcpu,
            memory=memory,
            error_message="没有该规格"
        )


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("测试 ECS 规格验证器")
    print("=" * 60)
    
    validator = SpecValidator()
    
    print("\n" + "=" * 60)
    print("场景1：有标准格式实例规格名称")
    print("=" * 60)
    
    test_cases_scenario1 = [
        ("ecs.g6.xlarge", None, None, True),
        ("ecs.g6.xlarge", 4, 16, True),
        ("ecs.g6.xlarge", 4, 17, False),
        ("ecs.notexist.xlarge", None, None, False),
    ]
    
    for spec_code, vcpu, memory, expected in test_cases_scenario1:
        result = validator.validate(spec_code=spec_code, vcpu=vcpu, memory=memory)
        status = "✅" if result.valid == expected else "❌"
        print(f"  {status} {spec_code} {vcpu}核{memory}G: valid={result.valid}, error={result.error_message or '无'}")
    
    print("\n" + "=" * 60)
    print("场景2：有规格族但没有标准规格名称")
    print("=" * 60)
    
    test_cases_scenario2 = [
        ("g6", 4, 16, True),
        ("g6", 4, 17, False),
        ("g6", None, None, False),
        ("g99", 4, 16, False),
        ("u1", 4, 8, True),
    ]
    
    for series, vcpu, memory, expected in test_cases_scenario2:
        result = validator.validate(series=series, vcpu=vcpu, memory=memory)
        status = "✅" if result.valid == expected else "❌"
        print(f"  {status} {series} {vcpu}核{memory}G: valid={result.valid}, spec={result.spec_code}, error={result.error_message or '无'}")
    
    print("\n" + "=" * 60)
    print("场景3：只有几核几G")
    print("=" * 60)
    
    test_cases_scenario3 = [
        (4, 8, True),
        (4, 16, True),
        (4, 32, True),
        (2, 128, False),
    ]
    
    for vcpu, memory, expected in test_cases_scenario3:
        result = validator.validate(vcpu=vcpu, memory=memory)
        status = "✅" if result.valid == expected else "❌"
        print(f"  {status} {vcpu}核{memory}G: valid={result.valid}, spec={result.spec_code}, series={result.series}, error={result.error_message or '无'}")