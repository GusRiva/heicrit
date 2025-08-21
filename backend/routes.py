from flask import Blueprint, request, jsonify
import os
from lxml import etree as et
try:
    from heipy.parsers import HeiEditionsParser
    from heipy.namespaces import ns
    from heipy.heipipe.pipeline_library.synoptic import HeiCritPipe
    from heipy.heipipe.step_library.heicrit import append_synoptic_links
    HEIPY_AVAILABLE = True
except ImportError:
    HEIPY_AVAILABLE = False

api = Blueprint('api', __name__)

# Global variables
sigla_mapping = {}
synoptic_map_data = {}

def load_sigla_mapping(project_directory=None, project_files=None):
    """
    Load sigla mapping from pipelines/config.py
    Can load from either a project directory or project files dictionary
    Returns the mapping dictionary or empty dict if not found
    """
    global sigla_mapping
    
    try:
        config_content = None
        config_path = None
        
        if project_directory:
            # Load from filesystem
            config_path = os.path.join(project_directory, 'pipelines', 'config.py')
            if not os.path.exists(config_path):
                print(f"Warning: Could not find pipelines/config.py in project directory: {project_directory}")
                sigla_mapping = {}
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_content = f.read()
        
        elif project_files:
            # Load from project files dictionary
            for file_path, file_data in project_files.items():
                if file_path.endswith('pipelines/config.py') or file_path == 'pipelines/config.py':
                    config_content = file_data['content']
                    config_path = file_path
                    break
            
            if config_content is None:
                print("Warning: Could not find pipelines/config.py in project files")
                sigla_mapping = {}
                return {}
        
        else:
            raise ValueError("Either project_directory or project_files must be provided")
        
        # Use exec to safely extract the mapping variable
        namespace = {}
        exec(config_content, namespace)
        
        mapping = namespace.get('mapping', None)
        if mapping is None:
            print(f"Warning: No 'mapping' variable found in {config_path}")
            sigla_mapping = {}
            return {}
        
        if not isinstance(mapping, dict):
            print(f"Warning: 'mapping' variable is not a dictionary in {config_path}")
            sigla_mapping = {}
            return {}
        
        if len(mapping) == 0:
            print(f"Warning: 'mapping' dictionary is empty in {config_path}")
        
        sigla_mapping = mapping
        print(f"Loaded sigla mapping with {len(mapping)} entries from {config_path}")
        return mapping
        
    except Exception as e:
        error_source = project_directory if project_directory else "project files"
        print(f"Error: Failed to load sigla mapping from {error_source}: {str(e)}")
        sigla_mapping = {}
        return {}

def parse_synoptic_map(corresp_path=None, base_dir=None, content=None)-> dict:
    """
    Parse synoptic map file and extract link elements with n and target attributes.
    Can parse from file path or direct content string.
    Returns a dictionary with n as key and target list as value.
    """
    try:
        if content:
            # Parse from content string
            xml_content = content
        elif corresp_path:
            # Parse from file path
            if not os.path.isabs(corresp_path):
                corresp_path = os.path.join(base_dir, corresp_path)
            
            corresp_path = os.path.abspath(corresp_path)
            if not os.path.exists(corresp_path):
                return {}
            
            with open(corresp_path, 'r', encoding='utf-8') as f:
                xml_content = f.read()
        else:
            return {}
        
        # Parse the synoptic map XML
        from io import BytesIO
        parser = HeiEditionsParser()
        content_bytes = xml_content.encode('utf-8')
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
        print(f"Error parsing synoptic map: {str(e)}")
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

@api.route('/save', methods=['POST'])
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


