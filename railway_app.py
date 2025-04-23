import os
import sys
from flask import Flask, jsonify

# Print startup information to help with debugging
print("Starting Minimal VibeChess Railway App...", file=sys.stderr)

# Create Flask app with no static folder
app = Flask(__name__)

@app.route('/health')
def health():
    print("Health check endpoint accessed", file=sys.stderr)
    return jsonify({'status': 'ok'}), 200

@app.route('/')
def index():
    print("Root endpoint accessed", file=sys.stderr)
    return jsonify({'status': 'ok', 'message': 'VibeChess API is running (minimal version)'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}", file=sys.stderr)
    app.run(host='0.0.0.0', port=port)
