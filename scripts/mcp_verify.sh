#!/bin/bash
# -*- coding: utf-8 -*-
#
# MCP 连通性校验脚本
# 检查配置文件并测试 MCP 连接
#

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 获取路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="$SKILL_DIR/config"
CONFIG_FILE="$CONFIG_DIR/config.json"

# 打印函数
print_check() {
    echo -e "${BLUE}[检查]${NC} $1"
}

print_success() {
    echo -e "${GREEN}  ✓ $1${NC}"
}

print_error() {
    echo -e "${RED}  ✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}  $1${NC}"
}

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

# 检查 app_id
check_app_id() {
    print_check "应用 ID (app_id) 配置"

    APP_ID=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    app_id = config.get('oauth', {}).get('app_id', '')
    if app_id == 'YOUR_APP_ID_HERE' or not app_id:
        print('EMPTY')
    else:
        print(app_id)
" 2>/dev/null)

    if [ "$APP_ID" = "EMPTY" ]; then
        print_error "应用 ID 未配置"
        print_info "请前往 RAM 控制台获取应用 ID"
        return 1
    else
        print_success "应用 ID: $APP_ID"
        return 0
    fi
}

# 检查 Token
check_token() {
    print_check "Access Token 配置"

    ACCESS_TOKEN=$(python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
    token = config.get('token', {}).get('access_token', '')
    if token == 'YOUR_ACCESS_TOKEN_HERE' or not token:
        print('EMPTY')
    else:
        print('SET')
" 2>/dev/null)

    if [ "$ACCESS_TOKEN" = "EMPTY" ]; then
        print_error "Access Token 未配置"
        print_info "请在本地运行 oauth_local_server.py 获取 Token"
        return 1
    else
        print_success "Access Token 已配置"
        return 0
    fi
}

# 测试 MCP 连接（使用正确的 JSON-RPC 协议）
test_mcp_connection() {
    print_check "MCP 连接测试"

    # 使用环境变量传递配置文件路径
    export MCP_CONFIG_FILE="$CONFIG_FILE"

    # 使用 Python 的 mcp_client 测试连接
    RESULT=$(python3 << 'PYEOF'
import json
import urllib.request
import urllib.error
import sys
import os

try:
    config_file = os.environ.get('MCP_CONFIG_FILE')

    if not config_file:
        print(json.dumps({"success": False, "error": "配置文件路径未设置"}))
        sys.exit(0)

    # 读取配置
    with open(config_file, 'r') as f:
        config = json.load(f)

    endpoint = config.get('mcp', {}).get('endpoint', '')
    access_token = config.get('token', {}).get('access_token', '')

    if not endpoint or not access_token:
        print(json.dumps({"success": False, "error": "配置不完整"}))
        sys.exit(0)

    # 步骤 1: Initialize 获取 session ID
    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "mcp-verify",
                "version": "1.0.0"
            }
        }
    }

    init_req = urllib.request.Request(
        endpoint,
        data=json.dumps(init_payload).encode('utf-8'),
        method='POST'
    )
    init_req.add_header('Authorization', f'Bearer {access_token}')
    init_req.add_header('Content-Type', 'application/json')
    init_req.add_header('Accept', 'application/json, text/event-stream')

    try:
        with urllib.request.urlopen(init_req, timeout=30) as response:
            session_id = response.headers.get('mcp-session-id')

            if not session_id:
                print(json.dumps({
                    "success": False,
                    "error": "未获取到 session ID",
                    "detail": "请检查 MCP Endpoint 是否正确"
                }))
                sys.exit(0)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')[:500]
        if e.code == 401:
            print(json.dumps({
                "success": False,
                "error": "Token 无效或已过期",
                "detail": "请重新运行 oauth_local_server.py 获取新 Token"
            }))
        elif e.code == 404:
            print(json.dumps({
                "success": False,
                "error": "Endpoint 不存在",
                "detail": "请检查 MCP Endpoint URL 是否正确"
            }))
        else:
            print(json.dumps({
                "success": False,
                "error": f"HTTP {e.code}",
                "detail": error_body
            }))
        sys.exit(0)
    except urllib.error.URLError as e:
        print(json.dumps({
            "success": False,
            "error": "网络连接失败",
            "detail": str(e.reason)
        }))
        sys.exit(0)

    # 步骤 2: 调用 tools/list
    tools_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }

    tools_req = urllib.request.Request(
        endpoint,
        data=json.dumps(tools_payload).encode('utf-8'),
        method='POST'
    )
    tools_req.add_header('Authorization', f'Bearer {access_token}')
    tools_req.add_header('Content-Type', 'application/json')
    tools_req.add_header('Accept', 'application/json')
    tools_req.add_header('mcp-session-id', session_id)

    with urllib.request.urlopen(tools_req, timeout=30) as response:
        result = json.loads(response.read().decode('utf-8'))
        # 处理多种返回格式: {"tools": []} 或 {"result": {"tools": []}} 或直接列表
        if isinstance(result, list):
            tools = result
        elif isinstance(result, dict):
            tools = result.get('tools', result.get('result', {}).get('tools', []))
        else:
            tools = []
        print(json.dumps({
            "success": True,
            "tools_count": len(tools)
        }))

except Exception as e:
    print(json.dumps({"success": False, "error": str(e)}))
PYEOF
 2>&1)

    # 检查是否有 Python 错误输出
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
        DETAIL=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin).get('detail', ''); print(d if d else '')" 2>/dev/null)

        print_error "MCP 连接失败: $ERROR"
        if [ -n "$DETAIL" ]; then
            print_info "详情: $DETAIL"
        fi
        return 1
    fi
}

# 主流程
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  MCP 连通性校验${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    ERRORS=0

    check_config_exists || ERRORS=$((ERRORS+1))
    check_mcp_endpoint || ERRORS=$((ERRORS+1))
    check_app_id || ERRORS=$((ERRORS+1))
    check_token || ERRORS=$((ERRORS+1))

    if [ $ERRORS -eq 0 ]; then
        test_mcp_connection || ERRORS=$((ERRORS+1))
    fi

    echo ""
    echo -e "${BLUE}========================================${NC}"

    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}  ✓ 校验通过，Skill 已就绪${NC}"
    else
        echo -e "${RED}  ✗ 发现 $ERRORS 个问题，请按提示修复${NC}"
    fi

    echo -e "${BLUE}========================================${NC}"
    echo ""

    exit $ERRORS
}

main