@api.route('/project/open', methods=['POST'])
def open_project():
    """
    Open and process a project directory with TEI apparatus files
    Expected JSON payload: {
        'apparatus_content': 'Apparatus XML content as string',
        'apparatus_filepath': 'relative path to apparatus file within project',
        'project_files': {path: {content: str, size: int}, ...}
    }
    """
    try:
        if not HEIPY_AVAILABLE:
            return jsonify({'error': 'heipy library not available'}), 500
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        apparatus_content = data.get('apparatus_content')
        apparatus_filepath = data.get('apparatus_filepath', 'apparatus.xml')
        project_files = data.get('project_files', {})
        
        # Extract project root directory from file paths to load sigla mapping
        if project_files:
            # Get the common root directory from the project files
            file_paths = list(project_files.keys())
            if file_paths:
                # Find the common root directory (typically the first part before '/')
                first_path = file_paths[0]
                project_root = first_path.split('/')[0] if '/' in first_path else ''
                if project_root:
                    # Use a dummy path since we don't have the actual filesystem path
                    # The sigla mapping will be loaded from the project files instead
                    load_sigla_mapping(project_files=project_files)
        
        if not apparatus_content:
            return jsonify({'error': 'No apparatus content provided'}), 400
        
        # Parse XML using HeiEditionsParser
        try:
            from io import BytesIO
            parser = HeiEditionsParser()
            content_bytes = apparatus_content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
        except Exception as xml_error:
            return jsonify({'error': f'Invalid XML: {str(xml_error)}'}), 400
        
        # Extract apparatus entries, resolve synoptic map, and extract main text from project
        try:
            synoptic_map = {}
            main_text_content = None
            
            # Find listApp element and extract corresp attribute
            list_app = root.find('.//tei:listApp', namespaces=ns)
            if list_app is not None:
                corresp = list_app.get('corresp')
                if corresp:
                    # Resolve corresp path within project files
                    synoptic_map = resolve_synoptic_map_from_project(corresp, apparatus_filepath, project_files)
                    # Store in global variable
                    global synoptic_map_data
                    synoptic_map_data = synoptic_map
            # Extract main text from Leithandschrift witness
            main_text_content = extract_leithandschrift_text(root, apparatus_filepath, project_files)
            
            # Find all app elements in the document
            app_elements = root.xpath('.//tei:app', namespaces=ns)
            
            apparatus_entries = []
            
            for i, app in enumerate(app_elements):
                entry = {
                    'id': i + 1,
                    'loc': app.get('loc'),
                    'corresp': app.get('corresp'),
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
                'apparatus_filepath': apparatus_filepath,
                'content_length': len(apparatus_content),
                'heipy_available': HEIPY_AVAILABLE,
                'apparatus_count': len(apparatus_entries),
                'apparatus_entries': apparatus_entries,
                'synoptic_map': synoptic_map,
                'synoptic_map_count': len(synoptic_map),
                'main_text': main_text_content
            }
            
        except Exception as processing_error:
            return jsonify({'error': f'Failed to extract apparatus entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500


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

def resolve_relative_path(target_path, base_filepath):
    """
    Resolve a relative path based on a base file path
    """
    # Get the directory of the base file
    base_dir = '/'.join(base_filepath.split('/')[:-1])
    
    if target_path.startswith('../'):
        # Handle relative paths like ../synopses/synoptic_map.xml
        path_parts = base_dir.split('/') if base_dir else []
        target_parts = target_path.split('/')
        
        for part in target_parts:
            if part == '..':
                if path_parts:
                    path_parts.pop()
            elif part and part != '.':
                path_parts.append(part)
        
        return '/'.join(path_parts)
    else:
        # Handle absolute or simple relative paths
        return target_path

def find_file_in_project(resolved_path, project_files):
    """
    Find a file in project files using exact and fuzzy matching
    """
    # First try exact match
    for project_path, file_data in project_files.items():
        if project_path.endswith(resolved_path) or project_path == resolved_path:
            return file_data
    
    # If exact match not found, try fuzzy matching
    for project_path, file_data in project_files.items():
        if resolved_path in project_path or project_path.endswith(resolved_path.split('/')[-1]):
            return file_data
    
    return None

def resolve_synoptic_map_from_project(corresp_path, apparatus_filepath, project_files):
    """
    Resolve synoptic map from project files using relative path resolution
    """
    try:
        resolved_path = resolve_relative_path(corresp_path, apparatus_filepath)
        file_data = find_file_in_project(resolved_path, project_files)
        
        if file_data:
            return parse_synoptic_map(content=file_data['content'])
        
        print(f"Synoptic map not found: {resolved_path}")
        return {}
        
    except Exception as e:
        print(f"Error resolving synoptic map: {str(e)}")
        return {}

def extract_leithandschrift_text(root, apparatus_filepath, project_files):
    """
    Extract main text from the Leithandschrift witness
    """
    try:
        # Find witness with ana="hc:Leithandschrift"
        leithandschrift_witness = root.find('.//tei:witness[@ana="hc:Leithandschrift"]', namespaces=ns)
        if leithandschrift_witness is None:
            return None
        
        # Get ptr target path
        ptr_element = leithandschrift_witness.find('.//tei:ptr', namespaces=ns)
        if ptr_element is None:
            return None
        
        target_path = ptr_element.get('target')
        if not target_path:
            return None
        
        # Resolve the target path within project files
        text_content = resolve_text_file_from_project(target_path, apparatus_filepath, project_files)
        return text_content
        
    except Exception as e:
        print(f"Error extracting Leithandschrift text: {str(e)}")
        return None

def resolve_text_file_from_project(target_path, apparatus_filepath, project_files):
    """
    Resolve text file from project files using relative path resolution
    """
    try:
        resolved_path = resolve_relative_path(target_path, apparatus_filepath)
        file_data = find_file_in_project(resolved_path, project_files)
        
        if file_data:
            return parse_main_text_file_content(file_data['content'])
        
        print(f"Text file not found: {resolved_path}")
        return None
        
    except Exception as e:
        print(f"Error resolving text file: {str(e)}")
        return None

def parse_main_text_file_content(content):
    """
    Parse text file using HeiCritPipe and return the result
    """
    try:
        pipeline = HeiCritPipe()
        pipeline.add_step(append_synoptic_links.get_step(), before_step= 'create_html',
                          parameters= {'sigla_mapping': sigla_mapping, 'synoptic_map': synoptic_map_data})
        result = pipeline.execute(content)
        return result
        
    except Exception as e:
        print(f"Error parsing text file with HeiCritPipe: {str(e)}")
        return None

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
            global synoptic_map_data
            
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
            
            # Store in global variable
            synoptic_map_data = synoptic_map
            
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

@api.route('/sigla-mapping', methods=['GET'])
def get_sigla_mapping():
    """
    Get the current sigla mapping dictionary
    """
    try:
        return jsonify({
            'success': True,
            'sigla_mapping': sigla_mapping,
            'count': len(sigla_mapping)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get sigla mapping: {str(e)}'}), 500

