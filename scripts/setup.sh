#!/bin/bash
# -*- coding: utf-8 -*-
#
# 阿里云持续运营 Skill 初始化脚本
# 交互式引导用户完成环境配置
#
# 使用方式：在项目根目录执行 bash ./scripts/setup.sh
# 可选参数：--no-confirm  跳过确认，全自动安装（适用于 CI/CD）
#

set -e

# 颜色定义（避免乱码）
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 解析参数
NO_CONFIRM=false
for arg in "$@"; do
    case "$arg" in
        --no-confirm)
            NO_CONFIRM=true
            ;;
    esac
done

# 获取脚本所在目录（支持从项目根目录执行 bash ./scripts/setup.sh）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$SKILL_DIR/config"

# 全局步骤计数器
STEP=0
step() {
    STEP=$((STEP + 1))
}

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

print_warn() {
    echo -e "${YELLOW}  ⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✗ $1${NC}"
}

print_separator() {
    echo ""
    echo -e "${BLUE}----------------------------------------${NC}"
    echo ""
}

# 确认提示（支持 --no-confirm 跳过）
confirm_action() {
    local prompt="$1"
    if $NO_CONFIRM; then
        print_info "[非交互模式] 自动确认: $prompt"
        return 0
    fi
    echo -n "$prompt [Y/n]: "
    read -r CONFIRM
    if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
        return 1
    fi
    return 0
}

# ==================== 步骤 1：检查 Python 环境 ====================

check_python() {
    step; print_step "$STEP" "检查 Python 环境"

    # 检查 python3 是否存在
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 python3 命令"
        _auto_install_python
        return $?
    fi

    # 检查版本 ≥ 3.10
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
        print_error "Python 版本过低: $PYTHON_VERSION（需要 ≥ 3.10）"
        _auto_install_python
        return $?
    fi

    print_success "Python 版本: $PYTHON_VERSION"
    return 0
}

# 自动安装 Python（辅助函数）
_auto_install_python() {
    print_info "尝试自动安装 Python 3..."

    if command -v apt-get &> /dev/null; then
        _pkg_install "apt-get" "python3"
    elif command -v yum &> /dev/null; then
        _pkg_install "yum" "python3"
    elif command -v dnf &> /dev/null; then
        _pkg_install "dnf" "python3"
    elif command -v apk &> /dev/null; then
        _pkg_install "apk" "python3"
    else
        print_error "不支持的包管理器，请手动安装 Python 3.10+"
        exit 1
    fi

    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python 安装成功: $PYTHON_VERSION"
        return 0
    else
        print_error "Python 安装失败，请手动安装"
        exit 1
    fi
}

# ==================== 步骤 2：确保 venv 模块可用 ====================

ensure_venv_module() {
    step; print_step "$STEP" "检查 venv 模块"

    # 检测 ensurepip 模块（venv 创建虚拟环境时需要它来安装 pip）
    # 注意：python3 -m venv --help 不会触发 ensurepip，所以不能作为检测依据
    if python3 -c "import ensurepip" &> /dev/null; then
        print_success "venv 模块已就绪"
        return 0
    fi

    # venv 不可用，需要安装
    print_warn "venv 模块不可用（缺少 python3-venv / ensurepip 包）"

    # 检测包管理器
    if command -v apt-get &> /dev/null; then
        PKG_MANAGER="apt"
        PKG_NAME="python3-venv"
        INSTALL_CMD="apt-get install -y $PKG_NAME"
    elif command -v yum &> /dev/null; then
        PKG_MANAGER="yum"
        PKG_NAME="python3-devel"
        INSTALL_CMD="yum install -y $PKG_NAME"
    elif command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"
        PKG_NAME="python3-venv"
        INSTALL_CMD="dnf install -y $PKG_NAME"
    elif command -v apk &> /dev/null; then
        PKG_MANAGER="apk"
        PKG_NAME="py3-virtualenv"
        INSTALL_CMD="apk add $PKG_NAME"
    else
        print_error "不支持的包管理器，请手动安装 venv 模块"
        print_info "  Debian/Ubuntu: sudo apt install python3-venv"
        print_info "  RHEL/CentOS:   sudo yum install python3-devel"
        print_info "  Fedora:        sudo dnf install python3-venv"
        print_info "  Alpine:        apk add py3-virtualenv"
        exit 1
    fi

    print_info "检测到系统: $PKG_MANAGER"
    print_info "需要安装: $PKG_NAME"

    if ! confirm_action "是否自动安装 $PKG_NAME？"; then
        print_error "用户取消安装"
        exit 1
    fi

    print_info "正在安装 $PKG_NAME ..."
    if $ELEVATED_INSTALL; then
        $INSTALL_CMD 2>&1
    else
        sudo $INSTALL_CMD 2>&1 || {
            print_warn "sudo 安装失败，尝试直接运行（当前可能已是 root）..."
            $INSTALL_CMD 2>&1
        }
    fi

    # 验证安装结果
    if python3 -m venv --help &> /dev/null; then
        print_success "$PKG_NAME 安装成功"
    else
        print_error "venv 模块安装失败，请手动执行："
        print_info "  $INSTALL_CMD"
        exit 1
    fi
}

