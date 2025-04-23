"""
自定义Stockfish引擎包装器，不依赖stockfish包
直接使用subprocess与Stockfish引擎通信
"""

import os
import sys
import subprocess
import time
import atexit
from pathlib import Path

class StockfishWrapper:
    """Stockfish引擎的简单包装器"""
    
    def __init__(self, path=None, depth=10, parameters=None):
        """
        初始化Stockfish引擎
        
        Args:
            path: Stockfish可执行文件的路径，如果为None则尝试自动查找
            depth: 搜索深度
            parameters: 引擎参数字典
        """
        print("========== StockfishWrapper初始化开始 ===========", file=sys.stderr)
        print(f"Python工作目录: {os.getcwd()}", file=sys.stderr)
        print(f"Python脚本路径: {__file__}", file=sys.stderr)
        print(f"Python环境变量 PATH: {os.environ.get('PATH', '')}", file=sys.stderr)
        
        self.depth = depth
        self.parameters = parameters or {}
        
        # 查找Stockfish路径
        print("---------- 开始查找Stockfish路径 ----------", file=sys.stderr)
        self.stockfish_path = path or self._find_stockfish_path()
        
        if not self.stockfish_path:
            print("\n*** 错误: 无法找到Stockfish引擎路径 ***", file=sys.stderr)
            
            # 列出当前目录结构
            print("\n当前目录结构:", file=sys.stderr)
            try:
                for root, dirs, files in os.walk(".", topdown=True, followlinks=False):
                    level = root.count(os.sep)
                    indent = ' ' * 4 * level
                    print(f"{indent}{os.path.basename(root)}/", file=sys.stderr)
                    sub_indent = ' ' * 4 * (level + 1)
                    for f in files:
                        print(f"{sub_indent}{f}", file=sys.stderr)
            except Exception as e:
                print(f"\n列出目录结构时出错: {e}", file=sys.stderr)
            
            # 尝试查找系统中的stockfish
            print("\n尝试在系统中查找stockfish:", file=sys.stderr)
            try:
                result = subprocess.run(['find', '/', '-name', 'stockfish', '-type', 'f', '-perm', '/u+x'], 
                                      capture_output=True, text=True, timeout=5)
                if result.stdout:
                    print(result.stdout, file=sys.stderr)
                else:
                    print("\u672a找到可执行的stockfish文件", file=sys.stderr)
            except Exception as e:
                print(f"\u6267行find命令时出错: {e}", file=sys.stderr)
            
            raise FileNotFoundError("无法找到Stockfish引擎")
        
        print(f"\n*** 最终使用Stockfish路径: {self.stockfish_path} ***", file=sys.stderr)
        print(f"Stockfish文件存在: {os.path.exists(self.stockfish_path)}", file=sys.stderr)
        print(f"Stockfish文件可执行: {os.access(self.stockfish_path, os.X_OK)}", file=sys.stderr)
        
        try:
            # 显示文件信息
            try:
                file_stat = os.stat(self.stockfish_path)
                print(f"Stockfish文件大小: {file_stat.st_size} 字节", file=sys.stderr)
                print(f"Stockfish文件权限: {oct(file_stat.st_mode)}", file=sys.stderr)
            except Exception as e:
                print(f"\u83b7取文件信息时出错: {e}", file=sys.stderr)
            
            # 启动Stockfish进程
            print("\n---------- 尝试启动Stockfish进程 ----------", file=sys.stderr)
            print(f"使用绝对路径启动Stockfish: {os.path.abspath(self.stockfish_path)}", file=sys.stderr)
            self.process = subprocess.Popen(
                os.path.abspath(self.stockfish_path),  # 确保使用绝对路径
                universal_newlines=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 确保进程在Python退出时关闭
            atexit.register(self.quit)
            
            # 设置引擎参数
            print("\n---------- 配置Stockfish引擎参数 ----------", file=sys.stderr)
            self._configure_engine()
            
            print("\n*** Stockfish引擎成功初始化 ***", file=sys.stderr)
        except Exception as e:
            print(f"\n*** 启动Stockfish引擎失败: {e} ***", file=sys.stderr)
            # 尝试手动测试Stockfish执行文件 - 使用绝对路径
            try:
                abs_path = os.path.abspath(self.stockfish_path)
                print(f"尝试使用绝对路径测试Stockfish: {abs_path}", file=sys.stderr)
                test_result = subprocess.run(
                    [abs_path, '--version'], 
                    capture_output=True, 
                    text=True, 
                    timeout=5
                )
                print(f"\u8fd4回码: {test_result.returncode}", file=sys.stderr)
                print(f"\u6807准输出: {test_result.stdout}", file=sys.stderr)
                print(f"\u9519误输出: {test_result.stderr}", file=sys.stderr)
            except Exception as test_e:
                print(f"\u624b动测试失败: {test_e}", file=sys.stderr)
            
            raise
    
    def _find_stockfish_path(self):
        # 获取项目的绝对路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"项目绝对路径: {base_dir}", file=sys.stderr)
        
        # 首先检查项目中的bin目录 - 使用绝对路径
        project_bin = os.path.join(base_dir, "bin", "stockfish")
        if os.path.exists(project_bin) and os.access(project_bin, os.X_OK):
            print(f"从项目的bin目录找到Stockfish: {project_bin}", file=sys.stderr)
            return project_bin
            
        # 然后检查环境变量
        if 'STOCKFISH_PATH' in os.environ:
            path = os.environ['STOCKFISH_PATH']
            print(f"从环境变量找到Stockfish路径: {path}", file=sys.stderr)
            return path
        
        # 检查.env.stockfish文件 - 使用绝对路径
        env_file = os.path.join(base_dir, ".env.stockfish")
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        if line.startswith('STOCKFISH_PATH='):
                            path = line.strip().split('=', 1)[1]
                            # 如果路径不是绝对路径，转换为绝对路径
                            if not os.path.isabs(path):
                                path = os.path.abspath(os.path.join(base_dir, path))
                                print(f"将相对路径转换为绝对路径: {path}", file=sys.stderr)
                            if os.path.exists(path) and os.access(path, os.X_OK):
                                print(f"从.env.stockfish文件找到Stockfish路径: {path}", file=sys.stderr)
                                return path
            except Exception as e:
                print(f"读取.env.stockfish文件时出错: {e}", file=sys.stderr)
        
        # 使用绝对路径
        base_dir = os.path.dirname(os.path.abspath(__file__))
        print(f"项目基础目录: {base_dir}", file=sys.stderr)
        
        # 检查常见路径 - 全部使用绝对路径
        common_paths = [
            os.path.join(base_dir, 'bin', 'stockfish'),        # 项目的bin目录
            os.path.join(base_dir, 'stockfish', 'stockfish'),  # 项目的stockfish目录
            '/opt/render/project/src/bin/stockfish',           # Render环境中的项目路径
            '/usr/games/stockfish',                             # Debian/Ubuntu位置
            '/usr/bin/stockfish',                               # Linux常见位置
            '/usr/local/bin/stockfish',                         # macOS常见位置
            '/opt/homebrew/bin/stockfish',                      # macOS Homebrew
        ]
        
        # 打印所有路径以便调试
        print("\n检查以下绝对路径:", file=sys.stderr)
        for path in common_paths:
            print(f"  - {path}", file=sys.stderr)
        
        # 检查项目中的stockfish目录 - 使用绝对路径
        stockfish_dir = os.path.join(base_dir, 'stockfish')
        if os.path.exists(stockfish_dir):
            print(f"检查stockfish目录: {stockfish_dir}", file=sys.stderr)
            # 列出目录内容
            try:
                for root, dirs, files in os.walk(stockfish_dir):
                    for file in files:
                        if file.startswith('stockfish'):
                            full_path = os.path.join(root, file)
                            if os.access(full_path, os.X_OK):
                                print(f"在stockfish目录中找到可执行文件: {full_path}", file=sys.stderr)
                                return full_path
            except Exception as e:
                print(f"遍历stockfish目录时出错: {e}", file=sys.stderr)
        
        # 尝试常见路径
        for path in common_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path
        
        # 尝试使用which命令 - 确保返回的是绝对路径
        try:
            print("尝试使用which命令查找stockfish", file=sys.stderr)
            result = subprocess.run(['which', 'stockfish'], capture_output=True, text=True)
            if result.returncode == 0:
                path = result.stdout.strip()
                if os.path.isabs(path):
                    print(f"which命令找到Stockfish: {path}", file=sys.stderr)
                    return path
                else:
                    print(f"which命令返回的不是绝对路径: {path}", file=sys.stderr)
        except Exception as e:
            print(f"执行which命令时出错: {e}", file=sys.stderr)
        
        return None
    
    def _configure_engine(self):
        """配置引擎参数"""
        # 设置UCI模式
        self._send_command("uci")
        
        # 设置技能等级和其他参数
        for name, value in self.parameters.items():
            self._send_command(f"setoption name {name} value {value}")
        
        # 准备就绪
        self._send_command("isready")
        self._read_output_until("readyok")
    
    def _send_command(self, command):
        """向引擎发送命令"""
        try:
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()
        except Exception as e:
            print(f"发送命令失败: {e}", file=sys.stderr)
    
    def _read_output_until(self, marker=None, timeout=5):
        """读取引擎输出直到遇到标记或超时"""
        output = []
        start_time = time.time()
        
        while True:
            if self.process.stdout.readable():
                line = self.process.stdout.readline().strip()
                if line:
                    output.append(line)
                    if marker and marker in line:
                        break
            
            if marker is None:
                break
                
            if time.time() - start_time > timeout:
                print(f"读取输出超时，未找到标记: {marker}", file=sys.stderr)
                break
            
            time.sleep(0.001)
        
        return output
    
    def set_position(self, fen=None, moves=None):
        """设置棋盘位置"""
        position_cmd = "position"
        
        if fen:
            position_cmd += f" fen {fen}"
        else:
            position_cmd += " startpos"
            
        if moves:
            position_cmd += f" moves {' '.join(moves)}"
            
        self._send_command(position_cmd)
    
    def get_best_move(self, time_limit=None):
        """获取最佳走法"""
        if time_limit:
            self._send_command(f"go movetime {time_limit}")
        else:
            self._send_command(f"go depth {self.depth}")
            
        output = self._read_output_until("bestmove")
        
        for line in output:
            if line.startswith("bestmove"):
                return line.split()[1]
        
        return None
    
    def set_skill_level(self, skill_level):
        """设置技能等级 (0-20)"""
        if not 0 <= skill_level <= 20:
            raise ValueError("技能等级必须在0-20之间")
            
        # Stockfish使用的参数
        self.parameters["Skill Level"] = skill_level
        self._send_command(f"setoption name Skill Level value {skill_level}")
    
    def get_evaluation(self):
        """获取当前局面的评估
        
        返回格式与原始Stockfish包兼容: {'type': 'cp', 'value': 12}
        """
        self._send_command("eval")
        output = self._read_output_until(None)
        
        # 默认评估
        evaluation = {'type': 'cp', 'value': 0}
        
        # 尝试从输出中解析评估值
        for line in output:
            if "Final evaluation" in line:
                try:
                    # 解析评估值，例如 "Final evaluation: +0.25 (white side)"
                    parts = line.split()
                    value_str = parts[2]
                    if value_str.startswith("+"):
                        value_str = value_str[1:]
                    value = float(value_str) * 100  # 转换为厘兵值
                    
                    if "(white side)" in line:
                        evaluation = {'type': 'cp', 'value': int(value)}
                    else:
                        evaluation = {'type': 'cp', 'value': -int(value)}
                    break
                except Exception as e:
                    print(f"解析评估值时出错: {e}", file=sys.stderr)
            elif "mate" in line.lower():
                try:
                    # 尝试解析将军步数
                    if "Mate in" in line:
                        mate_in = int(line.split("Mate in")[1].strip().split()[0])
                        evaluation = {'type': 'mate', 'value': mate_in}
                    break
                except Exception as e:
                    print(f"解析将军步数时出错: {e}", file=sys.stderr)
        
        return evaluation
    
    def quit(self):
        """关闭引擎"""
        if hasattr(self, 'process') and self.process:
            try:
                self._send_command("quit")
                self.process.terminate()
                self.process = None
            except:
                pass


# 简单测试
if __name__ == "__main__":
    try:
        engine = StockfishWrapper()
        print(f"Stockfish引擎路径: {engine.stockfish_path}")
        
        # 设置初始位置
        engine.set_position()
        
        # 获取最佳走法
        best_move = engine.get_best_move()
        print(f"最佳走法: {best_move}")
        
        # 关闭引擎
        engine.quit()
    except Exception as e:
        print(f"测试失败: {e}")
        sys.exit(1)
