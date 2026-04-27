# 阿里云持续运营 Skill

基于阿里云 OpenAPI MCP Server 实现的持续运营/运维工具集，为 OpenClaw Agent 提供阿里云资源报价、统计、分析等能力。

## 目录结构

```
aliyun-all-in-skill/
├── SKILL.md                           # Skill 定义文件（OpenClaw 识别入口）
├── README.md                          # 本文档
├── .gitignore                         # Git 忽略配置
├── config/
│   └── config.json.example            # 配置文件模板（需复制为 config.json）
├── references/
│   └── ecs_series.json                # ECS 规格数据（326 规格族，1902 规格）
└── scripts/
    ├── setup.sh                       # 交互式初始化脚本
    ├── mcp_verify.sh                  # MCP 连通性校验脚本
    ├── oauth_local_server.py.example  # OAuth 授权脚本模板
    ├── ecs_csv_quoter_auto.py         # ECS 场景一：CSV 自动报价入口
    ├── ecs_csv_quoter.py              # CSV 解析核心逻辑
    ├── ecs_text_quoter.py             # ECS 场景二：文本报价入口
    ├── ecs_spec_validator.py          # ECS 规格验证器
    ├── ecs_excel_generator.py         # Excel 报价单生成器
    ├── ecs_constants.py               # 公共常量定义
    ├── ecs_quoter.py                  # ECS 报价统一入口
    ├── mcp_client.py                  # MCP JSON-RPC 客户端
    ├── oss_stat.py                    # OSS 资源统计核心
    ├── oss_excel.py                   # OSS Excel 报告生成器（两种场景共用）
    ├── oss_quoter_auto.py             # OSS 场景一：AK 查询入口（含 ECS 快照）
    ├── oss_csv_quoter_auto.py         # OSS 场景二：CSV 统计入口（不含 ECS 快照）
    └── requirements.txt               # Python 依赖列表
```

## 文件说明

| 文件 | 功能 |
|------|------|
| `SKILL.md` | OpenClaw Skill 定义，包含触发条件、使用方式、参数说明 |
| `config/config.json` | MCP Endpoint、OAuth 配置、Token 存储（需手动创建） |
| `references/ecs_series.json` | ECS 规格族数据，用于规格验证和推断 |
| `scripts/setup.sh` | 交互式引导用户完成环境初始化 |
| `scripts/mcp_verify.sh` | 校验 MCP 连通性，诊断配置问题 |
| `scripts/oauth_local_server.py` | 本地 OAuth 授权，获取 Access Token |
| `scripts/mcp_client.py` | MCP JSON-RPC 2.0 客户端封装 |

## 快速安装

### 1. 克隆仓库

```bash
cd ~/.openclaw/skills
git clone https://github.com/TheChenV/aliyun-all-in-skill.git
cd aliyun-all-in-skill
```

### 2. 运行初始化脚本

```bash
./scripts/setup.sh
```

脚本会交互式引导你完成：
- Python 虬拟环境安装
- 参数配置（MCP Endpoint、app_id）
- 生成配置文件和 OAuth 脚本

### 3. 参数获取方式

#### Streamable HTTP Endpoint

1. 登录阿里云控制台（管理员账号）
2. 访问 https://api.aliyun.com/mcp
3. 点击「获取 Endpoint」或复制显示的 Streamable HTTP Endpoint

格式示例：
```
https://openapi-mcp.<region>.aliyuncs.com/id/<your-id>/mcp
```

#### 应用 ID (app_id)

1. 请管理员账号前往 https://ram.console.aliyun.com/applications
2. 选择「第三方应用」
3. 找到并安装「OpenAPI MCP Server」官方应用
4. 编辑「分配类型」为「全部分配」
5. 复制「应用 ID」

### 4. OAuth 授权

`setup.sh` 会生成 `oauth_local_server.py`，你需要：

1. 将脚本输出的 `oauth_local_server.py` 绝对路径对应的文件下载到本地（有浏览器的机器，如 Windows/MacOS）
2. 在本地操作系统（登录了阿里云管理员账户的电脑）上运行：`python oauth_local_server.py`
3. 浏览器会自动打开授权页面
4. 完成授权后，脚本输出 Token JSON
5. 手动编辑 `config/config.json`，将 `access_token`、`refresh_token`、`expires_at` 填入

### 5. 验证配置

```bash
./scripts/mcp_verify.sh
```

成功输出：
```
✅ MCP 连接成功！可用工具数量：XXX
```

失败会输出具体原因，按提示修复。

## 已完成功能

### ECS 报价

基于阿里云 ECS OpenAPI，支持多场景价格查询和 Excel 报价单生成。

**场景一：标准 CSV 格式自动报价**

文件名匹配 `ecs_instance_list_**_YYYY-MM-DD.csv` 时，直接报价，无需确认。

```bash
venv/bin/python3 scripts/ecs_csv_quoter_auto.py /path/to/file.csv
```

**场景二：文本配置报价**

用户提供的文本描述、非标准文件等，AI 先将用户描述转为标准格式，再传入脚本报价。

```bash
venv/bin/python3 scripts/ecs_text_quoter.py '配置内容' --region cn-hangzhou
```

**规格验证（3 种场景）**

| 场景 | 输入示例 | 验证方式 |
|------|---------|---------|
| 场景 1 | `ecs.g6.xlarge` | JSON 字典精确匹配 |
| 场景 2 | `c7 8核16G` | 规格族 + CPU/内存匹配 |
| 场景 3 | `16核32G` | 默认优先级推断匹配 |

**场景 3 默认优先级**：`u1 > u2i > c9i > g9i > r9i`

