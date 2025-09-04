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
                return {}
        
        else:
            raise ValueError("Either project_directory or project_files must be provided")
        
        # Use exec to safely extract the mapping variable
        namespace = {}
        exec(config_content, namespace)
        
        mapping = namespace.get('mapping', None)
        if mapping is None:
            return {}
        
        if not isinstance(mapping, dict):
            return {}
        
        return mapping
        
    except Exception as e:
        return {}



