"""
Apparatus class for managing apparatus data in HeiCrit.

This module provides a class-based structure for handling apparatus data
instead of using raw processing functions, making it easier to extend functionality and
maintain the codebase.
"""

from typing import Dict, List, Optional, Any
from io import BytesIO
from lxml import etree as et
from heipy.parsers import HeiEditionsParser
from heipy.namespaces import ns, prefix_format
from load_functions import resolve_relative_path, find_file_in_project


class Apparatus:
    """
    A class to manage apparatus data with improved structure and functionality.
    
    The apparatus contains apparatus entries extracted from TEI apparatus files.
    """
    
    def __init__(self, apparatus_filepath: str, project_files: Optional[Dict[str, Dict[str, Any]]] = None):
        """
        Initialize the Apparatus by parsing the apparatus file.
        
        Args:
            apparatus_filepath: Path to the apparatus file
            project_files: Optional dictionary of project files for project-based parsing
        """
        self._apparatus_filepath = apparatus_filepath
        self._project_files = project_files
        self._entries: List[Dict[str, Any]] = []
        self._leiths_path: Optional[str] = None
        self._root: Optional[et.Element] = None
        
        # Parse the apparatus file
        self._parse_apparatus_file()
    
    def _parse_apparatus_file(self) -> None:
        """
        Parse the apparatus file and extract entries and leithandschrift path.
        """
        try:
            # Get file content
            if self._project_files:
                # Load from project files
                file_data = find_file_in_project(self._apparatus_filepath, self._project_files)
                if not file_data:
                    raise FileNotFoundError(f"Apparatus file not found: {self._apparatus_filepath}")
                content = file_data['content']
            else:
                # Load from filesystem
                with open(self._apparatus_filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Parse XML content
            parser = HeiEditionsParser()
            content_bytes = content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            self._root = doc.getroot()
            
            # Extract leithandschrift path
            self._leiths_path = self._extract_leithandschrift_path()
            
            # Extract apparatus entries
            self._extract_apparatus_entries()
            
        except Exception as e:
            print(f"ERROR: Could not parse apparatus file {self._apparatus_filepath}: {str(e)}")
            raise
    
    def _extract_leithandschrift_path(self) -> Optional[str]:
        """
        Extract the siglum info for the leithandschrift.
        
        Returns:
            Path to the leithandschrift file or None if not found
        """
        try:
            if self._root is None:
                return None
                
            # Find witness with ana="hc:Leithandschrift"
            leithandschrift_witness = self._root.find('.//tei:witness[@ana="hc:Leithandschrift"]', namespaces=ns)
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
            print(f"ERROR: Could not extract leithandschrift path: {str(e)}")
            return None
    
    def _extract_apparatus_entries(self) -> None:
        """
        Extract apparatus entries from the parsed XML.
        """
        try:
            if self._root is None:
                return
                
            # Find all app elements in the document
            app_elements = self._root.xpath('.//tei:app', namespaces=ns)
            
            self._entries = []
            
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
                        'attributes': dict(rdg.attrib)
                    }
                    entry['readings'].append(reading)
                
                self._entries.append(entry)
                
        except Exception as e:
            print(f"ERROR: Could not extract apparatus entries: {str(e)}")
            raise
    
    def get_entries(self) -> List[Dict[str, Any]]:
        """
        Get the apparatus entries.
        
        Returns:
            List of apparatus entry dictionaries
        """
        return self._entries.copy()
    
    def set_entries(self, entries: List[Dict[str, Any]]) -> None:
        """
        Set/update the apparatus entries.
        
        Args:
            entries: List of apparatus entry dictionaries
        """
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        self._entries = entries.copy()
    
    def update_entry(self, entry_id: int, updated_entry: Dict[str, Any]) -> bool:
        """
        Update a specific apparatus entry.
        
        Args:
            entry_id: ID of the entry to update
            updated_entry: Updated entry data
            
        Returns:
            True if entry was updated, False if not found
        """
        for i, entry in enumerate(self._entries):
            if entry.get('id') == entry_id:
                self._entries[i] = updated_entry
                return True
        return False
    
    def get_entries_count(self) -> int:
        """
        Get the number of apparatus entries.
        
        Returns:
            Number of apparatus entries
        """
        return len(self._entries)
    
    def get_leiths_path(self) -> Optional[str]:
        """
        Get the leithandschrift file path.
        
        Returns:
            Path to the leithandschrift file or None if not found
        """
        return self._leiths_path
    
    def get_apparatus_filepath(self) -> str:
        """
        Get the apparatus file path.
        
        Returns:
            Path to the apparatus file
        """
        return self._apparatus_filepath
    
    def get_root(self) -> Optional[et.Element]:
        """
        Get the parsed XML root element (for internal use).
        
        Returns:
            XML root element or None if parsing failed
        """
        return self._root
    
    def get_witness_order(self) -> List[str]:
        """
        Extract the ordered list of witness IDs from the listWit section.
        
        Returns:
            List of witness xml:id values in the order they appear in listWit
        """
        if self._root is None:
            return []
        
        try:
            # Find all witness elements in listWit
            witness_elements = self._root.xpath('.//tei:listWit/tei:witness', namespaces=ns)
            witness_ids = []
            
            for witness in witness_elements:
                xml_id = witness.get('{http://www.w3.org/XML/1998/namespace}id')
                if xml_id:
                    witness_ids.append(xml_id)
            
            return witness_ids
            
        except Exception as e:
            print(f"ERROR: Could not extract witness order: {str(e)}")
            return []
    
    def get_witness_to_prefix_mapping(self) -> Dict[str, Dict[str, str]]:
        """
        Parse the witness-to-prefix mapping by comparing ptr targets with prefixDef replacementPatterns.
        Extract siglums from witness files if project_files are available.
        
        Returns:
            Dictionary mapping witness IDs to their prefix info and siglum
        """
        if self._root is None:
            return {}
        
        try:
            # Get all witness elements with their ptr targets and siglums
            witness_elements = self._root.xpath('.//tei:listWit/tei:witness', namespaces=ns)
            witness_info = {}
            
            for witness in witness_elements:
                xml_id = witness.get('{http://www.w3.org/XML/1998/namespace}id')
                ptr_element = witness.find('.//tei:ptr', namespaces=ns)
                siglum_element = witness.find('.//tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns)
                
                if xml_id and ptr_element is not None:
                    target = ptr_element.get('target')
                    siglum = siglum_element.text if siglum_element is not None and siglum_element.text else xml_id
                    
                    if target:
                        witness_info[xml_id] = {
                            'target': target,
                            'siglum': siglum
                        }
            
            # Get all prefixDef elements with ana="hc:SynopticTextPrefixDefinition"
            prefix_def_elements = self._root.xpath('.//tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]', namespaces=ns)
            prefix_patterns = {}
            
            for prefix_def in prefix_def_elements:
                ident = prefix_def.get('ident')
                replacement_pattern = prefix_def.get('replacementPattern')
                if ident and replacement_pattern:
                    # Extract the base path from replacementPattern (remove /$1 suffix)
                    base_path = replacement_pattern.replace('/$1', '')
                    prefix_patterns[ident] = base_path
            
            # Match witnesses to prefixes by comparing targets to replacement patterns
            mapping = {}
            for witness_id, info in witness_info.items():
                target = info['target']
                siglum = info['siglum']
                
                for prefix, base_path in prefix_patterns.items():
                    if target == base_path:
                        mapping[witness_id] = {
                            'synoptic_prefix': prefix,
                            'target_file': target,
                            'siglum': siglum
                        }
                        break
            
            return mapping
            
        except Exception as e:
            print(f"ERROR: Could not extract witness-to-prefix mapping: {str(e)}")
            return {}
    
    def _extract_siglum_from_witness_file(self, target_file: str) -> str:
        """
        Extract siglum from a witness file.
        
        Args:
            target_file: Path to the witness file
            
        Returns:
            The siglum if found, otherwise the filename without extension
        """
        if not self._project_files or not target_file:
            return target_file.split('/')[-1].replace('.xml', '') if target_file else ''
        
        try:
            # Resolve relative path and find file in project
            resolved_path = resolve_relative_path(target_file, self._apparatus_filepath)
            file_data = find_file_in_project(resolved_path, self._project_files)
            
            if not file_data:
                return target_file.split('/')[-1].replace('.xml', '')
            
            # Parse the witness file
            parser = HeiEditionsParser()
            content_bytes = file_data['content'].encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
            
            # Extract siglum from witness file
            siglum_element = root.find('.//tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns)
            if siglum_element is not None and siglum_element.text:
                return siglum_element.text
            
            # Fallback to filename without extension
            return target_file.split('/')[-1].replace('.xml', '')
            
        except Exception as e:
            print(f"WARNING: Could not extract siglum from {target_file}: {str(e)}")
            return target_file.split('/')[-1].replace('.xml', '') if target_file else ''
    
    def get_corresp_attribute(self) -> Optional[str]:
        """
        Get the corresp attribute from the listApp element.
        
        Returns:
            The corresp attribute value or None if not found
        """
        try:
            if self._root is None:
                return None
                
            list_app = self._root.find('.//tei:listApp', namespaces=ns)
            if list_app is not None:
                return list_app.get('corresp')
            
            return None
            
        except Exception as e:
            print(f"ERROR: Could not get corresp attribute: {str(e)}")
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the Apparatus to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the apparatus
        """
        return {
            'apparatus_filepath': self._apparatus_filepath,
            'entries': self._entries.copy(),
            'entries_count': self.get_entries_count(),
            'leiths_path': self._leiths_path,
            'corresp': self.get_corresp_attribute()
        }
    
    def __str__(self) -> str:
        """String representation of the Apparatus."""
        return f"Apparatus(filepath='{self._apparatus_filepath}', entries={self.get_entries_count()})"
    
    def __repr__(self) -> str:
        """Detailed string representation of the Apparatus."""
        return f"Apparatus(apparatus_filepath='{self._apparatus_filepath}', entries_count={self.get_entries_count()}, leiths_path='{self._leiths_path}')"
    

def process_synoptic_token(el:et.Element) -> str:
    tag_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    result = ''
    if tag_name in ['w', 'pc']:
        xml_id = el.get(prefix_format('xml','id'))
        result += f"<span class='syn-token syn-token-pre' data-token-id={xml_id}> </span><span class='syn-token syn-tei-{tag_name}' data-token-id='{xml_id}'>"
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
        result += "</span>"
    # elif tag_name in ['c']:
    #     result += "<span class='syn-tei-space'> </span>"
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
        if line_content:
            line_content += "<span class='syn-token syn-token-post'> </span>"
        else:
        # If no text content, try to get element info
            tag_name = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag_name == 'gap':
                return "<div class='synoptic-content-om'>om.</div>"
            return f"[{tag_name} element - no text content]"
        
        return line_content
        
    except Exception as e:
        return f"[Error processing element: {str(e)}]"
