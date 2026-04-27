---
name: aliyun-all-in-skill
description: 阿里云资源报价与统计工具。支持 ECS 报价查询和 OSS 资源统计。触发场景：(1) ECS报价、询价、云产品报价、阿里云报价、ECS 价格查询 (2) 发送 ecs_instance_list_*.csv 文件 (3) OSS统计、OSS分析、Bucket 统计、对象存储统计 (4) 发送 buckets_*.csv 文件。生成 Excel 后由 AI 通过 openclaw message send 发送到当前对话。
---

# 阿里云资源报价与统计

## 功能概述

- **ECS 报价**：查询阿里云 ECS 实例价格，生成 Excel 报价单
- **OSS 统计**：分析 OSS 资源使用情况，生成统计报告

## OSS 统计场景判断

AI 需根据输入类型自动判断 OSS 统计场景：

| 输入 | 场景 | 说明 |
|------|------|------|
| AK + SK | 场景一 | 基于 AK 查询账号 OSS 资源，**含 ECS 快照** |
| `buckets_YYYYMMDD.csv` 文件 | 场景二 | 基于 CSV 文件统计，**不含 ECS 快照** |

### OSS 场景一：基于 AK 查询（含 ECS 快照）

```bash
venv/bin/python3 scripts/oss_quoter_auto.py <AK> <SK>
```

### OSS 场景二：基于 CSV 文件（不含 ECS 快照）

文件名匹配 `buckets_*.csv` 时，使用 CSV 场景：

```bash
venv/bin/python3 scripts/oss_csv_quoter_auto.py /path/to/buckets_YYYYMMDD.csv
```

两种场景共用同一个 Excel 模板（地域、存储类型、冗余类型、实际存储、计费存储），场景二不含 ECS 快照行。

## ECS 报价

### 场景一：标准 CSV 格式（直接报价）

文件名匹配 `ecs_instance_list_**_YYYY-MM-DD.csv` 时，直接报价：

```bash
venv/bin/python3 scripts/ecs_csv_quoter_auto.py /path/to/file.csv
```

### 场景二：文本配置（AI 标准化后直接报价）

> ⚠️ **关键：标准化由 AI 完成，不是脚本！**
> **AI 必须先将用户描述转为标准格式，再传给脚本。**

```bash
venv/bin/python3 scripts/ecs_text_quoter.py '标准化配置内容' --region cn-hangzhou
```

**默认值**：地域默认 cn-hangzhou（杭州），磁盘类型默认 ESSD PL0，带宽计费方式默认按固定带宽。

## 执行流程（所有场景通用）

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 调用脚本 | 根据场景选择对应脚本 |
| 2 | 输出路径 | 脚本输出 `FILE_PATH:xxx.xlsx`，AI 读取此路径 |
| 3 | 发送文件 | AI 使用 `openclaw message send --channel <当前对话channel> --target <当前对话target> --media <文件路径>` 发送到当前对话 |
| 4 | 清理文件 | AI 发送成功后删除本地 Excel 文件 |

## 规格验证规则

| 场景 | 输入示例 | 验证方式 |
|------|---------|---------|
| 场景1 | `ecs.g6.xlarge` | 字典精确匹配 |
| 场景2 | `c7 8核16G` | 规格族+CPU/内存匹配 |
| 场景3 | `16核32G` | 默认优先级匹配 |

**场景3 默认优先级**：`u1 > u2i > c9i > g9i > r9i`

## 文件结构

```
aliyun-all-in-skill/
├── SKILL.md                           # Skill 定义文件
├── config/
│   └── config.json                    # MCP + OAuth 配置
├── references/
│   └── ecs_series.json                # ECS 规格数据
└── scripts/
    ├── ecs_csv_quoter_auto.py         # ECS 场景一：CSV 自动报价
    ├── ecs_text_quoter.py             # ECS 场景二：文本报价
    ├── oss_quoter_auto.py             # OSS 场景一：AK 查询（含快照）
    ├── oss_csv_quoter_auto.py         # OSS 场景二：CSV 统计（不含快照）
    ├── oss_excel.py                   # OSS Excel 生成器（共用）
    ├── oss_stat.py                    # OSS 分析核心
    ├── ecs_quoter.py                  # ECS 报价统一入口
    ├── mcp_client.py                  # MCP JSON-RPC 客户端
    ├── ...                            # 其他支撑脚本
    └── venv/                          # Python 虚拟环境
```

## 配置要求

`config/config.json` 需要配置 MCP 和 OAuth（ECS 报价必需，OSS 场景一也需要）：

```json
{
  "mcp": {
    "endpoint": "https://openapi-mcp.cn-hangzhou.aliyuncs.com/id/YOUR_ID/mcp"
  },
  "oauth": {
    "app_id": "YOUR_APP_ID"
  },
  "token": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1775045890
  }
}
```

首次使用需要 OAuth 授权。

### Python 依赖

```bash
cd scripts
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

依赖包：
- `openpyxl>=3.1.2` - Excel 生成
- `oss2>=2.19.0` - OSS SDK

## 参考文档

- [阿里云 OpenAPI MCP Server](https://help.aliyun.com/zh/openapi/integrating-openapi-mcp-server-into-agent)
- [ECS 实例规格族](https://help.aliyun.com/document_detail/25378.html)