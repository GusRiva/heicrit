import os
from io import BytesIO
from lxml import etree as et
from heipy.parsers import HeiEditionsParser
from heipy.namespaces import ns


def parse_xml_heieditions(content:str) -> et.Element:
    parser = HeiEditionsParser()
    content_bytes = content.encode('utf-8')
    doc = et.parse(BytesIO(content_bytes), parser)
    root = doc.getroot()
    return root


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


def load_sigla_mapping(project_directory=None, project_files=None):
    """
    Load sigla mapping from pipelines/config.py
    Can load from either a project directory or project files dictionary
    Returns the mapping dictionary or empty dict if not found
    """
    try:
        config_content = None
        config_path = None
        
        if project_directory:
            # Load from filesystem
            config_path = os.path.join(project_directory, 'pipelines', 'config.py')
            if not os.path.exists(config_path):
                print(f"Warning: Could not find pipelines/config.py in project directory: {project_directory}")
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
                return {}
        
        else:
            raise ValueError("Either project_directory or project_files must be provided")
        
        # Use exec to safely extract the mapping variable
        namespace = {}
        exec(config_content, namespace)
        
        mapping = namespace.get('mapping', None)
        if mapping is None:
            print(f"Warning: No 'mapping' variable found in {config_path}")
            return {}
        
        if not isinstance(mapping, dict):
            print(f"Warning: 'mapping' variable is not a dictionary in {config_path}")
            return {}
        
        if len(mapping) == 0:
            print(f"Warning: 'mapping' dictionary is empty in {config_path}")
        
        print(f"Loaded sigla mapping with {len(mapping)} entries from {config_path}")
        return mapping
        
    except Exception as e:
        error_source = project_directory if project_directory else "project files"
        print(f"Error: Failed to load sigla mapping from {error_source}: {str(e)}")
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
        
        root = parse_xml_heieditions(xml_content)
        
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
                    # 'n': n,
                    'target': target_list
                }
        
        return synoptic_map
        
    except Exception as e:
        print(f"Error parsing synoptic map: {str(e)}")
        return {}


def load_synoptic_map(corresp_path, apparatus_filepath, project_files):
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

