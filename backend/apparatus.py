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
from load_functions import resolve_relative_path, find_file_in_project, parse_location_token, local_name, base_locus_ids
from location_resolver import WitnessFragmentResolver, EMENDED, NORMALIZED, EMENDED_NORMALIZED

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

# A reading that agrees with the base text's own (uncorrected) reading at an
# emended location - shown merged with the base witness after the lemma
# bracket ("*K*atzen] Tatzen A B"), hidden when there is no emendation.
BASE_TEXT_SUPPORTING_ANA = 'hc:BaseTextSupportingVariant'

# Optional marker added to a variant type: this reading was used to emend the
# base text. Never changes how the reading itself is classified or shown.
CORRECTION_ANA = 'hc:CorrectionVariant'


def is_valid_reading_ana(ana: str | None) -> bool:
    """
    A reading's @ana is one primary type - an ALLOWED_NEW_FORMAT_ANA value
    or BASE_TEXT_SUPPORTING_ANA - optionally followed by CORRECTION_ANA
    (space-separated, e.g. "hc:SubstitutionVariant hc:CorrectionVariant").
    Transpositions take no marker.
    """
    tokens = (ana or '').split()
    primary = [t for t in tokens if t != CORRECTION_ANA]
    if len(primary) != 1 or len(tokens) - len(primary) > 1:
        return False
    if primary[0] == 'hc:TranspositionVariant':
        return len(tokens) == 1
    return primary[0] in ALLOWED_NEW_FORMAT_ANA or primary[0] == BASE_TEXT_SUPPORTING_ANA


def ana_tokens(element) -> list[str]:
    return (element.get('ana') or '').split()


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


