import os
import sys
import traceback
from dotenv import load_dotenv          # 1️⃣
from flask import Flask, request, jsonify, send_from_directory
import chess
from stockfish import Stockfish
from openai import OpenAI
import asyncio
import get_id
import json
import time

# 加载 .env 文件中的环境变量
load_dotenv()                            # 2️⃣

app = Flask(__name__, static_folder='static', static_url_path='')

# 添加404错误处理
@app.errorhandler(404)
def not_found_error(error):
    return send_from_directory(app.static_folder, 'index.html')

# 初始化国际象棋棋盘和 Stockfish
board = chess.Board()

# 尝试加载stockfish引擎，根据不同系统路径进行适配
try:
    # 尝试不同可能的stockfish路径
    possible_stockfish_paths = [
        "./stockfish-macos-m1-apple-silicon",  # 原始路径
        "./stockfish",                          # 普通命名
        "/usr/local/bin/stockfish",             # 系统安装路径
        "/opt/homebrew/bin/stockfish",          # Homebrew安装路径
        "stockfish"                             # 如果在PATH中
    ]
    
    stockfish_path = None
    for path in possible_stockfish_paths:
        try:
            print(f"尝试加载Stockfish，路径: {path}", file=sys.stderr)
            stockfish = Stockfish(path=path)
            stockfish_path = path
            print(f"成功加载Stockfish，使用路径: {path}", file=sys.stderr)
            break
        except Exception as e:
            print(f"路径 {path} 加载失败: {e}", file=sys.stderr)
    
    if stockfish_path is None:
        # 如果所有路径都失败，尝试使用不带路径的初始化（依赖系统PATH）
        try:
            print("尝试不指定路径加载Stockfish", file=sys.stderr)
            stockfish = Stockfish()
            print("成功使用系统PATH加载Stockfish", file=sys.stderr)
        except Exception as e:
            print(f"无法加载Stockfish，尝试最后的备选方案: {e}", file=sys.stderr)
            # 最后的备选方案 - 抛出异常并提供安装指南
            raise FileNotFoundError("无法找到Stockfish引擎。请确保已安装Stockfish，并设置正确的路径。" + 
                                   "可以通过以下方式安装:\n" +
                                   "- Mac: brew install stockfish\n" +
                                   "- Linux: apt install stockfish\n" +
                                   "- 或从 https://stockfishchess.org/download/ 下载")
    
    # 设置难度等级
    stockfish.set_skill_level(5)
except Exception as e:
    print(f"严重错误：Stockfish初始化失败: {e}", file=sys.stderr)
    print("程序将退出。请安装Stockfish并重试。", file=sys.stderr)
    sys.exit(1)

# 添加棋局状态变量，用于控制特殊规则
# 'A': 兵可以斜着走一格, 'B': 象可以走直线一格, 'C': 棋子有50%几率随机移动, 'D': 玩家特殊棋子被吃掉后敌方有50%几率消失, 'E': 玩家棋子被吃掉后敌方有99%几率被冻结一回合, 'F': 玩家的车/象/马吃掉敌方棋子后有50%几率连续走棋, 'G': 玩家的车/象/马吃掉敌方的兵/车/象/马后有99%几率将其变为己方棋子并随机重生, 'normal': 常规规则
chess_variant_state = 'normal'

# 添加随机走动概率配置
random_move_probability = 0.5  # 默认概率

# 根据Twitter用户评级设置的随机走动概率层级
rank_probability_map = {
    'A': 0.0,    # 1级：0%
    'B': 0.1,    # 2级：10%
    'C': 0.2,    # 3级：20%
    'D': 0.25,    # 4级：30%
    'E': 0.30,    # 5级：40%
    'F': 0.37,    # 6级：50%
    'G': 0.38   # G级默认使用50%概率
}

# 添加跟踪被冻结棋子的变量
frozen_piece_square = None  # 存储被冻结棋子的坐标

# 添加当前回合是否是连续走棋触发的额外回合标志
is_bonus_move_round = False

# 记录获得连续走棋机会的特定棋子位置
bonus_move_piece_square = None

# 添加当前比赛信息
current_match_info = {
    'twitter_user': '',
    'user_rank': '',
    'random_move_probability': random_move_probability,
    'random_move_level': 0
}

# 从环境变量读取 OpenAI Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not set. Please set it in your shell or .env file.", file=sys.stderr)
    sys.exit(1)

# 初始化 OpenAI 客户端
# client = OpenAI(api_key=api_key)        # 3️⃣

# 添加变体G的计数器，记录触发次数
variant_g_transform_count = 0
# 最大转化次数限制
variant_g_max_transforms = 3

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/set_level', methods=['POST'])
def set_level():
    data = request.get_json() or {}
    lvl = int(data.get('level', 5))
    stockfish.set_skill_level(lvl)
    return jsonify({'status': 'ok', 'level': lvl})


