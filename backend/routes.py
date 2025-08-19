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

def parse_synoptic_map(corresp_path, base_dir):
    """
    Parse synoptic map file and extract link elements with n and target attributes.
    Returns a dictionary with n as key and target list as value.
    """
    try:
        # Handle relative paths
        if not os.path.isabs(corresp_path):
            corresp_path = os.path.join(base_dir, corresp_path)
        
        # Resolve the path to handle .. properly
        corresp_path = os.path.abspath(corresp_path)
        if not os.path.exists(corresp_path):
            return {}
        
        # Parse the synoptic map XML file
        from io import BytesIO
        parser = HeiEditionsParser()
        
        with open(corresp_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content_bytes = content.encode('utf-8')
        doc = et.parse(BytesIO(content_bytes), parser)
        root = doc.getroot()
        
        # Extract link elements
        link_elements = root.xpath('.//tei:link', namespaces=ns)
        
        synoptic_map = {}
        
        for link in link_elements:
            n = link.get('n')
            target = link.get('target', '')
            
            if n:
                # Split target by whitespace and clean up
                target_list = [t.strip() for t in target.split() if t.strip()]
                synoptic_map[n] = {
                    'n': n,
                    'target': target_list
                }
        
        return synoptic_map
        
    except Exception as e:
        return {}

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
        
        # Extract apparatus entries (synoptic map is handled separately now)
        try:
            
            # Find all app elements in the document
            app_elements = root.xpath('.//tei:app', namespaces=ns)
            
            apparatus_entries = []
            
            for i, app in enumerate(app_elements):
                entry = {
                    'id': i + 1,
                    'loc': app.get('loc'),
                    'lemma': None,
                    'readings': []
                }
                
                # Extract lemma
                lem_element = app.find('.//tei:lem', namespaces=ns)
                if lem_element is not None:
                    entry['lemma'] = {
                        'text': ''.join(lem_element.itertext()).strip(),
                        'attributes': dict(lem_element.attrib)
                    }
                
                # Extract readings
                rdg_elements = app.xpath('.//tei:rdg', namespaces=ns)
                for rdg in rdg_elements:
                    reading = {
                        'text': ''.join(rdg.itertext()).strip(),
                        'wit': rdg.get('wit', ''),
                        'attributes': dict(rdg.attrib)
                    }
                    entry['readings'].append(reading)
                
                apparatus_entries.append(entry)
            
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

@api.route('/apparatus/process-with-project', methods=['POST'])
def process_apparatus_file_with_project():
    """
    Process a TEI apparatus file with project context for relative path resolution
    Expected JSON payload: {
        'content': 'XML content as string',
        'filepath': 'relative path within project',
        'project_files': {path: {content: str, size: int}, ...}
    }
    """
    try:
        if not HEIPY_AVAILABLE:
            return jsonify({'error': 'heipy library not available'}), 500
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        content = data.get('content')
        filepath = data.get('filepath', 'apparatus.xml')
        project_files = data.get('project_files', {})
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Parse XML using HeiEditionsParser
        try:
            from io import BytesIO
            parser = HeiEditionsParser()
            content_bytes = content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
        except Exception as xml_error:
            return jsonify({'error': f'Invalid XML: {str(xml_error)}'}), 400
        
        # Extract apparatus entries and resolve synoptic map from project
        try:
            synoptic_map = {}
            
            # Find listApp element and extract corresp attribute
            list_app = root.find('.//tei:listApp', namespaces=ns)
            if list_app is not None:
                corresp = list_app.get('corresp')
                if corresp:
                    # Resolve corresp path within project files
                    synoptic_map = resolve_synoptic_map_from_project(corresp, filepath, project_files)
            
            # Find all app elements in the document
            app_elements = root.xpath('.//tei:app', namespaces=ns)
            
            apparatus_entries = []
            
            for i, app in enumerate(app_elements):
                entry = {
                    'id': i + 1,
                    'loc': app.get('loc'),
                    'lemma': None,
                    'readings': []
                }
                
                # Extract lemma
                lem_element = app.find('.//tei:lem', namespaces=ns)
                if lem_element is not None:
                    entry['lemma'] = {
                        'text': ''.join(lem_element.itertext()).strip(),
                        'attributes': dict(lem_element.attrib)
                    }
                
                # Extract readings
                rdg_elements = app.xpath('.//tei:rdg', namespaces=ns)
                for rdg in rdg_elements:
                    reading = {
                        'text': ''.join(rdg.itertext()).strip(),
                        'wit': rdg.get('wit', ''),
                        'attributes': dict(rdg.attrib)
                    }
                    entry['readings'].append(reading)
                
                apparatus_entries.append(entry)
            
            result = {
                'success': True,
                'message': f'Found {len(apparatus_entries)} apparatus entries',
                'filepath': filepath,
                'content_length': len(content),
                'heipy_available': HEIPY_AVAILABLE,
                'apparatus_count': len(apparatus_entries),
                'apparatus_entries': apparatus_entries,
                'synoptic_map': synoptic_map,
                'synoptic_map_count': len(synoptic_map)
            }
            
        except Exception as processing_error:
            return jsonify({'error': f'Failed to extract apparatus entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

def resolve_synoptic_map_from_project(corresp_path, apparatus_filepath, project_files):
    """
    Resolve synoptic map from project files using relative path resolution
    """
    try:
        # Get the directory of the apparatus file
        apparatus_dir = '/'.join(apparatus_filepath.split('/')[:-1])
        
        # Resolve the relative corresp path
        if corresp_path.startswith('../'):
            # Handle relative paths like ../synopses/synoptic_map.xml
            path_parts = apparatus_dir.split('/') if apparatus_dir else []
            corresp_parts = corresp_path.split('/')
            
            for part in corresp_parts:
                if part == '..':
                    if path_parts:
                        path_parts.pop()
                elif part and part != '.':
                    path_parts.append(part)
            
            resolved_path = '/'.join(path_parts)
        else:
            # Handle absolute or simple relative paths
            resolved_path = corresp_path
        
        # Look for the file in project_files
        for project_path, file_data in project_files.items():
            if project_path.endswith(resolved_path) or project_path == resolved_path:
                # Parse the synoptic map content
                return parse_synoptic_map_content(file_data['content'])
        
        # If exact match not found, try fuzzy matching
        for project_path, file_data in project_files.items():
            if resolved_path in project_path or project_path.endswith(resolved_path.split('/')[-1]):
                return parse_synoptic_map_content(file_data['content'])
        
        print(f"Synoptic map not found: {resolved_path}")
        return {}
        
    except Exception as e:
        print(f"Error resolving synoptic map: {str(e)}")
        return {}

def parse_synoptic_map_content(content):
    """
    Parse synoptic map content directly
    """
    try:
        from io import BytesIO
        parser = HeiEditionsParser()
        content_bytes = content.encode('utf-8')
        doc = et.parse(BytesIO(content_bytes), parser)
        root = doc.getroot()
        
        # Extract link elements
        link_elements = root.xpath('.//tei:link', namespaces=ns)
        
        synoptic_map = {}
        
        for link in link_elements:
            n = link.get('n')
            target = link.get('target', '')
            
            if n:
                # Split target by whitespace and clean up
                target_list = [t.strip() for t in target.split() if t.strip()]
                synoptic_map[n] = {
                    'n': n,
                    'target': target_list
                }
        
        return synoptic_map
        
    except Exception as e:
        print(f"Error parsing synoptic map content: {str(e)}")
        return {}

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

@api.route('/synoptic/process', methods=['POST'])
def process_synoptic_map_file():
    """
    Process a synoptic map file directly
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
        filename = data.get('filename', 'synoptic_map.xml')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Parse XML using HeiEditionsParser
        try:
            from io import BytesIO
            parser = HeiEditionsParser()
            content_bytes = content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
        except Exception as xml_error:
            return jsonify({'error': f'Invalid XML: {str(xml_error)}'}), 400
        
        # Extract link elements directly
        try:
            link_elements = root.xpath('.//tei:link', namespaces=ns)
            
            synoptic_map = {}
            
            for link in link_elements:
                n = link.get('n')
                target = link.get('target', '')
                
                if n:
                    # Split target by whitespace and clean up
                    target_list = [t.strip() for t in target.split() if t.strip()]
                    synoptic_map[n] = {
                        'n': n,
                        'target': target_list
                    }
            
            result = {
                'success': True,
                'message': f'Found {len(synoptic_map)} synoptic map entries',
                'filename': filename,
                'content_length': len(content),
                'heipy_available': HEIPY_AVAILABLE,
                'synoptic_map_count': len(synoptic_map),
                'synoptic_map': synoptic_map
            }
            
        except Exception as processing_error:
            return jsonify({'error': f'Failed to extract synoptic map entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

