import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'VibeChess API is running'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
