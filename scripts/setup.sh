#!/bin/bash
# -*- coding: utf-8 -*-
#
# 阿里云持续运营 Skill 初始化脚本
# 交互式引导用户完成环境配置
# 使用 AK 静态凭证认证，无需 OAuth
#
# 使用方式：在项目根目录执行 bash ./scripts/setup.sh
# 可选参数：--no-confirm  跳过确认，全自动安装（适用于 CI/CD）
#

set -e

# 颜色定义（$'\033' 在赋值时解析，兼容性最好）
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
NC=$'\033[0m'

# 解析参数
NO_CONFIRM=false
for arg in "$@"; do
    case "$arg" in
        --no-confirm) NO_CONFIRM=true ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$SKILL_DIR/config"

STEP=0
step() { STEP=$((STEP + 1)); }

print_header() {
    echo ""
    printf '%b' "$BOLD"
    echo "========================================"
    echo "  $1"
    echo "========================================"
    printf '%b\n' "$NC"
    echo ""
}

print_step() { printf '%b[步骤 %d]%b %s\n' "$GREEN" "$1" "$NC" "$2"; }
print_info() { printf '  %b%s%b\n' "$YELLOW" "$1" "$NC"; }
print_success() { printf '  %b[OK]%b %s\n' "$GREEN" "$NC" "$1"; }
print_warn() { printf '  %b[WARN]%b %s\n' "$YELLOW" "$NC" "$1"; }
print_error() { printf '  %b[ERROR]%b %s\n' "$RED" "$NC" "$1"; }

print_separator() { echo ""; printf '%b' "$BLUE"; echo "----------------------------------------"; printf '%b\n' "$NC"; echo ""; }

confirm_action() {
    if $NO_CONFIRM; then
        print_info "[非交互模式] 自动确认: $1"
        return 0
    fi
    echo -n "$1 [Y/n]: "
    read -r CONFIRM
    [[ "$CONFIRM" =~ ^[Nn]$ ]] && return 1
    return 0
}

# ==================== 步骤 1：检查 Python 环境 ====================

check_python() {
    step; print_step "$STEP" "检查 Python 环境"
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 python3 命令"
        _auto_install_python
        return $?
    fi
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
        print_error "Python 版本过低: $PYTHON_VERSION（需要 >= 3.10）"
        _auto_install_python
        return $?
    fi
    print_success "Python 版本: $PYTHON_VERSION"
}

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
    else
        print_error "Python 安装失败，请手动安装"
        exit 1
    fi
}

# ==================== 步骤 2：确保 venv 模块可用 ====================

ensure_venv_module() {
    step; print_step "$STEP" "检查 venv 模块"
    if python3 -c "import ensurepip" &> /dev/null; then
        print_success "venv 模块已就绪"
        return 0
    fi
    print_warn "venv 模块不可用（缺少 python3-venv / ensurepip 包）"
    if command -v apt-get &> /dev/null; then
        PKG_MANAGER="apt"; PKG_NAME="python3-venv"; INSTALL_CMD="apt-get install -y $PKG_NAME"
    elif command -v yum &> /dev/null; then
        PKG_MANAGER="yum"; PKG_NAME="python3-devel"; INSTALL_CMD="yum install -y $PKG_NAME"
    elif command -v dnf &> /dev/null; then
        PKG_MANAGER="dnf"; PKG_NAME="python3-venv"; INSTALL_CMD="dnf install -y $PKG_NAME"
    elif command -v apk &> /dev/null; then
        PKG_MANAGER="apk"; PKG_NAME="py3-virtualenv"; INSTALL_CMD="apk add $PKG_NAME"
    else
        print_error "不支持的包管理器，请手动安装 venv 模块"
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
        sudo $INSTALL_CMD 2>&1 || { print_warn "sudo 安装失败，尝试直接运行..."; $INSTALL_CMD 2>&1; }
    fi
    if python3 -m venv --help &> /dev/null; then
        print_success "$PKG_NAME 安装成功"
    else
        print_error "venv 模块安装失败，请手动执行：$INSTALL_CMD"
        exit 1
    fi
}

# ==================== 步骤 3：创建虚拟环境 ====================

