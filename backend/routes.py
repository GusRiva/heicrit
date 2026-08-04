from flask import Blueprint, request, jsonify
import os
from lxml import etree as et

from heipy.heipipe.steps import PythonStep
# from heipy.heipipe.step_library.append_synoptic_links import append_synoptic_links_funct

from load_functions import resolve_relative_path, find_file_in_project
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct
from synoptic_map import SynopticMap
from apparatus import Apparatus, process_synoptic_unit_for_comparison



api = Blueprint('api', __name__)

# Global variables
synoptic_map = SynopticMap()
apparatus = None  # Global apparatus object for frontend modifications
project_files_cache = {}  # Cached project files from last finalize_project call

@api.route('/sigla-mapping', methods=['GET'])
def get_sigla_mapping():
    """
    Get the apparatus-based witness mapping
    """
    global apparatus
    try:
        if apparatus is None:
            return jsonify({
                'success': False,
                'error': 'No apparatus loaded'
            }), 400
        
        witness_mapping = apparatus.get_witness_to_prefix_mapping()
        return jsonify({
            'success': True,
            'witness_mapping': witness_mapping,
            'count': len(witness_mapping)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get witness mapping: {str(e)}'}), 500

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
        
        comparison_data = []
        
        # Parse data_link and get text representations
        tokens = data_link.split()
        for token in tokens:
            if ':' in token:
                prefix, element_id = token.split(':', 1)
                wit_elements = synoptic_map.get_wit_elements(prefix)
                if not wit_elements or len(wit_elements) == 0:
                    continue
                element = wit_elements.get(element_id)
                text_repr = process_synoptic_unit_for_comparison(element)
                
                comparison_data.append({
                    'token': token,
                    'prefix': prefix,
                    'text': text_repr
                })
        
        # Keep old format for backward compatibility
        comparison_texts = [item['text'] for item in comparison_data]
        
        return jsonify({
            'success': True,
            'comparison_texts': comparison_texts,
            'comparison_data': comparison_data
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
        
        with open(filename, encoding='utf-8') as f:
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
    global synoptic_map, apparatus, project_files_cache
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_filepath = data.get('apparatus_filepath')
        project_files = data.get('project_files', {})
        project_files_cache = project_files

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
            witness_order = apparatus.get_witness_order()
            witness_mapping = apparatus.get_witness_to_prefix_mapping()
            # Find leiths info from witness mapping
            leiths_info = None
            leiths_prefix = None
            if leiths_path:
                leiths_filename = leiths_path.split('/')[-1]
                for _witness_id, mapping_info in witness_mapping.items():
                    if mapping_info['target_file'].endswith(leiths_filename):
                        leiths_info = {
                            'siglum': mapping_info['siglum'],
                            'synoptic_pre': mapping_info['synoptic_prefix']
                        }
                        leiths_prefix = mapping_info['synoptic_prefix']
                        break
            
            # Get corresp attribute for synoptic map loading
            corresp = apparatus.get_corresp_attribute()
            if corresp:
                # Load synoptic map from project files using class method
                try:
                    synoptic_map.load_from_project(corresp, apparatus_filepath, project_files, 
                                                 leiths_prefix=leiths_prefix, 
                                                 apparatus_witness_mapping=witness_mapping)
                except Exception as synoptic_error:
                    print(f"ERROR loading synoptic map: {synoptic_error}")
                    
            # Now process main text with synoptic map available
            main_text_content = None
            if leiths_path:
                main_text_content = resolve_text_file_from_project(leiths_path, apparatus_filepath, project_files)
            
            result = {
                'success': True,
                'message': f'Found {len(apparatus_entries)} apparatus entries',
                'leiths-info': leiths_info,
                'apparatus_filepath': apparatus_filepath,
                'apparatus_count': len(apparatus_entries),
                'apparatus_entries': apparatus_entries,
                'witness_order': witness_order,
                'witness_mapping': witness_mapping,
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
            result = parse_main_text_file_content(file_data['content'])
            return result
        
        return None
        
    except Exception:
        return None

def parse_main_text_file_content(content):
    """
    Parse text file using HeiCritPipe and return the result
    """
    try:
        
        pipeline = HeiCritPipe()
        # Get witness mapping from apparatus if available
        witness_mapping = apparatus.get_witness_to_prefix_mapping() if apparatus else {}
        
        pipeline.add_step(PythonStep(append_synoptic_links_funct, name="heicrit_append_synoptic_links"), 
                          before_step= 'create_html',
                          parameters= {'witness_mapping': witness_mapping, 
                                       'synoptic_map': synoptic_map.get_loci()})
        
        result = pipeline.execute(content, input_format="xml_string")
        return result
        
    except Exception:
        import traceback
        traceback.print_exc()
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

# Sequential processing endpoints for real progress reporting

@api.route('/apparatus/parse', methods=['POST'])
def parse_apparatus_file():
    """
    Step 1: Parse apparatus file and store in global apparatus object
    """
    global apparatus
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        apparatus_content = data.get('apparatus_content')
        apparatus_filepath = data.get('apparatus_filepath')
        project_files = data.get('project_files', {})
        
        if not apparatus_content:
            return jsonify({'error': 'No apparatus content provided'}), 400
        if not apparatus_filepath:
            return jsonify({'error': 'No apparatus filepath provided'}), 400
        
        # Create Apparatus object and parse the file
        apparatus = Apparatus(apparatus_filepath, project_files)
        
        # Get basic info for response
        apparatus_entries = apparatus.get_entries()
        
        return jsonify({
            'success': True,
            'message': f'Parsed apparatus file with {len(apparatus_entries)} entries',
            'apparatus_count': len(apparatus_entries),
            'apparatus_filepath': apparatus_filepath
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to parse apparatus: {str(e)}'}), 500

@api.route('/witnesses/load', methods=['POST'])
def load_witness_mappings():
    """
    Step 2: Extract witness mappings from parsed apparatus
    """
    global apparatus
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded. Call /apparatus/parse first.'}), 400
        
        witness_order = apparatus.get_witness_order()
        witness_mapping = apparatus.get_witness_to_prefix_mapping()
        
        # Find leiths info from witness mapping
        leiths_path = apparatus.get_leiths_path()
        leiths_info = None
        leiths_prefix = None
        if leiths_path:
            leiths_filename = leiths_path.split('/')[-1]
            for _witness_id, mapping_info in witness_mapping.items():
                if mapping_info['target_file'].endswith(leiths_filename):
                    leiths_info = {
                        'siglum': mapping_info['siglum'],
                        'synoptic_pre': mapping_info['synoptic_prefix']
                    }
                    leiths_prefix = mapping_info['synoptic_prefix']
                    break
        
        return jsonify({
            'success': True,
            'message': f'Loaded {len(witness_mapping)} witness mappings',
            'witness_count': len(witness_mapping),
            'witness_order': witness_order,
            'witness_mapping': witness_mapping,
            'leiths_info': leiths_info,
            'leiths_prefix': leiths_prefix,
            'leiths_path': leiths_path
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load witnesses: {str(e)}'}), 500

@api.route('/synoptic/load', methods=['POST'])
def load_synoptic_map():
    """
    Step 3: Process synoptic map with witness data
    """
    global synoptic_map, apparatus, project_files_cache
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded. Call /apparatus/parse first.'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        project_files = data.get('project_files', {})
        project_files_cache = project_files
        apparatus_filepath = data.get('apparatus_filepath')
        leiths_prefix = data.get('leiths_prefix')
        synoptic_filepath = data.get('synoptic_filepath')

        # Get corresp attribute for synoptic map loading (declared by the apparatus file)
        corresp = apparatus.get_corresp_attribute()

        # An explicit synoptic_filepath (chosen by the user when corresp was
        # missing/ambiguous) takes precedence over the apparatus's own corresp.
        synoptic_path_to_load = synoptic_filepath or corresp

        synoptic_loaded = False
        if synoptic_path_to_load:
            witness_mapping = apparatus.get_witness_to_prefix_mapping()
            synoptic_loaded = synoptic_map.load_from_project(
                synoptic_path_to_load, apparatus_filepath, project_files,
                leiths_prefix=leiths_prefix,
                apparatus_witness_mapping=witness_mapping)

        return jsonify({
            'success': True,
            'message': f'Loaded synoptic map with {synoptic_map.get_loci_count()} locations',
            'synoptic_map_count': synoptic_map.get_loci_count(),
            'synoptic_wits_count': synoptic_map.get_wits_count(),
            'synoptic_map': synoptic_map.get_loci(),
            'synoptic_wits': synoptic_map.get_wits(),
            'synoptic_loaded': synoptic_loaded,
            'corresp': corresp
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load synoptic map: {str(e)}'}), 500

@api.route('/maintext/generate', methods=['POST'])
def generate_main_text():
    """
    Step 4: Generate main text HTML using loaded data
    """
    global apparatus, synoptic_map
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded. Call /apparatus/parse first.'}), 400
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        leiths_path = data.get('leiths_path')
        apparatus_filepath = data.get('apparatus_filepath')
        project_files = data.get('project_files', {})
        
        main_text_content = None
        if leiths_path:
            main_text_content = resolve_text_file_from_project(leiths_path, apparatus_filepath, project_files)
        
        return jsonify({
            'success': True,
            'message': 'Generated main text HTML',
            'main_text': main_text_content,
            'has_main_text': main_text_content is not None
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to generate main text: {str(e)}'}), 500

@api.route('/project/finalize', methods=['POST'])
def finalize_project():
    """
    Step 5: Return final combined project data
    """
    global apparatus, synoptic_map, project_files_cache
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded. Call /apparatus/parse first.'}), 400
        
        # Get all the processed data
        apparatus_entries = apparatus.get_entries()
        witness_order = apparatus.get_witness_order()
        witness_mapping = apparatus.get_witness_to_prefix_mapping()
        
        # Find leiths info
        leiths_path = apparatus.get_leiths_path()
        leiths_info = None
        if leiths_path:
            leiths_filename = leiths_path.split('/')[-1]
            for _witness_id, mapping_info in witness_mapping.items():
                if mapping_info['target_file'].endswith(leiths_filename):
                    leiths_info = {
                        'siglum': mapping_info['siglum'],
                        'synoptic_pre': mapping_info['synoptic_prefix']
                    }
                    break
        
        return jsonify({
            'success': True,
            'message': f'Project finalized with {len(apparatus_entries)} apparatus entries',
            'apparatus_count': len(apparatus_entries),
            'apparatus_entries': apparatus_entries,
            'witness_order': witness_order,
            'witness_mapping': witness_mapping,
            'leiths_info': leiths_info,
            'synoptic_map': synoptic_map.get_loci(),
            'synoptic_map_count': synoptic_map.get_loci_count(),
            'synoptic_wits': synoptic_map.get_wits(),
            'synoptic_wits_count': synoptic_map.get_wits_count(),
            'synoptic_file': synoptic_map.get_file_path()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to finalize project: {str(e)}'}), 500

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
            # Don't override an existing synoptic map that has witness elements loaded from project
            if synoptic_map.get_wits_count() > 0:
                # Check if any witnesses have elements (indicating project-based loading)
                has_elements = False
                for wit_id in synoptic_map.get_all_wit_idents():
                    wit_elements = synoptic_map.get_wit_elements(wit_id)
                    if wit_elements and len(wit_elements) > 0:
                        has_elements = True
                        break
                
                if has_elements:
                    return jsonify({'error': 'Synoptic map already loaded from project with witness elements. Cannot override.'}), 400
            
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


@api.route('/apparatus/save', methods=['POST'])
def save_apparatus_entries():
    """
    Save new apparatus entries to the apparatus file
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        apparatus_file = data.get('apparatus_file')
        new_entries = data.get('new_entries', [])
        project_directory = data.get('project_directory', '')
        
        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        
        if not new_entries:
            return jsonify({'error': 'No new entries to save'}), 400
        
        # Resolve apparatus file path
        # Check if apparatus_file already starts with project_directory
        print(apparatus_file, project_directory)
        if not os.path.isabs(apparatus_file):
            if apparatus_file.startswith(project_directory + '/'):
                # apparatus_file already contains project_directory, use as-is
                pass
            else:
                # apparatus_file is relative, join with project_directory
                apparatus_file = os.path.join(project_directory, apparatus_file)
        
        print(f"Resolved apparatus file path: {apparatus_file}")
        print(f"Current working directory: {os.getcwd()}")
        print(f"File exists: {os.path.exists(apparatus_file)}")
        
        # Try resolving from project root instead of backend directory
        if not os.path.exists(apparatus_file):
            project_root_path = os.path.join('..', apparatus_file)
            print(f"Trying from project root: {project_root_path}")
            print(f"Project root path exists: {os.path.exists(project_root_path)}")
            if os.path.exists(project_root_path):
                apparatus_file = project_root_path
        
        if not os.path.exists(apparatus_file):
            print(f"ERROR: File not found at {apparatus_file}")
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404
        
        with open(apparatus_file, encoding='utf-8') as f:
            content = f.read()
        
        root = et.fromstring(content.encode('utf-8'))
        
        # Find the text body where apparatus entries are stored
        body = root.find('.//{http://www.tei-c.org/ns/1.0}body')
        if body is None:
            return jsonify({'error': 'Could not find body element in apparatus file'}), 400
        
        
        # Create new apparatus entries and insert them in location order
        entries_added = 0
        for entry_data in new_entries:
            new_app = create_apparatus_element(entry_data)
            insert_apparatus_entry_in_order(body, new_app, entry_data['loc'])
            entries_added += 1
        
        output_content = et.tostring(root, encoding='unicode', pretty_print=True)
        
        with open(apparatus_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(output_content)

        
        return jsonify({
            'success': True,
            'message': f'Successfully added {entries_added} new apparatus entries',
            'entries_added': entries_added
        })
        
    except Exception as e:
        print(f"ERROR: Exception occurred: {str(e)}")
        print(f"Exception type: {type(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to save apparatus entries: {str(e)}'}), 500


def _set_element_content(element, data):
    """Set element text/children content from entry data dict."""
    TEI = 'http://www.tei-c.org/ns/1.0'
    children = data.get('children')
    if children:
        element.text = None
        for child_data in children:
            child = et.SubElement(element, f'{{{TEI}}}{child_data["tag"]}')
            child.text = child_data.get('text', '')
            child.tail = child_data.get('tail', '')
    else:
        element.text = data.get('text', '')


def create_apparatus_element(entry_data):
    """
    Create an XML apparatus element from entry data
    """
    TEI = 'http://www.tei-c.org/ns/1.0'
    app = et.Element(f'{{{TEI}}}app')
    app.set('loc', str(entry_data['loc']))
    app.set('corresp', entry_data['corresp'])

    if entry_data.get('lemma'):
        lemma_data = entry_data['lemma']
        lemma = et.SubElement(app, f'{{{TEI}}}lem')
        _set_element_content(lemma, lemma_data)
        for attr_name, attr_value in lemma_data['attributes'].items():
            lemma.set(attr_name, attr_value)

    for reading_data in entry_data.get('readings', []):
        rdg = et.SubElement(app, f'{{{TEI}}}rdg')
        _set_element_content(rdg, reading_data)
        for attr_name, attr_value in reading_data['attributes'].items():
            rdg.set(attr_name, attr_value)

    return app


def insert_apparatus_entry_in_order(body, new_app, loc):
    """
    Insert the new apparatus entry in the correct location order
    """
    loc_num = int(loc) if loc.isdigit() else 0

    # Find all existing app elements
    apps = body.findall('.//{http://www.tei-c.org/ns/1.0}app')

    # Find the correct insertion point
    insert_index = len(apps)  # Default to end

    for i, app in enumerate(apps):
        app_loc = app.get('loc', '0')
        app_loc_num = int(app_loc) if app_loc.isdigit() else 0

        if loc_num < app_loc_num:
            insert_index = i
            break

    # Insert the new element
    if insert_index < len(apps):
        # Insert before the found element
        parent = apps[insert_index].getparent()
        parent.insert(list(parent).index(apps[insert_index]), new_app)
    else:
        # Insert at the end
        if apps:
            parent = apps[-1].getparent()
            parent.append(new_app)
        else:
            # No existing apps, add to body
            body.append(new_app)


@api.route('/synoptic/table', methods=['POST'])
def get_synoptic_table():
    """
    Return the synoptic map as a table suitable for spreadsheet editing.
    Expected JSON: { "file_path": "project-relative path to synoptic map" }
    Returns: { "witnesses": [{prefix, siglum},...], "rows": [{n, cells},...], "file_path": "..." }
    """
    global project_files_cache
    try:
        from heipy.parsers import HeiEditionsParser
        from io import BytesIO

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        file_path = data.get('file_path')
        if not file_path:
            return jsonify({'error': 'No file_path provided'}), 400

        # Look up file content from the cached project files
        file_data = find_file_in_project(file_path, project_files_cache)
        if not file_data:
            return jsonify({'error': f'File not found in project: {file_path}'}), 404

        content = file_data['content']

        parser = HeiEditionsParser()
        doc = et.parse(BytesIO(content.encode('utf-8')), parser)
        root = doc.getroot()
        TEI = 'http://www.tei-c.org/ns/1.0'
        ns_map = {'tei': TEI}

        # Collect ordered witnesses from all prefixDef elements
        synoptic_prefix_defs = root.xpath(
            './/tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]',
            namespaces=ns_map
        )
        # Prefer siglums already resolved by the loaded Apparatus (it knows how to
        # look them up via the new format's external witness-index file, which
        # witness fragment files themselves carry no inline siglum for), falling
        # back to reading an inline idno directly from the witness file (old
        # format, or when no apparatus is currently loaded).
        apparatus_prefix_siglum = {}
        if apparatus is not None:
            try:
                for mapping_info in apparatus.get_witness_to_prefix_mapping().values():
                    prefix = mapping_info.get('synoptic_prefix')
                    if prefix:
                        apparatus_prefix_siglum[prefix] = mapping_info.get('siglum')
            except Exception:
                pass

        witnesses = []
        for pd in synoptic_prefix_defs:
            ident = pd.get('ident')
            replacement = pd.get('replacementPattern', '')
            # Strip trailing "/$1" to get the relative witness file path
            replacement_clean = replacement[:-3] if replacement.endswith('/$1') else replacement

            # Resolve the witness file path relative to the synoptic map's location
            witness_rel_path = resolve_relative_path(replacement_clean, file_path)

            # Strip leading path components to get a project-relative key
            file_name = replacement_clean.lstrip('.').lstrip('/')

            siglum = apparatus_prefix_siglum.get(ident)
            if not siglum:
                try:
                    witness_data = find_file_in_project(witness_rel_path, project_files_cache)
                    if witness_data:
                        witness_doc = et.parse(BytesIO(witness_data['content'].encode('utf-8')), parser)
                        siglum_el = witness_doc.getroot().find(
                            './/tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns_map
                        )
                        if siglum_el is not None and siglum_el.text:
                            siglum = siglum_el.text.strip()
                except Exception:
                    pass

            witnesses.append({
                'prefix': ident,
                'siglum': siglum or ident,
                'file_name': file_name
            })

        prefixes = [w['prefix'] for w in witnesses]

        # Parse link elements in document order
        link_elements = root.xpath('.//tei:link', namespaces=ns_map)
        rows = []
        for link in link_elements:
            n = link.get('n', '')
            target_str = link.get('target', '')
            target_tokens = [t.strip() for t in target_str.split() if t.strip()]
            cells = {}
            for token in target_tokens:
                if ':' in token:
                    prefix, value = token.split(':', 1)
                    if prefix in prefixes:
                        cells[prefix] = value
            rows.append({'n': n, 'cells': cells})

        return jsonify({
            'success': True,
            'witnesses': witnesses,
            'rows': rows,
            'file_path': file_path
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to load synoptic table: {str(e)}'}), 500


@api.route('/synoptic/save-table', methods=['POST'])
def save_synoptic_table():
    """
    Save an edited synoptic map table back to the XML file.
    Expected JSON: { "file_path": "...", "rows": [{n, cells: {prefix: value}},...] }
    Reads source from project_files_cache, writes to disk, returns xml_content for download fallback.
    """
    global project_files_cache
    try:
        from heipy.parsers import HeiEditionsParser
        from io import BytesIO

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        file_path = data.get('file_path')
        rows = data.get('rows', [])
        if not file_path:
            return jsonify({'error': 'No file_path provided'}), 400

        # Read source from cached project files
        file_data = find_file_in_project(file_path, project_files_cache)
        if not file_data:
            return jsonify({'error': f'File not found in project cache: {file_path}'}), 404

        content = file_data['content']

        parser = HeiEditionsParser()
        doc = et.parse(BytesIO(content.encode('utf-8')), parser)
        root = doc.getroot()
        TEI = 'http://www.tei-c.org/ns/1.0'
        ns_map = {'tei': TEI}

        # Get witness order from prefixDef (preserves column ordering)
        synoptic_prefix_defs = root.xpath(
            './/tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]',
            namespaces=ns_map
        )
        witness_order = [pd.get('ident') for pd in synoptic_prefix_defs if pd.get('ident')]

        # Find the standOff element (or body if standOff absent) that holds <link> elements
        standoff = root.find(f'{{{TEI}}}standOff')
        if standoff is None:
            link_els = root.xpath('.//tei:link', namespaces=ns_map)
            if link_els:
                standoff = link_els[0].getparent()
            else:
                standoff = root

        # Remove all existing link elements
        for link_el in standoff.findall(f'{{{TEI}}}link'):
            standoff.remove(link_el)

        # Rebuild link elements from rows
        for row in rows:
            n = str(row.get('n', '')).strip()
            if not n:
                continue
            cells = row.get('cells', {})
            target_parts = []
            for prefix in witness_order:
                value = cells.get(prefix, '').strip()
                if value:
                    target_parts.append(f'{prefix}:{value}')
            for prefix, value in cells.items():
                if prefix not in witness_order and value.strip():
                    target_parts.append(f'{prefix}:{value.strip()}')

            link_el = et.SubElement(standoff, f'{{{TEI}}}link')
            link_el.set('n', n)
            link_el.set('target', ' '.join(target_parts))
            link_el.tail = '\n      '

        output = '<?xml version="1.0" encoding="UTF-8"?>\n' + et.tostring(root, encoding='unicode', pretty_print=True)

        # Update cache so subsequent loads within the session reflect the changes
        for project_path, pf_data in project_files_cache.items():
            if project_path.endswith(file_path) or project_path == file_path:
                pf_data['content'] = output
                break

        # Try to write to disk (backend runs from backend/ dir, project is at ../<file_path>)
        disk_written = False
        for candidate in [file_path, os.path.join('..', file_path)]:
            if os.path.exists(candidate):
                with open(candidate, 'w', encoding='utf-8') as f:
                    f.write(output)
                disk_written = True
                break

        return jsonify({
            'success': True,
            'message': f'Saved {len(rows)} rows' + ('' if disk_written else ' (download to persist)'),
            'rows_saved': len(rows),
            'disk_written': disk_written,
            'xml_content': output,
            'filename': file_path.split('/')[-1]
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to save synoptic table: {str(e)}'}), 500


