#!/bin/bash
# 这个脚本用于在Render环境中下载和安装Stockfish

set -x  # 显示执行的命令

echo "====== 环境信息 ======"
echo "Current directory: $(pwd)"
echo "User: $(whoami)"
echo "PATH: $PATH"
echo "OS: $(uname -a)"

echo "====== 开始安装Stockfish... ======"

# 创建目录 - 使用绝对路径
BIN_DIR="$(pwd)/bin"
mkdir -p "$BIN_DIR"
echo "Created bin directory: $BIN_DIR"
ls -la "$BIN_DIR"

# 下载Stockfish (Linux版本)
echo "====== 下载Stockfish... ======"
DOWNLOAD_URL="https://github.com/official-stockfish/Stockfish/releases/download/sf_16/stockfish-ubuntu-x86-64-avx2.tar.gz"
TAR_FILE="$(pwd)/stockfish.tar.gz"

echo "Downloading from: $DOWNLOAD_URL"
echo "Saving to: $TAR_FILE"

curl -L -v "$DOWNLOAD_URL" -o "$TAR_FILE"
if [ $? -ne 0 ]; then
    echo "Failed to download Stockfish"
    exit 1
fi

ls -la "$TAR_FILE"

# 解压
echo "====== 解压Stockfish... ======"
tar -xzvf "$TAR_FILE"
if [ $? -ne 0 ]; then
    echo "Failed to extract Stockfish"
    exit 1
fi

ls -la

# 移动到当前项目的bin目录
echo "====== 安装Stockfish... ======"
STOCKFISH_BIN="$(pwd)/stockfish/stockfish-ubuntu-x86-64-avx2"
TARGET_BIN="$BIN_DIR/stockfish"

echo "Source binary: $STOCKFISH_BIN"
echo "Target binary: $TARGET_BIN"

if [ ! -f "$STOCKFISH_BIN" ]; then
    echo "ERROR: Source binary not found!"
    find "$(pwd)" -name "stockfish*" -type f
    exit 1
fi

chmod +x "$STOCKFISH_BIN"
cp -v "$STOCKFISH_BIN" "$TARGET_BIN"

ls -la "$TARGET_BIN"

# 设置环境变量
echo "====== 配置环境变量... ======"
STOCKFISH_PATH="$TARGET_BIN"
export STOCKFISH_PATH="$STOCKFISH_PATH"

# 创建多个环境变量文件
echo "STOCKFISH_PATH=$STOCKFISH_PATH" > .env.stockfish
echo "export STOCKFISH_PATH=$STOCKFISH_PATH" >> ~/.bashrc
echo "export STOCKFISH_PATH=$STOCKFISH_PATH" >> ~/.profile

# 将bin目录添加到PATH
echo "export PATH=$BIN_DIR:\$PATH" >> ~/.bashrc
echo "export PATH=$BIN_DIR:\$PATH" >> ~/.profile

# 立即更新当前PATH
export PATH="$BIN_DIR:$PATH"

# 清理
echo "====== 清理临时文件... ======"
rm -rf "$TAR_FILE" "$(pwd)/stockfish"

# 验证安装
echo "====== 验证Stockfish安装... ======"
if [ -f "$STOCKFISH_PATH" ]; then
    echo "Stockfish 安装成功: $STOCKFISH_PATH"
    ls -la "$STOCKFISH_PATH"
    file "$STOCKFISH_PATH"
    
    # 测试Stockfish是否可用
    echo "====== 测试Stockfish... ======"
    echo "quit" | "$STOCKFISH_PATH"
    RESULT=$?
    echo "Test exit code: $RESULT"
    
    if [ $RESULT -eq 0 ]; then
        echo "Stockfish 测试成功"
    else
        echo "Stockfish 测试失败"
        
        # 尝试直接运行来查看错误
        "$STOCKFISH_PATH" --help
        
        # 检查依赖关系
        ldd "$STOCKFISH_PATH" 2>/dev/null || echo "ldd not available"
        
        exit 1
    fi
    
    # 创建一个简单的包装脚本
    echo '#!/bin/bash\n"'"$STOCKFISH_PATH"'" "$@"' > "$BIN_DIR/stockfish.sh"
    chmod +x "$BIN_DIR/stockfish.sh"
    echo "Created wrapper script: $BIN_DIR/stockfish.sh"
    
    # 创建一个简单的Python脚本来测试Stockfish
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
    echo "Created test script: $BIN_DIR/test_stockfish.py"
    
    # 运行测试脚本
    python3 "$BIN_DIR/test_stockfish.py" || echo "Python test failed"
    
    # 创建一个简单的符号链接
    ln -sf "$STOCKFISH_PATH" /tmp/stockfish 2>/dev/null && echo "Created symlink at /tmp/stockfish" || echo "Failed to create symlink"
    
    # 显示当前目录结构
    echo "====== 当前目录结构 ======"
    find "$(pwd)" -type f -name "stockfish*" | xargs ls -la
    
    # 显示环境变量
    echo "====== 环境变量 ======"
    echo "STOCKFISH_PATH=$STOCKFISH_PATH"
    echo "PATH=$PATH"
else
    echo "Stockfish 安装失败"
    exit 1
fi

echo "====== Stockfish 安装完成 ======"