@app.route('/set_side', methods=['POST'])
def set_side():
    global board, chess_variant_state, random_move_probability, current_match_info, frozen_piece_square, is_bonus_move_round, bonus_move_piece_square, variant_g_transform_count
    data = request.get_json() or {}
    side = data.get('side', 'white')
    # 设置变体状态
    chess_variant_state = data.get('variant_state', 'normal')
    print(f"设置棋局状态为: {chess_variant_state}", file=sys.stderr)
    
    # 重置被冻结棋子状态
    frozen_piece_square = None
    
    # 重置额外回合标志
    is_bonus_move_round = False
    
    # 重置获得连续走棋机会的棋子位置
    bonus_move_piece_square = None
    
    # 重置变体G的转换计数器
    variant_g_transform_count = 0
    
    # 处理Twitter用户信息
    twitter_user = data.get('twitter_user', '')
    match_info = {}
    
    if twitter_user:
        print(f"收到比赛请求，Twitter用户: {twitter_user}", file=sys.stderr)
        # 从保存的用户数据中获取更多信息
        try:
            save_path = f"twitter_data_{twitter_user}.json"
            if os.path.exists(save_path):
                with open(save_path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                
                # 获取用户评级
                user_rank = user_data.get('user_rank', 'G')
                
                # 根据用户评级设置随机走动概率
                if user_rank in rank_probability_map:
                    # 更新全局随机走动概率
                    random_move_probability = rank_probability_map[user_rank]
                    
                    # 确定随机走动的级别
                    if random_move_probability == 0.0:
                        random_move_level = 1
                    elif random_move_probability == 0.1:
                        random_move_level = 2
                    elif random_move_probability == 0.2:
                        random_move_level = 3
                    elif random_move_probability == 0.25:
                        random_move_level = 4
                    elif random_move_probability == 0.3:
                        random_move_level = 5
                    elif random_move_probability == 0.37:
                        random_move_level = 6
                    else:
                        random_move_level = 0
                    
                    print(f"根据用户评级 {user_rank} 设置随机走动概率为: {random_move_probability * 100}% (级别 {random_move_level})", file=sys.stderr)
                else:
                    print(f"未知用户评级 {user_rank}，使用默认随机走动概率: {random_move_probability * 100}%", file=sys.stderr)
                    random_move_level = 0
                
                match_info = {
                    'twitter_user': twitter_user,
                    'player_name': user_data.get('name', twitter_user),
                    'user_rank': user_rank,
                    'followers_count': user_data.get('followers_count', 0),
                    'match_start_time': time.time(),
                    'variant': chess_variant_state,
                    'player_side': side,
                    'random_move_probability': random_move_probability,
                    'random_move_level': random_move_level
                }
                
                # 更新当前比赛信息
                current_match_info = match_info.copy()
                
                # 保存比赛信息
                match_path = f"match_data_{twitter_user}_{int(time.time())}.json"
                with open(match_path, "w", encoding="utf-8") as f:
                    json.dump(match_info, f, indent=2, ensure_ascii=False)
                print(f"比赛信息已保存到 {match_path}", file=sys.stderr)
        except Exception as e:
            print(f"保存比赛信息失败: {e}", file=sys.stderr)
            traceback.print_exc()
    
    board.reset()
    if side == 'black':
        # 为变体F做特殊初始化
        if chess_variant_state == 'F':
            print(f"黑方选择了变体F - 执行特殊初始化", file=sys.stderr)
            # 确保需要的变量都已初始化
            is_bonus_move_round = False
            bonus_move_piece_square = None
            
        stockfish.set_fen_position(board.fen())
        ai_move = stockfish.get_best_move()
        
        # 防御性检查：确保AI移动有效
        if not ai_move:
            print(f"警告: AI没有返回有效走法", file=sys.stderr)
            # 返回基本响应
            response = {
                'status': 'ok',
                'fen': board.fen(),
                'variant_state': chess_variant_state,
                'error': 'AI没有返回有效走法'
            }
            if match_info:
                response['match_info'] = match_info
            return jsonify(response)
        
        try:
            # 安全执行AI走法
            board.push_uci(ai_move)
            stockfish.set_fen_position(board.fen())
            evaluation = stockfish.get_evaluation()
            
            response = {
                'status': 'ok',
                'fen': board.fen(),
                'ai_move': ai_move,
                'evaluation': evaluation,
                'variant_state': chess_variant_state
            }
            
            # 添加比赛信息到响应中
            if match_info:
                response['match_info'] = match_info
                
            return jsonify(response)
        except Exception as e:
            # 处理可能发生的异常
            print(f"AI走棋错误: {e}", file=sys.stderr)
            traceback.print_exc()
            
            # 重置棋盘并返回错误信息
            board.reset()
            response = {
                'status': 'error',
                'message': f'AI走棋错误: {str(e)}',
                'fen': board.fen(),
                'variant_state': chess_variant_state
            }
            
            if match_info:
                response['match_info'] = match_info
                
            return jsonify(response)
    
    response = {
        'status': 'ok', 
        'fen': board.fen(),
        'variant_state': chess_variant_state
    }
    
    # 添加比赛信息到响应中
    if match_info:
        response['match_info'] = match_info
        
    return jsonify(response)


@app.route('/set_variant_state', methods=['POST'])
def set_variant_state():
    """设置国际象棋变体状态"""
    global chess_variant_state
    data = request.get_json() or {}
    state = data.get('state', 'normal')
    # 注意：变体C已经成为底层架构，不再作为独立变体提供
    available_states = ['A', 'B', 'D', 'E', 'F', 'G', 'normal']
    if state in available_states:
        chess_variant_state = state
        return jsonify({
            'status': 'ok',
            'variant_state': chess_variant_state,
            'message': f'棋局状态已设置为: {chess_variant_state}'
        })
    elif state == 'C':
        # 如果用户选择了原C变体，提示它现在是系统底层功能
        return jsonify({
            'status': 'info',
            'variant_state': 'normal',
            'message': '随机走位功能现已成为游戏的底层机制，应用于所有变体。已自动设置为标准模式。'
        })
    return jsonify({
        'status': 'error',
        'message': f'不支持的状态: {state}'
    })


@app.route('/get_variant_state', methods=['GET'])
def get_variant_state():
    """获取当前国际象棋变体状态"""
    return jsonify({
        'status': 'ok',
        'variant_state': chess_variant_state
    })


@app.route('/move', methods=['POST'])
def move():
    global board, chess_variant_state, frozen_piece_square, is_bonus_move_round, bonus_move_piece_square, variant_g_transform_count
    data = request.get_json() or {}
    move_uci = data.get('move', '')
    variant_move = data.get('variant_move', False)  # 标记是否为变体特殊走法
    
    # 处理特殊情况：前端传来position标记和FEN，表示直接从这个位置计算AI的下一步走法
    if move_uci == 'position' and 'fen' in data:
        fen = data.get('fen')
        try:
            # 直接从传来的FEN设置棋盘状态
            board.set_fen(fen)
            # AI应答
            stockfish.set_fen_position(board.fen())
            ai_move = stockfish.get_best_move()
            board.push_uci(ai_move)
            # 评估
            stockfish.set_fen_position(board.fen())
            evaluation = stockfish.get_evaluation()
            
            return jsonify({
                'status': 'success',
                'fen': board.fen(),
                'ai_move': ai_move,
                'evaluation': evaluation,
                'variant_state': chess_variant_state
            })
        except Exception as e:
            print(f"Error processing position: {e}", file=sys.stderr)
            return jsonify({
                'status': 'error', 
                'error': str(e),
                'variant_state': chess_variant_state
            })
    
    # 处理特殊变体走法
    if variant_move:
        try:
            from_square = move_uci[:2]
            to_square = move_uci[2:4]
            
            print(f"收到特殊变体走法请求: {from_square} -> {to_square}, 当前变体状态: {chess_variant_state}", file=sys.stderr)
            
            # 解析棋子位置
            from_row = int(from_square[1]) - 1
            from_col = ord(from_square[0]) - ord('a')
            to_row = int(to_square[1]) - 1
            to_col = ord(to_square[0]) - ord('a')
            
            print(f"解析后的位置信息 - 起始: [{from_col},{from_row}], 目标: [{to_col},{to_row}]", file=sys.stderr)
            
            # 获取棋子
            piece = board.piece_at(chess.square(from_col, from_row))
            
            if not piece:
                print(f"起始位置没有棋子", file=sys.stderr)
                return jsonify({'status': 'invalid', 'message': '起始位置没有棋子'})
            
            print(f"棋子信息: 类型={piece.piece_type}, 颜色={piece.color}", file=sys.stderr)
            
            # 初始化player_is_white变量，用于后续逻辑
            player_is_white = piece.color == chess.WHITE
            
            # 判断是否符合变体规则
            valid_move = False
            
            # A状态: 兵可以斜着走一格
            if chess_variant_state == 'A' and piece.piece_type == chess.PAWN:
                print(f"检查变体A规则(兵可斜走)", file=sys.stderr)
                # 检查是否是斜线走法 (列差为1)
                if abs(from_col - to_col) == 1:
                    print(f"列差为1，符合斜走条件", file=sys.stderr)
                    # 白兵向上走，黑兵向下走
                    if (piece.color == chess.WHITE and to_row == from_row + 1) or \
                       (piece.color == chess.BLACK and to_row == from_row - 1):
                        print(f"行走方向正确", file=sys.stderr)
                        # 确保目标位置为空
                        target_piece = board.piece_at(chess.square(to_col, to_row))
                        if not target_piece:
                            print(f"目标位置为空，符合变体A规则", file=sys.stderr)
                            valid_move = True
                        else:
                            print(f"目标位置不为空，不符合变体规则", file=sys.stderr)
                    else:
                        print(f"行走方向不正确", file=sys.stderr)
                else:
                    print(f"列差不为1，不符合斜走条件", file=sys.stderr)
            
            # B状态: 象可以走直线一格
            elif chess_variant_state == 'B' and piece.piece_type == chess.BISHOP:
                print(f"检查变体B规则(象可直走)", file=sys.stderr)
                # 检查是否是直线走法 (行差为1且列差为0，或列差为1且行差为0)
                if (abs(from_row - to_row) == 1 and from_col == to_col) or \
                   (abs(from_col - to_col) == 1 and from_row == to_row):
                    print(f"符合直走条件", file=sys.stderr)
                    # 确保目标位置为空
                    target_piece = board.piece_at(chess.square(to_col, to_row))
                    if not target_piece:
                        print(f"目标位置为空，符合变体B规则", file=sys.stderr)
                        valid_move = True
                    else:
                        print(f"目标位置不为空，不符合变体规则", file=sys.stderr)
                else:
                    print(f"不符合直走条件", file=sys.stderr)
            
            # C状态: 对于任何棋子，50%几率随机移动到一个不同的位置
            elif chess_variant_state == 'C':
                import random
                print(f"检查C状态变体规则(随机走法)", file=sys.stderr)
                
                # 首先检查原始移动是否合法（在旧的规则下）
                # 创建一个标准移动对象
                try:
                    standard_move = chess.Move(
                        from_square=chess.square(from_col, from_row),
                        to_square=chess.square(to_col, to_row)
                    )
                    
                    print(f"C状态原始移动: {standard_move.uci()}", file=sys.stderr)
                    
                    # 检查移动是否合法
                    if standard_move in board.legal_moves:
                        print(f"C状态: 原始移动合法", file=sys.stderr)
                        valid_move = True
                        
                        # 50%几率触发随机移动
                        random_chance = random.random()
                        print(f"C状态随机数值: {random_chance}", file=sys.stderr)
                        
                        if random_chance < 0.5:
                            print(f"C状态: 触发随机移动", file=sys.stderr)
                            
                            # 获取所有从当前起始位置可能的合法移动
                            from_square = chess.square(from_col, from_row)
                            legal_moves = [move for move in board.legal_moves if move.from_square == from_square]
                            print(f"C状态: 该棋子的所有合法走法数量: {len(legal_moves)}", file=sys.stderr)
                            for lm in legal_moves:
                                print(f"  合法走法: {lm.uci()}", file=sys.stderr)
                            
                            # 排除原始移动
                            other_moves = [move for move in legal_moves if move != standard_move]
                            print(f"C状态: 排除原走法后的其他走法数量: {len(other_moves)}", file=sys.stderr)
                            
                            if other_moves:
                                # 随机选择一个不同的目标位置
                                random_move = random.choice(other_moves)
                                random_to_square = random_move.to_square
                                random_to_col = chess.square_file(random_to_square)
                                random_to_row = chess.square_rank(random_to_square)
                                
                                print(f"C状态: 随机选择新位置 [{random_to_col},{random_to_row}]", file=sys.stderr)
                                print(f"C状态: 随机走法 {random_move.uci()}", file=sys.stderr)
                                
                                # 更新目标位置
                                to_col = random_to_col
                                to_row = random_to_row
                                to_square = chess.square_name(random_to_square)
                                
                                print(f"C状态: 目标位置更新为 {to_square}", file=sys.stderr)
                            else:
                                print(f"C状态: 没有其他合法走法可供随机选择，使用原始走法", file=sys.stderr)
                        else:
                            print(f"C状态: 未触发随机走法机制，使用原始走法", file=sys.stderr)
                    else:
                        print(f"C状态: 原始移动不合法", file=sys.stderr)
                        valid_move = False
                except Exception as e:
                    print(f"C状态处理错误: {e}", file=sys.stderr)
                    traceback.print_exc()
                    valid_move = False
            
            else:
                print(f"当前状态或棋子类型不符合特殊变体规则", file=sys.stderr)
            
            if valid_move:
                print(f"特殊变体走法验证通过，执行走法", file=sys.stderr)
                
                # 创建FEN，手动执行走法
                current_fen = board.fen()
                print(f"当前FEN(走法前): {current_fen}", file=sys.stderr)
                
                # 获取当前局面的FEN信息
                fen_parts = current_fen.split(' ')
                board_state = fen_parts[0]  # 棋盘状态部分
                
                # 手动移动棋子
                print(f"移动棋子: {from_square} -> {to_square}", file=sys.stderr)
                board.remove_piece_at(chess.square(from_col, from_row))
                board.set_piece_at(chess.square(to_col, to_row), piece)
                
                # 生成新的棋盘状态FEN
                player_move_fen = board.fen().split(' ')[0]
                print(f"移动后棋盘状态: {player_move_fen}", file=sys.stderr)
                
                # 更新回合
                active_color = 'b' if fen_parts[1] == 'w' else 'w'
                castling_rights = fen_parts[2]
                en_passant = '-'  # 特殊走法不涉及吃过路兵
                halfmove_clock = str(int(fen_parts[4]) + 1)
                fullmove_number = fen_parts[5]
                if active_color == 'w':  # 如果轮到白方，说明已经完成一个完整回合
                    fullmove_number = str(int(fullmove_number) + 1)
                
                # 创建玩家走法后的完整FEN
                player_move_complete_fen = f"{player_move_fen} {active_color} {castling_rights} {en_passant} {halfmove_clock} {fullmove_number}"
                print(f"玩家走法后的完整FEN: {player_move_complete_fen}", file=sys.stderr)
                
                # 设置棋盘状态为玩家走法后的状态
                board.set_fen(player_move_complete_fen)
                
                # AI应答 - 获取最佳走法
                print(f"设置Stockfish位置并计算AI应答", file=sys.stderr)
                stockfish.set_fen_position(player_move_complete_fen)
                ai_move = stockfish.get_best_move()
                print(f"AI走法: {ai_move}", file=sys.stderr)
                
                # 手动执行AI走法
                try:
                    # 解析AI走法坐标
                    ai_from_square = ai_move[:2]
                    ai_to_square = ai_move[2:4]
                    
                    ai_from_col = ord(ai_from_square[0]) - ord('a')
                    ai_from_row = int(ai_from_square[1]) - 1
                    ai_to_col = ord(ai_to_square[0]) - ord('a')
                    ai_to_row = int(ai_to_square[1]) - 1
                    
                    # 获取AI要移动的棋子
                    ai_piece = board.piece_at(chess.square(ai_from_col, ai_from_row))
                    if not ai_piece:
                        raise Exception(f"AI走法错误: 起始位置 {ai_from_square} 没有棋子")
                    
                    # 记录被吃的棋子(如果有)
                    captured_piece = board.piece_at(chess.square(ai_to_col, ai_to_row))
                    if captured_piece:
                        print(f"AI吃子: 在 {ai_to_square} 吃掉了 {captured_piece.symbol()}", file=sys.stderr)
                    
                    # 移动AI棋子
                    board.remove_piece_at(chess.square(ai_from_col, ai_from_row))
                    board.set_piece_at(chess.square(ai_to_col, ai_to_row), ai_piece)
                    
                    # 生成新的棋盘状态FEN
                    ai_move_fen = board.fen().split(' ')[0]
                    print(f"AI移动后棋盘状态: {ai_move_fen}", file=sys.stderr)
                    
                    # 更新回合
                    active_color = 'b' if active_color == 'w' else 'w'
                    halfmove_clock = str(int(halfmove_clock) + 1)
                    if active_color == 'w':
                        fullmove_number = str(int(fullmove_number) + 1)
                    
                    # 创建AI走法后的完整FEN
                    final_fen = f"{ai_move_fen} {active_color} {castling_rights} {en_passant} {halfmove_clock} {fullmove_number}"
                    print(f"AI走法后的完整FEN: {final_fen}", file=sys.stderr)
                    
                    # 设置最终的棋盘状态
                    board.set_fen(final_fen)
                    print(f"AI走法执行成功", file=sys.stderr)
                    
                except Exception as e:
                    print(f"AI走法执行错误: {str(e)}", file=sys.stderr)
                    traceback.print_exc()
                    # 如果手动执行AI走法失败，尝试使用chess库的方法
                    # 但是先保存玩家走法的结果
                    saved_player_move_fen = player_move_fen
                    
                    # 重置棋盘到玩家走法后的状态
                    board.set_fen(player_move_complete_fen)
                    # 尝试使用库方法执行AI走法
                    try:
                        board.push_uci(ai_move)
                        print(f"使用库方法执行AI走法成功", file=sys.stderr)
                    except Exception as e2:
                        print(f"库方法执行AI走法也失败: {str(e2)}", file=sys.stderr)
                        # 如果还是失败，至少保留玩家的走法
                        board.set_fen(player_move_complete_fen)
                
                # 评估最终局面
                stockfish.set_fen_position(board.fen())
                evaluation = stockfish.get_evaluation()
                
                response = {
                    'status': 'success',
                    'fen': board.fen(),
                    'ai_move': ai_move,
                    'evaluation': evaluation,
                    'variant_state': chess_variant_state,
                    'message': '特殊变体走法成功'
                }
                
                # 如果是C状态且应用了随机走法，添加标记
                if chess_variant_state == 'C' and to_square != move_uci[2:4]:
                    original_to = move_uci[2:4]
                    actual_to = to_square
                    
                    print(f"添加C状态随机走法信息: 原目标 {original_to}, 实际目标 {actual_to}", file=sys.stderr)
                    
                    response['random_move_applied'] = True
                    response['original_move'] = from_square + original_to
                    response['actual_move'] = from_square + actual_to
                    response['random_move_msg'] = f"随机走法已触发! 棋子移动到了 {actual_to} 而不是玩家选择的目标位置 {original_to}"
                    
                    print(f"随机走法响应信息: {response['random_move_msg']}", file=sys.stderr)
                
                return jsonify(response)
            else:
                print(f"特殊变体走法验证失败", file=sys.stderr)
                return jsonify({
                    'status': 'invalid', 
                    'message': '不符合当前变体规则的走法'
                })
                
        except Exception as e:
            print(f"Error processing variant move: {e}", file=sys.stderr)
            traceback.print_exc()
            return jsonify({
                'status': 'error', 
                'error': str(e),
                'variant_state': chess_variant_state
            })
    
    # 常规走法处理
    try:
        move_obj = chess.Move.from_uci(move_uci)
    except:
        return jsonify({'status': 'invalid'})
    if move_obj not in board.legal_moves:
        return jsonify({'status': 'invalid'})

    # 确定玩家是白方还是黑方
    player_is_white = board.turn == chess.WHITE
    
    # 记录玩家移动前的棋盘状态和目标位置可能存在的AI棋子
    target_square = move_obj.to_square
    from_square = move_obj.from_square
    captured_piece_before_move = board.piece_at(target_square)
    moving_piece = board.piece_at(from_square)
    
    # 变体G: 记录吃子前的信息，用于后面处理变体G的逻辑
    variant_g_triggered = False
    variant_g_captured_piece = None
    variant_g_captured_piece_type = None
    variant_g_msg = ""
    
    if chess_variant_state == 'G' and captured_piece_before_move:
        # 检查是否是玩家的超特殊棋子（车、骑士、象）吃掉敌方较特殊棋子（兵、车、骑士、象）
        is_player_piece = (player_is_white and moving_piece.color == chess.WHITE) or \
                          (not player_is_white and moving_piece.color == chess.BLACK)
        is_special_attacker = moving_piece.piece_type in [chess.ROOK, chess.KNIGHT, chess.BISHOP]
        is_special_target = captured_piece_before_move.piece_type in [chess.PAWN, chess.ROOK, chess.KNIGHT, chess.BISHOP]
        is_enemy_piece = (player_is_white and captured_piece_before_move.color == chess.BLACK) or \
                         (not player_is_white and captured_piece_before_move.color == chess.WHITE)
        
        # 判断是否符合变体G的触发条件
        if is_player_piece and is_special_attacker and is_special_target and is_enemy_piece and variant_g_transform_count < variant_g_max_transforms:
            print(f"变体G: 玩家的特殊棋子吃掉了敌方较特殊棋子", file=sys.stderr)
            print(f"变体G: 攻击棋子类型: {chess.piece_name(moving_piece.piece_type)}, 被吃棋子类型: {chess.piece_name(captured_piece_before_move.piece_type)}", file=sys.stderr)
            
            # 99%概率触发棋子转换
            import random
            # 根据Twitter用户评级设置转换概率
            transform_probability = 0.0  # 默认为0%
            if current_match_info.get('user_rank') == 'A':
                transform_probability = 0.0  # A级：0%
            elif current_match_info.get('user_rank') == 'B':
                transform_probability = 0.15  # B级：5%
            elif current_match_info.get('user_rank') == 'C':
                transform_probability = 0.18  # C级：10%
            elif current_match_info.get('user_rank') == 'D':
                transform_probability = 0.23  # D级：15%
            elif current_match_info.get('user_rank') == 'E':
                transform_probability = 0.28 # E级：20%
            elif current_match_info.get('user_rank') == 'F':
                transform_probability = 0.35  # F级：30%
            elif current_match_info.get('user_rank') == 'G':
                transform_probability = 0.39  # G级：30%
            
            transform_chance = random.random()
            print(f"变体G: 棋子转换概率计算: {transform_chance} < {transform_probability} = {transform_chance < transform_probability}", file=sys.stderr)
            
            if transform_chance < transform_probability:
                print(f"变体G: 棋子转换效果触发!", file=sys.stderr)
                
                # 保存被吃的棋子信息用于后续处理
                variant_g_triggered = True
                variant_g_captured_piece = captured_piece_before_move
                variant_g_captured_piece_type = captured_piece_before_move.piece_type
                
                # 增加变体G触发计数
                variant_g_transform_count += 1
                print(f"变体G: 已触发 {variant_g_transform_count}/{variant_g_max_transforms} 次", file=sys.stderr)
    
    # 随机走位机制（原变体C）- 现在应用于所有变体
    original_move = move_obj
    random_move_applied = False
    random_move_msg = ""
    
    # 将原C变体的随机走位逻辑应用到所有变体中
    import random
    print(f"检查随机走位机制 - 当前走法 {move_uci}", file=sys.stderr)
    print(f"当前随机走动概率: {random_move_probability * 100}%", file=sys.stderr)
    
    # 使用全局设置的随机走动概率
    random_chance = random.random()
    print(f"随机数值: {random_chance}", file=sys.stderr)
    
    if random_chance < random_move_probability:
        print(f"触发随机走法条件（<{random_move_probability}）满足", file=sys.stderr)
        # 获取所有从当前棋子出发的合法走法
        from_square = chess.parse_square(move_uci[:2])
        piece = board.piece_at(from_square)
        
        if piece:
            print(f"找到起始位置棋子: {piece.symbol()} 在 {move_uci[:2]}", file=sys.stderr)
            # 找出该棋子的所有合法走法
            legal_moves = [move for move in board.legal_moves if move.from_square == from_square]
            print(f"该棋子的所有合法走法数量: {len(legal_moves)}", file=sys.stderr)
            for lm in legal_moves:
                print(f"  合法走法: {lm.uci()}", file=sys.stderr)
            
            # 如果有多个合法走法，排除玩家选择的走法，随机选择一个
            other_moves = [move for move in legal_moves if move != original_move]
            print(f"排除原走法后的其他走法数量: {len(other_moves)}", file=sys.stderr)
            
            if other_moves:
                # 随机选择一个走法
                move_obj = random.choice(other_moves)
                random_move_applied = True
                to_square_name = chess.square_name(move_obj.to_square)
                from_square_name = chess.square_name(move_obj.from_square)
                random_move_msg = f"随机走法已触发! 棋子从{from_square_name}移动到了{to_square_name}而不是玩家选择的{move_uci[2:4]}"
                print(f"随机走法触发成功: 原始走法 {move_uci}, 实际执行 {move_obj.uci()}", file=sys.stderr)
                print(f"随机走法信息: {random_move_msg}", file=sys.stderr)
            else:
                print(f"没有其他合法走法可供随机选择，使用原始走法", file=sys.stderr)
        else:
            print(f"起始位置没有找到棋子: {move_uci[:2]}", file=sys.stderr)
    else:
        print(f"未触发随机走法，使用原始走法 {move_uci}", file=sys.stderr)
    
    # 玩家落子
    print(f"最终执行的走法: {move_obj.uci()}", file=sys.stderr)
    
    board.push(move_obj)
    
    # AI 应答
    stockfish.set_fen_position(board.fen())
    
    # 检查是否有被冻结的棋子，如果变体状态为E且被冻结的棋子存在，则在AI走子前处理
    ai_piece_frozen = False
    frozen_piece_msg = ""
    
    # 如果有被冻结的棋子且变体状态为E，生成新的AI走法时需要避开被冻结的棋子
    if chess_variant_state == 'E' and frozen_piece_square is not None:
        print(f"变体E: 检测到被冻结的棋子在 {chess.square_name(frozen_piece_square)}", file=sys.stderr)
        
        # 获取所有合法走法
        legal_moves = list(board.legal_moves)
        
        # 过滤掉使用被冻结棋子的走法
        valid_moves = [move for move in legal_moves if move.from_square != frozen_piece_square]
        
        if valid_moves:
            # 如果还有其他合法走法，让stockfish从这些走法中选择
            # 创建一个临时棋盘来测试最佳走法
            temp_board = chess.Board(board.fen())
            best_move = None
            best_score = float('-inf') if player_is_white else float('inf')
            
            for move in valid_moves:
                temp_board.set_fen(board.fen())
                temp_board.push(move)
                stockfish.set_fen_position(temp_board.fen())
                eval_result = stockfish.get_evaluation()
                
                current_score = 0
                if eval_result['type'] == 'cp':
                    current_score = eval_result['value'] / 100.0
                elif eval_result['type'] == 'mate':
                    current_score = 100 if eval_result['value'] > 0 else -100
                
                # 黑方(AI)寻找评分最低的走法，白方寻找评分最高的走法
                if (not player_is_white and current_score < best_score) or (player_is_white and current_score > best_score):
                    best_score = current_score
                    best_move = move
            
            if best_move:
                ai_move = best_move.uci()
                ai_piece_frozen = True
                frozen_piece_msg = f"AI的棋子在 {chess.square_name(frozen_piece_square)} 位置被冻结，无法移动！"
                print(f"变体E: AI选择了避开被冻结棋子的走法: {ai_move}", file=sys.stderr)
                
                # 记录AI走法前的状态
                pre_move_fen = board.fen()
                pre_move_turn = board.turn
                print(f"变体E: AI走法前状态 - FEN: {pre_move_fen}", file=sys.stderr)
                print(f"变体E: AI走法前回合 - {'白方' if pre_move_turn == chess.WHITE else '黑方'}", file=sys.stderr)
                
                # 执行走法
                try:
                    board.push_uci(ai_move)
                    print(f"变体E: AI走法后状态 - FEN: {board.fen()}", file=sys.stderr)
                    print(f"变体E: AI走法后回合 - {'白方' if board.turn == chess.WHITE else '黑方'}", file=sys.stderr)
                except Exception as e:
                    print(f"变体E: AI走法执行失败: {e}", file=sys.stderr)
                    traceback.print_exc()
                
                # 确保冻结的棋子被重置
                frozen_piece_square = None
                print(f"变体E: 重置被冻结棋子状态", file=sys.stderr)
                
            else:
                # 如果没有找到有效走法，可能是因为唯一的合法走法需要使用被冻结的棋子
                ai_move = stockfish.get_best_move()
                print(f"变体E: 没有找到避开被冻结棋子的走法，使用默认: {ai_move}", file=sys.stderr)
        else:
            # 如果没有有效走法了，只能使用被冻结的棋子
            ai_move = stockfish.get_best_move()
            print(f"变体E: 没有避开被冻结棋子的合法走法，使用默认: {ai_move}", file=sys.stderr)
        
        # 走完这一步后，重置被冻结的棋子状态
        print(f"变体E: 重置被冻结棋子状态", file=sys.stderr)
        frozen_piece_square = None
    else:
        # 正常获取AI走法
        ai_move = stockfish.get_best_move()
    
    # 解析AI走法
    ai_from_square = chess.parse_square(ai_move[:2])
    ai_to_square = chess.parse_square(ai_move[2:4])
    ai_piece = board.piece_at(ai_from_square)
    captured_by_ai = board.piece_at(ai_to_square)
    
    # 处理变体D: 当玩家特殊棋子被AI吃掉时，AI棋子有50%几率自爆
    ai_vanished = False
    vanish_msg = ""
    if chess_variant_state == 'D' and captured_by_ai:
        # 检查被AI吃掉的是否是玩家的特殊棋子(车、骑士、象、皇后)
        if ((player_is_white and captured_by_ai.color == chess.WHITE) or
            (not player_is_white and captured_by_ai.color == chess.BLACK)) and \
            captured_by_ai.piece_type in [chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.QUEEN]:
            
            print(f"变体D: AI吃掉了玩家的特殊棋子: {chess.piece_name(captured_by_ai.piece_type)}", file=sys.stderr)
            print(f"变体D: 玩家是白方: {player_is_white}, 被吃棋子颜色: {captured_by_ai.color}", file=sys.stderr)
            print(f"变体D: 被吃棋子类型: {chess.piece_name(captured_by_ai.piece_type)}", file=sys.stderr)
            
            # 保存被吃棋子的类型，防止执行AI走法后丢失信息
            captured_piece_type = captured_by_ai.piece_type
            captured_piece_name = chess.piece_name(captured_piece_type)
            
            # 50%的概率AI棋子自爆
            import random
            # 根据Twitter用户评级设置自爆概率
            vanish_probability = 0.0  # 默认为0%
            if current_match_info['user_rank'] == 'A':
                vanish_probability = 0.0  # A级：0%
            elif current_match_info['user_rank'] == 'B':
                vanish_probability = 0.15  # B级：5%
            elif current_match_info['user_rank'] == 'C':
                vanish_probability = 0.17  # C级：10%
            elif current_match_info['user_rank'] == 'D':
                vanish_probability = 0.20  # D级：15%
            elif current_match_info['user_rank'] == 'E':
                vanish_probability = 0.24  # E级：20%
            elif current_match_info['user_rank'] == 'F':
                vanish_probability = 0.35  # F级：30%
            elif current_match_info['user_rank'] == 'G':
                vanish_probability = 0.37  # G级：30%
            
            vanish_chance = random.random()
            print(f"变体D: 自爆概率计算: {vanish_chance} < {vanish_probability} = {vanish_chance < vanish_probability}", file=sys.stderr)
            
            if vanish_chance < vanish_probability:
                print(f"变体D: AI棋子自爆触发!", file=sys.stderr)
                ai_vanished = True
                
                # 执行AI走法（先吃掉玩家棋子）
                board.push_uci(ai_move)
                print(f"变体D: AI吃子后棋盘状态: {board.fen()}", file=sys.stderr)
                
                # 获取AI棋子的位置和类型（吃子后AI的棋子就在目标位置上）
                vanish_square = ai_to_square
                vanish_piece = board.piece_at(vanish_square)
                
                if vanish_piece:
                    vanish_piece_type = vanish_piece.piece_type
                    vanish_piece_name = chess.piece_name(vanish_piece_type)
                    
                    # 从棋盘上移除AI棋子（自爆效果）
                    board.remove_piece_at(vanish_square)
                    print(f"变体D: AI棋子在{chess.square_name(vanish_square)}位置自爆，已移除", file=sys.stderr)
                    
                    # 创建提示信息
                    vanish_msg = f"报应！AI的{vanish_piece_name}吃掉了您的{captured_piece_name}后发生自爆！"
                    print(f"变体D: {vanish_msg}", file=sys.stderr)
                else:
                    print(f"变体D: 错误 - 在{chess.square_name(vanish_square)}位置没有找到AI棋子", file=sys.stderr)
                    # 尝试恢复棋盘状态
                    ai_vanished = False
                    
            else:
                print(f"变体D: AI棋子幸运地避免了自爆(50%概率)", file=sys.stderr)
                # AI棋子没有自爆，正常执行走法
                board.push_uci(ai_move)
                print(f"变体D: 正常执行AI走法: {ai_move}", file=sys.stderr)
                ai_vanished = False
        else:
            # 不符合特殊棋子条件，不触发自爆
            print(f"变体D: 被吃的棋子不是玩家的特殊棋子，不触发自爆效果", file=sys.stderr)
    elif chess_variant_state == 'D':
        print(f"变体D: AI没有吃子，不触发自爆效果", file=sys.stderr)
    
    # 处理变体E: 当玩家棋子被AI吃掉时，AI棋子有99%概率被冻结一回合
    ai_freezes_applied = False
    if chess_variant_state == 'E' and captured_by_ai:
        # 检查被AI吃掉的是否是玩家的棋子(包括兵、车、骑士、象、皇后)
        if ((player_is_white and captured_by_ai.color == chess.WHITE) or
            (not player_is_white and captured_by_ai.color == chess.BLACK)):
            
            print(f"变体E: AI吃掉了玩家的棋子: {chess.piece_name(captured_by_ai.piece_type)}", file=sys.stderr)
            print(f"变体E: 吃子前棋盘状态FEN: {board.fen()}", file=sys.stderr)
            print(f"变体E: 玩家是白方: {player_is_white}, 被吃棋子颜色: {captured_by_ai.color}", file=sys.stderr)
            
            # 99%的概率AI棋子被冻结一回合
            import random
            # 根据Twitter用户评级设置冻结概率
            freeze_probability = 0.0  # 默认为0%
            if current_match_info.get('user_rank') == 'A':
                freeze_probability = 0.0  # A级：0%
            elif current_match_info.get('user_rank') == 'B':
                freeze_probability = 0.17  # B级：5%
            elif current_match_info.get('user_rank') == 'C':
                freeze_probability = 0.25 # C级：10%
            elif current_match_info.get('user_rank') == 'D':
                freeze_probability = 0.30  # D级：15%
            elif current_match_info.get('user_rank') == 'E':
                freeze_probability = 0.35  # E级：20%
            elif current_match_info.get('user_rank') == 'F':
                freeze_probability = 0.45  # F级：30%
            elif current_match_info.get('user_rank') == 'G':
                freeze_probability = 0.47  # G级：30%
                
            freeze_chance = random.random()
            print(f"变体E: 冻结概率计算: {freeze_chance} < {freeze_probability} = {freeze_chance < freeze_probability}", file=sys.stderr)
            if freeze_chance < freeze_probability:
                print(f"变体E: AI棋子被冻结触发", file=sys.stderr)
                ai_freezes_applied = True
                
                # 记录被冻结的棋子位置(AI吃子后的位置)
                frozen_piece_square = ai_to_square
                
                print(f"变体E: 记录被冻结棋子位置 {chess.square_name(frozen_piece_square)}", file=sys.stderr)
            else:
                print(f"变体E: AI棋子幸运地避免了被冻结(1%概率)", file=sys.stderr)
    
    # 变体F: 玩家的特殊棋子(车、骑士、象)吃掉敌方棋子后有50%几率连续走棋
    player_bonus_move = False
    bonus_move_msg = ""
    
    # 判断刚才玩家是否完成了一次吃子操作，且吃子的是特殊棋子(车、骑士、象)
    if chess_variant_state == 'F' and captured_piece_before_move:
        piece_from_move = board.piece_at(move_obj.to_square)  # 移动后棋子的位置
        
        # 确保是玩家的棋子
        is_player_piece = (player_is_white and piece_from_move.color == chess.WHITE) or \
                         (not player_is_white and piece_from_move.color == chess.BLACK)
        
        # 检查是否是特殊棋子(车、骑士、象)
        is_special_piece = piece_from_move.piece_type in [chess.ROOK, chess.KNIGHT, chess.BISHOP]
        
        # 判断刚才移动的棋子是否是玩家的特殊棋子，并且当前不是额外回合
        if is_player_piece and is_special_piece and not is_bonus_move_round:
            print(f"变体F: 玩家的特殊棋子吃掉了对方棋子", file=sys.stderr)
            print(f"变体F: 棋子类型: {chess.piece_name(piece_from_move.piece_type)}", file=sys.stderr)
            
            # 50%概率触发连续走棋
            import random
            # 根据Twitter用户评级设置概率
            bonus_probability = 0.0  # 默认为0%
            if current_match_info.get('user_rank') == 'A':
                bonus_probability = 0.0  # A级：0%
            elif current_match_info.get('user_rank') == 'B':
                bonus_probability = 0.15  # B级：5%
            elif current_match_info.get('user_rank') == 'C':
                bonus_probability = 0.17  # C级：10%
            elif current_match_info.get('user_rank') == 'D':
                bonus_probability = 0.20  # D级：15%
            elif current_match_info.get('user_rank') == 'E':
                bonus_probability = 0.25  # E级：20%
            elif current_match_info.get('user_rank') == 'F':
                bonus_probability = 0.35  # F级：30%
            elif current_match_info.get('user_rank') == 'G':
                bonus_probability = 0.37  # G级：30%
            
            bonus_chance = random.random()
            print(f"变体F: 连续走棋概率计算: {bonus_chance} < {bonus_probability} = {bonus_chance < bonus_probability}", file=sys.stderr)
            
            if bonus_chance < bonus_probability:
                print(f"变体F: 连续走棋效果触发!", file=sys.stderr)
                player_bonus_move = True
                
                # 记录获得连续走棋机会的特定棋子位置
                bonus_move_piece_square = move_obj.to_square
                print(f"变体F: 记录获得连续走棋机会的棋子位置 {chess.square_name(bonus_move_piece_square)}", file=sys.stderr)
                
                # 创建提示信息
                piece_name = chess.piece_name(piece_from_move.piece_type)
                piece_position = chess.square_name(move_obj.to_square)
                bonus_move_msg = f"幸运! 您的{piece_name}在{piece_position}位置获得了一次额外的走棋机会! 只有这个{piece_name}可以移动。"
                
                # 标记当前是额外回合
                is_bonus_move_round = True
                
                # 如果AI已经走了棋，需要修改FEN来让玩家继续走
                if not ai_freezes_applied:  # 只有在变体E没有冻结棋子的情况下才需要修改回合
                    # 修改回合为玩家回合
                    fen_parts = board.fen().split(' ')
                    original_turn = fen_parts[1]
                    fen_parts[1] = 'w' if player_is_white else 'b'  # 设置回合为玩家
                    
                    # 重组并应用新的FEN
                    new_fen = ' '.join(fen_parts) 
                    print(f"变体F: 修改回合 - 原始: {original_turn}, 新的: {fen_parts[1]}", file=sys.stderr)
                    
                    board.set_fen(new_fen)
                    print(f"变体F: 回合修改后棋盘状态: {board.fen()}", file=sys.stderr)
                    print(f"变体F: 修改后当前回合: {'白方' if board.turn == chess.WHITE else '黑方'}", file=sys.stderr)
            else:
                print(f"变体F: 连续走棋效果未触发，正常进入AI回合", file=sys.stderr)
                # 在正常轮换后重置额外回合标志
                is_bonus_move_round = False
                bonus_move_piece_square = None
        else:
            if is_bonus_move_round:
                print(f"变体F: 当前是额外回合，不再触发连续走棋效果", file=sys.stderr)
            # 在正常轮换后重置额外回合标志
            is_bonus_move_round = False
            bonus_move_piece_square = None
    
    # 特殊处理变体E冻结棋子（此时AI已经吃掉玩家棋子并被冻结）
    if ai_freezes_applied:
        # 执行AI走法
        board.push_uci(ai_move)
        print(f"变体E: AI吃子后棋盘状态: {board.fen()}", file=sys.stderr)
        print(f"变体E: 当前回合: {'白方' if board.turn == chess.WHITE else '黑方'}", file=sys.stderr)
        
        # 修改回合为玩家回合
        fen_parts = board.fen().split(' ')
        original_turn = fen_parts[1]
        fen_parts[1] = 'w' if player_is_white else 'b'  # 设置回合为玩家
        
        # 重组并应用新的FEN
        new_fen = ' '.join(fen_parts) 
        print(f"变体E: 修改回合 - 原始: {original_turn}, 新的: {fen_parts[1]}", file=sys.stderr)
        
        board.set_fen(new_fen)
        print(f"变体E: 回合修改后棋盘状态: {board.fen()}", file=sys.stderr)
        print(f"变体E: 修改后当前回合: {'白方' if board.turn == chess.WHITE else '黑方'}", file=sys.stderr)
        
        # 添加更明确的提示信息
        frozen_piece_msg = f"AI的棋子在 {chess.square_name(frozen_piece_square)} 位置被冻结，无法移动！轮到您继续下棋。"
        
        print(f"变体E: AI吃子后棋子被冻结，回合返回给玩家，FEN: {new_fen}", file=sys.stderr)
    else:
        # 正常执行AI走法（变体D可能已经处理过了，所以只在未被处理时执行）
        ai_move_already_applied = False
        # 变体D可能已经执行了走法
        if chess_variant_state == 'D' and captured_by_ai:
            # 检查变体D是否已经执行了AI走法
            if ((player_is_white and captured_by_ai.color == chess.WHITE) or 
                (not player_is_white and captured_by_ai.color == chess.BLACK)) and \
                captured_by_ai.piece_type in [chess.ROOK, chess.KNIGHT, chess.BISHOP, chess.QUEEN]:
                ai_move_already_applied = True
        
        # 只有在变体D没有执行走法且没有处理被冻结棋子时才执行AI走法
        if not ai_move_already_applied and not ai_piece_frozen and not player_bonus_move and not ai_vanished:
            print(f"执行正常AI走法: {ai_move}, 当前FEN: {board.fen()}", file=sys.stderr)
            board.push_uci(ai_move)
            print(f"AI走法后棋盘状态: {board.fen()}", file=sys.stderr)
    
    # 处理变体G的棋子转换效果
    variant_g_new_piece_square = None
    if variant_g_triggered:
        # 创建玩家方颜色的新棋子
        player_color = chess.WHITE if player_is_white else chess.BLACK
        new_piece = chess.Piece(variant_g_captured_piece_type, player_color)
        
        # 找出棋盘上所有空格子
        empty_squares = []
        for sq in chess.SQUARES:
            if not board.piece_at(sq):
                empty_squares.append(sq)
        
        if empty_squares:
            # 随机选择一个空格子
            import random
            random_square = random.choice(empty_squares)
            variant_g_new_piece_square = random_square
            
            # 在随机格子上放置新棋子
            board.set_piece_at(random_square, new_piece)
            print(f"变体G: 在{chess.square_name(random_square)}位置放置了新的{chess.piece_name(new_piece.piece_type)}", file=sys.stderr)
            
            # 创建提示信息
            captured_piece_name = chess.piece_name(variant_g_captured_piece_type)
            new_square_name = chess.square_name(random_square)
            variant_g_msg = f"魔法转换! 敌方的{captured_piece_name}被转化为您的{captured_piece_name}，并重生在{new_square_name}位置！(已触发{variant_g_transform_count}/{variant_g_max_transforms}次)"
            
            print(f"变体G: {variant_g_msg}", file=sys.stderr)
    
    # 评估
    stockfish.set_fen_position(board.fen())
    evaluation = stockfish.get_evaluation()

    response = {
        'status': 'success',
        'fen': board.fen(),
        'ai_move': ai_move,
        'evaluation': evaluation,
        'variant_state': chess_variant_state
    }
    
    # 如果应用了随机走法，添加到响应中
    if random_move_applied:
        response['random_move_applied'] = True
        response['original_move'] = original_move.uci()
        response['actual_move'] = move_obj.uci()
        response['random_move_msg'] = random_move_msg
    
    # 如果变体E触发了冻结效果，添加相关信息
    if ai_freezes_applied:
        piece_name = chess.piece_name(captured_by_ai.piece_type)
        response['special_effect'] = 'frozen'
        response['special_effect_msg'] = frozen_piece_msg
        response['turn_override'] = True
        response['next_player'] = 'white' if board.turn == chess.WHITE else 'black'  # 添加明确的回合指示
        response['legal_moves_debug'] = [move.uci() for move in board.legal_moves]  # 添加合法走法列表
        print(f"变体E消息: {response.get('special_effect_msg')}", file=sys.stderr)
        print(f"变体E响应详情: 特效={response.get('special_effect')}, 当前FEN={response.get('fen')}", file=sys.stderr)
        print(f"变体E合法走法: {response.get('legal_moves_debug')}", file=sys.stderr)
    elif ai_piece_frozen:
        response['special_effect'] = 'frozen_move'
        response['special_effect_msg'] = frozen_piece_msg
        response['legal_moves_debug'] = [move.uci() for move in board.legal_moves]  # 添加合法走法列表
        response['next_player'] = 'white' if board.turn == chess.WHITE else 'black'  # 显式指示下一回合玩家
        print(f"变体E消息: {response.get('special_effect_msg')}", file=sys.stderr)
        print(f"变体E避开走法响应详情: 特效={response.get('special_effect')}, 当前FEN={response.get('fen')}", file=sys.stderr)
        print(f"变体E避开走法合法走法: {response.get('legal_moves_debug')}", file=sys.stderr)
    elif player_bonus_move:
        response['special_effect'] = 'bonus_move'
        response['special_effect_msg'] = bonus_move_msg
        response['turn_override'] = True
        response['next_player'] = 'white' if player_is_white else 'black'  # 添加明确的回合指示
        response['legal_moves_debug'] = [move.uci() for move in board.legal_moves]  # 添加合法走法列表
        
        # 添加获得连续走棋机会的棋子位置
        if bonus_move_piece_square is not None:
            response['bonus_move_piece'] = chess.square_name(bonus_move_piece_square)
        
        print(f"变体F消息: {response.get('special_effect_msg')}", file=sys.stderr)
        print(f"变体F响应详情: 特效={response.get('special_effect')}, 当前FEN={response.get('fen')}", file=sys.stderr)
        print(f"变体F合法走法: {response.get('legal_moves_debug')}", file=sys.stderr)
    elif ai_vanished:
        # 变体D触发自爆效果
        response['special_effect'] = 'vanish'
        response['special_effect_msg'] = vanish_msg
        print(f"变体D消息: {response.get('special_effect_msg')}", file=sys.stderr)
        print(f"变体D响应详情: 特效={response.get('special_effect')}, 当前FEN={response.get('fen')}", file=sys.stderr)
    else:
        # 如果没有触发任何特殊效果，在AI回合结束后重置额外回合标志
        is_bonus_move_round = False
        bonus_move_piece_square = None
    
    # 如果变体G触发了棋子转换效果，添加相关信息
    if variant_g_triggered and variant_g_new_piece_square is not None:
        response['special_effect'] = 'transform'
        response['special_effect_msg'] = variant_g_msg
        response['transform_piece_square'] = chess.square_name(variant_g_new_piece_square)
        response['transform_count'] = variant_g_transform_count
        response['transform_max'] = variant_g_max_transforms
        print(f"变体G响应详情: 特效={response.get('special_effect')}, 当前FEN={response.get('fen')}", file=sys.stderr)
    
    print(f"最终响应状态: {response.get('status')}, 当前FEN: {response.get('fen')}", file=sys.stderr)
    print(f"当前回合: {'白方' if board.turn == chess.WHITE else '黑方'}, 合法走法数量: {len(list(board.legal_moves))}", file=sys.stderr)
    
    return jsonify(response)


@app.route('/reset', methods=['GET'])
def reset():
    global board, chess_variant_state, frozen_piece_square, is_bonus_move_round, bonus_move_piece_square, variant_g_transform_count
    board.reset()
    # 重置被冻结棋子状态
    frozen_piece_square = None
    # 重置额外回合标志
    is_bonus_move_round = False
    # 重置获得连续走棋机会的棋子位置
    bonus_move_piece_square = None
    # 重置变体G的转换计数器
    variant_g_transform_count = 0
    return jsonify({
        'status': 'ok', 
        'fen': board.fen(),
        'variant_state': chess_variant_state
    })


@app.route('/commentary', methods=['POST'])
def commentary():
    data = request.get_json() or {}
    fen = data.get('fen', '')
    if not fen:
        return jsonify({'text': 'No position provided.'}), 400

    prompt = f"""You are a friendly chess commentator. The current position in FEN is:
{fen}

Please give a brief, fun commentary (1–2 sentences) about the position,
mentioning whose initiative it is, any tactical motifs or plans,
and keep it lighthearted."""

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a chess commentator."},
                {"role": "user",   "content": prompt}
            ],
            temperature=0.8,
            max_tokens=60,
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI Commentary Error:", e, file=sys.stderr)
        traceback.print_exc()
        text = "Commentary service error."
    return jsonify({'text': text})

