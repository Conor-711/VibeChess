import os
import sys
import traceback
from flask import Flask, jsonify, send_from_directory

# Print startup information to help with debugging
print("Starting VibeChess Railway App...", file=sys.stderr)
print(f"Python version: {sys.version}", file=sys.stderr)
print(f"Environment variables: {os.environ.keys()}", file=sys.stderr)

# Create Flask app
app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/health')
def health():
    print("Health check endpoint accessed", file=sys.stderr)
    return jsonify({'status': 'ok'}), 200

@app.route('/')
def index():
    # First try to serve the static file
    try:
        if os.path.exists(os.path.join(app.static_folder, 'index.html')):
            print("Serving static index.html", file=sys.stderr)
            return send_from_directory(app.static_folder, 'index.html')
    except Exception as e:
        print(f"Error serving static file: {e}", file=sys.stderr)
    
    # If that fails, return a simple response
    print("Serving API response for root endpoint", file=sys.stderr)
    return jsonify({'status': 'ok', 'message': 'VibeChess API is running'}), 200

# Add error handler for debugging
@app.errorhandler(Exception)
def handle_exception(e):
    print(f"Unhandled exception: {e}", file=sys.stderr)
    print(traceback.format_exc(), file=sys.stderr)
    return jsonify({
        "status": "error",
        "message": str(e),
        "traceback": traceback.format_exc()
    }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on port {port}", file=sys.stderr)
    app.run(host='0.0.0.0', port=port, debug=False)
