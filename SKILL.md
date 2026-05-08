---
name: aliyun-all-in-skill
description: 阿里云资源报价与统计工具。支持 ECS 报价查询和 OSS 资源统计、RDS 报价。触发场景：(1) ECS 报价、询价、云产品报价、阿里云报价、ECS 价格查询 (2) 发送 ecs_instance_list_*.csv 文件 (3) RDS 报价、发送 rds_instance_list_*.csv 文件 (4) OSS 统计、OSS 分析、Bucket 统计、对象存储统计 (5) 发送 buckets_*.csv 文件。生成 Excel 后由 AI 通过 openclaw message send 发送到当前对话。
---

# 阿里云资源报价与统计

## 功能概述

- **ECS 报价**：查询阿里云 ECS 实例价格，生成 Excel 报价单
- **RDS 报价**：查询阿里云 RDS 实例价格（MySQL、SQLServer、PostgreSQL、MariaDB），生成 Excel 报价单
- **OSS 统计**：分析 OSS 资源使用情况，生成统计报告

## RDS 报价场景判断

AI 需根据输入类型自动判断 RDS 报价场景：

| 输入 | 场景 | 说明 |
|------|------|------|
| `rds_instance_list_<地域>_YYYY 年 MM 月 DD 日 时_分_秒.csv` 文件 | 场景一 | 基于 CSV 文件自动报价 |
| 待定 | 场景二 | 待定 |

### RDS 场景一：标准 CSV 格式（直接报价）

文件名匹配 `rds_instance_list_**_YYYY-MM-DD.csv` 或 `rds_instance_list_**_YYYY 年 MM 月 DD 日.csv` 时，直接报价：

```bash
venv/bin/python3 scripts/rds_csv_quoter_auto.py /path/to/file.csv
```

**报价说明：**
- 支持 4 种数据库类型：MySQL、SQLServer、PostgreSQL、MariaDB
- 自动查询 1 年和 3 年价格
- 自动选择 1 年目录价最高的实例应用"新客首购 6 折优惠"（限 1 次，限 1 件）
- 输出 Excel 格式与 ECS 报价单一致

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

**输出格式**：Excel 报价单共 10 列

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| 产品名称 | **实例 ID** | 产品描述 | 地域 | 数量 | 1年目录价 | 1年折扣价 | 3年目录价 | 3年折扣价 | 备注 |

- B列"实例 ID"对应 CSV 文件中每行的 A 列（实例 ID）
- 从 B 列开始所有数据向右移动一列

### 场景二：文本配置（非 CSV 格式的 ECS 报价）

适用场景：用户提供文字描述配置（如几台实例，每台实例的规格、磁盘、带宽等），而非标准 CSV 文件。

```bash
venv/bin/python3 scripts/ecs_text_quoter.py '配置内容' --region cn-hangzhou
```

**输出格式**：Excel 报价单共 9 列

| A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|
| 产品名称 | 产品描述 | 地域 | 数量 | 1年目录价 | 1年折扣价 | 3年目录价 | 3年折扣价 | 备注 |

- 无"实例 ID"列（与场景一不同）

**默认值**：地域默认 cn-hangzhou（杭州），磁盘类型默认 ESSD PL0，带宽计费方式默认按固定带宽。

#### 规格判断规则

脚本内置 `ecs_spec_validator.py` 从 `references/ecs_series.json` 加载规格数据，自动判断以下三种场景：

**场景 1：有标准格式的实例规格名称（ecs.<规格族>.<规格大小>）**

- a. 规格不存在 → 不报价，备注红色字体 "该规格不存在"
- b. 规格存在：
  - i. 同时提供了几核几G → 校验规格名称与几核几G 是否匹配：匹配则报价，不匹配则不报价，备注红色字体 "ECS 规格和配置描述不一致"
  - ii. 没有提供几核几G → 直接按照该规格报价

**场景 2：有规格族但没有标准规格名称**

根据语义检索规格族（如 u1、g8i、c6、g7a 等），大小写不影响（U1 = u1），但必须完全一致（u1 ≠ u2i，c9 ≠ c9i ≠ c9a）：

- a. 有准确规格族 + 提供了几核几G → 在 `ecs_series.json` 中查找该规格族下是否有对应配置：
  - i. 有匹配规格 → 按匹配的规格报价
  - ii. 无匹配规格 → 不报价，备注红色字体 "没有提供具体的规格要求"
- b. 有准确规格族 + 没有几核几G → 不报价，备注红色字体 "缺少配置要求"
- c. 规格族不存在 → 不报价，备注红色字体 "该规格"

**场景 3：只有几核几G**

按照默认优先级匹配：`u1 > u2i > c9i > g9i > r9i`

- 匹配到 → 按匹配的规格报价
- 五个优先级规格族中都不存在 → 不报价，备注红色字体 "没有该规格"

#### 系统盘/数据盘规则

- 只提供了大小（如 100GB、100G、100GiB、1T、1TB、1TiB 等）→ 默认按照 **ESSD PL0** 类型报价
- 没有 "系统盘" "数据盘" 关键字时：
  - 只有一个盘的大小 → 默认为系统盘
  - 有多个盘的大小 → 从小到大排列，最小的为系统盘，剩余为数据盘（数据盘1、数据盘2…）