def set_main_witness(rdg_element: et.Element, witness_id: str, prefix: str) -> bool:
    """
    Make witness_id the main witness of a <ptr> reading: its <ptr>s (those
    addressing "prefix:...") move to the front of the <rdg> - the first
    <ptr> names the main witness, whose text the reading shows - and its
    "#id" to the front of @wit. Other children keep their order. Returns
    False (changing nothing) if the reading has no <ptr> of that witness,
    e.g. a transposition (<link>s) or a witness it doesn't record.
    """
    ptrs = rdg_element.findall('tei:ptr', namespaces=ns)
    main_ptrs = [p for p in ptrs if (p.get('target') or '').startswith(f'{prefix}:')]
    if not main_ptrs:
        return False
    first_ptr_index = rdg_element.index(ptrs[0])
    for ptr in main_ptrs:
        rdg_element.remove(ptr)
    for offset, ptr in enumerate(main_ptrs):
        rdg_element.insert(first_ptr_index + offset, ptr)
    wit_ids = (rdg_element.get('wit') or '').split()
    if f'#{witness_id}' in wit_ids:
        wit_ids.remove(f'#{witness_id}')
    rdg_element.set('wit', ' '.join([f'#{witness_id}', *wit_ids]))
    return True


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

            resolver = self.get_resolver()
            for i, app in enumerate(app_elements):
                self._entries.append(self._extract_new_format_entry(i, app, resolver))

            self._generated_entries = self._generate_unrecorded_emendation_entries(app_elements, resolver)

        except Exception as e:
            print(f"ERROR: Could not extract apparatus entries: {str(e)}")
            raise

    def _generate_unrecorded_emendation_entries(self, app_elements,
                                                resolver: WitnessFragmentResolver) -> list[dict[str, Any]]:
        """
        Provisional entries for every emendation in the base text that no
        <app> records yet - so an emended critical text never silently lacks
        its apparatus entry. Built by the same rules as a recorded emendation
        (emended lemma, then the uncorrected base reading), with no further
        readings. Never written to the file: they carry is_generated=True and
        no 'id' (ids index real <app> elements), and become real entries
        only when the editor creates one from them.
        """
        try:
            base_id = self._get_base_witness_id()
            base_prefix = self.get_witness_to_prefix_mapping().get(base_id, {}).get('synoptic_prefix')
            if not base_prefix:
                return []

            covered: set = set()
            for app in app_elements:
                targets = [app.get('target')] if app.get('target') else []
                for ptr in app.findall('tei:lem/tei:ptr', namespaces=ns):
                    targets.append(ptr.get('target'))
                for target in targets:
                    if target and target.startswith(f'{base_prefix}:'):
                        covered |= resolver.covered_elements(target)

            generated = []
            for target, unit in resolver.emendation_units(base_prefix):
                # Recorded if an <app> addresses the unit or any of its tokens
                # (e.g. one side of a token-spanning <choice>).
                if unit in covered or any(t in covered for t in unit.iter()
                                          if isinstance(t.tag, str) and local_name(t) in ('w', 'pc')):
                    continue
                lemma = self._resolve_target_lemma(target, resolver, emended=True)
                loc, corresp = self._loc_and_corresp_for_token(target, resolver)
                generated.append({
                    'id': None,
                    'is_generated': True,
                    'loc': loc,
                    'corresp': corresp,
                    'target': target,
                    'lemma': lemma,
                    'lemma_is_explicit': False,
                    'readings': [],
                    'is_emendation': True,
                    'base_reading': self._resolve_base_reading(target, [], [], resolver),
                    'note': None,
                })
            return generated
        except Exception as e:
            print(f"WARNING: Could not generate entries for unrecorded emendations: {str(e)}")
            return []

    def get_generated_entries(self) -> list[dict[str, Any]]:
        """Provisional entries for unrecorded emendations (see above)."""
        return list(getattr(self, '_generated_entries', []))

    def get_display_entries(self, synoptic_loci: dict | None = None) -> list[dict[str, Any]]:
        """
        What the frontend shows: the real entries (whose 'id' indexes the
        <app> elements - every write route relies on that) followed by the
        generated ones. Never use this for index-based write logic.

        synoptic_loci (SynopticMap.get_loci()): places whole-verse additions
        at their added locus, and adds suggested whole-verse entries for
        verses the synoptic map shows as missing (see _generate_verse_entries).
        """
        entries = self.get_entries()
        if not synoptic_loci:
            return entries + self.get_generated_entries()
        resolver = self.get_resolver()
        entries = [self._fix_verse_addition_entry(e, synoptic_loci)
                   if e.get('is_verse_entry') and resolver.is_absent_verse_token(e.get('target')) else e
                   for e in entries]
        located = self._locate_at_synoptic_loci(entries + self.get_generated_entries(), synoptic_loci)
        return located + self._generate_verse_entries(synoptic_loci, entries)

    def _locate_at_synoptic_loci(self, entries: list[dict], synoptic_loci: dict) -> list[dict]:
        """
        Re-derive each token-addressed entry's loc/corresp against the loci the
        synoptic map links: a token belongs to the nearest element around it
        that the map links (a heading, a <seg> inside a verse, ...), which
        without the map can only be guessed (see resolve_line_locator). The
        location label is the locus's own @n from the map when it has one, so
        an entry and its locus's placeholder read the same. Whole-unit
        entries are located at the unit they address - except additions
        (the unit is absent from the base), placed by _fix_verse_addition_entry.
        """
        locus_ids = base_locus_ids(synoptic_loci, self._base_prefix())
        if not locus_ids:
            return entries
        resolver = self.get_resolver()
        app_elements = self._root.xpath('.//tei:app', namespaces=ns) if self._root is not None else []
        located = []
        for entry in entries:
            if entry.get('is_verse_entry') and resolver.is_absent_verse_token(entry.get('target')):
                # placed at its added locus by _fix_verse_addition_entry
                located.append(entry)
                continue
            token = entry.get('target')
            entry_id = entry.get('id')
            if not token and entry_id and 0 < entry_id <= len(app_elements):
                token = self._anchor_token(app_elements[entry_id - 1])
            loc, corresp = self._loc_and_corresp_for_token(token, resolver, locus_ids)
            if corresp is None:
                located.append(entry)
                continue
            entry = dict(entry)
            entry['corresp'] = corresp
            entry['loc'] = (synoptic_loci.get(corresp) or {}).get('n') or loc
            located.append(entry)
        return located

    def get_resolver(self) -> WitnessFragmentResolver:
        """The (cached) resolver for this apparatus's witness fragments."""
        if getattr(self, '_resolver', None) is None:
            self._resolver = WitnessFragmentResolver(
                self._apparatus_filepath, self._project_files, self.get_witness_to_prefix_mapping())
        return self._resolver

    def lift_emendation_target(self, target: str | None) -> str | None:
        """
        Map a lemma token selection that exactly covers a token-spanning
        emendation container (a whole-token <surplus>, or the sic or corr
        side of a <choice>) to that container's own id, e.g. "a:w_5_4" ->
        "a:surplus_1" - the form app/@target must take for such an entry.
        Any other target is returned unchanged.
        """
        if not target:
            return target
        return self.get_resolver().emendation_container_for(target) or target

    def describe_emendation(self, target: str | None) -> dict[str, Any]:
        """
        For the entry-creation UI: whether target (after lifting) is an
        emended span - only then does it offer the emendation markers
        (hc:CorrectionVariant / hc:BaseTextSupportingVariant) - and its
        emended (lemma) and uncorrected (base text) renderings.
        """
        lifted = self.lift_emendation_target(target)
        resolver = self.get_resolver()
        if not lifted or not resolver.has_emendation(lifted):
            return {'target': lifted, 'is_emendation': False}
        emended_text, emended_html = resolver.resolve_text_html([lifted], mode=EMENDED)
        base_text, base_html = resolver.resolve_text_html([lifted])
        return {
            'target': lifted,
            'is_emendation': True,
            'emended_text': emended_text,
            'emended_html': emended_html,
            'base_text': base_text,
            'base_html': base_html,
        }

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

        rdg_elements = app.findall('tei:rdg', namespaces=ns)
        is_verse_entry = lem_element is None and resolver.is_verse_token(target)
        is_emendation = (lem_element is None and bool(target) and not is_verse_entry
                         and resolver.has_emendation(target))
        entry['is_emendation'] = is_emendation
        entry['is_verse_entry'] = is_verse_entry

        if lem_element is not None:
            entry['lemma'] = self._extract_lem_or_rdg(lem_element, resolver)
        elif is_verse_entry:
            entry['lemma'] = self._verse_lemma(target, resolver)
        elif target:
            entry['lemma'] = self._resolve_target_lemma(target, resolver, emended=is_emendation)
        else:
            entry['lemma'] = self._resolve_transposition_lemma(app, resolver)

        for rdg in rdg_elements:
            entry['readings'].append(self._extract_lem_or_rdg(rdg, resolver))

        if is_emendation:
            entry['base_reading'] = self._resolve_base_reading(target, rdg_elements, entry['readings'], resolver)

        entry['loc'], entry['corresp'] = self._derive_loc_and_corresp(app, resolver)
        entry['note'] = self._extract_entry_note(app)

        return entry

    # --- Whole-verse entries ------------------------------------------------

    @staticmethod
    def _span_label(first_n: str | None, last_n: str | None) -> str:
        """'' for one verse (the location number is shown anyway), '5–6' for a span."""
        if not first_n or not last_n or first_n == last_n:
            return ''
        return f'{first_n}–{last_n}'

    def _verse_lemma(self, target: str, resolver: WitnessFragmentResolver,
                     label: str | None = None) -> dict[str, Any]:
        """
        Lemma of a whole-verse entry: no verse text, only the verse number(s)
        - empty for a single verse, '5–6' for a span. For an addition (the
        target is the gap left()/right() of a base verse) the label comes
        from the synoptic loci, see get_display_entries.
        """
        if label is None:
            spec = parse_location_token(target)
            verses = resolver.verse_elements(spec) if spec else []
            label = self._span_label(verses[0].get('n'), verses[-1].get('n')) if verses else ''
        return {
            'text': label,
            'html': html_escape(label),
            'attributes': {'corresp': resolver.normalize_corresp_token(target)},
        }

    def _witness_for_prefix(self, prefix: str) -> str | None:
        if not hasattr(self, '_prefix_to_witness'):
            self._prefix_to_witness = {
                info['synoptic_prefix']: wit_id
                for wit_id, info in self.get_witness_to_prefix_mapping().items()
                if info.get('synoptic_prefix')
            }
        return self._prefix_to_witness.get(prefix)

    def _base_prefix(self) -> str | None:
        base_id = self._get_base_witness_id()
        return self.get_witness_to_prefix_mapping().get(base_id, {}).get('synoptic_prefix')

    def prepare_verse_entry(self, target_verses: list[str], readings: list[dict]) -> tuple[str | None, str | None]:
        """
        For saving a whole-verse entry: collapse the lemma's one-per-verse
        tokens into a single target (an <l>, a range of consecutive <l>, or
        the gap of a verse the base lacks) and each reading's pointers into
        ranges, and set each reading's variant type from the shape: base
        verse absent -> Addition, reading verse absent -> Omission, else
        Substitution. Returns (target, error).
        """
        resolver = self.get_resolver()
        base_prefix = self._base_prefix()
        if not target_verses:
            return None, 'Select the base text verse (click its siglum) before saving.'
        if any(not t.startswith(f'{base_prefix}:') for t in target_verses):
            return None, 'The lemma verse must be selected on the base text row.'
        if any(not resolver.is_verse_token(t) for t in target_verses):
            return None, 'The lemma selection is not a whole location (a verse, heading, paragraph, ...).'
        parts = resolver.collapse_verse_ptrs(target_verses)
        if len(parts) != 1:
            return None, ('The lemma locations must be consecutive and of one kind (or a single '
                          'location the base text lacks).')
        target = parts[0]
        base_absent = resolver.is_absent_verse_token(target)

        for reading in readings:
            ptrs = reading.get('ptrs') or []
            if any(not resolver.is_verse_token(p) for p in ptrs):
                return None, 'A reading in a whole-location entry must select whole locations (click the siglum).'
            reading['ptrs'] = resolver.collapse_verse_ptrs(ptrs)
            reading_absent = all(resolver.is_absent_verse_token(p) for p in reading['ptrs'])
            if base_absent and reading_absent:
                return None, 'The base text and a reading cannot both lack the verse.'
            reading['ana'] = ('hc:AdditionVariant' if base_absent
                              else 'hc:OmissionVariant' if reading_absent
                              else 'hc:SubstitutionVariant')
        return target, None

    @staticmethod
    def _locus_base_token(locus_key: str) -> str:
        """Synoptic locus key without its '#N' disambiguator."""
        return locus_key.split('#', 1)[0]

    def _addition_loci_for_entry(self, entry: dict, synoptic_loci: dict) -> list[str]:
        """Loci keys (in order) of the added verses an addition entry records."""
        resolver = self.get_resolver()
        verse_tokens = set()
        for reading in entry.get('readings') or []:
            for token in (reading.get('attributes', {}).get('corresp') or '').split():
                verse_tokens.add(token)
        return [key for key, info in synoptic_loci.items()
                if self._locus_base_token(key) == entry.get('target')
                and verse_tokens & set(info.get('target') or [])
                and resolver.is_absent_verse_token(self._locus_base_token(key))]

    def _fix_verse_addition_entry(self, entry: dict, synoptic_loci: dict) -> dict:
        """
        An addition's target (the gap after a base verse) is shared by every
        verse added there (40a, 40b, ...): place the entry at the first added
        locus it records and label it with their numbers.
        """
        keys = self._addition_loci_for_entry(entry, synoptic_loci)
        if not keys:
            return entry
        entry = dict(entry)
        first, last = synoptic_loci[keys[0]], synoptic_loci[keys[-1]]
        entry['corresp'] = keys[0]
        entry['loc'] = first.get('n') or entry.get('loc')
        entry['lemma'] = self._verse_lemma(entry['target'], self.get_resolver(),
                                           label=self._span_label(first.get('n'), last.get('n')))
        return entry

    def _generate_verse_entries(self, synoptic_loci: dict, real_entries: list[dict]) -> list[dict]:
        """
        Provisional whole-verse entries from the synoptic map, like the
        suggestions for unrecorded emendations: never written to the file
        until the editor confirms them.
        - Omissions: a witness whose synoptic token is the gap left()/right()
          of a verse, at loci where the base has a verse. Consecutive loci
          form one span; witnesses with the same span share one reading.
          Lacunae (any other non-verse token) are not variants - skipped.
        - Additions: loci where the base has only the gap and witnesses have
          verses. Consecutive such loci at the same gap with the same
          witnesses form one entry.
        Pairs already recorded by a real verse entry are skipped.
        """
        try:
            resolver = self.get_resolver()
            base_prefix = self._base_prefix()
            if not base_prefix or not synoptic_loci:
                return []

            # Recorded pairs: (base verse id, witness prefix) for omissions
            # and substitutions, (witness prefix, witness verse id) for additions.
            covered_omit: set = set()
            covered_add: set = set()
            for entry in real_entries:
                if not entry.get('is_verse_entry'):
                    continue
                base_ids = resolver.verse_ids(entry['target'])
                for reading in entry.get('readings') or []:
                    for token in (reading.get('attributes', {}).get('corresp') or '').split():
                        spec = parse_location_token(token)
                        if not spec:
                            continue
                        for base_id in base_ids:
                            covered_omit.add((base_id, spec['prefix']))
                        if spec['kind'] == 'single':
                            covered_add.add((spec['prefix'], spec['id']))

            def split_token(token):
                spec = parse_location_token(token)
                return (spec['prefix'], spec) if spec else (None, None)

            generated: list[dict] = []

            # --- omissions ---
            runs: dict[str, dict] = {}  # prefix -> open run
            finished: list[dict] = []

            def close(prefix):
                run = runs.pop(prefix, None)
                if run:
                    finished.append(run)

            for key, info in synoptic_loci.items():
                base_token = self._locus_base_token(key)
                base_prefix_of_key, base_spec = split_token(base_token)
                base_is_verse = (base_spec is not None and base_spec['kind'] == 'single'
                                 and resolver.is_verse_spec(base_spec))
                absent_here: dict[str, str] = {}
                if base_is_verse:
                    for token in info.get('target') or []:
                        prefix, _spec = split_token(token)
                        if prefix and prefix != base_prefix and resolver.is_absent_verse_token(token) \
                                and (base_spec['id'], prefix) not in covered_omit:
                            absent_here[prefix] = token
                for prefix in list(runs):
                    if prefix not in absent_here:
                        close(prefix)
                for prefix, token in absent_here.items():
                    run = runs.get(prefix)
                    if run:
                        run['end'] = base_spec['id']
                        if token not in run['tokens']:
                            run['tokens'].append(token)
                    else:
                        runs[prefix] = {'prefix': prefix, 'start': base_spec['id'], 'end': base_spec['id'],
                                        'key': key, 'n': info.get('n'), 'tokens': [token]}
            for prefix in list(runs):
                close(prefix)

            spans: dict[tuple, list[dict]] = {}
            for run in finished:
                spans.setdefault((run['start'], run['end']), []).append(run)
            for (start, end), span_runs in spans.items():
                target = (f'{base_prefix}:{start}' if start == end
                          else f'{base_prefix}:range({start}, {end})')
                ptrs = [t for run in span_runs for t in run['tokens']]
                wit_ids = [w for w in (self._witness_for_prefix(r['prefix']) for r in span_runs) if w]
                entry = self._generated_verse_entry(target, span_runs[0]['key'], span_runs[0]['n'],
                                                    'hc:OmissionVariant', wit_ids, ptrs, resolver)
                generated.append(entry)

            # --- additions ---
            group: dict | None = None

            def flush():
                if group and group['ptrs']:
                    wit_ids = [w for w in (self._witness_for_prefix(p) for p in group['prefixes']) if w]
                    ptrs = resolver.collapse_verse_ptrs(group['ptrs'])
                    entry = self._generated_verse_entry(group['target'], group['keys'][0], group['n'],
                                                        'hc:AdditionVariant', wit_ids, ptrs, resolver)
                    first_n = synoptic_loci[group['keys'][0]].get('n')
                    last_n = synoptic_loci[group['keys'][-1]].get('n')
                    entry['lemma'] = self._verse_lemma(group['target'], resolver,
                                                       label=self._span_label(first_n, last_n))
                    generated.append(entry)

            for key, info in synoptic_loci.items():
                base_token = self._locus_base_token(key)
                if not resolver.is_absent_verse_token(base_token):
                    flush()
                    group = None
                    continue
                present: dict[str, str] = {}
                for token in info.get('target') or []:
                    prefix, spec = split_token(token)
                    if (prefix and prefix != base_prefix and spec['kind'] == 'single'
                            and resolver.is_verse_spec(spec) and (prefix, spec['id']) not in covered_add):
                        present[prefix] = token
                prefixes = tuple(sorted(present))
                if group and group['target'] == base_token and group['prefixes'] == prefixes:
                    group['keys'].append(key)
                    group['ptrs'].extend(present.values())
                else:
                    flush()
                    group = {'target': base_token, 'prefixes': prefixes, 'keys': [key],
                             'n': info.get('n'), 'ptrs': list(present.values())}
            flush()

            return generated
        except Exception as e:
            print(f"WARNING: Could not generate verse entries from the synoptic map: {str(e)}")
            return []

    def _generated_verse_entry(self, target: str, locus_key: str, n: str | None, ana: str,
                               wit_ids: list[str], ptrs: list[str],
                               resolver: WitnessFragmentResolver) -> dict:
        if ana == 'hc:OmissionVariant':
            text, html = 'om.', '<i>om.</i>'
        else:
            text, html = resolver.resolve_text_html(ptrs, mode=NORMALIZED)
        return {
            'id': None,
            'is_generated': True,
            'is_verse_entry': True,
            'loc': n,
            'corresp': locus_key,
            'target': target,
            'lemma': self._verse_lemma(target, resolver),
            'lemma_is_explicit': False,
            'readings': [{
                'text': text,
                'html': html,
                'ptrs': ptrs,
                'attributes': {
                    'wit': ' '.join(f'#{w}' for w in wit_ids),
                    'ana': ana,
                    'corresp': ' '.join(resolver.normalize_corresp_token(p) for p in ptrs),
                },
            }],
            'is_emendation': False,
            'note': None,
        }

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

        text, html = resolver.resolve_ordered_text_html(base_tokens, mode=NORMALIZED)
        if not text:
            return None
        return {
            'text': text,
            'html': html,
            'attributes': {'corresp': ' '.join(resolver.normalize_corresp_token(t) for t in base_tokens)}
        }

    def _resolve_base_reading(self, target: str, rdg_elements, readings: list[dict[str, Any]],
                              resolver: WitnessFragmentResolver) -> dict[str, Any]:
        """
        The base text's own, uncorrected reading at an emended location - shown
        as the first reading after the lemma bracket, attributed to the base
        witness plus every hc:BaseTextSupportingVariant reading's witnesses
        ("*K*atzen] Tatzen A B"). Empty (e.g. an <supplied> addition with
        nothing transmitted) renders as om.
        """
        text, html = resolver.resolve_text_html([target])
        if not text:
            text, html = 'om.', '<i>om.</i>'

        wit_ids = []
        base_id = self._get_base_witness_id()
        if base_id:
            wit_ids.append(base_id)
        for rdg, reading in zip(rdg_elements, readings, strict=True):
            if BASE_TEXT_SUPPORTING_ANA in ana_tokens(rdg):
                for wit in (reading['attributes'].get('wit') or '').split():
                    wit_id = wit.lstrip('#')
                    if wit_id and wit_id not in wit_ids:
                        wit_ids.append(wit_id)

        return {
            'text': text,
            'html': html,
            'wit_ids': wit_ids,
            'attributes': {
                'wit': ' '.join(f'#{w}' for w in wit_ids),
                'corresp': resolver.normalize_corresp_token(target),
            },
        }

    def _resolve_target_lemma(self, target: str, resolver: WitnessFragmentResolver,
                              emended: bool = False) -> dict[str, Any]:
        """
        Resolve @target - the base text's own reading at this location - into a
        lemma dict, the new-format equivalent of the old format's inline <lem>.
        A target that resolves to no text (e.g. a left()/right() gap position with
        no base-text content at all) renders as an omission, matching the
        classical apparatus convention used elsewhere for omission variants.

        emended: the span contains an editorial emendation - render the edited
        text (corr/supplied in italics, surplus removed) instead of the
        transmitted one; see location_resolver's EMENDED mode. The lemma is
        always normalized (<reg>, long s as 's'), like the base-text row in
        Location Details.
        """
        text, html = resolver.resolve_text_html(
            [target], mode=EMENDED_NORMALIZED if emended else NORMALIZED)
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
        is_omission = 'hc:OmissionVariant' in ana_tokens(element)

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
        if not attributes.get('wit'):
            derived_wit = self._derive_wit_from_targets(ptrs, links)
            if derived_wit:
                attributes['wit'] = derived_wit

        # The main witness of a reading is the one whose <ptr> comes first:
        # its text is the reading's (resolve_text_html takes the first
        # prefix), and its siglum is listed first - so put it first in wit.
        main_wit = self._witness_for_target(ptrs[0].get('target')) if ptrs else None
        if main_wit and attributes.get('wit'):
            wit_ids = attributes['wit'].split()
            if f'#{main_wit}' in wit_ids:
                wit_ids.remove(f'#{main_wit}')
                attributes['wit'] = ' '.join([f'#{main_wit}', *wit_ids])

        result = {
            'text': text,
            'html': html,
            'attributes': attributes
        }
        if main_wit:
            result['main_wit'] = main_wit
        if entry_links:
            result['links'] = entry_links

        return result

    def _witness_for_target(self, target: str | None) -> str | None:
        """The witness id whose synoptic prefix a "prefix:..." target uses."""
        if not hasattr(self, '_prefix_to_witness'):
            self._prefix_to_witness = {
                info['synoptic_prefix']: wit_id
                for wit_id, info in self.get_witness_to_prefix_mapping().items()
                if info.get('synoptic_prefix')
            }
        spec = parse_location_token(target) if target else None
        return self._prefix_to_witness.get(spec['prefix']) if spec else None

    def _derive_wit_from_targets(self, ptrs, links) -> str | None:
        """
        Derive a reading's witnesses from the "prefix:" of its <ptr> (or
        <link> witness-side) targets, for a <rdg> written without @wit.
        """
        targets = [p.get('target') or '' for p in ptrs]
        for link_el in links:
            targets.extend((link_el.get('target') or '').split()[1:])
        wit_ids = []
        for target in targets:
            wit_id = self._witness_for_target(target)
            if wit_id and wit_id not in wit_ids:
                wit_ids.append(wit_id)
        return ' '.join(f'#{w}' for w in wit_ids) or None

    def _derive_loc_and_corresp(self, app, resolver: WitnessFragmentResolver) -> tuple[str | None, str | None]:
        """
        Derive a display 'loc' (line number) and 'corresp' (leiths-anchored line
        key, "prefix:line_xml_id") for a new-format <app> element, which no longer
        carries @loc/@corresp itself. Anchors on @target when present; otherwise
        (transposition entries) anchors on the first <link>'s first (base-side)
        token.
        """
        return self._loc_and_corresp_for_token(self._anchor_token(app), resolver)

    @staticmethod
    def _anchor_token(app) -> str | None:
        """The token an <app> is located by: @target, else (transpositions) the
        first <link>'s first (base-side) token."""
        token = app.get('target')
        if not token:
            first_link = app.find('.//tei:rdg/tei:link', namespaces=ns)
            if first_link is not None:
                link_targets = (first_link.get('target') or '').split()
                if link_targets:
                    token = link_targets[0]
        return token

    def _loc_and_corresp_for_token(self, token: str | None,
                                   resolver: WitnessFragmentResolver,
                                   locus_ids: set[str] | None = None) -> tuple[str | None, str | None]:
        """(location label, "prefix:locus_xml_id") of the locus a location token
        lies in - see WitnessFragmentResolver.resolve_line_locator."""
        try:
            if not token:
                return None, None

            spec = parse_location_token(token)
            if not spec:
                return None, None

            anchor_id = spec['start'] if spec['kind'] == 'range' else spec['id']
            line_n, line_xml_id = resolver.resolve_line_locator(spec['prefix'], anchor_id, locus_ids)
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
            'entries': self.get_display_entries(),
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
    

