"""
SynopticMap class for managing synoptic map data in HeiCrit.

This module provides a flexible class-based structure for handling synoptic map data
instead of using raw dictionaries, making it easier to extend functionality and
maintain the codebase.
"""

from typing import Any
from io import BytesIO
from lxml import etree as et
from heipy.parsers import HeiEditionsParser
from heipy.namespaces import ns
from load_functions import resolve_relative_path, find_file_in_project


class SynopticMap:
    """
    A class to manage synoptic map data.
    
    The synoptic map contains loci of variation relative to the Leithandschrift,
    stored in the format: 'a:l_1': {'n': '1', 'target': ['a:l_1', 'b:l_1', ...]}
    """
    
    def __init__(self, file_path: str | None = None):
        """
        Initialize the SynopticMap.
        
        Args:
            file_path: Optional path to the synoptic map file
        """
        self._loci: dict[str, dict[str, Any]] = {}
        self._file_path: str | None = file_path
        self._wits: dict[str, dict[str, str]] = {}  # Store witness information
        
    def get_loci(self) -> dict[str, dict[str, Any]]:
        """
        Get the complete loci dictionary.
        
        Returns:
            Dictionary containing all synoptic map loci data
        """
        return self._loci.copy()  # Return a copy to prevent external modification
    
    def get_wits(self) -> dict[str, dict[str, Any]]:
        """
        Get witness information dictionary for JSON serialization (excludes XML elements).
        
        Returns:
            Dictionary containing witness information without XML elements
        """
        wits_copy = {}
        for ident, wit_info in self._wits.items():
            wits_copy[ident] = {
                'file_name': wit_info.get('file_name'),
                'elements_count': len(wit_info.get('elements', {})),
                'siglum': wit_info.get('siglum')
            }
        return wits_copy
    
    def set_wits(self, wits_dict: dict[str, dict[str, str]]) -> None:
        """
        Set/update the witness information dictionary.
        
        Args:
            wits_dict: Dictionary containing witness information
        """
        if not isinstance(wits_dict, dict):
            raise ValueError("wits_dict must be a dictionary")
        self._wits = wits_dict.copy()
    
    def get_file_path(self) -> str | None:
        """
        Get the file path where this synoptic map was loaded from.
        
        Returns:
            File path or None if not set
        """
        return self._file_path
    
    def set_file_path(self, file_path: str) -> None:
        """
        Set the file path for this synoptic map.
        
        Args:
            file_path: Path to the synoptic map file
        """
        self._file_path = file_path
    
    def get_loci_count(self) -> int:
        """
        Get the number of loci entries.
        
        Returns:
            Number of loci in the synoptic map
        """
        return len(self._loci)
    
    def has_locus(self, locus_id: str) -> bool:
        """
        Check if a specific locus exists in the synoptic map.
        
        Args:
            locus_id: The locus identifier to check for
            
        Returns:
            True if the locus exists, False otherwise
        """
        return locus_id in self._loci
    
    def get_locus_info(self, locus_id: str) -> dict[str, Any] | None:
        """
        Get information for a specific locus.
        
        Args:
            locus_id: The locus identifier to get info for
            
        Returns:
            Dictionary containing locus information or None if not found
        """
        return self._loci.get(locus_id)
    
    def get_all_locus_ids(self) -> list[str]:
        """
        Get a list of all locus identifiers.
        
        Returns:
            List of all locus IDs in the synoptic map
        """
        return list(self._loci.keys())
    
    def get_loci_by_n_value(self, n_value: str) -> list[str]:
        """
        Get all locus IDs that have a specific 'n' value.
        
        Args:
            n_value: The 'n' value to search for
            
        Returns:
            List of locus IDs that match the given 'n' value
        """
        matching_loci = []
        for locus_id, info in self._loci.items():
            if info.get('n') == n_value:
                matching_loci.append(locus_id)
        return matching_loci
    
    def get_targets_for_locus(self, locus_id: str) -> list[str]:
        """
        Get the target list for a specific locus.
        
        Args:
            locus_id: The locus identifier
            
        Returns:
            List of targets for the locus, or empty list if not found
        """
        locus_info = self.get_locus_info(locus_id)
        if locus_info and 'target' in locus_info:
            print(locus_info['target'])
            return locus_info['target'].copy()
        return []
    
    def get_wit_info(self, wit_ident: str) -> dict[str, Any] | None:
        """
        Get information for a specific witness (JSON-serializable, excludes XML elements).
        
        Args:
            wit_ident: The witness identifier
            
        Returns:
            Dictionary containing witness information or None if not found
        """
        wit_info = self._wits.get(wit_ident)
        if wit_info:
            return {
                'file_name': wit_info.get('file_name'),
                'elements_count': len(wit_info.get('elements', {}))
            }
        return None
    
    def get_wit_elements(self, wit_ident: str) -> dict[str, Any] | None:
        """
        Get XML elements for a specific witness (for internal use).
        
        Args:
            wit_ident: The witness identifier
            
        Returns:
            Dictionary mapping xml:id to XML elements, or None if not found
        """
        wit_info = self._wits.get(wit_ident)
        if wit_info:
            return wit_info.get('elements', {})
        return None
    
    def get_all_wit_idents(self) -> list[str]:
        """
        Get a list of all witness identifiers.
        
        Returns:
            List of all witness IDs in the synoptic map
        """
        return list(self._wits.keys())
    
    def get_wits_count(self) -> int:
        """
        Get the number of witness entries.
        
        Returns:
            Number of witnesses in the synoptic map
        """
        return len(self._wits)
    
    def clear(self) -> None:
        """
        Clear all loci and witness data.
        """
        self._loci.clear()
        self._wits.clear()
    
    def is_empty(self) -> bool:
        """
        Check if the synoptic map is empty.
        
        Returns:
            True if no loci are stored, False otherwise
        """
        return len(self._loci) == 0
    
    def parse_content(self, content: str, leiths_prefix: str | None = None,
                     apparatus_filepath: str | None = None,
                     project_files: dict[str, dict[str, Any]] | None = None,
                     apparatus_witness_mapping: dict[str, dict[str, str]] | None = None) -> bool:
        """
        Parse synoptic map content from XML string and populate the loci.
        
        Args:
            content: XML content as string
            leiths_prefix: Prefix for filtering leithandschrift entries
            apparatus_filepath: Path to apparatus file for resolving witness file paths
            project_files: Dictionary of project files for parsing witness files
            apparatus_witness_mapping: Mapping of witness IDs to their info from apparatus (for filtering)
            
        Returns:
            True if parsing was successful, False otherwise
        """
        try:
            parser = HeiEditionsParser()
            content_bytes = content.encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
            
            # Extract prefixDef elements for witness information
            prefix_def_elements = root.xpath('.//tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]', namespaces=ns)
            
            wits_map = {}
            for prefix_def in prefix_def_elements:
                ident = prefix_def.get('ident')
                replacement_pattern = prefix_def.get('replacementPattern', '')
                file_name = None
                if replacement_pattern is not None:
                    file_name = replacement_pattern[3:-3]
                
                if ident:
                    # Filter: only process witnesses that are mentioned in apparatus
                    if apparatus_witness_mapping is not None:
                        # Check if this prefix corresponds to any witness in the apparatus
                        is_in_apparatus = any(
                            mapping_info.get('synoptic_prefix') == ident
                            for mapping_info in apparatus_witness_mapping.values()
                        )
                        if not is_in_apparatus:
                            print(f"INFO: Skipping witness file {file_name} (prefix: {ident}) - not in apparatus")
                            continue
                    wit_info = {
                        'file_name': file_name
                    }
                    
                    # Parse witness file and extract elements if project files are available
                    if file_name and apparatus_filepath and project_files:
                        try:
                            parse_result = self._parse_witness_file(file_name, apparatus_filepath, project_files)
                            if isinstance(parse_result, dict) and 'elements' in parse_result:
                                wit_info['elements'] = parse_result['elements']
                                wit_info['siglum'] = parse_result.get('siglum')
                            else:
                                # Backward compatibility for old return format
                                wit_info['elements'] = parse_result
                        except Exception as e:
                            print(f"WARNING: Could not parse witness file {file_name}: {str(e)}")
                            wit_info['elements'] = {}
                    else:
                        wit_info['elements'] = {}
                    
                    wits_map[ident] = wit_info
            # Extract link elements
            link_elements = root.xpath('.//tei:link', namespaces=ns)
            
            loci_map = {}
            found_keys = set()
            for link in link_elements:
                n = link.get('n')
                target = link.get('target', '')
                target_list = [t.strip() for t in target.split() if t.strip()]
                
                if not leiths_prefix:
                    print("ERROR: Can't find main text prefix.")
                    return False
                corresp_in_leiths = [x for x in target_list if x.startswith(f"{leiths_prefix}:")]
                # Use the first corresp format as key
                loci_map_key = corresp_in_leiths[0]
                if loci_map_key in found_keys:
                    loci_map[loci_map_key]['target'] += target_list
                else:
                    loci_map[loci_map_key] = {
                        'n': n,
                        'target': target_list
                    }
                    found_keys.add(loci_map_key)
            
            self._loci = loci_map
            self._wits = wits_map
            return True
            
        except Exception as e:
            print(f"ERROR: Could not parse synoptic map content: {str(e)}")
            return False
    
    def _parse_witness_file(self, file_name: str, apparatus_filepath: str, 
                           project_files: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """
        Parse a witness file and extract all elements with xml:id attributes.
        
        Args:
            file_name: Name of the witness file to parse
            apparatus_filepath: Path to the apparatus file (for relative resolution)
            project_files: Dictionary of project files
            
        Returns:
            Dictionary mapping xml:id to element objects
        """
        try:
            resolved_path = resolve_relative_path(file_name, apparatus_filepath)
            file_data = find_file_in_project(resolved_path, project_files)
            
            
            if not file_data:
                return {}
            
            # Parse the witness file
            parser = HeiEditionsParser(resolve_entities=True)
            content_bytes = file_data['content'].encode('utf-8')
            doc = et.parse(BytesIO(content_bytes), parser)
            root = doc.getroot()
            
            # Extract siglum from the witness file
            siglum = root.find('.//tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns)
            siglum_text = siglum.text if siglum is not None else None
            
            elements_map = {}
            for el in root.iter():
                if "{http://www.w3.org/XML/1998/namespace}id" not in el.attrib or el.tag == "{http://www.tei-c.org/ns/1.0}w":
                    continue
                xml_id = el.get("{http://www.w3.org/XML/1998/namespace}id")
                elements_map[xml_id] = el
            return {'elements': elements_map, 'siglum': siglum_text}
            
        except Exception as e:
            print(f"ERROR: Could not parse witness file {file_name}: {str(e)}")
            return {'elements': {}, 'siglum': None}

    def load_from_project(self, corresp_path: str, apparatus_filepath: str, 
                         project_files: dict[str, dict[str, Any]], 
                         leiths_prefix: str | None = None,
                         apparatus_witness_mapping: dict[str, dict[str, str]] | None = None) -> bool:
        """
        Load synoptic map from project files using relative path resolution.
        
        Args:
            corresp_path: Path to the synoptic map file (relative to apparatus file)
            apparatus_filepath: Path to the apparatus file (for relative resolution)
            project_files: Dictionary of project files {path: {content: str, ...}}
            leiths_prefix: Prefix for filtering leithandschrift entries
            apparatus_witness_mapping: Mapping of witness IDs to their info from apparatus (for filtering)
            
        Returns:
            True if loading was successful, False otherwise
        """
        try:
            resolved_path = resolve_relative_path(corresp_path, apparatus_filepath)
            file_data = find_file_in_project(resolved_path, project_files)
            
            if file_data:
                self._file_path = resolved_path
                return self.parse_content(file_data['content'], leiths_prefix, apparatus_filepath, project_files, apparatus_witness_mapping)
            
            return False
            
        except Exception as e:
            print(f"ERROR: Could not load synoptic map from project: {str(e)}")
            return False
    
    def to_dict(self) -> dict[str, Any]:
        """
        Convert the SynopticMap to a dictionary for serialization.
        
        Returns:
            Dictionary representation of the synoptic map
        """
        return {
            'loci': self._loci.copy(),
            'wits': self._wits.copy(),
            'file_path': self._file_path,
            'loci_count': self.get_loci_count(),
            'wits_count': self.get_wits_count()
        }
    
    def __str__(self) -> str:
        """String representation of the SynopticMap."""
        return f"SynopticMap(count={self.get_loci_count()}, file_path='{self._file_path}')"
    
    def __repr__(self) -> str:
        """Detailed string representation of the SynopticMap."""
        return f"SynopticMap(loci={self._loci}, file_path='{self._file_path}')"