# ==================== 步骤 3：创建虚拟环境 ====================

create_venv() {
    step; print_step "$STEP" "创建 Python 虚拟环境"

    if [ -d "$SCRIPT_DIR/venv" ]; then
        # 验证现有 venv 是否可用
        if "$SCRIPT_DIR/venv/bin/python3" -m pip --version &> /dev/null; then
            print_info "虚拟环境已存在且可用，跳过创建"
            return 0
        else
            print_warn "虚拟环境已存在但不可用，将重新创建..."
            rm -rf "$SCRIPT_DIR/venv"
        fi
    fi

    cd "$SCRIPT_DIR"
    python3 -m venv venv
    print_success "虚拟环境创建完成"

    # 验证 pip 可用
    if "$SCRIPT_DIR/venv/bin/python3" -m pip --version &> /dev/null; then
        PIP_VERSION=$("$SCRIPT_DIR/venv/bin/pip3" --version 2>&1 | awk '{print $2}')
        print_success "pip 版本: $PIP_VERSION"
    else
        print_error "pip 不可用，虚拟环境创建可能不完整"
        exit 1
    fi
}

# ==================== 步骤 4：安装依赖 ====================

install_dependencies() {
    step; print_step "$STEP" "安装 Python 依赖"

    cd "$SCRIPT_DIR"

    if [ -f "requirements.txt" ]; then
        source venv/bin/activate
        pip install --upgrade pip -q 2>&1
        pip install -r requirements.txt -q
        print_success "依赖安装完成"
    else
        print_error "未找到 requirements.txt"
        exit 1
    fi
}

# ==================== 步骤 5：配置 MCP Endpoint ====================

