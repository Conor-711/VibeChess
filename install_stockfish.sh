#!/bin/bash
# 这个脚本用于在Render环境中下载和安装Stockfish
# 简化版本 - 直接下载到bin目录并设置正确的权限

set -e  # 遇到错误立即停止
set -x  # 显示执行的命令

echo "====== 环境信息 ======"
echo "Current directory: $(pwd)"
echo "User: $(whoami)"
echo "PATH: $PATH"
echo "OS: $(uname -a)"

echo "====== 开始安装Stockfish... ======"

# 创建目录 - 使用绝对路径
PROJECT_DIR="$(pwd)"
BIN_DIR="$PROJECT_DIR/bin"
mkdir -p "$BIN_DIR"
echo "Created bin directory: $BIN_DIR"

# 直接下载Stockfish可执行文件
echo "====== 下载Stockfish可执行文件... ======"
DOWNLOAD_URL="https://github.com/official-stockfish/Stockfish/releases/download/sf_16/stockfish-ubuntu-x86-64-avx2"
TARGET_BIN="$BIN_DIR/stockfish"

echo "Downloading from: $DOWNLOAD_URL"
echo "Saving to: $TARGET_BIN"

# 直接下载可执行文件到bin目录
curl -L "$DOWNLOAD_URL" -o "$TARGET_BIN"
if [ $? -ne 0 ]; then
    echo "Failed to download Stockfish"
    exit 1
fi

# 设置可执行权限
chmod +x "$TARGET_BIN"
if [ $? -ne 0 ]; then
    echo "Failed to set executable permission"
    exit 1
fi

# 显示文件信息
ls -la "$TARGET_BIN"
file "$TARGET_BIN"

# 设置环境变量
echo "====== 配置环境变量... ======"
STOCKFISH_PATH="$TARGET_BIN"
export STOCKFISH_PATH="$STOCKFISH_PATH"

# 创建环境变量文件
echo "STOCKFISH_PATH=$STOCKFISH_PATH" > "$PROJECT_DIR/.env.stockfish"

# 将bin目录添加到PATH
export PATH="$BIN_DIR:$PATH"

# 验证安装
echo "====== 验证Stockfish安装... ======"
if [ -f "$STOCKFISH_PATH" ]; then
    echo "Stockfish 安装成功: $STOCKFISH_PATH"
    
    # 测试Stockfish是否可用
    echo "====== 测试Stockfish... ======"
    echo "quit" | "$STOCKFISH_PATH"
    RESULT=$?
    echo "Test exit code: $RESULT"
    
    if [ $RESULT -eq 0 ]; then
        echo "Stockfish 测试成功"
    else
        echo "Stockfish 测试失败"
        # 检查依赖关系
        ldd "$STOCKFISH_PATH" 2>/dev/null || echo "ldd not available"
        exit 1
    fi
    
    # 创建一个简单的Python测试脚本
    cat > "$BIN_DIR/test_stockfish.py" << EOL
#!/usr/bin/env python3
import subprocess
import sys
import os

print(f"Current directory: {os.getcwd()}")
print(f"Stockfish path: {os.environ.get('STOCKFISH_PATH', 'Not set')}")

try:
    stockfish_path = "$STOCKFISH_PATH"
    print(f"Testing Stockfish at: {stockfish_path}")
    print(f"File exists: {os.path.exists(stockfish_path)}")
    print(f"File executable: {os.access(stockfish_path, os.X_OK)}")
    
    result = subprocess.run([stockfish_path], 
                          input="quit\n", 
                          text=True, 
                          capture_output=True, 
                          timeout=2)
    print(f"Return code: {result.returncode}")
    print(f"Output: {result.stdout[:100]}...")
    print("Test successful!")
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
EOL
    chmod +x "$BIN_DIR/test_stockfish.py"
    
    # 运行测试脚本
    python3 "$BIN_DIR/test_stockfish.py" || echo "Python test failed"
    
    # 显示环境变量
    echo "====== 环境变量 ======"
    echo "STOCKFISH_PATH=$STOCKFISH_PATH"
else
    echo "Stockfish 安装失败"
    exit 1
fi

# 创建一个简单的README文件
cat > "$BIN_DIR/README.txt" << EOL
Stockfish binary installed by install_stockfish.sh
Path: $STOCKFISH_PATH
Date: $(date)
EOL

echo "====== Stockfish 安装完成 ======"
echo "Stockfish路径: $STOCKFISH_PATH"
