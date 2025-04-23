#!/bin/bash
# 这个脚本用于在Render环境中下载和安装Stockfish

echo "====== 开始安装Stockfish... ======"

# 创建目录
mkdir -p bin
echo "Created bin directory in: $(pwd)/bin"

# 下载Stockfish (Linux版本)
echo "====== 下载Stockfish... ======"
curl -L https://github.com/official-stockfish/Stockfish/releases/download/sf_16/stockfish-ubuntu-x86-64-avx2.tar.gz -o stockfish.tar.gz
if [ $? -ne 0 ]; then
    echo "Failed to download Stockfish"
    exit 1
fi

# 解压
echo "====== 解压Stockfish... ======"
tar -xzf stockfish.tar.gz
if [ $? -ne 0 ]; then
    echo "Failed to extract Stockfish"
    exit 1
fi

# 移动到当前项目的bin目录
echo "====== 安装Stockfish... ======"
chmod +x stockfish/stockfish-ubuntu-x86-64-avx2
cp stockfish/stockfish-ubuntu-x86-64-avx2 bin/stockfish

# 设置环境变量
echo "====== 配置环境变量... ======"
STOCKFISH_PATH="$(pwd)/bin/stockfish"
export STOCKFISH_PATH="$STOCKFISH_PATH"
echo "STOCKFISH_PATH=$STOCKFISH_PATH" > .env.stockfish

# 清理
echo "====== 清理临时文件... ======"
rm -rf stockfish.tar.gz stockfish

# 验证安装
echo "====== 验证Stockfish安装... ======"
if [ -f "$STOCKFISH_PATH" ]; then
    echo "Stockfish 安装成功: $STOCKFISH_PATH"
    ls -la "$STOCKFISH_PATH"
    
    # 测试Stockfish是否可用
    echo "====== 测试Stockfish... ======"
    echo "quit" | "$STOCKFISH_PATH"
    if [ $? -eq 0 ]; then
        echo "Stockfish 测试成功"
    else
        echo "Stockfish 测试失败"
        exit 1
    fi
else
    echo "Stockfish 安装失败"
    exit 1
fi

echo "====== Stockfish 安装完成 ======"
