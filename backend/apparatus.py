"""
Apparatus class for managing apparatus data in HeiCrit.

This module provides a class-based structure for handling apparatus data
instead of using raw processing functions, making it easier to extend functionality and
maintain the codebase.
"""

from __future__ import annotations

from typing import Any
from io import BytesIO
from html import escape as html_escape
from lxml import etree as et
from lxml import html as lxml_html
from heipy.parsers import HeiEditionsParser
from heipy.namespaces import ns, prefix_format
from load_functions import resolve_relative_path, find_file_in_project, parse_location_token
from location_resolver import WitnessFragmentResolver

XML_ID = '{http://www.w3.org/XML/1998/namespace}id'
TEI_NS = 'http://www.tei-c.org/ns/1.0'


def _inline_to_html(element) -> str:
    """Convert inline TEI content to safe HTML, mapping <emph> to <em> and <mentioned> to <i>."""
    result = html_escape(element.text or '')
    for child in element:
        if not isinstance(child.tag, str):  # skip comments and processing instructions
            continue
        local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        inner = _inline_to_html(child)
        if local == 'emph':
            result += f'<em>{inner}</em>'
        elif local == 'mentioned':
            result += f'<i>{inner}</i>'
        else:
            result += inner
        result += html_escape(child.tail or '')
    return result


def _append_text(target_element, text: str) -> None:
    """Append text to target_element's mixed content (as tail of its last child, or as its own .text if it has none yet)."""
    if not text:
        return
    if len(target_element) > 0:
        last_child = target_element[-1]
        last_child.tail = (last_child.tail or '') + text
    else:
        target_element.text = (target_element.text or '') + text


def _copy_html_into_note(html_element, note_element) -> None:
    """
    Recursively copy a contenteditable HTML fragment's content into note_element,
    converting italics (<i>/<em>, or a "font-style: italic" span - browsers vary
    in what execCommand('italic') produces) into <mentioned>, treating <br> as a
    space, and flattening any other wrapper element (div/span/b/... that a
    contenteditable region may introduce) down to its text content.
    """
    _append_text(note_element, html_element.text)
    for child in html_element:
        tag = child.tag.lower() if isinstance(child.tag, str) else ''
        style = (child.get('style') or '').lower()
        is_italic = tag in ('i', 'em') or 'italic' in style

        if is_italic:
            mentioned_element = et.SubElement(note_element, f'{{{TEI_NS}}}mentioned')
            _copy_html_into_note(child, mentioned_element)
        elif tag == 'br':
            _append_text(note_element, ' ')
        else:
            _copy_html_into_note(child, note_element)
        _append_text(note_element, child.tail)


def html_note_to_tei(note_html: str) -> et.Element:
    """
    Convert an edited note's HTML (from the frontend's contenteditable note
    field) into a TEI <note> element, the inverse of _inline_to_html's
    <mentioned> -> <i> mapping used to display it.
    """
    wrapper = lxml_html.fragment_fromstring(f'<div>{note_html}</div>', create_parent=False)
    note_element = et.Element(f'{{{TEI_NS}}}note')
    _copy_html_into_note(wrapper, note_element)
    return note_element


# Variant types the new-format write path accepts.
ALLOWED_NEW_FORMAT_ANA = frozenset({
    'hc:AdditionVariant',
    'hc:OmissionVariant',
    'hc:SubstitutionVariant',
    'hc:TranspositionVariant',
})


def build_ptr_element(target: str) -> et.Element:
    """Build a single new-format <ptr target="prefix:location"/> element."""
    ptr_element = et.Element(f'{{{TEI_NS}}}ptr')
    ptr_element.set('target', target)
    return ptr_element


def build_link_element(base_target: str, witness_targets: list[str]) -> et.Element:
    """Build a single new-format <link target="base_target wit1_target wit2_target ..."/>
    element, pairing one base-text token with every witness token that shares
    that same position (used for transpositions instead of <ptr>) - witnesses
    with an identical transposition pattern collapse into one <link> rather
    than duplicating the same base position once per witness."""
    link_element = et.Element(f'{{{TEI_NS}}}link')
    link_element.set('target', ' '.join([base_target, *witness_targets]))
    return link_element