def _regularize_long_s(text: str | None, prefer_reg: bool) -> str | None:
    """
    In the regularized (prefer_reg) reading, replace the medial/long-s
    character (ſ, U+017F) with a plain 's' - a manuscript typographic
    variant with no meaning of its own, normalized away the same way
    orig/reg <choice> alternatives are. Left untouched in the diplomatic
    reading. text may be None (mirrors the .text/.tail attributes it wraps).
    """
    if prefer_reg and text:
        return text.replace('ſ', 's')
    return text


def compute_editorial_addition_ids(root: et.Element) -> set[str]:
    """
    Return the xml:ids of every element that falls between a sibling
    <milestone ana="hc:EditorialAdditionSpan" spanTo="#X"/> and its matching
    <anchor xml:id="X"/> - content reconstructed from other witnesses because
    it's entirely missing from this text (e.g. a run of verses the
    manuscript skips).

    Computed once per witness file at parse time (see
    SynopticMap._parse_witness_file) instead of walked live on every
    Location Details request: a single forward pass over the whole tree in
    document order naturally sweeps in every element between a milestone and
    its anchor, at any nesting depth, without needing a separate per-element
    ancestor/sibling walk.

    The HeiCritPipe pipeline (base text column) expands this same span into
    an ana attribute via the revision_spans step; the Location Details code
    path renders straight from the parsed witness fragment without running
    that pipeline, so it has to recognize the raw span structure itself.

    Known limitation (not present in real data, no worse than the previous
    implementation): overlapping/nested spans aren't tracked - a second
    milestone opening before the first's anchor is reached silently replaces
    the open span instead of nesting.
    """
    ids: set[str] = set()
    open_target: str | None = None
    for el in root.iter():
        if not isinstance(el.tag, str):  # skip comments and processing instructions
            continue
        tag = local_name(el)
        if tag == 'milestone' and el.get('ana') == 'hc:EditorialAdditionSpan':
            open_target = (el.get('spanTo') or '').lstrip('#') or None
            continue
        if tag == 'anchor':
            if open_target is not None and el.get(XML_ID) == open_target:
                xml_id = el.get(XML_ID)
                if xml_id:
                    ids.add(xml_id)
                open_target = None
            continue
        if open_target is not None:
            xml_id = el.get(XML_ID)
            if xml_id:
                ids.add(xml_id)
    return ids