**Excel 报价单标准格式输出**

**表格结构（9 列）**

| 列 | 标头 | 内容说明 |
|----|------|----------|
| A | 产品名称 | 固定为「ECS 云服务器」 |
| B | 产品描述 | 多行文本，含实例规格、镜像、系统盘、数据盘、公网带宽 |
| C | 地域 | 地域名称（如「杭州（cn-hangzhou）」） |
| D | 数量 | 固定为 1 |
| E | 官网目录价（元/1年） | 1 年官网标准价 |
| F | 官网折扣价（元/1年） | 1 年实际折扣价 |
| G | 官网目录价（元/3年） | 3 年官网标准价 |
| H | 官网折扣价（元/3年） | 3 年实际折扣价 |
| I | 备注 | 折扣规则说明 |

**产品描述格式示例**

```
实例规格：计算型 c7 / ecs.c7.2xlarge (8 vCPU 16 GiB)
镜像：CentOS 7.9 64 bit
系统盘：ESSD 云盘 PL0 500GiB
数据盘：ESSD 云盘 PL1 500GiB
公网带宽：按固定带宽 2Mbps
```

**表格附加行**

- 第一行：客户名称 + 报价日期
- 合计行：各价格列自动汇总
- 备注行：「产品价格可能有波动，以官网实际价格为准」（红色字体）

### OSS 资源统计

分析 OSS Bucket 使用情况，生成统计报告。支持两种场景：

**场景一：基于 AK 查询（含 ECS 快照）**

通过 AccessKey 查询阿里云账号的 OSS 资源使用情况，额外包含 ECS 快照统计。

```bash
venv/bin/python3 scripts/oss_quoter_auto.py <AccessKey_ID> <AccessKey_Secret>
```

**场景二：基于 CSV 文件统计（不含 ECS 快照）**

文件名匹配 `buckets_*.csv` 时，基于阿里云控制台导出的标准 OSS 资源清单进行统计。

```bash
venv/bin/python3 scripts/oss_csv_quoter_auto.py /path/to/buckets_YYYYMMDD.csv
```

**两种场景共用同一个 Excel 模板**（地域、存储类型、冗余类型、实际存储大小、计费存储大小），区别是场景二不含 ECS 快照行。

**统计维度**

| 维度 | 内容 |
|------|------|
| 地域 | 按地域聚合（华东1杭州、华北2北京等） |
| 存储类型 | 标准/低频/归档/冷归档/深度冷归档 |
| 冗余类型 | 本地冗余(LRS)/同城冗余(ZRS) |
| 存储量 | 实际存储 + 计费存储 |

### 文件发送机制

脚本只负责生成 Excel 文件并输出路径（`FILE_PATH:xxx.xlsx`），文件发送由 AI（OpenClaw Agent）通过 `openclaw message send` 完成：

```bash
openclaw message send --channel <当前对话channel> --target <当前对话target> --media <文件路径>
```

这种设计确保 Skill 天然支持所有 channel（飞书、Telegram、WhatsApp、Discord 等），无需硬编码任何 channel 或账号信息。

## 未来规划

基于阿里云 OpenAPI MCP Server 的能力，本项目将持续扩展以下场景：

### 产品报价扩展
- **RDS 报价**：关系型数据库价格查询
- **OSS 报价**：对象存储费用估算
- **资源包报价**：预付费资源包推荐与计算
- **SLB 报价**：负载均衡价格查询
- **NAT 网关报价**：网关费用估算

### 成本分析
- **多维度成本统计**：按产品/地域/标签/时间统计
- **成本趋势分析**：月度/季度成本变化趋势
- **成本预测**：基于历史数据预测未来成本
- **成本对比**：不同规格/配置成本对比

### 资源监控
- **ECS 状态监控**：实例运行状态、资源使用率
- **OSS 状态监控**：Bucket 存储趋势、访问统计
- **RDS 状态监控**：数据库性能指标、连接数监控
- **告警聚合**：多产品告警信息汇总

### 故障排查
- **日志分析**：云产品日志自动分析
- **异常诊断**：常见问题自动诊断
- **修复建议**：故障修复方案推荐

### 安全审计
- **权限检查**：RAM 权限配置审计
- **合规检测**：安全配置合规检查
- **漏洞扫描**：安全漏洞识别

### 资源优化
- **规格推荐**：基于负载推荐合适规格
- **闲置资源识别**：低利用率资源识别
- **资源整合建议**：资源整合优化方案

### 续费管理
- **到期预警**：即将到期资源提醒
- **续费建议**：续费时机和方式建议
- **自动续费配置**：批量续费设置

### 账单分析
- **账单明细解析**：详细账单项目分析
- **按产品统计**：各产品费用占比
- **按地域统计**：各地域费用分布
- **按标签统计**：标签维度费用聚合

## 依赖说明

### Python 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `openpyxl` | >=3.1.2 | Excel 文件生成 |
| `oss2` | >=2.19.0 | OSS SDK（可选，仅 OSS 场景一需要） |

### 系统要求

- Python 3.10+
- 操作系统：Linux / macOS / Windows
- 网络访问：阿里云 OpenAPI MCP Server

## 参考文档

- [阿里云 OpenAPI MCP Server 官方文档](https://help.aliyun.com/zh/openapi/integrating-openapi-mcp-server-into-agent)
- [ECS 实例规格族](https://help.aliyun.com/document_detail/25378.html)
- [OSS 产品文档](https://help.aliyun.com/document_detail/31817.html)

## 许可证

Apache-2.0 License

## 贡献

欢迎提交 Issue 和 Pull Request。