def build_rdg_element(wit_ids: list[str], ana: str, ptr_targets: list[str]) -> et.Element:
    """
    Build a new-format <rdg wit="#id1 #id2" ana="..."><ptr .../>...</rdg>
    element from already-resolved witness ids and ptr target strings.
    """
    rdg_element = et.Element(f'{{{TEI_NS}}}rdg')
    rdg_element.set('wit', ' '.join(f'#{wit_id}' for wit_id in wit_ids))
    rdg_element.set('ana', ana)
    for ptr_target in ptr_targets:
        rdg_element.append(build_ptr_element(ptr_target))
    return rdg_element


def build_transposition_rdg_element(wit_ids: list[str], link_pairs: list[dict]) -> et.Element:
    """
    Build a new-format <rdg wit="#id1 #id2" ana="hc:TranspositionVariant">
    <link .../>...</rdg> element from already-resolved witness ids and
    base/witnesses link pairs ({'base': 'prefix:id', 'witnesses': ['prefix:id', ...]}).
    """
    rdg_element = et.Element(f'{{{TEI_NS}}}rdg')
    rdg_element.set('wit', ' '.join(f'#{wit_id}' for wit_id in wit_ids))
    rdg_element.set('ana', 'hc:TranspositionVariant')
    for pair in link_pairs:
        rdg_element.append(build_link_element(pair['base'], pair['witnesses']))
    return rdg_element


def build_new_format_app_element(target: str | None, readings: list[dict]) -> et.Element:
    """
    Build a whole new-format <app target="..."><rdg .../>...</app> element.

    Args:
        target: the @target address (the base text's own reading location).
            None/omitted for transposition-only entries, which anchor via
            their first <link> instead (see Apparatus._derive_loc_and_corresp).
        readings: list of dicts, one per <rdg> to build - either
            {'wit': [ids], 'ana': str, 'ptrs': [targets]} (ptr-based) or
            {'wit': [ids], 'ana': 'hc:TranspositionVariant', 'links': [{'base','witnesses'}, ...]}
            (link-based)

    Returns:
        The unattached <app> element - the caller is responsible for
        inserting it into (or replacing children of) the document tree.
    """
    app_element = et.Element(f'{{{TEI_NS}}}app')
    if target:
        app_element.set('target', target)
    for reading in readings:
        if reading.get('links'):
            app_element.append(build_transposition_rdg_element(reading['wit'], reading['links']))
        else:
            app_element.append(build_rdg_element(reading['wit'], reading['ana'], reading['ptrs']))
    return app_element


