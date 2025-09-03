from flask import Blueprint, request, jsonify
import os
from lxml import etree as et

from heipy.heipipe.steps import PythonStep
from heipy.namespaces import prefix_format
# from heipy.heipipe.step_library.append_synoptic_links import append_synoptic_links_funct

from load_functions import resolve_relative_path, find_file_in_project
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct
from synoptic_map import SynopticMap
from apparatus import Apparatus



api = Blueprint('api', __name__)

# Global variables
synoptic_map = SynopticMap()
apparatus = None  # Global apparatus object for frontend modifications 


def process_synoptic_token(el:et.Element) -> str:
    tag_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    result = ''
    if tag_name in ['w', 'pc']:
        result += f"<span class='syn-token syn-tei-{tag_name}' data-token-id='{el.get(prefix_format('xml','id'))}'>"
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
        result += "</span>"
    elif tag_name in ['c']:
        result += "<span class='syn-token syn-tei-space'> </span>"
    elif tag_name in ['choice', 'lg', 'l']:
        for child in el:
            result += process_synoptic_token(child)
        if el.tail is not None and el.tail.strip() != '':
            result += el.tail
    elif tag_name in ['orig', 'sic', 'hi', 'initial']:
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
        if el.tail is not None and el.tail.strip() != '':
            result += el.tail
    elif tag_name in ['titlePart']:
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
            
        
    return result


def process_synoptic_unit_for_comparison(element:et.Element) -> str:
    """
    Process an XML synoptic unit and return a string representation for comparison.
    
    Args:
        element: The lxml etree Element to process
        
    Returns:
        String representation of the element content
    """
    if element is None:
        return '<div class="synoptic-content-no-data">Stelle nicht gefunden</div>'
    
    try:
        # Get the text content of the element, stripping whitespace
        # line_content = ''.join(element.itertext()).strip()
        line_content = ''
        for el in element:
            line_content += process_synoptic_token(el)
        
        # If no text content, try to get element info
        if not line_content:
            for el in element:
                print(el)
            tag_name = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag_name == 'gap':
                return "<div class='synoptic-content-om'>om.</div>"
            return f"[{tag_name} element - no text content]"
        
        return line_content
        
    except Exception as e:
        return f"[Error processing element: {str(e)}]"



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
    global synoptic_map, apparatus
    try:    
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        apparatus_filepath = data.get('apparatus_filepath')
        project_files = data.get('project_files', {})
        
        
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
                for witness_id, mapping_info in witness_mapping.items():
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
        # Get witness mapping from apparatus if available
        witness_mapping = apparatus.get_witness_to_prefix_mapping() if apparatus else {}
        
        pipeline.add_step(PythonStep(append_synoptic_links_funct, name="heicrit_append_synoptic_links"), 
                          before_step= 'create_html',
                          parameters= {'witness_mapping': witness_mapping, 
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
        print("=== apparatus/save endpoint called ===")
        
        data = request.get_json()
        if not data:
            print("ERROR: No data provided")
            return jsonify({'error': 'No data provided'}), 400
        
        print(f"Received data: {data}")
        
        apparatus_file = data.get('apparatus_file')
        new_entries = data.get('new_entries', [])
        project_directory = data.get('project_directory', '')
        
        print(f"apparatus_file: {apparatus_file}")
        print(f"project_directory: {project_directory}")
        print(f"new_entries count: {len(new_entries)}")
        
        if not apparatus_file:
            print("ERROR: No apparatus file specified")
            return jsonify({'error': 'No apparatus file specified'}), 400
        
        if not new_entries:
            print("ERROR: No new entries to save")
            return jsonify({'error': 'No new entries to save'}), 400
        
        # Resolve apparatus file path
        # Check if apparatus_file already starts with project_directory
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
        
        # Load and parse the apparatus file
        print("Loading apparatus file...")
        with open(apparatus_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print(f"File loaded, content length: {len(content)}")
        
        print("Parsing XML...")
        root = et.fromstring(content.encode('utf-8'))
        print("XML parsed successfully")
        
        # Find the text body where apparatus entries are stored
        body = root.find('.//{http://www.tei-c.org/ns/1.0}body')
        if body is None:
            print("ERROR: No body element found")
            return jsonify({'error': 'Could not find body element in apparatus file'}), 400
        
        print("Body element found")
        
        # Create new apparatus entries and insert them in location order
        entries_added = 0
        for entry_data in new_entries:
            print(f"Processing entry: {entry_data}")
            new_app = create_apparatus_element(entry_data)
            insert_apparatus_entry_in_order(body, new_app, entry_data['loc'])
            entries_added += 1
        
        print(f"Processed {entries_added} entries")
        
        # Write back to file
        print("Generating output XML...")
        output_content = et.tostring(root, encoding='unicode', pretty_print=True)
        
        print("Writing to file...")
        with open(apparatus_file, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write(output_content)
        
        print("File written successfully")
        
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


def create_apparatus_element(entry_data):
    """
    Create an XML apparatus element from entry data
    """
    app = et.Element('{http://www.tei-c.org/ns/1.0}app')
    app.set('loc', str(entry_data['loc']))
    app.set('corresp', entry_data['corresp'])
    
    # Add lemma if present
    if entry_data.get('lemma'):
        lemma_data = entry_data['lemma']
        lemma = et.SubElement(app, '{http://www.tei-c.org/ns/1.0}lem')
        lemma.text = lemma_data['text']
        
        for attr_name, attr_value in lemma_data['attributes'].items():
            lemma.set(attr_name, attr_value)
    
    # Add readings
    for reading_data in entry_data.get('readings', []):
        rdg = et.SubElement(app, '{http://www.tei-c.org/ns/1.0}rdg')
        rdg.text = reading_data['text']
        
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