create_venv() {
    step; print_step "$STEP" "创建 Python 虚拟环境"
    if [ -d "$SCRIPT_DIR/venv" ]; then
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
    if "$SCRIPT_DIR/venv/bin/python3" -m pip --version &> /dev/null; then
        PIP_VERSION=$("$SCRIPT_DIR/venv/bin/pip3" --version 2>&1 | awk '{print $2}')
        print_success "pip 版本: $PIP_VERSION"
    else
        print_error "pip 不可用"
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
    printf '%b如何获取 MCP Endpoint：%b\n' "$YELLOW" "$NC"
    echo ""
    echo "  1. 登录阿里云控制台"
    printf '  2. 访问: %bhttps://api.aliyun.com/mcp%b\n' "$CYAN" "$NC"
    echo "  3. 复制 Streamable HTTP Endpoint"
    echo ""
    printf '%b格式示例：%b\n' "$YELLOW" "$NC"
    printf '  %bhttps://openapi-mcp.<region>.aliyuncs.com/id/<your-id>/mcp%b\n' "$CYAN" "$NC"
    print_separator
    echo -n "请输入 MCP Endpoint: "
    read MCP_ENDPOINT
    if [ -z "$MCP_ENDPOINT" ]; then
        print_error "MCP Endpoint 不能为空"
        exit 1
    fi
    if [[ ! "$MCP_ENDPOINT" =~ ^https:// ]]; then
        print_error "MCP Endpoint 格式错误，应以 https:// 开头"
        exit 1
    fi
    print_success "MCP Endpoint 已记录"
}

# ==================== 步骤 6：配置 AK 凭证 ====================

get_ak_credentials() {
    step; print_step "$STEP" "配置 AK 静态凭证"
    print_separator
    printf '%b如何获取 AccessKey：%b\n' "$YELLOW" "$NC"
    echo ""
    echo "  1. 登录阿里云 RAM 控制台："
    printf '     %bhttps://ram.console.aliyun.com/users%b\n' "$CYAN" "$NC"
    echo ""
    echo "  2. 找到对应的 RAM 用户，点击进入详情"
    echo ""
    echo "  3. 在 认证管理 标签页中："
    echo "     - 找到 AccessKey 区域"
    echo "     - 点击 创建 AccessKey"
    echo ""
    echo "  4. 创建成功后，保存 AccessKey ID 和 AccessKey Secret"
    echo ""
    printf '%b前置条件：%b\n' "$YELLOW" "$NC"
    echo ""
    echo "  该 RAM 用户需要授予以下权限策略："
    printf '  %bAliyunOpenAPIMCPServerStaticCredentialAccess%b\n' "$CYAN" "$NC"
    echo ""
    echo "  在 RAM 控制台 -> 用户 -> 权限管理 -> 添加权限 -> 搜索该策略名称"
    print_separator
    echo -n "请输入 AccessKey ID: "
    read AK_ID
    if [ -z "$AK_ID" ]; then
        print_error "AccessKey ID 不能为空"
        exit 1
    fi
    echo -n "请输入 AccessKey Secret: "
    read AK_SECRET
    if [ -z "$AK_SECRET" ]; then
        print_error "AccessKey Secret 不能为空"
        exit 1
    fi
    print_success "AK 凭证已记录"
}

# ==================== 步骤 7：生成配置文件 ====================

generate_config() {
    step; print_step "$STEP" "生成配置文件"
    mkdir -p "$CONFIG_DIR"
    export MCP_ENDPOINT AK_ID AK_SECRET CONFIG_DIR
    python3 << 'PYEOF'
import json, os

config = {
    "output_dir": "/root/.openclaw/workspace/download/",
    "mcp": {"endpoint": os.environ["MCP_ENDPOINT"]},
    "ak": {
        "access_key_id": os.environ["AK_ID"],
        "access_key_secret": os.environ["AK_SECRET"]
    }
}

config_dir = os.environ["CONFIG_DIR"]
with open(os.path.join(config_dir, "config.json"), "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
    f.write("\n")
PYEOF
    print_success "config.json 已生成: config/config.json"
}

# ==================== 后续步骤提示 ====================

show_next_steps() {
    print_header "初始化完成 - 请继续完成以下步骤"
    printf '%b========================================%b\n' "$YELLOW" "$NC"
    printf '%b  后续步骤%b\n' "$YELLOW" "$NC"
    printf '%b========================================%b\n' "$YELLOW" "$NC"
    echo ""

    printf '%b[步骤 1]%b 配置 RAM 权限\n' "$GREEN" "$NC"
    echo "  确保 AK 对应的 RAM 用户已授予以下策略："
    printf '  %bAliyunOpenAPIMCPServerStaticCredentialAccess%b\n' "$CYAN" "$NC"
    echo "  如已配置，可跳过此步骤。"
    echo ""

    printf '%b[步骤 2]%b 校验 MCP 连通性\n' "$GREEN" "$NC"
    echo "  运行以下命令校验："
    printf '  %b./scripts/mcp_verify.sh%b\n' "$CYAN" "$NC"
    echo ""

    printf '%b[步骤 3]%b 测试报价\n' "$GREEN" "$NC"
    echo "  ECS 报价（文本模式）："
    printf "  %bvenv/bin/python3 scripts/ecs_text_quoter.py '配置描述'%b\n" "$CYAN" "$NC"
    echo ""
    echo "  RDS 报价（文本模式）："
    printf "  %bvenv/bin/python3 scripts/rds_text_quoter.py '配置描述'%b\n" "$CYAN" "$NC"
    echo ""

    printf '%b========================================%b\n' "$YELLOW" "$NC"
    echo ""
    printf '%bAK 静态凭证认证，无需定期刷新，永不过期。%b\n' "$GREEN" "$NC"
    echo ""
}

# ==================== 工具函数 ====================

ELEVATED_INSTALL=false
if [ "$EUID" -eq 0 ]; then
    ELEVATED_INSTALL=true
elif command -v sudo &> /dev/null && sudo -n true 2>/dev/null; then
    ELEVATED_INSTALL=true
fi

_pkg_install() {
    local manager="$1"
    local package="$2"
    if ! confirm_action "自动安装 $package？"; then
        print_error "用户取消安装"
        exit 1
    fi
    print_info "正在安装 $package ..."
    if [ "$manager" = "apt-get" ]; then
        if $ELEVATED_INSTALL; then apt-get update -qq 2>&1 || true
        else sudo apt-get update -qq 2>&1 || print_warn "apt-get update 失败，尝试继续..."; fi
    fi
    if $ELEVATED_INSTALL; then
        $manager install -y "$package" 2>&1
    else
        sudo $manager install -y "$package" 2>&1 || { print_warn "sudo 安装失败，尝试直接运行..."; $manager install -y "$package" 2>&1; }
    fi
}

# ==================== 主流程 ====================

main() {
    print_header "阿里云持续运营 Skill 初始化（AK 模式）"
    if $NO_CONFIRM; then print_info "运行模式: 非交互（全自动）"; echo ""; fi

    check_python              # 步骤 1
    ensure_venv_module        # 步骤 2
    create_venv               # 步骤 3
    install_dependencies      # 步骤 4
    get_mcp_endpoint          # 步骤 5
    get_ak_credentials        # 步骤 6
    generate_config           # 步骤 7

    show_next_steps
}

main