@app.route('/api/twitter_profile/<username>')
async def get_twitter_profile(username):
    try:
        user_data = await get_id.get_twitter_user_id(username)
        if not user_data or 'data' not in user_data:
            return jsonify({'error': '无法获取用户信息'})
        
        return jsonify(user_data)
    except Exception as e:
        print(f"Twitter profile error: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/twitter_info')
def twitter_info():
    username = request.args.get('username')
    if not username:
        return jsonify({'status': 'error', 'error': '请提供Twitter用户名'})
    
    try:
        user_data = asyncio.run(get_id.get_twitter_user_id(username))
        
        # 调试信息
        print(f"Twitter API Response for {username}:", file=sys.stderr)
        print(json.dumps(user_data, indent=2), file=sys.stderr)
        
        # 提取有用的数据并保存到文件
        useful_data = {}
        user_rank = None  # 初始化用户评级变量
        sm_rank = None    # 初始化S/M评级变量
        ab_rank = None    # 初始化A1/B2评级变量

        if 'data' in user_data and 'user' in user_data['data'] and 'result' in user_data['data']['user']:
            result = user_data['data']['user']['result']
            if 'legacy' in result:
                legacy = result['legacy']
                # 只存储有用的字段
                useful_data = {
                    'name': legacy.get('name', ''),
                    'screen_name': legacy.get('screen_name', ''),
                    'description': legacy.get('description', ''),
                    'followers_count': legacy.get('followers_count', 0),
                    'friends_count': legacy.get('friends_count', 0),
                    'statuses_count': legacy.get('statuses_count', 0),
                    'favourites_count': legacy.get('favourites_count', 0),
                    'media_count': legacy.get('media_count', 0),
                    'profile_image_url_https': legacy.get('profile_image_url_https', ''),
                    'created_at': legacy.get('created_at', ''),
                    'location': legacy.get('location', ''),
                    'verified': legacy.get('verified', False)
                }
                
                # 计算S/M评级
                followers_count = legacy.get('followers_count', 0)
                statuses_count = legacy.get('statuses_count', 0)
                
                # 防止除以零错误
                if followers_count > 0:
                    status_follower_ratio = statuses_count / followers_count
                    if status_follower_ratio < 0.2:
                        sm_rank = 'S'
                    else:
                        sm_rank = 'M'
                    
                    # 保存计算的比率和评级
                    useful_data['status_follower_ratio'] = status_follower_ratio
                    useful_data['sm_rank'] = sm_rank
                    
                    print(f"用户 {username} 的S/M评级为: {sm_rank} (比值: {status_follower_ratio:.4f})", file=sys.stderr)
                else:
                    # 如果粉丝数为0，设置为M级（避免除以零）
                    useful_data['status_follower_ratio'] = float('inf')
                    useful_data['sm_rank'] = 'M'
                    print(f"用户 {username} 的粉丝数为0，默认设置为M级", file=sys.stderr)
                
                # 计算A1/B2评级: (friends_count + favourites_count) / statuses_count
                friends_count = legacy.get('friends_count', 0)
                favourites_count = legacy.get('favourites_count', 0)
                
                # 防止除以零错误
                if statuses_count > 0:
                    engagement_ratio = (friends_count + favourites_count) / statuses_count
                    if engagement_ratio > 2:
                        ab_rank = 'A1'
                    else:
                        ab_rank = 'B2'
                    
                    # 保存计算的比率和评级
                    useful_data['engagement_ratio'] = engagement_ratio
                    useful_data['ab_rank'] = ab_rank
                    
                    print(f"用户 {username} 的A1/B2评级为: {ab_rank} (比值: {engagement_ratio:.4f})", file=sys.stderr)
                else:
                    # 如果状态数为0，设置为A1级（高互动但低发文）
                    useful_data['engagement_ratio'] = float('inf')
                    useful_data['ab_rank'] = 'A1'
                    print(f"用户 {username} 的状态数为0，默认设置为A1级", file=sys.stderr)
                
                # 根据粉丝数对用户进行评级
                followers_count = legacy.get('followers_count', 0)
                if followers_count <= 50:
                    user_rank = 'A'
                elif followers_count <= 1000:
                    user_rank = 'B'
                elif followers_count <= 5000:
                    user_rank = 'C'
                elif followers_count <= 10000:
                    user_rank = 'D'
                elif followers_count <= 50000:
                    user_rank = 'E'
                elif followers_count <= 100000:
                    user_rank = 'F'
                else:
                    user_rank = 'G'
                
                # 将评级添加到有用数据中
                useful_data['user_rank'] = user_rank
                print(f"用户 {username} 的评级为: {user_rank} (粉丝数: {followers_count})", file=sys.stderr)
                
                # 处理URL字段
                if 'entities' in legacy and 'url' in legacy['entities'] and 'urls' in legacy['entities']['url']:
                    urls = legacy['entities']['url']['urls']
                    if urls and len(urls) > 0 and 'expanded_url' in urls[0]:
                        useful_data['expanded_url'] = urls[0]['expanded_url']
                
                # 存储简化后的数据
                save_path = f"twitter_data_{username}.json"
                with open(save_path, "w", encoding="utf-8") as f:
                    json.dump(useful_data, f, indent=2, ensure_ascii=False)
                print(f"Useful Twitter data for {username} saved to {save_path}", file=sys.stderr)
        
        if not user_data:
            return jsonify({'status': 'error', 'error': '无法获取用户信息'})
        
        # 检查是否有用户数据 - 即使有错误，只要有data节点就继续处理
        if 'data' not in user_data or 'user' not in user_data['data']:
            # 只有在完全没有数据的情况下才报错
            if 'errors' in user_data:
                error_msg = user_data['errors'][0]['message'] if user_data['errors'] else '未知错误'
                return jsonify({'status': 'error', 'error': error_msg})
            return jsonify({'status': 'error', 'error': '无法获取用户数据'})
        
        user = user_data['data']['user']
        
        # 检查是否有结果
        if 'result' not in user:
            return jsonify({'status': 'error', 'error': '用户不存在'})
            
        result = user['result']
        
        # 获取legacy字段
        if 'legacy' not in result:
            return jsonify({'status': 'error', 'error': '无法获取用户详细信息'})
            
        legacy = result['legacy']
        
        # 打印完整的legacy数据以便调试
        print("Twitter user legacy data:", file=sys.stderr)
        print(json.dumps(legacy, indent=2), file=sys.stderr)
        
        # 提取需要的数据，确保处理所有可能的数据格式
        response_data = {
            'status': 'success',
            'name': legacy.get('name', ''),
            'username': legacy.get('screen_name', ''),
            'followers_count': legacy.get('followers_count', 0),
            'description': legacy.get('description', '').replace('\n', '<br>')
        }
        
        # 添加用户评级
        if user_rank:
            response_data['user_rank'] = user_rank
            followers_count = legacy.get('followers_count', 0)
            response_data['rank_description'] = f"用户评级: {user_rank} (粉丝数: {followers_count})"
        
        # 添加额外的信息
        if 'profile_image_url_https' in legacy:
            response_data['profile_image'] = legacy['profile_image_url_https']
            
        if 'created_at' in legacy:
            response_data['created_at'] = legacy['created_at']
            
        if 'statuses_count' in legacy:
            response_data['tweets_count'] = legacy['statuses_count']
            
        if 'friends_count' in legacy:
            response_data['following_count'] = legacy['friends_count']
            
        # 添加更多的用户信息
        if 'verified' in legacy:
            response_data['verified'] = legacy['verified']
            
        if 'url' in legacy:
            response_data['url'] = legacy['url']
            
        if 'location' in legacy:
            response_data['location'] = legacy['location']
            
        if 'entities' in legacy and 'url' in legacy['entities'] and 'urls' in legacy['entities']['url']:
            urls = legacy['entities']['url']['urls']
            if urls and len(urls) > 0 and 'expanded_url' in urls[0]:
                response_data['expanded_url'] = urls[0]['expanded_url']
                
        # 添加媒体计数和收藏计数
        if 'media_count' in legacy:
            response_data['media_count'] = legacy['media_count']
            
        if 'favourites_count' in legacy:
            response_data['favourites_count'] = legacy['favourites_count']
                
        return jsonify(response_data)
    except Exception as e:
        print(f"Twitter info error: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/refresh_twitter_token')
def refresh_twitter_token():
    try:
        new_token = asyncio.run(get_id.refresh_guest_token())
        # 更新全局token
        get_id.guest_token = new_token
        return jsonify({
            'status': 'success', 
            'message': 'Twitter token refreshed successfully',
            'token': new_token
        })
    except Exception as e:
        print(f"Token refresh error: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})

@app.route('/view_twitter_data/<username>')
def view_twitter_data(username):
    try:
        save_path = f"twitter_data_{username}.json"
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 确保显示S/M评级数据（如果有）
            sm_rank_info = ""
            if 'sm_rank' in data:
                sm_rank = data.get('sm_rank')
                ratio = data.get('status_follower_ratio', 0)
                sm_rank_info = f"S/M评级: {sm_rank} (状态/粉丝比: {ratio:.4f})"
                print(f"用户 {username} 的S/M评级信息: {sm_rank_info}", file=sys.stderr)
            
            # 确保显示A1/B2评级数据（如果有）
            ab_rank_info = ""
            if 'ab_rank' in data:
                ab_rank = data.get('ab_rank')
                ratio = data.get('engagement_ratio', 0)
                ab_rank_info = f"A1/B2评级: {ab_rank} (互动/状态比: {ratio:.4f})"
                print(f"用户 {username} 的A1/B2评级信息: {ab_rank_info}", file=sys.stderr)
            
            # 返回存储的精简数据
            return jsonify({
                'status': 'success',
                'message': f"Twitter精简数据已从文件{save_path}读取",
                'data': data,
                'sm_rank_info': sm_rank_info,
                'ab_rank_info': ab_rank_info
            })
        else:
            return jsonify({
                'status': 'error',
                'error': f"找不到{username}的数据文件，请先获取数据"
            })
    except Exception as e:
        print(f"View Twitter data error: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})

# 添加一个新路由，用于获取Twitter用户排名信息
@app.route('/twitter_rank/<username>')
def twitter_rank(username):
    try:
        save_path = f"twitter_data_{username}.json"
        if os.path.exists(save_path):
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            user_rank = data.get('user_rank', '未知')
            followers_count = data.get('followers_count', 0)
            
            # 获取S/M评级信息（如果有）
            sm_rank = data.get('sm_rank', '未知')
            status_follower_ratio = data.get('status_follower_ratio', 0)
            
            # 获取A1/B2评级信息（如果有）
            ab_rank = data.get('ab_rank', '未知')
            engagement_ratio = data.get('engagement_ratio', 0)
            
            rank_descriptions = {
                'A': '入门级账号 (0-50粉丝)',
                'B': '新兴账号 (51-1000粉丝)',
                'C': '小型KOL (1001-5000粉丝)',
                'D': '中型KOL (5001-10000粉丝)',
                'E': '大型KOL (10001-50000粉丝)',
                'F': '超级KOL (50001-100000粉丝)',
                'G': '顶级KOL/名人 (100001+粉丝)'
            }
            
            sm_rank_descriptions = {
                'S': '低活跃度用户 (状态/粉丝比 < 0.2)',
                'M': '中高活跃度用户 (状态/粉丝比 >= 0.2)'
            }
            
            ab_rank_descriptions = {
                'A1': '高互动用户 (互动/状态比 > 2)',
                'B2': '低互动用户 (互动/状态比 <= 2)'
            }
            
            rank_description = rank_descriptions.get(user_rank, '未知评级')
            sm_rank_description = sm_rank_descriptions.get(sm_rank, '未知活跃度')
            ab_rank_description = ab_rank_descriptions.get(ab_rank, '未知互动度')
            
            return jsonify({
                'status': 'success',
                'username': username,
                'followers_count': followers_count,
                'user_rank': user_rank,
                'rank_description': rank_description,
                'sm_rank': sm_rank,
                'sm_rank_description': sm_rank_description,
                'status_follower_ratio': status_follower_ratio,
                'ab_rank': ab_rank,
                'ab_rank_description': ab_rank_description,
                'engagement_ratio': engagement_ratio,
                'data': data
            })
        else:
            return jsonify({
                'status': 'error',
                'error': f"找不到{username}的数据文件，请先获取用户数据"
            })
    except Exception as e:
        print(f"获取Twitter用户评级错误: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})

# 添加一个新路由来查看已保存的比赛记录
@app.route('/match_history')
def match_history():
    try:
        # 获取所有match_data文件
        match_files = [f for f in os.listdir('.') if f.startswith('match_data_') and f.endswith('.json')]
        matches = []
        
        for file in match_files:
            try:
                with open(file, "r", encoding="utf-8") as f:
                    match_data = json.load(f)
                    
                # 转换时间戳为可读格式
                if 'match_start_time' in match_data:
                    timestamp = match_data['match_start_time']
                    match_data['match_start_time_readable'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
                    
                matches.append(match_data)
            except Exception as e:
                print(f"读取比赛记录失败 {file}: {e}", file=sys.stderr)
        
        # 按时间倒序排序
        matches.sort(key=lambda x: x.get('match_start_time', 0), reverse=True)
        
        return jsonify({
            'status': 'success',
            'match_count': len(matches),
            'matches': matches
        })
    except Exception as e:
        print(f"获取比赛历史失败: {e}", file=sys.stderr)
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})

# 添加获取当前随机走动概率配置的端点
@app.route('/get_random_move_config', methods=['GET'])
def get_random_move_config():
    global random_move_probability, current_match_info
    
    # 将概率转换为百分比显示
    probability_percent = random_move_probability * 100
    
    # 确定概率级别
    level = 0
    if random_move_probability == 0.0:
        level = 1
    elif random_move_probability == 0.1:
        level = 2
    elif random_move_probability == 0.2:
        level = 3
    elif random_move_probability == 0.3:
        level = 4
    elif random_move_probability == 0.4:
        level = 5
    elif random_move_probability == 0.5:
        level = 6
    
    # 构建描述
    level_descriptions = {
        1: "1级 - 无随机走动 (0%)",
        2: "2级 - 低随机走动 (10%)",
        3: "3级 - 较低随机走动 (20%)",
        4: "4级 - 中等随机走动 (30%)",
        5: "5级 - 较高随机走动 (40%)",
        6: "6级 - 高随机走动 (50%)"
    }
    
    description = level_descriptions.get(level, f"未知级别 - {probability_percent}%")
    
    rank_descriptions = {
        'A': "A级 - 入门级账号 (0-50粉丝)",
        'B': "B级 - 新兴账号 (51-1000粉丝)",
        'C': "C级 - 小型KOL (1001-5000粉丝)",
        'D': "D级 - 中型KOL (5001-10000粉丝)",
        'E': "E级 - 大型KOL (10001-50000粉丝)",
        'F': "F级 - 超级KOL (50001-100000粉丝)",
        'G': "G级 - 顶级KOL/名人 (100001+粉丝)"
    }
    
    # 返回配置信息
    response = {
        'status': 'ok',
        'random_move_probability': random_move_probability,
        'probability_percent': probability_percent,
        'level': level,
        'description': description,
        'current_match': current_match_info
    }
    
    # 如果有当前比赛用户信息，添加详细的用户等级描述
    if current_match_info and 'user_rank' in current_match_info:
        user_rank = current_match_info['user_rank']
        if user_rank in rank_descriptions:
            response['user_rank_description'] = rank_descriptions[user_rank]
    
    return jsonify(response)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
