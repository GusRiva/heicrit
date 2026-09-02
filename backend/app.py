import socket

from flask import Flask, jsonify
from flask_cors import CORS
from routes import api

def create_app():
    app = Flask(__name__)
    CORS(app)

    app.register_blueprint(api, url_prefix='/api')

    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy'})

    return app

# Uncommon port we try first, so a fresh install usually gets a stable,
# predictable port instead of a random one every launch. Falls back to an
# OS-assigned free port if this one is already taken.
DEFAULT_PORT = 57321

def find_free_port(preferred_port=DEFAULT_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', preferred_port))
        except OSError:
            s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

if __name__ == '__main__':
    app = create_app()
    port = find_free_port()
    # electron/main.js parses this line from stdout to learn which port to
    # tell the frontend to use - must print before app.run() starts serving.
    print(f'HEICRIT_BACKEND_PORT={port}', flush=True)
    # use_reloader=False: the reloader re-execs this script in a subprocess,
    # which would call find_free_port() a second time and bind a different
    # port than the one already printed above.
    app.run(debug=True, use_reloader=False, host='127.0.0.1', port=port)