# 这个文件只是一个入口点，用于Render部署
# 它导入并重新导出backend.py中的Flask应用

from backend import app

# 如果这个文件被直接运行
if __name__ == '__main__':
    app.run(debug=True)
