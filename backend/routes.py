from flask import Blueprint, request, jsonify
import os
from lxml import etree as et

from heipy.namespaces import ns
from heipy.heipipe.steps import PythonStep
# from heipy.heipipe.step_library.append_synoptic_links import append_synoptic_links_funct

from load_functions import load_sigla_mapping, parse_xml_heieditions, resolve_relative_path, find_file_in_project
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct
from synoptic_map import SynopticMap



api = Blueprint('api', __name__)

# Global variables
sigla_mapping = {}
synoptic_map = SynopticMap() 



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
    global sigla_mapping, synoptic_map
    try:    
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
                    sigla_mapping = load_sigla_mapping(project_files=project_files)
        
        if not apparatus_content:
            return jsonify({'error': 'No apparatus content provided'}), 400
        
        # Parse XML using HeiEditionsParser
        try:
            apparatus_root = parse_xml_heieditions(apparatus_content)
        except Exception as xml_error:
            return jsonify({'error': f'Invalid XML: {str(xml_error)}'}), 400
        
        
        try:
            leiths_path = extract_leithandschrift_path(apparatus_root)
            leiths_info = sigla_mapping.get(leiths_path.split('/')[-1])

            leiths_prefix = None
            if leiths_info is not None:
                leiths_prefix = leiths_info.get('synoptic_pre')
            
            # Find listApp element and extract corresp attribute
            list_app = apparatus_root.find('.//tei:listApp', namespaces=ns)
            if list_app is not None:
                corresp = list_app.get('corresp')
                if corresp:
                    # Load synoptic map from project files using class method
                    try:
                        synoptic_map.load_from_project(corresp, apparatus_filepath, project_files, leiths_prefix=leiths_prefix)
                    except Exception as synoptic_error:
                        print(f"ERROR loading synoptic map: {synoptic_error}")
                        import traceback
                        traceback.print_exc()
                    
            # Now process main text with synoptic map available
            main_text_content = None
            main_text_content = resolve_text_file_from_project(leiths_path, apparatus_filepath, project_files)
            
            
            # Find all app elements in the document
            app_elements = apparatus_root.xpath('.//tei:app', namespaces=ns)
            
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
                'leiths-info': leiths_info,
                'apparatus_filepath': apparatus_filepath,
                'content_length': len(apparatus_content),
                'apparatus_count': len(apparatus_entries),
                'apparatus_entries': apparatus_entries,
                'synoptic_map': synoptic_map.get_loci(),
                'synoptic_map_count': synoptic_map.get_loci_count(),
                'synoptic_wits': synoptic_map.get_wits(),
                'synoptic_wits_count': synoptic_map.get_wits_count(),
                'main_text': main_text_content
            }
            
            
        except Exception as processing_error:
            print(f"ERROR in open_project processing: {processing_error}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Failed to extract apparatus entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        print(f"ERROR in open_project outer catch: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500


def extract_leithandschrift_path(root: et.Element):
    """Extract the siglum info for the leiths."""
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
        
        return target_path
        
    except Exception as e:
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
        
        return None
        
    except Exception as e:
        return None

def parse_main_text_file_content(content):
    """
    Parse text file using HeiCritPipe and return the result
    """
    try:
        pipeline = HeiCritPipe()
        pipeline.add_step(PythonStep(append_synoptic_links_funct, name="heicrit_append_synoptic_links"), 
                          before_step= 'create_html',
                          parameters= {'sigla_mapping': sigla_mapping, 
                                       'synoptic_map': synoptic_map.get_loci()})
        result = pipeline.execute(content)
        return result
        
    except Exception as e:
        return None

@api.route('/apparatus/validate', methods=['POST'])
def validate_apparatus_file():
    """
    Validate if a file is a proper TEI apparatus file
    """
    try:    
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
    global synoptic_map
    try:    
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        content = data.get('content')
        filename = data.get('filename', 'synoptic_map.xml')
        
        if not content:
            return jsonify({'error': 'No content provided'}), 400
        
        # Parse content using class method
        try:
            success = synoptic_map.parse_content(content)
            if success:
                synoptic_map.set_file_path(filename)
            
            result = {
                'success': True,
                'message': f'Found {synoptic_map.get_loci_count()} synoptic map entries and {synoptic_map.get_wits_count()} witnesses',
                'filename': filename,
                'content_length': len(content),
                'synoptic_map_count': synoptic_map.get_loci_count(),
                'synoptic_map': synoptic_map.get_loci(),
                'synoptic_wits_count': synoptic_map.get_wits_count(),
                'synoptic_wits': synoptic_map.get_wits()
            }
            
        except Exception as processing_error:
            return jsonify({'error': f'Failed to extract synoptic map entries: {str(processing_error)}'}), 500
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500