def process_synoptic_token(el:et.Element, prefer_reg: bool = False) -> str:
    """
    prefer_reg selects, within a plain <choice><orig>.../<reg>...</choice>
    alternation, which side wins: False (default) keeps the diplomatic
    <orig> reading (today's behavior everywhere); True prefers the first
    <reg> (regularized) reading instead - used for the base-text row, which
    shows the regularized text with the diplomatic form available in a
    separate toggleable row. Threaded through every recursive call so nested
    <choice> elements resolve with the same preference as their ancestor.
    """
    if not isinstance(el.tag, str):  # skip comments and processing instructions
        return ''
    tag_name = el.tag.split('}')[-1] if '}' in el.tag else el.tag
    result = ''
    if tag_name == 'pc' and prefer_reg:
        # The base-text row (Location Details) drops punctuation entirely in
        # the regularized reading - only the diplomatic row (prefer_reg=False)
        # shows it.
        pass
    elif tag_name in ['w', 'pc']:
        xml_id = el.get(prefix_format('xml','id'))
        result += f"<span class='syn-token syn-token-pre' data-token-id='{xml_id}'> </span><span class='syn-token syn-tei-{tag_name}' data-token-id='{xml_id}'>"
        if el.text is not None:
            result += _regularize_long_s(el.text.strip(), prefer_reg)
        for child in el:
            result += process_synoptic_token(child, prefer_reg)
        result += "</span>"
    # elif tag_name in ['c']:
    #     result += "<span class='syn-tei-space'> </span>"
    elif tag_name == 'choice':
        children = [c for c in el if isinstance(c.tag, str)]
        child_tags = {c.tag.split('}')[-1] if '}' in c.tag else c.tag for c in children}
        if children and child_tags <= {'orig', 'reg'}:
            # A plain orig/reg alternation (possibly with more than one
            # <reg>, e.g. Iwein_J_Wien.xml's <orig>w</orig><reg>w</reg>
            # <reg>u</reg> - the first <reg> wins when preferred). Any other
            # <choice> composition (am/ex abbreviation pairs, corr/sic, a
            # nested <choice> sibling, ...) falls through to the pass-through
            # branch below, unchanged.
            origs = [c for c in children if (c.tag.split('}')[-1] if '}' in c.tag else c.tag) == 'orig']
            regs = [c for c in children if (c.tag.split('}')[-1] if '}' in c.tag else c.tag) == 'reg']
            chosen = None
            if prefer_reg and regs:
                chosen = regs[0]
            elif origs:
                chosen = origs[0]
            # No fallback to regs[0] here when not prefer_reg and there's no
            # <orig> at all (a single real case in AH_E.xml) - rendering
            # nothing keeps the diplomatic reading's output unchanged from
            # before this function gained the prefer_reg parameter.
            if chosen is not None:
                result += _render_choice_alternative(chosen, prefer_reg)
        elif 'corr' in child_tags:
            # An editorial correction (<sic>/<corr>, inside a token or spanning
            # whole tokens): the regularized base-text row shows the emended
            # text, marked in italics; the diplomatic row and every other
            # witness show the transmitted <sic> (nothing, if there is none).
            wanted = 'corr' if prefer_reg else 'sic'
            chosen = next((c for c in children if local_name(c) == wanted), None)
            if chosen is not None:
                inner = _render_choice_alternative(chosen, prefer_reg)
                if prefer_reg and inner:
                    inner = f"<em class='syn-emendation'>{inner}</em>"
                result += inner
        else:
            for child in el:
                result += process_synoptic_token(child, prefer_reg)
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name in ['lg', 'l']:
        for child in el:
            result += process_synoptic_token(child, prefer_reg)
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name == 'reg':
        # Regularized/normalized form - suppressed; the diplomatic <orig> (or
        # plain text) sibling is preferred, matching the same convention used
        # to render apparatus reading text from these files (location_resolver).
        # Its tail is still part of the surrounding flow, so it isn't dropped.
        # (Only reached for a <reg> that ISN'T the chosen alternative of a
        # plain orig/reg <choice> - that case is handled, without hitting
        # this branch, by _render_choice_alternative above.)
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name == 'titlePart':
        if el.text is not None:
            result += _regularize_long_s(el.text.strip(), prefer_reg)
        for child in el:
            result += process_synoptic_token(child, prefer_reg)
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
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name == 'note':
        result += _render_note_marker(el)
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name == 'supplied':
        # An editorial reconstruction of illegible/damaged text (typically a
        # <choice> sibling of an <orig><gap/></orig>). Shown in italics on
        # the regularized base-text row only - suppressed on the diplomatic
        # row and for every other witness, both of which use prefer_reg=False.
        if prefer_reg:
            inner = ''
            if el.text is not None:
                inner += _regularize_long_s(el.text.strip(), prefer_reg)
            for child in el:
                inner += process_synoptic_token(child, prefer_reg)
                if child.tail is not None and child.tail.strip() != '':
                    inner += _regularize_long_s(child.tail, prefer_reg)
            result += f"<em class='syn-supplied'>{inner}</em>"
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name in ('del', 'add'):
        # Scribal deletions and additions (inside a <subst> or on their
        # own): the regularized base-text row shows the corrected text -
        # additions underlined, deletions dropped; the diplomatic row and
        # every other witness show both, deletions struck through.
        if tag_name == 'add' or not prefer_reg:
            inner = _render_inner(el, prefer_reg)
            if inner:
                result += f"<span class='syn-{tag_name}'>{inner}</span>"
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    elif tag_name == 'surplus':
        # Text present in the source but editorially flagged as erroneous/
        # extra - the mirror of <supplied>: kept as plain text in the
        # diplomatic reading (prefer_reg=False, same as every other witness),
        # dropped entirely from the regularized base-text row.
        if not prefer_reg:
            if el.text is not None:
                result += _regularize_long_s(el.text.strip(), prefer_reg)
            for child in el:
                result += process_synoptic_token(child, prefer_reg)
                if child.tail is not None and child.tail.strip() != '':
                    result += _regularize_long_s(child.tail, prefer_reg)
        elif any(isinstance(d.tag, str) and local_name(d) in ('w', 'pc') for d in el.iter()):
            # A whole-token <surplus> (e.g. a word the editor deletes) stays
            # visible - struck through - on the regularized row too, so its
            # tokens remain selectable as the lemma of an apparatus entry.
            # In-word surplus (above) is simply dropped from that row.
            inner = ''
            for child in el:
                inner += process_synoptic_token(child, prefer_reg)
            result += f"<span class='syn-surplus'>{inner}</span>"
        if el.tail is not None and el.tail.strip() != '':
            result += _regularize_long_s(el.tail, prefer_reg)
    else:
        # Default: any other inline element (orig, sic, hi, initial, ex,
        # metamark, ...) is transparent pass-through content - include its own
        # text, its children, and every child's tail. Using a default rather
        # than a fixed whitelist avoids silently dropping real word content
        # (e.g. <ex>n</ex> abbreviation expansions) whenever markup not
        # anticipated by an explicit branch appears in the source.
        result += _render_choice_alternative(el, prefer_reg)
    return result


