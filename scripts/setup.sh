#!/bin/bash
# -*- coding: utf-8 -*-
#
# 阿里云持续运营 Skill 初始化脚本
# 交互式引导用户完成环境配置
#
# 使用方式：在项目根目录执行 bash ./scripts/setup.sh
#

set -e

# 颜色定义（避免乱码）
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 获取脚本所在目录（支持从项目根目录执行 bash ./scripts/setup.sh）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$SKILL_DIR/config"

# 打印函数
print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

print_step() {
    echo -e "${GREEN}[步骤 $1]${NC} $2"
}

print_info() {
    echo -e "${CYAN}  $1${NC}"
}

print_success() {
    echo -e "${GREEN}  ✓ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✗ $1${NC}"
}

print_separator() {
    echo ""
    echo -e "${BLUE}----------------------------------------${NC}"
    echo ""
}

# 检查 Python 环境
check_python() {
    print_step 1 "检查 Python 环境"
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python 版本: $PYTHON_VERSION"
        return 0
    else
        print_error "未找到 python3，请先安装 Python 3.10+"
        exit 1
    fi
}

# 创建虚拟环境
create_venv() {
    print_step 2 "创建 Python 虚拟环境"
    
    if [ -d "$SCRIPT_DIR/venv" ]; then
        print_info "虚拟环境已存在，跳过创建"
        return 0
    fi
    
    cd "$SCRIPT_DIR"
    python3 -m venv venv
    print_success "虚拟环境创建完成"
}

# 安装依赖
install_dependencies() {
    print_step 3 "安装 Python 依赖"
    
    cd "$SCRIPT_DIR"
    
    if [ -f "requirements.txt" ]; then
        source venv/bin/activate
        pip install -r requirements.txt -q
        print_success "依赖安装完成"
    else
        print_error "未找到 requirements.txt"
        exit 1
    fi
}