#### 带宽规则

- 提供了带宽大小（如 100M、100Mbps 等）：
  - 明确说明了固定带宽或按流量计费 → 按说明的方式报价
  - 没有说明计费方式 → **1-20Mbps 默认按固定带宽**，**21Mbps 及以上默认按流量计费**
- 没有提供带宽 → 无带宽

#### 镜像规则

免费镜像（Alibaba Cloud Linux、Ubuntu、CentOS、Debian 等）和收费镜像的判断：

- **收费镜像**：Red Hat、SUSE、Alibaba Cloud Linux 3 Pro、Windows（在中国香港及海外地域创建）
- **免费镜像**：除上述收费镜像外的其他镜像（Windows 在中国内地地域免费）

处理方式：

- 免费镜像 → 产品描述中镜像行统一写为 **"公共免费镜像"**
- 收费镜像 → 不报价，价格留空，备注红色字体 "涉及收费镜像，请人工确认"，产品描述中保留实际镜像名称

## 执行流程（所有场景通用）

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 调用脚本 | 根据场景选择对应脚本 |
| 2 | 输出路径 | 脚本输出 `FILE_PATH:xxx.xlsx`，AI 读取此路径 |
| 3 | 发送文件 | 钉钉渠道用 `MEDIA:` 指令，其他渠道用 `openclaw message send` CLI（见下方「文件发送⚠️」） |
| 4 | 清理文件 | AI 发送成功后删除本地 Excel 文件 |

## 文件发送 ⚠️

AI 需根据当前会话渠道（通过 inbound context 中的 `channel` 字段判断）选择对应发送方式：

| 渠道 | `channel` 值 | 发送方式 |
|------|-------------|----------|
| 钉钉 | `dingtalk-connector` | 裸露文件路径（独占一行） |
| 其他渠道 | feishu / telegram / discord 等 | `openclaw message send` CLI |

### 方式一：钉钉渠道 — 裸露文件路径

在回复中将文件绝对路径**独占一行**，前后无其他字符（包括 `MEDIA:` 前缀）：

```
报价单已生成，请查收。

/root/.openclaw/workspace/download/阿里云资源清单260508-112945.xlsx
```

**注意：**
- 路径必须是绝对路径
- 必须独占一行，行首行尾不能有其他字符
- **不能加 `MEDIA:` 前缀**（钉钉连接器通过正则匹配裸露路径，`MEDIA:` 前缀会导致匹配失败）
- 支持的扩展名：xlsx, xls, pdf, doc, docx, ppt, pptx, txt, zip, rar, 7z, mp4, mp3 等
- 钉钉连接器会自动识别路径、上传文件并发送，然后从消息中移除路径文本
- 发送后需清理本地文件

### 方式二：其他渠道 — CLI 命令

通过 `exec` 工具执行：

```bash
openclaw message send --channel feishu --target "user:ou_xxxxx" \
  --media "/root/.openclaw/workspace/download/阿里云资源清单260508-112945.xlsx"
```

根据实际渠道替换 `--channel` 参数（如 `telegram` / `discord` / `feishu` 等）。

### 完整流程示例

```bash
# 1. 生成报价单
venv/bin/python3 scripts/ecs_csv_quoter_auto.py /path/to/file.csv
# 输出 FILE_PATH:/root/.openclaw/workspace/download/阿里云资源清单260508-112945.xlsx

# 2. 发送文件
# 钉钉渠道：在回复中写 MEDIA:/root/.openclaw/workspace/download/阿里云资源清单260508-112945.xlsx
# 其他渠道：openclaw message send --channel feishu --target "user:xxx" --media "/path/to/file.xlsx"

# 3. 发送成功后清理
rm "/root/.openclaw/workspace/download/阿里云资源清单260508-112945.xlsx"
```



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
    ├── rds_csv_quoter_auto.py         # RDS 场景一：CSV 自动报价
    ├── rds_csv_quoter.py              # RDS 报价核心逻辑
    ├── rds_excel_generator.py         # RDS Excel 生成器
    ├── rds_constants.py               # RDS 常量定义
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

`config/config.json` 需要配置 MCP 和 OAuth（ECS 报价必需，RDS 报价也需要，OSS 场景一也需要）：

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

### 输出目录配置

所有场景生成的文件（ECS 报价单、RDS 报价单、OSS 统计报告等）统一输出到同一目录，通过 `config.json` 的 `output_dir` 字段配置：

```json
{
  "output_dir": "/root/.openclaw/workspace/download/",
  "mcp": { ... },
  ...
}
```

- **默认值**：`/root/.openclaw/workspace/download/`
- 用户可自行修改为其他路径，脚本会自动创建目录（`os.makedirs(exist_ok=True)`）
- 入口脚本读取该配置后通过环境变量 `ALIYUN_SKILL_OUTPUT_DIR` 传递给生成器类
- `FILE_PATH:` 输出和 `openclaw message send --media` 均基于此目录

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
- [RDS 产品详情](https://www.aliyun.com/product/rds)
