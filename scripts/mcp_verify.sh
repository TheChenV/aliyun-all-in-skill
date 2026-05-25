#!/bin/bash
# -*- coding: utf-8 -*-
#
# MCP 连通性校验脚本
# 检查配置文件并测试 MCP 连接
#

set -e

# 颜色定义（$'\033' 在赋值时解析，兼容性最好）
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BLUE=$'\033[0;34m'
BOLD=$'\033[1m'
NC=$'\033[0m'

# 获取路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$SKILL_DIR/config"
CONFIG_FILE="$CONFIG_DIR/config.json"

# 打印函数
print_check() { printf '%b[检查]%b %s\n' "$BLUE" "$NC" "$1"; }
print_success() { printf '  %b[OK]%b %s\n' "$GREEN" "$NC" "$1"; }
print_error() { printf '  %b[ERROR]%b %s\n' "$RED" "$NC" "$1"; }
print_info() { printf '  %b%s%b\n' "$YELLOW" "$1" "$NC"; }

# 检查 config.json 是否存在
check_config_exists() {
    print_check "配置文件是否存在"
    if [ -f "$CONFIG_FILE" ]; then
        print_success "config.json 存在: $CONFIG_FILE"
        return 0
    else
        print_error "config.json 不存在"
        print_info "请先运行 setup.sh 生成配置文件"
        return 1
    fi
}

# 检查 MCP Endpoint
check_mcp_endpoint() {
    print_check "MCP Endpoint 配置"
    ENDPOINT=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    endpoint = config.get('mcp', {}).get('endpoint', '')
    if endpoint == 'YOUR_MCP_ENDPOINT_HERE' or not endpoint:
        print('EMPTY')
    else:
        print(endpoint)
" 2>/dev/null)
    if [ "$ENDPOINT" = "EMPTY" ]; then
        print_error "MCP Endpoint 未配置"
        print_info "请访问 https://api.aliyun.com/mcp 获取 Endpoint"
        return 1
    else
        print_success "MCP Endpoint: $ENDPOINT"
        return 0
    fi
}

# 检查 AK 凭证
check_ak_credentials() {
    print_check "AK 静态凭证配置"
    AK_CHECK=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    ak = config.get('ak', {})
    ak_id = ak.get('access_key_id', '')
    ak_secret = ak.get('access_key_secret', '')
    if ak_id == 'YOUR_AK_ID_HERE' or not ak_id:
        print('ID_EMPTY')
    elif ak_secret == 'YOUR_AK_SECRET_HERE' or not ak_secret:
        print('SECRET_EMPTY')
    else:
        print('OK')
" 2>/dev/null)
    case "$AK_CHECK" in
        ID_EMPTY)
            print_error "AccessKey ID 未配置"
            print_info "请在 config.json 中配置 ak.access_key_id"
            return 1
            ;;
        SECRET_EMPTY)
            print_error "AccessKey Secret 未配置"
            print_info "请在 config.json 中配置 ak.access_key_secret"
            return 1
            ;;
        OK)
            print_success "AK 凭证已配置"
            return 0
            ;;
        *)
            print_error "无法解析 AK 配置"
            return 1
            ;;
    esac
}

# 检查 venv 和 mcp-proxy 依赖
check_venv_and_proxy() {
    print_check "venv 和 mcp-proxy 依赖"
    VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
    if [ ! -f "$VENV_PYTHON" ]; then
        print_error "venv Python 不存在: $VENV_PYTHON"
        print_info "请先运行 setup.sh 创建虚拟环境"
        return 1
    fi
    if ! "$VENV_PYTHON" -c "import alibabacloud.mcp_proxy" 2>/dev/null; then
        print_error "mcp-proxy 未安装"
        print_info "请运行: venv/bin/pip install alibabacloud.mcp-proxy"
        return 1
    fi
    PROXY_VERSION=$("$VENV_PYTHON" -c "from alibabacloud.mcp_proxy import __version__; print(__version__)" 2>/dev/null)
    print_success "mcp-proxy 已安装 (版本: $PROXY_VERSION)"
    return 0
}

# 测试 MCP 连接（通过 mcp_client.py）
test_mcp_connection() {
    print_check "MCP 连接测试"
    VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
    RESULT=$("$VENV_PYTHON" -c "
import sys, os, json
sys.path.insert(0, '$SCRIPT_DIR')
from mcp_client import MCPClient

try:
    client = MCPClient()
    tools = client.list_tools()
    client.close()
    print(json.dumps({'success': True, 'tools_count': len(tools)}))
except Exception as e:
    print(json.dumps({'success': False, 'error': str(e)}))
" 2>&1)

    if echo "$RESULT" | grep -q "^Traceback"; then
        print_error "MCP 连接失败: Python 错误"
        print_info "请检查 Python 环境和依赖"
        echo "$RESULT" | head -20
        return 1
    fi

    SUCCESS=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)

    if [ "$SUCCESS" = "True" ]; then
        TOOLS_COUNT=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tools_count', 0))")
        print_success "MCP 连接成功！可用工具数量: $TOOLS_COUNT"
        return 0
    else
        ERROR=$(echo "$RESULT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('error', '未知错误'))" 2>/dev/null)
        print_error "MCP 连接失败: $ERROR"
        return 1
    fi
}

# 主流程
main() {
    echo ""
    printf '%b========================================%b\n' "$BOLD$BLUE" "$NC"
    printf '%b  MCP 连通性校验%b\n' "$BOLD$BLUE" "$NC"
    printf '%b========================================%b\n' "$BOLD$BLUE" "$NC"
    echo ""

    ERRORS=0

    check_config_exists || ERRORS=$((ERRORS+1))
    check_mcp_endpoint || ERRORS=$((ERRORS+1))
    check_ak_credentials || ERRORS=$((ERRORS+1))
    check_venv_and_proxy || ERRORS=$((ERRORS+1))

    if [ $ERRORS -eq 0 ]; then
        test_mcp_connection || ERRORS=$((ERRORS+1))
    fi

    echo ""
    printf '%b========================================%b\n' "$BLUE" "$NC"

    if [ $ERRORS -eq 0 ]; then
        printf '  %b[OK]%b 校验通过，Skill 已就绪\n' "$GREEN" "$NC"
    else
        printf '  %b[ERROR]%b 发现 %d 个问题，请按提示修复\n' "$RED" "$NC" "$ERRORS"
    fi

    printf '%b========================================%b\n' "$BLUE" "$NC"
    echo ""

    exit $ERRORS
}

main
