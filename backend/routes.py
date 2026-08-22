from flask import Blueprint, request, jsonify
import os
from lxml import etree as et

from heipy.heipipe.steps import PythonStep
# from heipy.heipipe.step_library.append_synoptic_links import append_synoptic_links_funct
from heipy.namespaces import ns

from load_functions import resolve_relative_path, find_file_in_project
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct
from synoptic_map import SynopticMap
from apparatus import (
    Apparatus, process_synoptic_unit_for_comparison, html_note_to_tei,
    build_new_format_app_element, build_rdg_element, ALLOWED_NEW_FORMAT_ANA
)



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
    global apparatus, project_files_cache
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_content = data.get('apparatus_content')
        apparatus_filepath = data.get('apparatus_filepath')
        project_files = data.get('project_files', {})
        # Cache here - this is the only step in the open sequence that's
        # still guaranteed to receive the full project_files payload; the
        # later steps (synoptic/load, maintext/generate) now reuse this
        # cache instead of requiring it to be re-sent (see routes.py's
        # /synoptic/load and /maintext/generate).
        project_files_cache = project_files

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

        # project_files doesn't change within a single project-open sequence -
        # /apparatus/parse already sent and cached the full set, so accept an
        # omitted/empty project_files here and reuse the cache instead of
        # requiring the (potentially very large) payload to be re-sent.
        project_files = data.get('project_files') or project_files_cache
        if data.get('project_files'):
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
        synoptic_error = None
        if synoptic_path_to_load:
            witness_mapping = apparatus.get_witness_to_prefix_mapping()
            synoptic_loaded = synoptic_map.load_from_project(
                synoptic_path_to_load, apparatus_filepath, project_files,
                leiths_prefix=leiths_prefix,
                apparatus_witness_mapping=witness_mapping)
            if not synoptic_loaded:
                # Distinguish "found the file but its content is invalid" from
                # "couldn't resolve/find a file" - only the latter should make
                # the frontend fall back to letting the user pick another file.
                synoptic_error = synoptic_map.get_parse_error()

        return jsonify({
            'success': True,
            'message': f'Loaded synoptic map with {synoptic_map.get_loci_count()} locations',
            'synoptic_map_count': synoptic_map.get_loci_count(),
            'synoptic_wits_count': synoptic_map.get_wits_count(),
            'synoptic_map': synoptic_map.get_loci(),
            'synoptic_wits': synoptic_map.get_wits(),
            'synoptic_loaded': synoptic_loaded,
            'synoptic_error': synoptic_error,
            # Set as soon as the file is found, even if parsing it then fails,
            # so the synoptic map editor can still open it (e.g. to fix a
            # synoptic_error) without the apparatus having loaded successfully.
            'synoptic_file': synoptic_map.get_file_path(),
            'corresp': corresp
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load synoptic map: {str(e)}'}), 500

@api.route('/maintext/generate', methods=['POST'])
def generate_main_text():
    """
    Step 4: Generate main text HTML using loaded data
    """
    global apparatus, synoptic_map, project_files_cache
    try:
        if apparatus is None:
            return jsonify({'error': 'No apparatus loaded. Call /apparatus/parse first.'}), 400

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        leiths_path = data.get('leiths_path')
        apparatus_filepath = data.get('apparatus_filepath')
        # project_files doesn't change within a single project-open sequence -
        # reuse the cache populated by /apparatus/parse instead of requiring
        # the (potentially very large) payload to be re-sent here too.
        project_files = data.get('project_files') or project_files_cache
        if data.get('project_files'):
            project_files_cache = project_files
        
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
            else:
                parse_error = synoptic_map.get_parse_error()
                return jsonify({
                    'error': (parse_error or {}).get('message', 'Failed to parse synoptic map content'),
                    'synoptic_error': parse_error
                }), 400

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


def resolve_apparatus_file_on_disk(apparatus_file, project_directory):
    """
    Resolve an apparatus file path (as sent by the frontend, relative to the
    project directory) to an actual path on disk, trying the project-root
    fallback the same way the apparatus write routes need to.
    Returns None if no such file can be found.
    """
    if project_directory and os.path.isabs(project_directory):
        # The Electron desktop app's native "Open Project" dialog sends the
        # real absolute directory path here (backend/routes.py's cwd is
        # always inside the app bundle, not wherever the project actually
        # lives - see electron/main.js's dialog:open-project-directory).
        # apparatus_file still carries the directory's own name as its
        # leading segment (see frontend/app.js's readFilesIntoProjectFiles),
        # so strip that before joining or it would be doubled.
        dir_name = os.path.basename(project_directory.rstrip('/'))
        relative = apparatus_file
        if relative.startswith(dir_name + '/'):
            relative = relative[len(dir_name) + 1:]
        candidate = os.path.join(project_directory, relative)
        return candidate if os.path.exists(candidate) else None

    if not os.path.isabs(apparatus_file):
        if apparatus_file.startswith(project_directory + '/'):
            # apparatus_file already contains project_directory, use as-is
            pass
        else:
            apparatus_file = os.path.join(project_directory, apparatus_file)

    if not os.path.exists(apparatus_file):
        # Try resolving from project root instead of backend directory
        project_root_path = os.path.join('..', apparatus_file)
        if os.path.exists(project_root_path):
            apparatus_file = project_root_path

    return apparatus_file if os.path.exists(apparatus_file) else None


def write_apparatus_file_and_refresh(resolved_file, apparatus_file, root):
    """
    Serialize root, write it to resolved_file on disk, keep project_files_cache
    in sync (the same pattern /synoptic/save-table already uses), and
    reconstruct the global `apparatus` object from the fresh content so the
    caller's response - and any later read via the cache - reflects the write.

    apparatus_file must be the project-relative path as received from the
    frontend request (the same convention /apparatus/parse already uses to
    construct Apparatus), NOT resolved_file's on-disk path - project_files_cache
    keys and Apparatus's file-resolution logic both expect the project-relative
    form.
    """
    global apparatus, project_files_cache

    output_content = et.tostring(root, encoding='unicode', pretty_print=True)
    full_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + output_content

    with open(resolved_file, 'w', encoding='utf-8') as f:
        f.write(full_content)

    for project_path, pf_data in project_files_cache.items():
        if project_path.endswith(apparatus_file) or project_path == apparatus_file:
            pf_data['content'] = full_content
            break

    apparatus = Apparatus(apparatus_file, project_files_cache)
    return apparatus


@api.route('/apparatus/note/save', methods=['POST'])
def save_apparatus_note():
    """
    Save an edited note (new-format entries only) back into the apparatus file,
    attaching it to a specific entry's <lem> or <rdg> child as a <note> element
    (with <mentioned> for italicized spans, converted from the frontend's
    contenteditable HTML).
    Expected JSON: {
        apparatus_file, project_directory,
        entry_index (0-based position among <app> elements in document order),
        target: 'lemma' | 'reading',
        reading_index (required when target == 'reading'),
        note_html: str (may be empty/whitespace-only to remove the note)
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_file = data.get('apparatus_file')
        project_directory = data.get('project_directory', '')
        entry_index = data.get('entry_index')
        target = data.get('target')
        reading_index = data.get('reading_index')
        note_html = data.get('note_html', '')

        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        if entry_index is None or target not in ('lemma', 'reading'):
            return jsonify({'error': 'entry_index and a valid target (lemma/reading) are required'}), 400

        resolved_file = resolve_apparatus_file_on_disk(apparatus_file, project_directory)
        if not resolved_file:
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404

        with open(resolved_file, encoding='utf-8') as f:
            content = f.read()

        root = et.fromstring(content.encode('utf-8'))
        app_elements = root.xpath('.//tei:app', namespaces=ns)
        if entry_index < 0 or entry_index >= len(app_elements):
            return jsonify({'error': f'No apparatus entry at index {entry_index}'}), 404
        app_element = app_elements[entry_index]

        if target == 'lemma':
            host_element = app_element.find('tei:lem', namespaces=ns)
            if host_element is None:
                return jsonify({'error': 'This entry has no <lem> element to attach a note to'}), 400
        else:
            rdg_elements = app_element.findall('tei:rdg', namespaces=ns)
            if reading_index is None or reading_index < 0 or reading_index >= len(rdg_elements):
                return jsonify({'error': f'No reading at index {reading_index}'}), 400
            host_element = rdg_elements[reading_index]

        existing_note = host_element.find('tei:note', namespaces=ns)
        if existing_note is not None:
            host_element.remove(existing_note)

        if note_html and note_html.strip():
            host_element.append(html_note_to_tei(note_html))

        write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)

        return jsonify({'success': True})

    except Exception as e:
        print(f"ERROR: Could not save apparatus note: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to save note: {str(e)}'}), 500


def _load_app_elements_for_write(apparatus_file, project_directory):
    """
    Resolve+read+parse the apparatus file fresh from disk for a write
    operation, returning (resolved_file, root, app_elements). Raises the same
    exceptions the caller's try/except already handles; callers should check
    for a None resolved_file (file not found) themselves before proceeding.
    """
    resolved_file = resolve_apparatus_file_on_disk(apparatus_file, project_directory)
    if not resolved_file:
        return None, None, None

    with open(resolved_file, encoding='utf-8') as f:
        content = f.read()

    root = et.fromstring(content.encode('utf-8'))
    app_elements = root.xpath('.//tei:app', namespaces=ns)
    return resolved_file, root, app_elements


def _validate_new_format_readings(readings):
    """
    Validate the shared 'readings' shape used by entry create/update. Returns
    an error string, or None if valid.

    Transposition readings (ana == hc:TranspositionVariant) are structurally
    different from the other three types: they carry 'links' (one base token
    paired with a list of witness tokens sharing that same position) instead
    of 'ptrs', and an <app> anchors via its first <link> rather than @target -
    so an entry can't mix transposition and non-transposition readings.
    """
    if not readings or not isinstance(readings, list):
        return 'At least one reading is required'

    ana_values = {reading.get('ana') for reading in readings}
    is_transposition = 'hc:TranspositionVariant' in ana_values
    if is_transposition and len(ana_values) > 1:
        return 'Transposition readings cannot be mixed with other variant types in the same entry'

    for reading in readings:
        if not reading.get('wit'):
            return 'Each reading needs at least one witness'
        if reading.get('ana') not in ALLOWED_NEW_FORMAT_ANA:
            return f"Invalid or missing variant type (ana): {reading.get('ana')!r}"

        if reading.get('ana') == 'hc:TranspositionVariant':
            if reading.get('ptrs'):
                return 'Transposition readings use links, not ptrs'
            links = reading.get('links')
            if not links:
                return 'Each transposition reading needs at least one link pair'
            for pair in links:
                if not pair.get('base') or not pair.get('witnesses'):
                    return 'Each transposition link needs a base token and at least one witness token reference'
        else:
            if reading.get('links'):
                return 'Only transposition readings use links'
            if not reading.get('ptrs'):
                return 'Each reading needs at least one token reference'

    return None


@api.route('/apparatus/entry/create', methods=['POST'])
def create_apparatus_entry_new_format():
    """
    Create a new apparatus entry in the new data model. Either target/<ptr>
    based (Addition/Omission/Substitution) or, for a transposition entry,
    target-less/<link> based (readings carry 'links' instead of 'ptrs' - see
    _validate_new_format_readings).
    Expected JSON: {
        apparatus_file, project_directory,
        target: "b:range(w_71_2_4,w_71_2_5)",  # omitted/null for transposition-only entries
        readings: [ { wit: [ids], ana: "hc:...", ptrs: [...] | links: [{base, witnesses: [...]}, ...] }, ... ]
    }
    Response: { success, apparatus_entries: [...], created_entry_id }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_file = data.get('apparatus_file')
        project_directory = data.get('project_directory', '')
        target = data.get('target')
        readings = data.get('readings')

        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        readings_error = _validate_new_format_readings(readings)
        if readings_error:
            return jsonify({'error': readings_error}), 400

        is_transposition = readings[0].get('ana') == 'hc:TranspositionVariant'
        if not is_transposition and not target:
            return jsonify({'error': 'target is required'}), 400

        resolved_file, root, app_elements = _load_app_elements_for_write(apparatus_file, project_directory)
        if not resolved_file:
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404

        list_app = root.find('.//tei:listApp', namespaces=ns)
        parent = list_app if list_app is not None else root.find('.//tei:body', namespaces=ns)
        if parent is None:
            return jsonify({'error': 'Could not find <listApp> or <body> in apparatus file'}), 400

        new_app = build_new_format_app_element(target, readings)
        parent.append(new_app)

        updated_apparatus = write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)
        fresh_entries = updated_apparatus.get_entries()

        # Keep the file grouped by verse: if appending landed the new entry out
        # of verse order (e.g. creating a verse-2 entry after verse 3-20
        # already exist), re-sort <listApp>'s children by verse number and
        # write once more. Reuses the loc values get_entries() just computed
        # above - no extra text/witness resolution beyond what this request
        # already had to do to build the response.
        if list_app is not None:
            try:
                numeric_locs = [int(e.get('loc')) for e in fresh_entries]
                already_sorted = all(
                    numeric_locs[i] <= numeric_locs[i + 1] for i in range(len(numeric_locs) - 1))
            except (TypeError, ValueError):
                already_sorted = True  # can't safely reason about non-numeric locs - leave order as-is

            if not already_sorted:
                current_children = list(list_app)
                for i in sorted(range(len(current_children)), key=lambda i: numeric_locs[i]):
                    list_app.append(current_children[i])  # append moves an existing child - reconstructs sorted order
                updated_apparatus = write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)
                fresh_entries = updated_apparatus.get_entries()

        return jsonify({
            'success': True,
            'apparatus_entries': fresh_entries,
            'created_entry_id': len(fresh_entries)
        })

    except Exception as e:
        print(f"ERROR: Could not create apparatus entry: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to create entry: {str(e)}'}), 500


@api.route('/apparatus/entry/update', methods=['POST'])
def update_apparatus_entry_new_format():
    """
    Update an existing new-format apparatus entry's target/readings.
    Expected JSON: {
        apparatus_file, project_directory,
        entry_index (0-based, document order among <app> elements),
        target, readings: [ { wit, ana, ptrs }, ... ]
    }
    Rejects (400) transposition entries (no @target) and explicit-<lem>
    entries (has a <lem> child) - both stay read-only in this pass.
    Rebuild strategy: wholesale-replaces the <app>'s children, but preserves
    each existing <rdg>'s <note> by matching it to the new <rdg> at the same
    index position. This is not a true diff - if an edit reorders/adds/removes
    reading groups such that index positions shift, a note could reattach to
    the wrong reading or be dropped. Acceptable for now since reading-group
    index ordering is stable within a normal edit session.
    Response: { success, apparatus_entries: [...] }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_file = data.get('apparatus_file')
        project_directory = data.get('project_directory', '')
        entry_index = data.get('entry_index')
        target = data.get('target')
        readings = data.get('readings')

        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        if entry_index is None:
            return jsonify({'error': 'entry_index is required'}), 400
        if not target:
            return jsonify({'error': 'target is required'}), 400
        readings_error = _validate_new_format_readings(readings)
        if readings_error:
            return jsonify({'error': readings_error}), 400

        resolved_file, root, app_elements = _load_app_elements_for_write(apparatus_file, project_directory)
        if not resolved_file:
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404
        if entry_index < 0 or entry_index >= len(app_elements):
            return jsonify({'error': f'No apparatus entry at index {entry_index}'}), 404

        app_element = app_elements[entry_index]

        if app_element.get('target') is None:
            return jsonify({'error': 'This entry is a transposition and cannot be edited here'}), 400
        if app_element.find('tei:lem', namespaces=ns) is not None:
            return jsonify({'error': 'This entry has an explicit <lem> override and cannot be edited here'}), 400

        old_rdg_elements = app_element.findall('tei:rdg', namespaces=ns)
        preserved_notes = {}
        for index, rdg in enumerate(old_rdg_elements):
            note_element = rdg.find('tei:note', namespaces=ns)
            if note_element is not None:
                preserved_notes[index] = note_element

        for child in list(app_element):
            app_element.remove(child)
        app_element.set('target', target)

        for index, reading in enumerate(readings):
            rdg_element = build_rdg_element(reading['wit'], reading['ana'], reading['ptrs'])
            if index in preserved_notes:
                rdg_element.append(preserved_notes[index])
            app_element.append(rdg_element)

        updated_apparatus = write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)

        return jsonify({
            'success': True,
            'apparatus_entries': updated_apparatus.get_entries()
        })

    except Exception as e:
        print(f"ERROR: Could not update apparatus entry: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to update entry: {str(e)}'}), 500


@api.route('/apparatus/entry/delete', methods=['POST'])
def delete_apparatus_entry_new_format():
    """
    Delete an existing new-format apparatus entry.
    Expected JSON: { apparatus_file, project_directory, entry_index }
    Response: { success, apparatus_entries: [...] }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_file = data.get('apparatus_file')
        project_directory = data.get('project_directory', '')
        entry_index = data.get('entry_index')

        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        if entry_index is None:
            return jsonify({'error': 'entry_index is required'}), 400

        resolved_file, root, app_elements = _load_app_elements_for_write(apparatus_file, project_directory)
        if not resolved_file:
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404
        if entry_index < 0 or entry_index >= len(app_elements):
            return jsonify({'error': f'No apparatus entry at index {entry_index}'}), 404

        app_element = app_elements[entry_index]
        app_element.getparent().remove(app_element)

        updated_apparatus = write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)

        return jsonify({
            'success': True,
            'apparatus_entries': updated_apparatus.get_entries()
        })

    except Exception as e:
        print(f"ERROR: Could not delete apparatus entry: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to delete entry: {str(e)}'}), 500


@api.route('/apparatus/entry/reorder', methods=['POST'])
def reorder_apparatus_entries_new_format():
    """
    Persist a manual reorder of a set of existing apparatus entries (e.g. the
    subentries sharing one verse/corresp group) to the file. The referenced
    entries are repositioned, in the given relative order, as a contiguous
    block starting at the position of the earliest one among them - every
    other <app> element's relative position is left untouched. Cross-verse
    order is derived client-side from each entry's line number and doesn't
    depend on raw file order, so this only needs to reposition the given set.
    Expected JSON: {
        apparatus_file, project_directory,
        entry_order: [entry_index, ...]  # 0-based, document order (same
                                           # addressing as entry_index on
                                           # update/delete) - the CURRENT
                                           # indices of the entries being
                                           # reordered, listed in their NEW
                                           # desired sequence
    }
    Response: { success, apparatus_entries: [...] }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        apparatus_file = data.get('apparatus_file')
        project_directory = data.get('project_directory', '')
        entry_order = data.get('entry_order')

        if not apparatus_file:
            return jsonify({'error': 'No apparatus file specified'}), 400
        if not entry_order or len(entry_order) < 2:
            return jsonify({'error': 'entry_order must list at least 2 entry indices'}), 400
        if len(set(entry_order)) != len(entry_order):
            return jsonify({'error': 'entry_order contains duplicate indices'}), 400

        resolved_file, root, app_elements = _load_app_elements_for_write(apparatus_file, project_directory)
        if not resolved_file:
            return jsonify({'error': f'Apparatus file not found: {apparatus_file}'}), 404

        if any(i < 0 or i >= len(app_elements) for i in entry_order):
            return jsonify({'error': 'entry_order contains an out-of-range index'}), 400

        parent = app_elements[entry_order[0]].getparent()
        # Captured before removing anything: the earliest-positioned entry in
        # the set is always at or before every other index being moved, so
        # later removals (which only touch entries at or after this point)
        # can't invalidate this index.
        insert_index = list(parent).index(app_elements[min(entry_order)])

        elements_to_move = [app_elements[i] for i in entry_order]
        for element in elements_to_move:
            parent.remove(element)
        for offset, element in enumerate(elements_to_move):
            parent.insert(insert_index + offset, element)

        updated_apparatus = write_apparatus_file_and_refresh(resolved_file, apparatus_file, root)

        return jsonify({
            'success': True,
            'apparatus_entries': updated_apparatus.get_entries()
        })

    except Exception as e:
        print(f"ERROR: Could not reorder apparatus entries: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Failed to reorder entries: {str(e)}'}), 500


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

        # Rebuild link elements from rows. A row is only meaningful if it has
        # at least one witness target - `n` is NOT a reliable presence check:
        # new-format synoptic maps (e.g. Iwein's) legitimately omit @n on
        # every <link>, so filtering on blank `n` here previously discarded
        # essentially the entire file on save.
        for row in rows:
            n = str(row.get('n', '')).strip()
            cells = row.get('cells', {})
            target_parts = []
            for prefix in witness_order:
                value = cells.get(prefix, '').strip()
                if value:
                    target_parts.append(f'{prefix}:{value}')
            for prefix, value in cells.items():
                if prefix not in witness_order and value.strip():
                    target_parts.append(f'{prefix}:{value.strip()}')

            if not target_parts:
                continue

            link_el = et.SubElement(standoff, f'{{{TEI}}}link')
            if n:
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