def _render_choice_alternative(el, prefer_reg: bool) -> str:
    """
    Render el's own content (text + children, recursively threading
    prefer_reg + each child's tail, plus el's own tail) without dispatching
    el itself through process_synoptic_token's tag-based branches.

    Used for two purposes: (1) as process_synoptic_token's default
    pass-through case, and (2) to render a <choice>'s chosen orig/reg
    alternative - critically, when the chosen alternative is a <reg>, it
    must NOT go through the normal tag switch, since the standalone
    tag_name == 'reg' branch unconditionally suppresses reg content (that
    branch exists to drop an UNCHOSEN stray <reg>, not the one just chosen).
    """
    result = _render_inner(el, prefer_reg)
    if el.tail is not None and el.tail.strip() != '':
        result += _regularize_long_s(el.tail, prefer_reg)
    return result


def _render_inner(el, prefer_reg: bool) -> str:
    """el's own text and children (each followed by its tail), without el's tail."""
    result = ''
    if el.text is not None:
        result += _regularize_long_s(el.text.strip(), prefer_reg)
    for child in el:
        result += process_synoptic_token(child, prefer_reg)
        if child.tail is not None and child.tail.strip() != '':
            result += _regularize_long_s(child.tail, prefer_reg)
    return result


def _render_note_marker(note_element) -> str:
    """
    Render an editorial/transcription <note> as a clickable star marker whose
    full text is stashed in a data attribute - the frontend shows it in a
    popup on click instead of dumping the note text inline into the witness
    reading, which would otherwise corrupt the transcription being displayed.
    """
    note_text = ' '.join(''.join(note_element.itertext()).split())
    return (
        "<span class='syn-note-marker' tabindex='0' role='button' "
        f"data-note-text=\"{html_escape(note_text)}\" title='Anmerkung anzeigen'>★</span>"
    )