class Apparatus:
    """
    A class to manage apparatus data with improved structure and functionality.
    
    The apparatus contains apparatus entries extracted from TEI apparatus files.
    """
    
    def __init__(self, apparatus_filepath: str, project_files: dict[str, dict[str, Any]] | None = None):
        """
        Initialize the Apparatus by parsing the apparatus file.
        
        Args:
            apparatus_filepath: Path to the apparatus file
            project_files: Optional dictionary of project files for project-based parsing
        """
        self._apparatus_filepath = apparatus_filepath
        self._project_files = project_files
        self._entries: list[dict[str, Any]] = []
        self._leiths_path: str | None = None
        self._root: et.Element | None = None

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
                with open(self._apparatus_filepath, encoding='utf-8') as f:
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
    
    
    def _get_base_witness_id(self) -> str | None:
        """
        Get the xml:id of the base witness (witness[@ana="hc:BaseText"]).
        """
        if self._root is None:
            return None
        witness = self._root.find('.//tei:witness[@ana="hc:BaseText"]', namespaces=ns)
        if witness is None:
            return None
        return witness.get(XML_ID)

    def _read_related_file(self, relative_path: str) -> str | None:
        """
        Read a file referenced (relatively) from the apparatus file, from either
        the in-memory project files or the filesystem.
        """
        resolved_path = resolve_relative_path(relative_path, self._apparatus_filepath)
        if self._project_files:
            file_data = find_file_in_project(resolved_path, self._project_files)
            return file_data['content'] if file_data else None
        try:
            with open(resolved_path, encoding='utf-8') as f:
                return f.read()
        except OSError:
            return None

    def _extract_leithandschrift_path(self) -> str | None:
        """
        Extract the siglum info for the leithandschrift.
        
        Returns:
            Path to the leithandschrift file or None if not found
        """
        try:
            if self._root is None:
                return None
                
            # Find witness with ana="hc:Leithandschrift"
            leithandschrift_witness = self._root.find('.//tei:witness[@ana="hc:BaseText"]', namespaces=ns)
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

            resolver = WitnessFragmentResolver(
                self._apparatus_filepath, self._project_files, self.get_witness_to_prefix_mapping())
            for i, app in enumerate(app_elements):
                self._entries.append(self._extract_new_format_entry(i, app, resolver))

        except Exception as e:
            print(f"ERROR: Could not extract apparatus entries: {str(e)}")
            raise

    def _extract_new_format_entry(self, index: int, app, resolver: WitnessFragmentResolver) -> dict[str, Any]:
        """
        Extract an apparatus entry in the new data model: @target on <app> (or none,
        for transpositions), <lem>/<rdg> addressed via <ptr>/<link> children instead
        of inline text. Produces the SAME top-level shape as the old format
        ('id', 'loc', 'corresp', 'lemma', 'readings') plus an additive 'target'
        field, so downstream consumers don't need format-specific handling.

        @target itself now plays the role the old format's <lem> element played:
        it addresses the base text's own reading at this location, and is resolved
        into the entry's lemma. An explicit <lem> child (rare - used when the
        editor adopts a majority reading that differs from the base text's own,
        e.g. the base text omits a word most other witnesses have) overrides it.
        """
        target = app.get('target')
        lem_element = app.find('tei:lem', namespaces=ns)
        entry = {
            'id': index + 1,
            'loc': None,
            'corresp': None,
            'target': target,
            'lemma': None,
            'lemma_is_explicit': lem_element is not None,
            'readings': []
        }

        if lem_element is not None:
            entry['lemma'] = self._extract_lem_or_rdg(lem_element, resolver)
        elif target:
            entry['lemma'] = self._resolve_target_lemma(target, resolver)
        else:
            entry['lemma'] = self._resolve_transposition_lemma(app, resolver)

        for rdg in app.findall('tei:rdg', namespaces=ns):
            entry['readings'].append(self._extract_lem_or_rdg(rdg, resolver))

        entry['loc'], entry['corresp'] = self._derive_loc_and_corresp(app, resolver)
        entry['note'] = self._extract_entry_note(app)

        return entry

    def _extract_entry_note(self, app) -> dict[str, Any] | None:
        """
        Find this entry's editorial <note> (at most one is expected in practice,
        living on the <lem> or one of the <rdg> children) and expose it as a
        single entry-level field, editable and re-attachable to its source
        element by 'target'/'reading_index'.

        When no <note> exists yet, still returns an (empty) descriptor pointing
        at a sensible default attachment point (the <lem> if present, otherwise
        the first <rdg>), so the frontend can offer an empty, editable note area
        that saves to a sensible place - only returns None when the entry has
        neither a <lem> nor any <rdg> to attach a new note to.
        """
        lem_element = app.find('tei:lem', namespaces=ns)
        rdg_elements = app.findall('tei:rdg', namespaces=ns)

        if lem_element is not None:
            note_element = lem_element.find('tei:note', namespaces=ns)
            if note_element is not None:
                return self._build_note_dict(note_element, 'lemma', None)

        for index, rdg in enumerate(rdg_elements):
            note_element = rdg.find('tei:note', namespaces=ns)
            if note_element is not None:
                return self._build_note_dict(note_element, 'reading', index)

        if lem_element is not None:
            return {'text': '', 'html': '', 'target': 'lemma', 'reading_index': None}
        if rdg_elements:
            return {'text': '', 'html': '', 'target': 'reading', 'reading_index': 0}
        return None

    def _build_note_dict(self, note_element, target: str, reading_index: int | None) -> dict[str, Any]:
        return {
            'text': ''.join(note_element.itertext()).strip(),
            'html': _inline_to_html(note_element).strip(),
            'target': target,
            'reading_index': reading_index
        }

    def _resolve_transposition_lemma(self, app, resolver: WitnessFragmentResolver) -> dict[str, Any] | None:
        """
        Reconstruct the lemma for a transposition entry (no @target) from the
        base-side (first) token of every <link target="base_id wit1_id wit2_id ..."/>
        - the base text's own word order at these positions, analogous to
        @target's role elsewhere.
        """
        link_holder = app.find('tei:rdg', namespaces=ns)
        if link_holder is None:
            link_holder = app.find('tei:lem', namespaces=ns)
        if link_holder is None:
            return None

        base_tokens = []
        for link_el in link_holder.findall('tei:link', namespaces=ns):
            parts = (link_el.get('target') or '').split()
            if parts:
                base_tokens.append(parts[0])
        if not base_tokens:
            return None

        text, html = resolver.resolve_ordered_text_html(base_tokens)
        if not text:
            return None
        return {
            'text': text,
            'html': html,
            'attributes': {'corresp': ' '.join(resolver.normalize_corresp_token(t) for t in base_tokens)}
        }

    def _resolve_target_lemma(self, target: str, resolver: WitnessFragmentResolver) -> dict[str, Any]:
        """
        Resolve @target - the base text's own reading at this location - into a
        lemma dict, the new-format equivalent of the old format's inline <lem>.
        A target that resolves to no text (e.g. a left()/right() gap position with
        no base-text content at all) renders as an omission, matching the
        classical apparatus convention used elsewhere for omission variants.
        """
        text, html = resolver.resolve_text_html([target])
        if not text:
            text, html = 'om.', '<i>om.</i>'
        return {
            'text': text,
            'html': html,
            'attributes': {'corresp': resolver.normalize_corresp_token(target)}
        }

    def _extract_lem_or_rdg(self, element, resolver: WitnessFragmentResolver) -> dict[str, Any]:
        """
        Extract a new-format <lem>/<rdg> element: resolve its <ptr> children (or
        <link> pairs, for transpositions) into text/html, and synthesize an
        'attributes.corresp' string from the resolved target(s) so downstream
        consumers (frontend highlighting) can keep using the existing
        prefix:id/range()/left()/right() grammar unchanged. corresp tokens are
        normalized (right() -> left() of the next token) so gap positions
        highlight correctly regardless of where in the line they fall - see
        WitnessFragmentResolver.normalize_corresp_token.
        """
        ptrs = element.findall('tei:ptr', namespaces=ns)
        links = element.findall('tei:link', namespaces=ns)

        text, html, corresp, entry_links = '', '', None, None
        is_omission = element.get('ana') == 'hc:OmissionVariant'

        if ptrs:
            target_tokens = [p.get('target') for p in ptrs if p.get('target')]
            if target_tokens:
                corresp = ' '.join(resolver.normalize_corresp_token(t) for t in target_tokens)
                if is_omission:
                    text, html = 'om.', '<i>om.</i>'
                else:
                    text, html = resolver.resolve_text_html(target_tokens)
        elif links:
            # Each <link target="base wit1 wit2 ..."/> pairs one base position
            # with every witness token that shares it - witnesses with an
            # identical transposition pattern are written as a single <link>
            # rather than duplicating the same base position once per witness,
            # so a link can have more than the minimum 2 space-separated parts.
            pairs = [(link_el.get('target') or '').split() for link_el in links]
            pairs = [pair for pair in pairs if len(pair) >= 2]
            if pairs:
                # Only the witness-side tokens go into this reading's own corresp -
                # the base-side tokens are already covered by the entry's lemma
                # (_resolve_transposition_lemma), so including them here too would
                # double-highlight them (green from the lemma, then orange from
                # this reading, visually winning).
                witness_side_tokens = [token for pair in pairs for token in pair[1:]]
                corresp = ' '.join(resolver.normalize_corresp_token(t) for t in witness_side_tokens)
                text, html = resolver.resolve_ordered_text_html(witness_side_tokens)
                entry_links = [{'base': pair[0], 'witness': token} for pair in pairs for token in pair[1:]]

        attributes = dict(element.attrib)
        if corresp:
            attributes['corresp'] = corresp

        result = {
            'text': text,
            'html': html,
            'attributes': attributes
        }
        if entry_links:
            result['links'] = entry_links

        return result

    def _derive_loc_and_corresp(self, app, resolver: WitnessFragmentResolver) -> tuple[str | None, str | None]:
        """
        Derive a display 'loc' (line number) and 'corresp' (leiths-anchored line
        key, "prefix:line_xml_id") for a new-format <app> element, which no longer
        carries @loc/@corresp itself. Anchors on @target when present; otherwise
        (transposition entries) anchors on the first <link>'s first (base-side)
        token.
        """
        try:
            token = app.get('target')
            if not token:
                first_link = app.find('.//tei:rdg/tei:link', namespaces=ns)
                if first_link is not None:
                    link_targets = (first_link.get('target') or '').split()
                    if link_targets:
                        token = link_targets[0]

            if not token:
                return None, None

            spec = parse_location_token(token)
            if not spec:
                return None, None

            anchor_id = spec['start'] if spec['kind'] == 'range' else spec['id']
            line_n, line_xml_id = resolver.resolve_line_locator(spec['prefix'], anchor_id)
            if line_xml_id is None:
                return line_n, None
            return line_n, f"{spec['prefix']}:{line_xml_id}"

        except Exception as e:
            print(f"WARNING: Could not derive loc/corresp for app element: {str(e)}")
            return None, None
    
    def get_entries(self) -> list[dict[str, Any]]:
        """
        Get the apparatus entries.
        
        Returns:
            List of apparatus entry dictionaries
        """
        return self._entries.copy()
    
    def set_entries(self, entries: list[dict[str, Any]]) -> None:
        """
        Set/update the apparatus entries.
        
        Args:
            entries: List of apparatus entry dictionaries
        """
        if not isinstance(entries, list):
            raise ValueError("entries must be a list")
        self._entries = entries.copy()
    
    def update_entry(self, entry_id: int, updated_entry: dict[str, Any]) -> bool:
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
    
    def get_leiths_path(self) -> str | None:
        """
        Get the leithandschrift TEXT file path.

        Old format: the base witness's <ptr target="..."/> already points directly
        at its text file. New format: it points at "<index file>#<witness-id>"
        (a shared witness-metadata index, not a text file) - in that case, resolve
        the real text file via the prefix mapping, keyed off the base witness id.

        Returns:
            Path to the leithandschrift text file or None if not found
        """
        if not self._leiths_path:
            return None
        if '#' not in self._leiths_path:
            return self._leiths_path

        base_witness_id = self._get_base_witness_id()
        if not base_witness_id:
            return None
        mapping = self.get_witness_to_prefix_mapping()
        info = mapping.get(base_witness_id)
        return info['target_file'] if info else None
    
    def get_apparatus_filepath(self) -> str:
        """
        Get the apparatus file path.
        
        Returns:
            Path to the apparatus file
        """
        return self._apparatus_filepath
    
    def get_root(self) -> et.Element | None:
        """
        Get the parsed XML root element (for internal use).
        
        Returns:
            XML root element or None if parsing failed
        """
        return self._root
    
    def get_witness_order(self) -> list[str]:
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
    
    def get_witness_to_prefix_mapping(self) -> dict[str, dict[str, str]]:
        """
        Parse the witness-to-prefix mapping.

        Matches each prefixDef to a witness using, in order: (1) an explicit
        prefixDef/@corresp="#witnessId" back-link (new format); (2) comparing the
        witness's own ptr/@target to the prefixDef's replacementPattern base path
        (old format, where the witness ptr already points at its text file); (3)
        prefixDef/@ident == witness xml:id (new-format fallback, since the witness
        ptr there points at a shared index file rather than a text file, so (2)
        never matches).

        Returns:
            Dictionary mapping witness IDs to their prefix info and siglum
        """
        if self._root is None:
            return {}

        try:
            witness_elements = self._root.xpath('.//tei:listWit/tei:witness', namespaces=ns)
            witnesses_by_id = {}
            witness_targets = {}

            for witness in witness_elements:
                xml_id = witness.get(XML_ID)
                if not xml_id:
                    continue
                witnesses_by_id[xml_id] = witness
                ptr_element = witness.find('.//tei:ptr', namespaces=ns)
                if ptr_element is not None:
                    witness_targets[xml_id] = ptr_element.get('target')

            prefix_def_elements = self._root.xpath('.//tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]', namespaces=ns)

            mapping = {}
            for prefix_def in prefix_def_elements:
                ident = prefix_def.get('ident')
                replacement_pattern = prefix_def.get('replacementPattern')
                if not ident or not replacement_pattern:
                    continue
                target_file = replacement_pattern.replace('/$1', '')

                witness_id = None
                corresp = prefix_def.get('corresp')
                if corresp and corresp.lstrip('#') in witnesses_by_id:
                    witness_id = corresp.lstrip('#')
                else:
                    for wid, target in witness_targets.items():
                        if target == target_file:
                            witness_id = wid
                            break
                    if witness_id is None and ident in witnesses_by_id:
                        witness_id = ident

                if witness_id is None:
                    continue

                mapping[witness_id] = {
                    'synoptic_prefix': ident,
                    'target_file': target_file,
                    'siglum': self._resolve_witness_siglum(witnesses_by_id[witness_id])
                }

            return mapping

        except Exception as e:
            print(f"ERROR: Could not extract witness-to-prefix mapping: {str(e)}")
            return {}

    def _resolve_witness_siglum(self, witness_element) -> str:
        """
        Resolve a witness's editorial siglum.

        Old format: the siglum is declared inline as a child of the witness itself.
        New format: the witness's ptr/@target is "<index file>#<fragment-id>"; the
        siglum lives in the shared index file, under a <witness xml:id="fragment-id">
        declaration there.

        Args:
            witness_element: the <witness> element from listWit

        Returns:
            The siglum if found, otherwise the witness's own xml:id
        """
        xml_id = witness_element.get(XML_ID) or ''

        try:
            inline_siglum = witness_element.find('.//tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns)
            if inline_siglum is not None and inline_siglum.text:
                return inline_siglum.text.strip()

            ptr_element = witness_element.find('.//tei:ptr', namespaces=ns)
            target = ptr_element.get('target') if ptr_element is not None else None
            if target and '#' in target:
                index_path, fragment_id = target.split('#', 1)
                content = self._read_related_file(index_path)
                if content:
                    parser = HeiEditionsParser(recover=True)
                    doc = et.parse(BytesIO(content.encode('utf-8')), parser)
                    index_root = doc.getroot()
                    fragment_witness = index_root.find(f'.//tei:witness[@xml:id="{fragment_id}"]', namespaces=ns)
                    if fragment_witness is not None:
                        siglum_element = fragment_witness.find('.//tei:idno[@ana="hc:EditorialSiglum"]', namespaces=ns)
                        if siglum_element is not None and siglum_element.text:
                            return siglum_element.text.strip()

        except Exception as e:
            print(f"WARNING: Could not resolve siglum for witness '{xml_id}': {str(e)}")

        return xml_id
    
    def get_corresp_attribute(self) -> str | None:
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
    
    def to_dict(self) -> dict[str, Any]:
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
    if not isinstance(el.tag, str):  # skip comments and processing instructions
        return ''
    tag_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    result = ''
    if tag_name in ['w', 'pc']:
        xml_id = el.get(prefix_format('xml','id'))
        result += f"<span class='syn-token syn-token-pre' data-token-id='{xml_id}'> </span><span class='syn-token syn-tei-{tag_name}' data-token-id='{xml_id}'>"
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
    elif tag_name == 'reg':
        # Regularized/normalized form - suppressed; the diplomatic <orig> (or
        # plain text) sibling is preferred, matching the same convention used
        # to render apparatus reading text from these files (location_resolver).
        # Its tail is still part of the surrounding flow, so it isn't dropped.
        if el.tail is not None and el.tail.strip() != '':
            result += el.tail
    elif tag_name == 'titlePart':
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
    elif tag_name == 'gap':
        star_count = 3
        if el.get('unit') == 'character':
            try:
                parsed = int(el.get('quantity', ''))
                if parsed > 0:
                    star_count = parsed
            except ValueError:
                pass
        result += f"<span class='syn-gap-marker'>{'*' * star_count}</span>"
        if el.tail is not None and el.tail.strip() != '':
            result += el.tail
    else:
        # Default: any other inline element (orig, sic, hi, initial, ex,
        # metamark, ...) is transparent pass-through content - include its own
        # text, its children, and every child's tail. Using a default rather
        # than a fixed whitelist avoids silently dropping real word content
        # (e.g. <ex>n</ex> abbreviation expansions) whenever markup not
        # anticipated by an explicit branch appears in the source.
        if el.text is not None:
            result += el.text.strip()
        for child in el:
            result += process_synoptic_token(child)
            if child.tail is not None and child.tail.strip() != '':
                result += child.tail
        if el.tail is not None and el.tail.strip() != '':
            result += el.tail
    return result


def _last_token_id(element) -> str:
    """Return the xml:id of the last w or pc element in the subtree (document order)."""
    last_id = None
    for el in element.iter():
        if not isinstance(el.tag, str):  # skip comments and processing instructions
            continue
        tag = el.tag.split('}')[-1] if '}' in el.tag else el.tag
        if tag in ['w', 'pc']:
            xml_id = el.get(prefix_format('xml', 'id'))
            if xml_id:
                last_id = xml_id
    return last_id


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
            last_id = _last_token_id(element)
            post_attr = f" data-token-id='{last_id}'" if last_id else ''
            line_content += f"<span class='syn-token syn-token-post'{post_attr}> </span>"
        else:
        # If no text content, try to get element info
            tag_name = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag_name == 'gap':
                return "<div class='synoptic-content-om'>om.</div>"
            return f"[{tag_name} element - no text content]"
        
        return line_content
        
    except Exception as e:
        return f"[Error processing element: {str(e)}]"
