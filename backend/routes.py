from flask import Blueprint, request, jsonify
import os
from lxml import etree as et

from heipy.heipipe.steps import PythonStep
# from heipy.heipipe.step_library.append_synoptic_links import append_synoptic_links_funct

from load_functions import load_sigla_mapping, resolve_relative_path, find_file_in_project
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct
from synoptic_map import SynopticMap
from apparatus import Apparatus



api = Blueprint('api', __name__)

# Global variables
sigla_mapping = {}
synoptic_map = SynopticMap()
apparatus = None  # Global apparatus object for frontend modifications 


def process_synoptic_unit_for_comparison(element) -> str:
    """
    Process an XML element and return a string representation for comparison.
    
    Args:
        element: The lxml etree Element to process
        
    Returns:
        String representation of the element content
    """
    if element is None:
        return "[Element not found]"
    
    try:
        # Get the text content of the element, stripping whitespace
        text_content = ''.join(element.itertext()).strip()
        
        # If no text content, try to get element info
        if not text_content:
            tag_name = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            return f"[{tag_name} element - no text content]"
        
        return text_content
        
    except Exception as e:
        return f"[Error processing element: {str(e)}]"



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

@api.route('/apparatus', methods=['GET'])
def get_apparatus():
    """
    Get the current apparatus information
    """
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded'}), 404
        
        return jsonify({
            'success': True,
            'apparatus': apparatus.to_dict()
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get apparatus: {str(e)}'}), 500

@api.route('/apparatus/entry/<int:entry_id>', methods=['PUT'])
def update_apparatus_entry(entry_id):
    """
    Update a specific apparatus entry
    """
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        updated_entry = data.get('entry')
        if not updated_entry:
            return jsonify({'error': 'No entry data provided'}), 400
        
        success = apparatus.update_entry(entry_id, updated_entry)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Entry {entry_id} updated successfully'
            })
        else:
            return jsonify({'error': f'Entry {entry_id} not found'}), 404
        
    except Exception as e:
        return jsonify({'error': f'Failed to update apparatus entry: {str(e)}'}), 500

@api.route('/synoptic/compare', methods=['POST'])
def get_synoptic_comparison():
    """
    Get synoptic comparison data for location details replacement
    Expected JSON payload: { 'data_link': 'a:l_1 b:l_1' }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        data_link = data.get('data_link')
        if not data_link:
            return jsonify({'error': 'No data_link provided'}), 400
        
        # print(f"DEBUG: Received data_link: '{data_link}'")
        # print(f"DEBUG: Available synoptic loci count: {synoptic_map.get_loci_count()}")
        # print(f"DEBUG: Available witness count: {synoptic_map.get_wits_count()}")
        
        # Debug witness information
        all_wit_idents = synoptic_map.get_all_wit_idents()
        print(f"DEBUG: All witness identifiers: {all_wit_idents}")
        
        # Check a few witness elements to understand structure
        for wit_id in all_wit_idents[:3]:  # Check first 3 witnesses
            wit_info = synoptic_map.get_wit_info(wit_id)
            # print(f"DEBUG: Witness '{wit_id}' info: {wit_info}")
            wit_elements = synoptic_map.get_wit_elements(wit_id)
            if wit_elements:
                element_keys = list(wit_elements.keys())[:5]  # Show first 5 element keys
        
        comparison_texts = []
        
        # Parse data_link and get text representations
        tokens = data_link.split()
        # print(f"DEBUG: Tokens: {tokens}")
        for token in tokens:
            if ':' in token:
                prefix, element_id = token.split(':', 1)
                # print(f"DEBUG: Processing token '{token}' - prefix: '{prefix}', element_id: '{element_id}'")
                
                wit_elements = synoptic_map.get_wit_elements(prefix)
                # print(f"DEBUG: wit_elements for '{prefix}': {wit_elements is not None}")
                if wit_elements and len(wit_elements) > 0:
                    # print(f"DEBUG: Number of elements for '{prefix}': {len(wit_elements)}")
                    element = wit_elements.get(element_id)
                    # print(f"DEBUG: Found element '{element_id}': {element is not None}")
                    text_repr = process_synoptic_unit_for_comparison(element)
                    # print(f"DEBUG: Text representation: '{text_repr}'")
                else:
                    text_repr = f"[Witness '{prefix}' not found]"
                    # print(f"DEBUG: Witness not found, using: '{text_repr}'")
                
                comparison_texts.append(text_repr)
        
        return jsonify({
            'success': True,
            'comparison_texts': comparison_texts
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get synoptic comparison: {str(e)}'}), 500

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
        'apparatus_filepath': 'relative path to apparatus file within project',
        'project_files': {path: {content: str, size: int}, ...}
    }
    """
    global sigla_mapping, synoptic_map, apparatus
    try:    
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        apparatus_filepath = data.get('apparatus_filepath')
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
        
        if not apparatus_filepath:
            return jsonify({'error': 'No apparatus filepath provided'}), 400
        
        # Create Apparatus object and parse the file
        try:
            apparatus = Apparatus(apparatus_filepath, project_files)
        except Exception as apparatus_error:
            return jsonify({'error': f'Failed to parse apparatus file: {str(apparatus_error)}'}), 400
        
        
        try:
            # Get information from the apparatus object
            leiths_path = apparatus.get_leiths_path()
            apparatus_entries = apparatus.get_entries()
            
            leiths_info = None
            if leiths_path:
                leiths_info = sigla_mapping.get(leiths_path.split('/')[-1])

            leiths_prefix = None
            if leiths_info is not None:
                leiths_prefix = leiths_info.get('synoptic_pre')
            
            # Get corresp attribute for synoptic map loading
            corresp = apparatus.get_corresp_attribute()
            if corresp:
                # Load synoptic map from project files using class method
                try:
                    synoptic_map.load_from_project(corresp, apparatus_filepath, project_files, leiths_prefix=leiths_prefix)
                except Exception as synoptic_error:
                    print(f"ERROR loading synoptic map: {synoptic_error}")
                    
            # Now process main text with synoptic map available
            main_text_content = None
            if leiths_path:
                main_text_content = resolve_text_file_from_project(leiths_path, apparatus_filepath, project_files)
            
            
            synoptic_map.get_wits()
            result = {
                'success': True,
                'message': f'Found {len(apparatus_entries)} apparatus entries',
                'leiths-info': leiths_info,
                'apparatus_filepath': apparatus_filepath,
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


