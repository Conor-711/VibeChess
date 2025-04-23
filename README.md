# Lichess Game Analyzer

这是一个用于分析Lichess国际象棋游戏的工具。该项目可以获取用户的对局数据，并提供分析功能。

## 功能特点

- 获取Lichess用户的对局数据
- 分析棋局
- 可视化棋盘界面
- 使用Stockfish引擎进行棋局评估

## 安装

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/Lichess-game.git
cd Lichess-game

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或者
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

```bash
python backend.py
```

在浏览器中访问 `http://localhost:5000` 即可使用。

## 许可证

MIT 