# 获取 MCP Endpoint
get_mcp_endpoint() {
    print_step 4 "配置 MCP Endpoint"
    
    print_separator
    echo -e "${YELLOW}如何获取 MCP Endpoint：${NC}"
    echo ""
    echo "  1. 使用管理员账号登录阿里云控制台"
    echo ""
    echo "  2. 访问 MCP 控制台："
    echo -e "${CYAN}     https://api.aliyun.com/mcp${NC}"
    echo ""
    echo "  3. 在页面中找到「Streamable HTTP Endpoint」"
    echo ""
    echo "  4. 点击复制按钮，获取完整的 Endpoint URL"
    echo ""
    echo -e "${YELLOW}Endpoint 格式示例：${NC}"
    echo -e "${CYAN}  https://openapi-mcp.<region>.aliyuncs.com/id/<your-id>/mcp${NC}"
    print_separator
    
    echo -n "请输入 MCP Endpoint: "
    read MCP_ENDPOINT
    
    if [ -z "$MCP_ENDPOINT" ]; then
        print_error "MCP Endpoint 不能为空"
        exit 1
    fi
    
    # 验证格式
    if [[ ! "$MCP_ENDPOINT" =~ ^https:// ]]; then
        print_error "MCP Endpoint 格式错误，应以 https:// 开头"
        exit 1
    fi
    
    print_success "MCP Endpoint 已记录"
}

# 获取 app_id
get_app_id() {
    print_step 5 "配置应用 ID (app_id)"
    
    print_separator
    echo -e "${YELLOW}如何获取应用 ID (app_id)：${NC}"
    echo ""
    echo "  1. 使用管理员账号登录阿里云 RAM 控制台："
    echo -e "${CYAN}     https://ram.console.aliyun.com/applications${NC}"
    echo ""
    echo "  2. 在左侧菜单选择「第三方应用」"
    echo ""
    echo "  3. 找到并点击「OpenAPI MCP Server」官方应用"
    echo ""
    echo "  4. 点击「安装应用」按钮"
    echo ""
    echo "  5. 在「分配授权对象」页面："
    echo "     - 编辑「分配类型」为「全部分配」"
    echo "     - 确认安装"
    echo ""
    echo "  6. 安装完成后，在应用详情页面："
    echo "     - 找到「应用 ID」字段"
    echo "     - 点击复制按钮"
    echo ""
    echo -e "${YELLOW}应用 ID 格式示例：${NC}"
    echo -e "${CYAN}  <一串数字>${NC}"
    print_separator
    
    echo -n "请输入应用 ID (app_id): "
    read APP_ID
    
    if [ -z "$APP_ID" ]; then
        print_error "应用 ID 不能为空"
        exit 1
    fi
    
    print_success "应用 ID 已记录"
}

# 生成 config.json
generate_config() {
    print_step 6 "生成配置文件"
    
    # 确保 config 目录存在
    mkdir -p "$CONFIG_DIR"
    
    # 生成 config.json（token 字段为占位符，需用户手动填写）
    cat > "$CONFIG_DIR/config.json" << EOF
{
  "mcp": {
    "endpoint": "$MCP_ENDPOINT"
  },
  "oauth": {
    "app_name": "alibabacloud-api-mcp-server@app.1263926834388048.onaliyun.com",
    "app_id": "$APP_ID",
    "scopes": ["openid", "/internal/acs/openapi", "aliuid"]
  },
  "token": {
    "access_token": "YOUR_ACCESS_TOKEN_HERE",
    "refresh_token": "YOUR_REFRESH_TOKEN_HERE",
    "expires_at": 0
  }
}
EOF
    
    print_success "config.json 已生成: config/config.json"
}

# 生成 oauth_local_server.py
generate_oauth_script() {
    print_step 7 "生成 OAuth 授权脚本"
    
    # 替换模板中的参数
    sed -e "s|YOUR_APP_ID_HERE|$APP_ID|g" \
        -e "s|YOUR_MCP_ENDPOINT_HERE|$MCP_ENDPOINT|g" \
        "$SCRIPT_DIR/oauth_local_server.py.example" > "$SCRIPT_DIR/oauth_local_server.py"
    
    print_success "oauth_local_server.py 已生成: scripts/oauth_local_server.py"
}

# 输出后续步骤
show_next_steps() {
    print_header "初始化完成 - 请继续完成以下步骤"
    
    # 获取绝对路径
    OAUTH_SCRIPT_PATH="$SCRIPT_DIR/oauth_local_server.py"
    
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  后续步骤${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    
    echo -e "${GREEN}[步骤 1] 下载 OAuth 脚本到本地${NC}"
    echo "  将以下文件下载到您的本地电脑（有浏览器的机器，如 Windows/MacOS）："
    echo -e "${CYAN}  $OAUTH_SCRIPT_PATH${NC}"
    echo ""
    
    echo -e "${GREEN}[步骤 2] 本地运行 OAuth 脚本${NC}"
    echo "  在您的本地操作系统（登录了阿里云管理员账户的 Windows/MacOS 等）上运行："
    echo -e "${CYAN}  python oauth_local_server.py${NC}"
    echo ""
    
    echo -e "${GREEN}[步骤 3] 完成浏览器授权${NC}"
    echo "  脚本会自动打开浏览器授权页面"
    echo "  使用阿里云管理员账号登录并确认授权"
    echo ""
    
    echo -e "${GREEN}[步骤 4] 获取并填写 Token${NC}"
    echo "  授权成功后，脚本会输出 JSON 格式的 Token"
    echo "  将以下字段手动填入 config/config.json："
    echo -e "${CYAN}  - access_token${NC}"
    echo -e "${CYAN}  - refresh_token${NC}"
    echo -e "${CYAN}  - expires_at${NC}"
    echo ""
    
    echo -e "${GREEN}[步骤 5] 校验 MCP 连通性${NC}"
    echo "  Token 填写完成后，在服务器上运行以下命令校验："
    echo -e "${CYAN}  ./scripts/mcp_verify.sh${NC}"
    echo ""
    
    echo -e "${YELLOW}========================================${NC}"
    echo ""
}

# 主流程
main() {
    print_header "阿里云持续运营 Skill 初始化"
    
    check_python
    create_venv
    install_dependencies
    get_mcp_endpoint
    get_app_id
    generate_config
    generate_oauth_script
    
    show_next_steps
}

main