get_mcp_endpoint() {
    step; print_step "$STEP" "配置 MCP Endpoint"

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

# ==================== 步骤 6：配置应用 ID ====================

get_app_id() {
    step; print_step "$STEP" "配置应用 ID (app_id)"

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

# ==================== 步骤 7：生成配置文件 ====================

generate_config() {
    step; print_step "$STEP" "生成配置文件"

    # 确保 config 目录存在
    mkdir -p "$CONFIG_DIR"

    # 使用 Python 生成 JSON，避免 shell 转义问题
    export MCP_ENDPOINT APP_ID CONFIG_DIR
    python3 << 'PYEOF'
import json, os

config = {
    "output_dir": "/root/.openclaw/workspace/download/",
    "mcp": {"endpoint": os.environ["MCP_ENDPOINT"]},
    "oauth": {
        "app_name": "alibabacloud-api-mcp-server@app.1263926834388048.onaliyun.com",
        "app_id": os.environ["APP_ID"],
        "scopes": ["openid", "/internal/acs/openapi", "aliuid"]
    },
    "token": {
        "access_token": "YOUR_ACCESS_TOKEN_HERE",
        "refresh_token": "YOUR_REFRESH_TOKEN_HERE",
        "expires_at": 0
    }
}

config_dir = os.environ["CONFIG_DIR"]
with open(os.path.join(config_dir, "config.json"), "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF

    print_success "config.json 已生成: config/config.json"
}

# ==================== 步骤 8：生成 OAuth 脚本 ====================

generate_oauth_script() {
    step; print_step "$STEP" "生成 OAuth 授权脚本"

    # 替换模板中的参数
    sed -e "s|YOUR_APP_ID_HERE|$APP_ID|g" \
        -e "s|YOUR_MCP_ENDPOINT_HERE|$MCP_ENDPOINT|g" \
        "$SCRIPT_DIR/oauth_local_server.py.example" > "$SCRIPT_DIR/oauth_local_server.py"

    print_success "oauth_local_server.py 已生成: scripts/oauth_local_server.py"
}

# ==================== 后续步骤提示 ====================

show_next_steps() {
    print_header "初始化完成 - 请继续完成以下步骤"

    OAUTH_SCRIPT_PATH="$SCRIPT_DIR/oauth_local_server.py"

    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  后续步骤${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""

    echo -e "${GREEN}[步骤 1] 下载 OAuth 脚本到本地${NC}"
    echo "  将以下文件下载到您的本地电脑（有浏览器的机器）："
    echo -e "${CYAN}  $OAUTH_SCRIPT_PATH${NC}"
    echo ""

    echo -e "${GREEN}[步骤 2] 本地运行 OAuth 脚本${NC}"
    echo "  在本地操作系统上运行（需已登录阿里云管理员账号）："
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
    echo "  Token 填写完成后，运行以下命令校验："
    echo -e "${CYAN}  ./scripts/mcp_verify.sh${NC}"
    echo ""

    echo -e "${GREEN}[提示] 文件发送方式${NC}"
    echo "  生成的文件通过以下命令发送到当前对话："
    echo -e "${CYAN}  openclaw message send --channel <channel> --target <target> --media <文件路径>${NC}"
    echo "  无需额外配置飞书账号。"
    echo ""

    echo -e "${GREEN}[提示] 输出目录${NC}"
    echo "  所有生成的文件默认输出到："
    echo -e "${CYAN}  /root/.openclaw/workspace/download/${NC}"
    echo "  可在 config.json 中修改 output_dir 字段自定义路径。"
    echo ""

    echo -e "${YELLOW}========================================${NC}"
    echo ""
}

# ==================== 工具函数：包安装 ====================

# 检测是否有 sudo 权限或已是 root
ELEVATED_INSTALL=false
if [ "$EUID" -eq 0 ]; then
    ELEVATED_INSTALL=true
elif command -v sudo &> /dev/null && sudo -n true 2>/dev/null; then
    ELEVATED_INSTALL=true
fi

# 通用包安装函数
_pkg_install() {
    local manager="$1"
    local package="$2"

    if ! confirm_action "自动安装 $package？"; then
        print_error "用户取消安装"
        exit 1
    fi

    print_info "正在安装 $package ..."

    # apt 需要先 update
    if [ "$manager" = "apt-get" ]; then
        if $ELEVATED_INSTALL; then
            apt-get update -qq 2>&1 || true
        else
            sudo apt-get update -qq 2>&1 || {
                print_warn "apt-get update 失败，尝试继续安装..."
            }
        fi
    fi

    if $ELEVATED_INSTALL; then
        $manager install -y "$package" 2>&1
    else
        sudo $manager install -y "$package" 2>&1 || {
            print_warn "sudo 安装失败，尝试直接运行..."
            $manager install -y "$package" 2>&1
        }
    fi
}

# ==================== 主流程 ====================

main() {
    print_header "阿里云持续运营 Skill 初始化"

    if $NO_CONFIRM; then
        print_info "运行模式: 非交互（全自动）"
        echo ""
    fi

    check_python            # 步骤 1：检查 Python（缺失则自动安装）
    ensure_venv_module      # 步骤 2：确保 venv 模块可用（缺失则自动安装）
    create_venv             # 步骤 3：创建虚拟环境
    install_dependencies    # 步骤 4：安装 Python 依赖
    get_mcp_endpoint        # 步骤 5：配置 MCP Endpoint
    get_app_id              # 步骤 6：配置应用 ID
    generate_config         # 步骤 7：生成配置文件
    generate_oauth_script   # 步骤 8：生成 OAuth 脚本

    show_next_steps
}

main
