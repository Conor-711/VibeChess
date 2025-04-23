import os
import subprocess
import sys
from pathlib import Path

def find_stockfish_path():
    """
    尝试找到Stockfish引擎的路径
    """
    # 首先检查环境变量
    if 'STOCKFISH_PATH' in os.environ:
        return os.environ['STOCKFISH_PATH']
    
    # 检查常见的路径
    common_paths = [
        'stockfish',                      # 如果在PATH中
        '/usr/bin/stockfish',             # Linux常见位置
        '/usr/local/bin/stockfish',       # macOS常见位置
        '/opt/homebrew/bin/stockfish',    # macOS Homebrew
        str(Path.home() / 'stockfish'),   # 用户主目录
        './stockfish',                    # 当前目录
    ]
    
    # 检查项目中的stockfish目录
    stockfish_dir = Path(__file__).parent / 'stockfish'
    if stockfish_dir.exists():
        for item in stockfish_dir.glob('**/*'):
            if item.is_file() and item.name.startswith('stockfish'):
                if os.access(str(item), os.X_OK):  # 检查是否可执行
                    return str(item)
    
    # 尝试在PATH中查找
    try:
        result = subprocess.run(['which', 'stockfish'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    
    # 尝试常见路径
    for path in common_paths:
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path
    
    # 如果在Render环境中，尝试使用apt安装的路径
    if os.environ.get('RENDER'):
        return '/usr/games/stockfish'
    
    return None

def check_stockfish_installation():
    """
    检查Stockfish是否正确安装
    """
    stockfish_path = find_stockfish_path()
    
    if not stockfish_path:
        print("警告: 无法找到Stockfish引擎。")
        print("请安装Stockfish并确保它在PATH中，或设置STOCKFISH_PATH环境变量。")
        print("安装方法:")
        print("- Mac: brew install stockfish")
        print("- Linux: apt-get install stockfish")
        print("- 或从 https://stockfishchess.org/download/ 下载")
        return None
    
    # 验证路径是否有效
    try:
        result = subprocess.run([stockfish_path], input="quit\n", text=True, capture_output=True, timeout=2)
        if result.returncode != 0:
            print(f"警告: 在路径 {stockfish_path} 的Stockfish似乎不能正常工作。")
            return None
    except Exception as e:
        print(f"警告: 测试Stockfish时出错: {e}")
        return None
    
    print(f"Stockfish引擎找到于: {stockfish_path}")
    return stockfish_path

# 如果直接运行此脚本，则输出Stockfish路径
if __name__ == "__main__":
    path = check_stockfish_installation()
    if path:
        print(f"Stockfish路径: {path}")
    else:
        print("无法找到有效的Stockfish引擎")
        sys.exit(1)
