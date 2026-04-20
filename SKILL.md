---
name: aliyun-all-in-skill
description: 阿里云资源报价与统计工具。支持 ECS 报价查询和 OSS 资源统计。触发场景：(1) ECS报价、询价、云产品报价、阿里云报价、ECS 价格查询 (2) 发送 ecs_instance_list_*.csv 文件 (3) OSS统计、OSS分析、Bucket 统计、对象存储统计。自动生成 Excel 报价单并发送到飞书。
---

# 阿里云资源报价与统计

## 功能概述

- **ECS 报价**：查询阿里云 ECS 实例价格，生成 Excel 报价单
- **OSS 统计**：分析 OSS Bucket 使用情况，生成统计报告

## 使用方式

### ECS 报价

#### 场景一：标准 CSV 格式（直接报价）

文件名匹配 `ecs_instance_list_**_YYYY-MM-DD.csv` 时，直接报价：

```bash
venv/bin/python3 scripts/ecs_csv_quoter_auto.py /path/to/file.csv -t <用户open_id>
```

#### 场景二：文本配置（AI 标准化后直接报价）

其他所有形式（文本描述、非标准文件）执行以下流程：

> ⚠️ **关键：标准化由 AI 完成，不是脚本！**
> 用户的自然语言描述五花八门（`系统盘500G`、`固定宽带2M`、`1、4核16G` 等），脚本的 Python 解析器对宽松格式支持有限。
> **AI 必须先将用户描述转为标准格式，再传给脚本。**

1. **AI 预处理**：理解用户自然语言描述，提取每项实例的 CPU、内存、系统盘、数据盘、带宽等参数
2. **AI 标准化输出**：转为标准格式字符串，如 `实例规格：8核64G 系统盘：50GiB 数据盘：1000GiB 带宽：5Mbps`
3. **直接报价**：无需二次确认，将标准化配置传入脚本执行

```bash
venv/bin/python3 scripts/ecs_text_quoter.py '标准化配置内容' --region cn-hangzhou -t <用户open_id>
```

**默认值**：地域默认 cn-hangzhou（杭州），磁盘类型默认 ESSD PL0，带宽计费方式默认按固定带宽。

**自动执行流程**（传入 `-t` 参数后自动完成，无需额外操作）：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 查询价格 | 逐台实例调用 MCP 查询 1 年和 3 年价格 |
| 2 | 生成 Excel | 报价单保存到 `~/.openclaw/workspace/download/` 目录 |
| 3 | 发送文件 | 自动调用 `openclaw message send --channel feishu --target <用户open_id> --media <文件路径>` 发送到飞书 |
| 4 | 清理文件 | 发送成功后自动删除本地 Excel 文件 |

**注意**：`-t/--target` 为必须参数，不传入则脚本退出。

### OSS 统计

```bash
venv/bin/python3 scripts/oss_quoter_auto.py <AK> <SK> -t <用户open_id>
```

## 参数说明

| 参数 | 说明 |
|------|------|
| `-t, --target` | 目标用户 open_id（必须） |
| `-m, --message` | 自定义发送消息（可选） |
| `--region` | 地域代码，默认 cn-hangzhou（可选） |

### 环境变量

| 变量 | 说明 |
|------|------|
| `FEISHU_TARGET` | 目标用户 open_id（与 --target 二选一） |
| `FEISHU_ACCOUNT` | 飞书账号名称（覆盖 config.json 中的 feishu_account） |

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
├── README.md                          # 项目文档
├── .gitignore                         # Git 忽略配置
├── config/
│   └── config.json.example            # 配置文件模板
│   └── config.json                    # 实际配置（需手动创建）
├── references/
│   └── ecs_series.json                # ECS 规格数据（326 规格族，1902 规格）
└── scripts/
    ├── setup.sh                       # 交互式初始化脚本
    ├── mcp_verify.sh                  # MCP 连通性校验脚本
    ├── oauth_local_server.py.example  # OAuth 授权脚本模板
    ├── oauth_local_server.py          # 实际 OAuth 脚本（需手动生成）
    ├── venv/                          # Python 虚拟环境
    ├── ecs_csv_quoter_auto.py         # 场景一：CSV 自动报价入口
    ├── ecs_csv_quoter.py              # CSV 解析核心逻辑
    ├── ecs_text_quoter.py             # 场景二：文本报价入口
    ├── ecs_spec_validator.py          # ECS 规格验证器
    ├── ecs_excel_generator.py         # Excel 报价单生成器
    ├── ecs_constants.py               # 公共常量定义
    ├── ecs_quoter.py                  # MCP 价格查询封装
    ├── mcp_client.py                  # MCP JSON-RPC 客户端
    ├── oss_stat.py                    # OSS 资源统计核心
    ├── oss_excel.py                   # OSS Excel 报告生成
    ├── oss_quoter_auto.py             # OSS 统计自动发送
    └── requirements.txt               # Python 依赖列表
```

**核心文件说明：**

| 文件 | 功能 |
|------|------|
| `config/config.json` | MCP Endpoint、OAuth 配置、Token 存储 |
| `references/ecs_series.json` | ECS 规格族数据，用于规格验证和推断 |
| `scripts/setup.sh` | 交互式引导用户完成环境初始化 |
| `scripts/mcp_verify.sh` | 校验 MCP 连通性，诊断配置问题 |
| `scripts/mcp_client.py` | MCP JSON-RPC 2.0 客户端封装 |

## 配置要求

### MCP 配置

`config/config.json` 需要配置：

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
  },
  "feishu_account": "feishu-yunbao"
}
```

`feishu_account` 字段（可选）：指定发送报价单时使用的飞书账号名称。如果不配置，脚本将使用 OpenClaw 默认飞书账号。支持通过 `FEISHU_ACCOUNT` 环境变量覆盖。

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

## 移植指南

1. 复制整个 skill 目录
2. 创建虚拟环境并安装依赖
3. 配置 `config/config.json`（MCP endpoint、OAuth）
4. 首次使用需要 OAuth 授权
5. 调用时传入正确的 `--target` 参数

## 参考文档

- [阿里云 OpenAPI MCP Server](https://help.aliyun.com/zh/openapi/integrating-openapi-mcp-server-into-agent)
- [ECS 实例规格族](https://help.aliyun.com/document_detail/25378.html)
