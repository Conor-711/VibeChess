import os
import subprocess
import sys
from pathlib import Path

def find_stockfish_path():
    """
    尝试找到Stockfish引擎的路径
    """
    print("开始查找Stockfish路径...", file=sys.stderr)
    
    # 首先检查环境变量
    if 'STOCKFISH_PATH' in os.environ:
        path = os.environ['STOCKFISH_PATH']
        print(f"从环境变量STOCKFISH_PATH找到路径: {path}", file=sys.stderr)
        return path
    
    # 检查常见的路径
    common_paths = [
        'stockfish',                      # 如果在PATH中
        '/usr/bin/stockfish',             # Linux常见位置
        '/usr/local/bin/stockfish',       # macOS常见位置
        '/opt/homebrew/bin/stockfish',    # macOS Homebrew
        '/usr/games/stockfish',           # Debian/Ubuntu位置
        '/opt/render/project/bin/stockfish', # Render可能的位置
        '/bin/stockfish',                 # 其他可能位置
        '/sbin/stockfish',                # 其他可能位置
        str(Path.home() / 'stockfish'),   # 用户主目录
        './stockfish',                    # 当前目录
    ]
    
    # 检查项目中的stockfish目录
    stockfish_dir = Path(__file__).parent / 'stockfish'
    print(f"检查项目stockfish目录: {stockfish_dir}", file=sys.stderr)
    if stockfish_dir.exists():
        print(f"stockfish目录存在，检查可执行文件", file=sys.stderr)
        for item in stockfish_dir.glob('**/*'):
            if item.is_file() and item.name.startswith('stockfish'):
                print(f"找到可能的stockfish文件: {item}", file=sys.stderr)
                if os.access(str(item), os.X_OK):  # 检查是否可执行
                    print(f"找到可执行的stockfish: {item}", file=sys.stderr)
                    return str(item)
                else:
                    print(f"文件不可执行: {item}", file=sys.stderr)
    else:
        print(f"stockfish目录不存在", file=sys.stderr)
    
    # 尝试在PATH中查找
    try:
        print("尝试使用which命令查找stockfish", file=sys.stderr)
        result = subprocess.run(['which', 'stockfish'], capture_output=True, text=True)
        if result.returncode == 0:
            path = result.stdout.strip()
            print(f"which命令找到stockfish: {path}", file=sys.stderr)
            return path
        else:
            print(f"which命令未找到stockfish: {result.stderr}", file=sys.stderr)
    except Exception as e:
        print(f"执行which命令时出错: {e}", file=sys.stderr)
    
    # 尝试常见路径
    print("检查常见路径...", file=sys.stderr)
    for path in common_paths:
        print(f"检查路径: {path}", file=sys.stderr)
        if os.path.exists(path):
            print(f"路径存在: {path}", file=sys.stderr)
            if os.access(path, os.X_OK):
                print(f"找到可执行的stockfish: {path}", file=sys.stderr)
                return path
            else:
                print(f"文件存在但不可执行: {path}", file=sys.stderr)
        else:
            print(f"路径不存在: {path}", file=sys.stderr)
    
    # 尝试查找系统中所有的stockfish文件
    try:
        print("尝试使用find命令查找所有stockfish文件", file=sys.stderr)
        result = subprocess.run(['find', '/', '-name', 'stockfish', '-type', 'f'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            paths = result.stdout.strip().split('\n')
            print(f"find命令找到以下stockfish文件: {paths}", file=sys.stderr)
            for path in paths:
                if os.access(path, os.X_OK):
                    print(f"找到可执行的stockfish: {path}", file=sys.stderr)
                    return path
    except Exception as e:
        print(f"执行find命令时出错: {e}", file=sys.stderr)
    
    print("未找到stockfish路径", file=sys.stderr)
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
