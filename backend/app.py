from flask import Flask, request, jsonify
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

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='127.0.0.1', port=5000)