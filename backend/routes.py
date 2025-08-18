from flask import Blueprint, request, jsonify
import os
from lxml import etree as et
try:
    from heipy.parsers import HeiEditionsParser
    from heipy.namespaces import ns
    import heipy.validation
    HEIPY_AVAILABLE = True
except ImportError:
    HEIPY_AVAILABLE = False

api = Blueprint('api', __name__)

@api.route('/files', methods=['GET'])
def list_files():
    try:
        directory = request.args.get('directory', '.')
        files = []
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                files.append({
                    'name': filename,
                    'path': filepath,
                    'size': os.path.getsize(filepath),
                    'modified': os.path.getmtime(filepath)
                })
        return jsonify({'files': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/file/<path:filename>', methods=['GET'])
def get_file(filename):
    try:
        if not os.path.exists(filename):
            return jsonify({'error': 'File not found'}), 404
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return jsonify({
            'filename': os.path.basename(filename),
            'content': content,
            'path': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/file', methods=['POST'])
def save_file():
    try:
        data = request.get_json()
        filename = data.get('filename')
        content = data.get('content', '')
        
        if not filename:
            return jsonify({'error': 'Filename required'}), 400
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return jsonify({'message': 'File saved successfully', 'filename': filename})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api.route('/apparatus/process', methods=['POST'])
def process_apparatus_file():
    """
    Process a TEI apparatus file using heipy
    Expected JSON payload: {
        'content': 'XML content as string',
        'filename': 'original filename'
    }
    """
    try:
        if not HEIPY_AVAILABLE:
            return jsonify({'error': 'heipy library not available'}), 500
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        content = data.get('content')
        filename = data.get('filename', 'apparatus.xml')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Parse XML using HeiEditionsParser
        try:
            from io import BytesIO
            parser = HeiEditionsParser()
            # Convert string to bytes for proper XML parsing with encoding declaration
            content_bytes = content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
        except Exception as xml_error:
            return jsonify({'error': f'Invalid XML: {str(xml_error)}'}), 400
        
        # Extract all app elements
        try:
            # Find all app elements in the document
            app_elements = root.xpath('.//tei:app', namespaces=ns)
            
            apparatus_entries = []
            
            for app in app_elements:
                apparatus_entries.append(app.get('loc'))    
            
            
            result = {
                'success': True,
                'message': f'Found {len(apparatus_entries)} apparatus entries',
                'filename': filename,
                'content_length': len(content),
                'heipy_available': HEIPY_AVAILABLE,
                'apparatus_count': len(apparatus_entries),
                'apparatus_entries': apparatus_entries
            }
            
        except Exception as processing_error:
            return jsonify({'error': f'Failed to extract apparatus entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@api.route('/apparatus/validate', methods=['POST'])
def validate_apparatus_file():
    """
    Validate if a file is a proper TEI apparatus file
    """
    try:
        if not HEIPY_AVAILABLE:
            return jsonify({'error': 'heipy library not available'}), 500
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # TODO: Add your specific TEI apparatus validation logic here
        # This is where you'll implement validation using heipy
        
        # Basic validation for now
        is_valid = True
        validation_messages = []
        
        # Check for basic TEI structure
        if '<TEI' not in content and '<tei' not in content:
            is_valid = False
            validation_messages.append('File does not appear to be a TEI document')
        
        result = {
            'valid': is_valid,
            'messages': validation_messages,
            'heipy_available': HEIPY_AVAILABLE
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Validation failed: {str(e)}'}), 500