def _render_line_notes(element) -> str:
    """
    Render any <note> elements associated with this line via @target.

    Witness files place these as siblings of <l> inside <lg> (or similar
    containers), pointing back at the line with @target="#<xml:id>" - not as
    children of <l> itself - so process_synoptic_token's own 'note' branch
    (which only sees actual children) never encounters them. Look them up
    explicitly among element's siblings and append their star markers.
    """
    xml_id = element.get(prefix_format('xml', 'id'))
    parent = element.getparent()
    if not xml_id or parent is None:
        return ''
    target = f'#{xml_id}'
    result = ''
    for sibling in parent:
        if not isinstance(sibling.tag, str):
            continue
        tag_name = sibling.tag.split('}')[-1] if '}' in sibling.tag else sibling.tag
        if tag_name == 'note' and sibling.get('target') == target:
            result += _render_note_marker(sibling)
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


def process_synoptic_unit_for_comparison(
    element: et.Element,
    prefer_reg: bool = False,
    editorial_addition_ids: set[str] | None = None,
) -> str:
    """
    Process an XML synoptic unit and return a string representation for comparison.

    Args:
        element: The lxml etree Element to process
        prefer_reg: see process_synoptic_token - False (default) renders the
            diplomatic reading, True the regularized one.
        editorial_addition_ids: the set of xml:ids (from
            SynopticMap.get_wit_editorial_addition_ids) that fall inside an
            hc:EditorialAdditionSpan in this witness's file - only consulted
            on the diplomatic (prefer_reg=False) path.

    Returns:
        String representation of the element content
    """
    if element is None:
        return '<div class="synoptic-content-no-data">Stelle nicht gefunden</div>'

    try:
        # A whole unit reconstructed from other witnesses (e.g. a verse this
        # manuscript skips entirely) has nothing to diplomatically transcribe -
        # same as an empty <gap>, the grey/diplomatic row shows "om." instead
        # of the reconstructed text (which is still shown on the regularized
        # row, via prefer_reg=True).
        if not prefer_reg and editorial_addition_ids and element.get(XML_ID) in editorial_addition_ids:
            return "<div class='synoptic-content-om'>om.</div>"

        # Get the text content of the element, stripping whitespace
        # line_content = ''.join(element.itertext()).strip()
        line_content = ''
        for el in element:
            line_content += process_synoptic_token(el, prefer_reg)
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

        line_content += _render_line_notes(element)
        return line_content
        
    except Exception as e:
        return f"[Error processing element: {str(e)}]"
