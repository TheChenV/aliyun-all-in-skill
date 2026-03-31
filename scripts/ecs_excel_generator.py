#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Excel 生成器 - 生成阿里云资源清单 Excel 文件
严格按照 REQUIREMENTS.md 的格式要求实现
"""

import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Color, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.merge import MergeCell
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont


class ExcelGenerator:
    """Excel 生成器类"""
    
    # 颜色定义
    SKY_BLUE_FILL = PatternFill(start_color="87CEEB", end_color="87CEEB", fill_type="solid")  # 天蓝色
    RED_FONT = Font(color="FF0000")  # 红色字体
    
    # 字体样式
    DEFAULT_FONT = Font(name="微软雅黑", size=11, bold=True)
    
    # 对齐方式
    CENTER_ALIGNMENT = Alignment(horizontal="center", vertical="center")
    LEFT_ALIGNMENT = Alignment(horizontal="left", vertical="center")
    WRAP_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)  # 自动换行
    
    # 边框样式
    THIN_BORDER = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # 输出目录
    OUTPUT_DIR = "/root/.openclaw/workspace/download/"
    
    def __init__(self, customer_name: str = ""):
        """
        初始化 Excel 生成器
        
        Args:
            customer_name: 客户名称
        """
        self.wb = Workbook()
        self.ws = self.wb.active
        self.ws.title = "资源清单"
        self.customer_name = customer_name
        self.data_rows = []
        
    def add_data_row(self, product_name: str, product_desc: str, region: str, 
                     quantity: int = 1, price_1y_list: float = None, 
                     price_1y_discount: float = None, price_3y_list: float = None,
                     price_3y_discount: float = None, remark: str = "", 
                     is_error: bool = False):
        """
        添加数据行
        
        Args:
            product_name: 产品名称
            product_desc: 产品描述
            region: 地域
            quantity: 数量
            price_1y_list: 官网目录价（1 年）
            price_1y_discount: 官网折扣价（1 年）
            price_3y_list: 官网目录价（3 年）
            price_3y_discount: 官网折扣价（3 年）
            remark: 备注
            is_error: 是否为错误行（询价失败）
        """
        self.data_rows.append({
            "product_name": product_name,
            "product_desc": product_desc,
            "region": region,
            "quantity": quantity,
            "price_1y_list": price_1y_list,
            "price_1y_discount": price_1y_discount,
            "price_3y_list": price_3y_list,
            "price_3y_discount": price_3y_discount,
            "remark": remark,
            "is_error": is_error
        })
    
    def _generate_filename(self) -> str:
        """生成文件名：阿里云资源清单 YYMMDD-HHMMSS.xlsx"""
        timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
        return f"阿里云资源清单{timestamp}.xlsx"
    
    def _apply_header_style(self, row: int, col_start: int, col_end: int):
        """应用标头行样式"""
        for col in range(col_start, col_end + 1):
            cell = self.ws.cell(row=row, column=col)
            cell.font = self.DEFAULT_FONT
            cell.fill = self.SKY_BLUE_FILL
            cell.alignment = self.CENTER_ALIGNMENT
            cell.border = self.THIN_BORDER  # 添加边框
    
    def _apply_data_style(self, row: int, col_start: int, col_end: int, is_error: bool = False):
        """应用数据行样式"""
        for col in range(col_start, col_end + 1):
            cell = self.ws.cell(row=row, column=col)
            cell.font = self.DEFAULT_FONT
            cell.alignment = self.CENTER_ALIGNMENT
            cell.border = self.THIN_BORDER  # 添加边框
            # A 列背景色（从第二行到合计行）
            if col == col_start:
                cell.fill = self.SKY_BLUE_FILL
            # 错误行备注列红色字体
            if is_error and col == col_end:
                cell.font = Font(name="微软雅黑", size=11, bold=True, color="FF0000")
    
    def _format_currency(self, value: float) -> str:
        """格式化货币：￥XX.XX"""
        if value is None:
            return ""
        return f"￥{value:,.2f}"
    
    def generate(self) -> str:
        """
        生成 Excel 文件
        
        Returns:
            生成的文件路径
        """
        ws = self.ws
        
        # 确保输出目录存在
        os.makedirs(self.OUTPUT_DIR, exist_ok=True)
        
        # === 第一行：标题行 ===
        # A-H 合并单元格：客户名称
        ws.merge_cells('A1:H1')
        cell_a1 = ws.cell(row=1, column=1)
        cell_a1.value = f"客户名称：{self.customer_name}" if self.customer_name else "客户名称："
        cell_a1.font = self.DEFAULT_FONT
        cell_a1.alignment = self.LEFT_ALIGNMENT
        
        # I 列：报价日期
        cell_i1 = ws.cell(row=1, column=9)
        quote_date = datetime.now().strftime("%Y年%m月%d日")
        cell_i1.value = f"报价日期：{quote_date}"
        cell_i1.font = self.DEFAULT_FONT
        cell_i1.alignment = self.CENTER_ALIGNMENT
        
        # 第一行所有单元格添加边框
        for col in range(1, 10):
            ws.cell(row=1, column=col).border = self.THIN_BORDER
        
        # === 第二行：标头行 ===
        headers = [
            "产品名称", "产品描述", "地域", "数量",
            "官网目录价（元/1 年）", "官网折扣价（元/1 年）",
            "官网目录价（元/3 年）", "官网折扣价（元/3 年）",
            "备注"
        ]
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=2, column=col)
            cell.value = header
            self._apply_header_style(2, col, col)
        
        # === 第三行起：数据行 ===
        current_row = 3
        for data in self.data_rows:
            # A 列：产品名称
            ws.cell(row=current_row, column=1, value=data["product_name"])
            # B 列：产品描述（多行文本）
            ws.cell(row=current_row, column=2, value=data["product_desc"])
            # C 列：地域
            ws.cell(row=current_row, column=3, value=data["region"])
            # D 列：数量
            ws.cell(row=current_row, column=4, value=data["quantity"])
            # E 列：官网目录价（1 年）
            ws.cell(row=current_row, column=5, value=data["price_1y_list"])
            # F 列：官网折扣价（1 年）
            ws.cell(row=current_row, column=6, value=data["price_1y_discount"])
            # G 列：官网目录价（3 年）
            ws.cell(row=current_row, column=7, value=data["price_3y_list"])
            # H 列：官网折扣价（3 年）
            ws.cell(row=current_row, column=8, value=data["price_3y_discount"])
            # I 列：备注（折扣说明）
            ws.cell(row=current_row, column=9, value=data["remark"])
            # 应用样式
            self._apply_data_style(current_row, 1, 9, is_error=data["is_error"])
            
            # 单独设置需要自动换行的单元格（在 _apply_data_style 之后）
            ws.cell(row=current_row, column=2).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)  # 产品描述
            ws.cell(row=current_row, column=9).alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)  # 备注
            
            # 设置行高（根据内容自动调整，至少 100）
            ws.row_dimensions[current_row].height = 100
            
            current_row += 1
        
        # === 合计行（倒数第二行）===
        total_row = current_row
        ws.cell(row=total_row, column=1, value="合计")
        self._apply_data_style(total_row, 1, 9)
        
        # 计算合计值
        for col in range(5, 9):  # E-H 列
            total = sum(
                row[f"price_{1 if col <= 6 else 3}y_{'list' if col % 2 == 1 else 'discount'}"]
                for row in self.data_rows
                if row[f"price_{1 if col <= 6 else 3}y_{'list' if col % 2 == 1 else 'discount'}"] is not None
            )
            ws.cell(row=total_row, column=col, value=total)
        
        # === 最后一行：备注行 ===
        note_row = total_row + 1
        ws.merge_cells(f'A{note_row}:I{note_row}')
        cell_note = ws.cell(row=note_row, column=1)
        
        # 使用富文本实现部分文字红色
        # "备注："黑色 + "产品价格可能有波动，以官网实际价格为准"红色
        cell_note.value = CellRichText(
            TextBlock(InlineFont(rFont='微软雅黑', sz=11, b=True), "备注："),
            TextBlock(InlineFont(rFont='微软雅黑', sz=11, b=True, color='FFFF0000'), "产品价格可能有波动，以官网实际价格为准")
        )
        # 居中对齐
        cell_note.alignment = self.CENTER_ALIGNMENT
        
        # 备注行所有单元格添加边框
        for col in range(1, 10):
            ws.cell(row=note_row, column=col).border = self.THIN_BORDER
        
        ws.row_dimensions[note_row].height = 30
        
        # === 设置列宽 ===
        # 列宽：产品名称、产品描述、地域、数量、价格列x4、备注
        column_widths = [15, 50, 18, 10, 25, 25, 25, 25, 35]  # E-H 价格列宽度 25
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = width
        
        # === 保存文件 ===
        filename = self._generate_filename()
        filepath = os.path.join(self.OUTPUT_DIR, filename)
        self.wb.save(filepath)
        
        return filepath
    
    def cleanup(self, filepath: str):
        """
        清理本地文件
        
        Args:
            filepath: 文件路径
        """
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"已删除本地文件：{filepath}")
        except Exception as e:
            print(f"删除文件失败：{e}")


def create_product_desc(instance_spec: str, image: str, system_disk: str, 
                        data_disk: str, bandwidth: str) -> str:
    """
    创建产品描述文本
    
    Args:
        instance_spec: 实例规格描述
        image: 镜像
        system_disk: 系统盘
        data_disk: 数据盘
        bandwidth: 带宽
        
    Returns:
        格式化后的产品描述
    """
    desc_parts = []
    
    if instance_spec:
        desc_parts.append(f"实例规格：{instance_spec}")
    if image:
        desc_parts.append(f"镜像：{image}")
    if system_disk:
        desc_parts.append(f"系统盘：{system_disk}")
    if data_disk:
        desc_parts.append(f"数据盘：{data_disk}")
    if bandwidth:
        desc_parts.append(f"公网带宽：{bandwidth}")
    
    return "\n".join(desc_parts)


if __name__ == "__main__":
    # 测试代码
    generator = ExcelGenerator(customer_name="测试客户")
    
    # 添加测试数据
    generator.add_data_row(
        product_name="ECS 云服务器",
        product_desc=create_product_desc(
            instance_spec="计算型 c9i / ecs.c9i.xlarge (4 vCPU 8 GiB)",
            image="Alibaba Cloud Linux 3.2104 LTS 64 位 (安全加固)",
            system_disk="ESSD 云盘 PL0 40GiB",
            data_disk="ESSD 云盘 PL1 40GiB",
            bandwidth="按固定带宽 3Mbps"
        ),
        region="杭州（cn-hangzhou）",
        quantity=1,
        price_1y_list=1234.56,
        price_1y_discount=987.65,
        price_3y_list=3703.68,
        price_3y_discount=2962.95,
        remark="首年优惠 20%，三年优惠 25%"
    )
    
    # 添加错误行测试
    generator.add_data_row(
        product_name="ECS 云服务器",
        product_desc=create_product_desc(
            instance_spec="未知规格",
            image="Alibaba Cloud Linux 3.2104 LTS 64 位",
            system_disk="ESSD 云盘 PL0 40GiB",
            data_disk="",
            bandwidth=""
        ),
        region="杭州（cn-hangzhou）",
        quantity=1,
        is_error=True,
        remark="询价失败：规格不存在"
    )
    
    # 生成文件
    filepath = generator.generate()
    print(f"Excel 文件已生成：{filepath}")
