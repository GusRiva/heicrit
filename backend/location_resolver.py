"""
Resolves "prefix:location" addresses (used in the new apparatus data model's
<ptr>/<link> elements) against witness fragment text files, producing the
reading text/HTML that used to be written inline in the old data model.
"""

from __future__ import annotations

from io import BytesIO
from html import escape as html_escape
from lxml import etree as et
from heipy.parsers import HeiEditionsParser
from load_functions import resolve_relative_path, find_file_in_project, parse_location_token, local_name

XML_ID = '{http://www.w3.org/XML/1998/namespace}id'


DIPLOMATIC = 'diplomatic'
EMENDED = 'emended'

# Inline-token and container-level elements that mark an editorial
# emendation of the text (see test_data/emendatio/spec/app_emendatio.xml).
EMENDATION_CONTAINER_TAGS = ('choice', 'surplus', 'supplied')


def _child_tags(el) -> set[str]:
    return {local_name(c) for c in el if isinstance(c.tag, str)}


def _is_correction_choice(el) -> bool:
    """<choice> pairing an erroneous <sic> with an editorial <corr>."""
    return local_name(el) == 'choice' and 'corr' in _child_tags(el)


def _in_correction_choice(el) -> bool:
    parent = el.getparent()
    return parent is not None and _is_correction_choice(parent)


def _is_reconstruction_supplied(el) -> bool:
    """
    <supplied> as the reconstruction of illegible/damaged text, i.e. a
    sibling of an <orig> inside a <choice> (e.g. <choice><orig><gap/></orig>
    <supplied>en</supplied></choice>) - not an emendation, and rendered as
    plain text in both modes (unchanged from before the modes existed).
    """
    parent = el.getparent()
    return parent is not None and local_name(parent) == 'choice' and 'orig' in _child_tags(parent)


def is_emendation_element(el) -> bool:
    """True if el itself marks an editorial emendation of the base text."""
    if not isinstance(el.tag, str):
        return False
    tag = local_name(el)
    if tag == 'choice':
        return _is_correction_choice(el)
    if tag == 'surplus':
        return True
    if tag == 'supplied':
        return not _is_reconstruction_supplied(el)
    return False


def _emendation_context(token) -> str | None:
    """
    How a token's ancestors (up to its <l>) place it in an emendation:
    'added' (inside a <corr> or emendation <supplied>: not transmitted),
    'removed' (inside a <sic> paired with a <corr>, or a <surplus>: not in
    the edited text), or None.
    """
    for ancestor in token.iterancestors():
        tag = local_name(ancestor)
        if tag == 'l':
            break
        if tag == 'corr' and _in_correction_choice(ancestor):
            return 'added'
        if tag == 'supplied' and not _is_reconstruction_supplied(ancestor):
            return 'added'
        if (tag == 'sic' and _in_correction_choice(ancestor)) or tag == 'surplus':
            return 'removed'
    return None


def _token_in_context(token, mode: str) -> list[tuple[et.Element, bool]]:
    """
    A directly addressed token as a (token, italic) list, honouring the
    emendation it sits in: dropped where its side doesn't belong to mode,
    italic when it is emended text in EMENDED mode.
    """
    context = _emendation_context(token)
    if context == 'added':
        return [(token, True)] if mode == EMENDED else []
    if context == 'removed':
        return [] if mode == EMENDED else [(token, False)]
    return [(token, False)]


def _render_token(element, mode: str = DIPLOMATIC) -> tuple[str, str]:
    """
    Render a witness token element (<w>/<pc>) to (text, html), preferring the
    diplomatic <orig> form over <reg> when a <choice> is present, and mapping
    <emph> to <em> in the html output (matching apparatus._inline_to_html's
    convention for editorial emphasis).

    mode selects how editorial emendations are rendered:
    - DIPLOMATIC (default; every witness reading, and the base text's own
      uncorrected reading): the source as transmitted - <sic> and <surplus>
      kept, <corr> and <supplied> dropped.
    - EMENDED (the lemma of an emended base-text span): the edited text -
      <sic> dropped, <corr>/<supplied> shown in italics, <surplus> replaced
      by "[ ]" at its position.
    """
    text_parts: list[str] = []
    html_parts: list[str] = []

    def walk_wrapped(child, wrapper_tag: str):
        inner_text_start = len(text_parts)
        inner_html_start = len(html_parts)
        walk(child)
        inner_text = ''.join(text_parts[inner_text_start:])
        inner_html = ''.join(html_parts[inner_html_start:])
        del text_parts[inner_text_start:]
        del html_parts[inner_html_start:]
        text_parts.append(inner_text)
        html_parts.append(f'<{wrapper_tag}>{inner_html}</{wrapper_tag}>' if inner_html else '')

    def walk(el):
        # Pretty-printing whitespace between a <choice>'s alternatives
        # (<choice><sic/>\n   <corr>d</corr>) is not text.
        in_choice = local_name(el) == 'choice'
        if el.text and not (in_choice and not el.text.strip()):
            text_parts.append(el.text)
            html_parts.append(html_escape(el.text))
        for child in el:
            if not isinstance(child.tag, str):
                continue
            tag = local_name(child)
            if tag == 'reg':
                pass
            elif tag == 'sic' and _in_correction_choice(child):
                if mode != EMENDED:
                    walk(child)
            elif tag == 'corr' and _in_correction_choice(child):
                if mode == EMENDED:
                    if ''.join(child.itertext()).strip():
                        walk_wrapped(child, 'em')
                    else:
                        # An empty <corr/> deletes its <sic> - marked like
                        # an in-word <surplus>.
                        text_parts.append('[ ]')
                        html_parts.append('[ ]')
            elif tag == 'supplied' and not _is_reconstruction_supplied(child):
                if mode == EMENDED:
                    walk_wrapped(child, 'em')
            elif tag == 'surplus':
                if mode == EMENDED:
                    text_parts.append('[ ]')
                    html_parts.append('[ ]')
                else:
                    walk(child)
            elif tag == 'emph':
                walk_wrapped(child, 'em')
            else:
                walk(child)
            if child.tail and not (in_choice and not child.tail.strip()):
                text_parts.append(child.tail)
                html_parts.append(html_escape(child.tail))

    walk(element)
    return ''.join(text_parts).strip(), ''.join(html_parts).strip()


def _collect_tokens(container, mode: str = DIPLOMATIC, italic: bool = False) -> list[tuple[et.Element, bool]]:
    """
    Collect the <w>/<pc> tokens inside a non-token container (an <l>, or a
    token-spanning <choice>/<surplus>/<supplied>), in document order, as
    (token, italic) pairs - descending through intermediate markup but
    choosing ONE side of every <choice> (sic vs. corr by mode, orig over reg)
    and dropping container-level <surplus>/<supplied> per mode, the same
    rules _render_token applies inside a single token. italic marks tokens
    that lie inside an emendation in EMENDED mode.
    """
    tokens: list[tuple[et.Element, bool]] = []
    tag = local_name(container)

    if tag == 'choice':
        tags = _child_tags(container)
        if 'corr' in tags:
            side = 'corr' if mode == EMENDED else 'sic'
            side_italic = italic or mode == EMENDED
        elif 'orig' in tags:
            side, side_italic = 'orig', italic
        else:
            side, side_italic = None, italic
        for child in container:
            if not isinstance(child.tag, str):
                continue
            if side is None or local_name(child) == side:
                tokens.extend(_collect_tokens(child, mode, side_italic))
                if side is not None:
                    break
        return tokens

    for child in container:
        tokens.extend(_collect_child_tokens(child, mode, italic))
    return tokens


def _collect_child_tokens(child, mode: str = DIPLOMATIC, italic: bool = False) -> list[tuple[et.Element, bool]]:
    """_collect_tokens' handling of ONE child of a container."""
    if not isinstance(child.tag, str):
        return []
    child_tag = local_name(child)
    if child_tag in ('w', 'pc'):
        return [(child, italic)]
    if child_tag in ('note', 'reg'):
        return []
    if child_tag == 'surplus':
        return _collect_tokens(child, mode, italic) if mode != EMENDED else []
    if child_tag == 'supplied' and not _is_reconstruction_supplied(child):
        return _collect_tokens(child, mode, True) if mode == EMENDED else []
    return _collect_tokens(child, mode, italic)


def _render_tokens(tokens: list[tuple[et.Element, bool]], mode: str = DIPLOMATIC) -> tuple[str, str]:
    """
    Join rendered tokens with single spaces; a run of consecutive italic
    tokens becomes ONE <em> span ("<em>keine Hunde</em>", not two).
    """
    texts: list[str] = []
    html_runs: list[tuple[bool, list[str]]] = []
    for token, italic in tokens:
        text, html = _render_token(token, mode)
        if text:
            texts.append(text)
        if html:
            if html_runs and html_runs[-1][0] == italic:
                html_runs[-1][1].append(html)
            else:
                html_runs.append((italic, [html]))
    htmls = [f"<em>{' '.join(run)}</em>" if italic else ' '.join(run) for italic, run in html_runs]
    return ' '.join(texts), ' '.join(htmls)


def _render_container(container, mode: str = DIPLOMATIC) -> tuple[str, str]:
    """
    Render a non-token container element (e.g. a whole <l>, or a
    token-spanning <choice>) by joining the rendered text/html of its
    <w>/<pc> tokens - avoids picking up the raw pretty-printing whitespace
    between them that a naive text-node walk over the whole subtree would
    include.
    """
    return _render_tokens(_collect_tokens(container, mode), mode)


class WitnessFragmentResolver:
    """
    Resolves "prefix:location" tokens (single id / range() / left() / right())
    into witness token elements and their rendered text/HTML, by reading the
    per-poem witness fragment files a project's prefixDef entries point at.

    Every public method fails soft (logs and returns an empty/None result)
    rather than raising, so one bad or missing reference doesn't take down
    the whole apparatus load.
    """

    def __init__(self, apparatus_filepath: str, project_files: dict | None,
                 witness_prefix_mapping: dict):
        self._apparatus_filepath = apparatus_filepath
        self._project_files = project_files
        self._prefix_to_target_file = {
            info['synoptic_prefix']: info['target_file']
            for info in witness_prefix_mapping.values()
            if info.get('synoptic_prefix') and info.get('target_file')
        }
        self._fragment_cache: dict[str, dict | None] = {}

    def _get_fragment(self, prefix: str) -> dict | None:
        if prefix in self._fragment_cache:
            return self._fragment_cache[prefix]

        fragment = None
        target_file = self._prefix_to_target_file.get(prefix)
        if target_file:
            try:
                resolved_path = resolve_relative_path(target_file, self._apparatus_filepath)
                if self._project_files is not None:
                    file_data = find_file_in_project(resolved_path, self._project_files)
                    content = file_data['content'] if file_data else None
                else:
                    with open(resolved_path, encoding='utf-8') as f:
                        content = f.read()

                if content:
                    # recover=True: some witness fragments reference entities missing
                    # from heipy's bundled declaration set (e.g. &aelig;/&oelig; inside
                    # <reg> regularizations we don't even render) - don't let one bad
                    # entity anywhere in the document block resolving unrelated tokens.
                    parser = HeiEditionsParser(resolve_entities=True, recover=True)
                    doc = et.parse(BytesIO(content.encode('utf-8')), parser)
                    root = doc.getroot()
                    by_id = {}
                    for el in root.iter():
                        if not isinstance(el.tag, str):
                            continue
                        xml_id = el.get(XML_ID)
                        if xml_id:
                            by_id[xml_id] = el
                    fragment = {'root': root, 'by_id': by_id}
            except Exception as e:
                print(f"WARNING: Could not resolve witness fragment for prefix '{prefix}': {str(e)}")

        self._fragment_cache[prefix] = fragment
        return fragment

    def resolve_element(self, prefix: str, xml_id: str) -> et.Element | None:
        fragment = self._get_fragment(prefix)
        if not fragment:
            return None
        return fragment['by_id'].get(xml_id)

    def _next_token_id(self, prefix: str, xml_id: str) -> str | None:
        """Return the xml:id of the next <w>/<pc> sibling after xml_id, if any."""
        el = self.resolve_element(prefix, xml_id)
        if el is None:
            return None
        parent = el.getparent()
        if parent is None:
            return None
        found_self = False
        for child in parent:
            if not isinstance(child.tag, str):
                continue
            if found_self and local_name(child) in ('w', 'pc'):
                return child.get(XML_ID)
            if child is el:
                found_self = True
        return None

    def normalize_corresp_token(self, token: str) -> str:
        """
        Rewrite "prefix:right(id)" to the equivalent "prefix:left(next_id)" when a
        following <w>/<pc> sibling exists.

        The synoptic comparison view (process_synoptic_unit_for_comparison) only
        emits ONE trailing gap-marker span per line - for the line's very last
        token - but a leading gap-marker span before EVERY token. So right(id)
        only highlights correctly when id is the last token on the line; for any
        other position it must be expressed as left() of the following token to
        find a matching span in the rendered HTML. Any other token form (left,
        single, range) is returned unchanged.
        """
        spec = parse_location_token(token)
        if spec and spec['kind'] == 'single':
            # A token-spanning emendation container (<choice xml:id>,
            # <surplus xml:id>) has no span of its own in the rendered rows -
            # expand it to every <w>/<pc> inside it (both the sic and the
            # corr side), so whichever row shows them gets highlighted.
            el = self.resolve_element(spec['prefix'], spec['id'])
            if el is not None and local_name(el) in EMENDATION_CONTAINER_TAGS:
                ids = [t.get(XML_ID) for t in el.iter() if isinstance(t.tag, str)
                       and local_name(t) in ('w', 'pc') and t.get(XML_ID)]
                if ids:
                    return ' '.join(f"{spec['prefix']}:{i}" for i in ids)
            return token
        if spec and spec['kind'] == 'range':
            # A range whose ends sit in different containers (e.g. across
            # the <sic> and <corr> of an id-less <choice>) can't be walked
            # in one rendered row - list its tokens individually.
            start_el = self.resolve_element(spec['prefix'], spec['start'])
            end_el = self.resolve_element(spec['prefix'], spec['end'])
            if start_el is not None and end_el is not None and start_el.getparent() is not end_el.getparent():
                ids = [el.get(XML_ID) for el in self._span_elements(spec)
                       if local_name(el) in ('w', 'pc') and el.get(XML_ID)]
                if ids:
                    return ' '.join(f"{spec['prefix']}:{i}" for i in ids)
            return token
        if not spec or spec['kind'] != 'right':
            return token
        next_id = self._next_token_id(spec['prefix'], spec['id'])
        if not next_id:
            return token
        return f"{spec['prefix']}:left({next_id})"

    def resolve_line_locator(self, prefix: str, xml_id: str) -> tuple[str | None, str | None]:
        """Return (line @n, line @xml:id) for the <l> containing (or being) xml_id."""
        el = self.resolve_element(prefix, xml_id)
        if el is None:
            return None, None
        if local_name(el) == 'l':
            line_el = el
        else:
            line_el = next((a for a in el.iterancestors() if local_name(a) == 'l'), None)
        if line_el is None:
            return None, None
        return line_el.get('n'), line_el.get(XML_ID)

    def _range_tokens(self, prefix: str, start_id: str, end_id: str,
                      mode: str = DIPLOMATIC) -> list[tuple[et.Element, bool]]:
        """
        The (token, italic) pairs from start_id through end_id. When both
        share a parent, every sibling in between is included - descending
        into token-spanning containers (a <choice>/<surplus> between them)
        per mode, see _collect_tokens.
        """
        fragment = self._get_fragment(prefix)
        if not fragment:
            return []
        start_el = fragment['by_id'].get(start_id)
        end_el = fragment['by_id'].get(end_id)
        if start_el is None or end_el is None:
            return []

        parent = start_el.getparent()
        if parent is None or end_el.getparent() is not parent:
            # Start and end in different containers (e.g. one in a <sic>,
            # one in its <corr>): take every token of their common ancestor
            # that lies between them in document order, chosen per mode.
            start_ancestors = [start_el, *start_el.iterancestors()]
            common = next((a for a in [end_el, *end_el.iterancestors()] if a in start_ancestors), None)
            if common is None:
                return _token_in_context(start_el, mode) + _token_in_context(end_el, mode)
            order = {el: i for i, el in enumerate(common.iter())}
            lo, hi = order[start_el], order[end_el]
            in_span = [(t, it) for t, it in _collect_tokens(common, mode) if lo <= order.get(t, -1) <= hi]
            context_italic = _emendation_context(common) == 'added' and mode == EMENDED
            return [(t, it or context_italic) for t, it in in_span]

        collecting = False
        tokens: list[tuple[et.Element, bool]] = []
        for child in parent:
            if child is start_el:
                collecting = True
            if collecting:
                tokens.extend(_collect_child_tokens(child, mode))
            if child is end_el:
                break
        return tokens

    def _render_token_range(self, prefix: str, start_id: str, end_id: str,
                            mode: str = DIPLOMATIC) -> tuple[str, str]:
        return _render_tokens(self._range_tokens(prefix, start_id, end_id, mode), mode)

    def _neighbour_token(self, el, direction: int):
        """
        The nearest <w>/<pc> before (direction=-1) or after (+1) el in
        document order within the same <l>, skipping tokens inside el itself.
        """
        line_el = next((a for a in el.iterancestors() if local_name(a) == 'l'), None)
        scope = line_el if line_el is not None else el.getparent()
        if scope is None:
            return None
        inside = set(el.iter())
        tokens = [t for t in scope.iter() if isinstance(t.tag, str) and local_name(t) in ('w', 'pc')]
        if direction > 0:
            after = False
            for t in tokens:
                if t in inside:
                    after = True
                elif after:
                    return t
            if not after:
                # el holds no token: find the first token after it in document order
                order = list(scope.iter())
                pos = order.index(el) if el in order else -1
                return next((t for t in tokens if order.index(t) > pos), None)
            return None
        before = None
        for t in tokens:
            if t in inside:
                return before
            before = t
        return before

    def _resolve_id(self, prefix: str, xml_id: str, mode: str = DIPLOMATIC) -> tuple[str, str]:
        el = self.resolve_element(prefix, xml_id)
        if el is None:
            return '', ''
        if local_name(el) in ('w', 'pc'):
            return _render_tokens(_token_in_context(el, mode), mode)
        if mode == EMENDED and local_name(el) == 'surplus':
            # A whole-token <surplus> deleted by the editor: in the emended
            # text it is a gap, rendered like a left()/right() position -
            # "vor <next token>" (or "nach <previous token>" at line end).
            for direction, marker in ((1, 'vor'), (-1, 'nach')):
                neighbour = self._neighbour_token(el, direction)
                if neighbour is not None:
                    text, html = _render_token(neighbour, mode)
                    if text:
                        return f'{marker} {text}', f'<em>{marker}</em> {html}'
            return '', ''
        return _render_container(el, mode)

    def _document_order_key(self, prefix: str, xml_id: str) -> int:
        """
        Return a sortable key reflecting xml_id's position in document order
        within its fragment - used to reconstruct a witness's actual word order
        from an unordered/differently-ordered set of token references (e.g. a
        transposition's <link> pairs, which are declared in the BASE text's
        order, not necessarily the witness's).
        """
        fragment = self._get_fragment(prefix)
        if not fragment:
            return 0
        order_index = fragment.get('order_index')
        if order_index is None:
            order_index = {}
            for i, el in enumerate(fragment['root'].iter()):
                xid = el.get(XML_ID)
                if xid and xid not in order_index:
                    order_index[xid] = i
            fragment['order_index'] = order_index
        return order_index.get(xml_id, 0)

    def _are_adjacent(self, spec_a: dict, spec_b: dict) -> bool:
        """
        True if spec_b's token immediately follows spec_a's with no other
        w/pc token in between - used by resolve_ordered_text_html to detect a
        skipped token between two consecutive entries of a reconstructed
        transposition lemma/reading.
        """
        if spec_a['prefix'] != spec_b['prefix']:
            return False
        el_a = self.resolve_element(spec_a['prefix'], spec_a['id'])
        el_b = self.resolve_element(spec_b['prefix'], spec_b['id'])
        if el_a is None or el_b is None:
            return False
        parent = el_a.getparent()
        if parent is None or el_b.getparent() is not parent:
            return False
        collecting = False
        for child in parent:
            if child is el_a:
                collecting = True
                continue
            if collecting:
                if child is el_b:
                    return True
                if isinstance(child.tag, str) and local_name(child) in ('w', 'pc'):
                    return False
        return False

    def resolve_ordered_text_html(self, tokens: list[str]) -> tuple[str, str]:
        """
        Resolve MULTIPLE distinct single-id tokens (e.g. the base-side or
        witness-side tokens of a transposition's <link> pairs) into one
        text/html string, ordered by each token's actual position in ITS OWN
        witness's document - not by the order the tokens happen to be listed
        in - so the reconstructed phrase reflects that witness's real word
        order rather than the order links were declared in. A gap between two
        consecutive tokens (i.e. the transposition skipped over an
        intervening word) is marked with an ellipsis, the classical
        apparatus convention for omitted material. Tokens are deduplicated
        (by prefix+id) before rendering, since the same base token can appear
        once per witness sharing the same transposition pattern - without
        this, both the word and the gap detection would be thrown off by the
        repeat.
        """
        specs = [s for s in (parse_location_token(t) for t in tokens) if s and s['kind'] == 'single']
        specs.sort(key=lambda s: self._document_order_key(s['prefix'], s['id']))

        deduped: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for spec in specs:
            key = (spec['prefix'], spec['id'])
            if key not in seen:
                seen.add(key)
                deduped.append(spec)

        texts: list[str] = []
        htmls: list[str] = []
        prev_spec: dict | None = None
        for spec in deduped:
            text, html = self._resolve_id(spec['prefix'], spec['id'])
            if not text and not html:
                continue
            if prev_spec is not None and not self._are_adjacent(prev_spec, spec):
                texts.append('…')
                htmls.append('…')
            if text:
                texts.append(text)
            if html:
                htmls.append(html)
            prev_spec = spec
        return ' '.join(texts), ' '.join(htmls)

    def _resolve_spec(self, spec: dict, mode: str = DIPLOMATIC) -> tuple[str, str]:
        prefix = spec['prefix']
        kind = spec['kind']
        try:
            if kind == 'single':
                return self._resolve_id(prefix, spec['id'], mode)
            if kind == 'range':
                return self._render_token_range(prefix, spec['start'], spec['end'], mode)
            if kind in ('left', 'right'):
                # left(id)/right(id) mark a gap position relative to an anchor token
                # that DOES exist (id itself resolves fine) - render it the same way
                # the old format's editors wrote it inline: "vor <anchor>" / "nach
                # <anchor>" (before/after), e.g. docs/data.md's "<emph>vor</emph>
                # miſlichen". Shows WHERE the gap is, instead of a bare 'om.'.
                text, html = self._resolve_id(prefix, spec['id'], mode)
                if not text:
                    return '', ''
                marker = 'vor' if kind == 'left' else 'nach'
                return f'{marker} {text}', f'<em>{marker}</em> {html}'
        except Exception as e:
            print(f"WARNING: Could not resolve text for token spec {spec}: {str(e)}")
        return '', ''

    def resolve_text_html(self, target_tokens: list[str], mode: str = DIPLOMATIC) -> tuple[str, str]:
        """
        Resolve the first target token (in order) that yields non-empty text/html.
        """
        for token in target_tokens:
            spec = parse_location_token(token)
            if not spec:
                continue
            text, html = self._resolve_spec(spec, mode)
            if text or html:
                return text, html
        return '', ''

    def _span_elements(self, spec: dict) -> list[et.Element]:
        """
        The elements a single/range spec covers (left()/right() gap positions
        cover none): the element itself, or every sibling from start through end.
        """
        if spec['kind'] == 'single':
            el = self.resolve_element(spec['prefix'], spec['id'])
            return [el] if el is not None else []
        if spec['kind'] != 'range':
            return []
        start_el = self.resolve_element(spec['prefix'], spec['start'])
        end_el = self.resolve_element(spec['prefix'], spec['end'])
        if start_el is None or end_el is None:
            return []
        parent = start_el.getparent()
        if parent is None or end_el.getparent() is not parent:
            # Different containers: every token between them in document
            # order within their common ancestor.
            start_ancestors = [start_el, *start_el.iterancestors()]
            common = next((a for a in [end_el, *end_el.iterancestors()] if a in start_ancestors), None)
            if common is None:
                return [start_el, end_el]
            tokens = [t for t in common.iter() if isinstance(t.tag, str) and local_name(t) in ('w', 'pc')]
            return tokens[tokens.index(start_el):tokens.index(end_el) + 1] if start_el in tokens and end_el in tokens else [start_el, end_el]
        elements, collecting = [], False
        for child in parent:
            if child is start_el:
                collecting = True
            if collecting and isinstance(child.tag, str):
                elements.append(child)
            if child is end_el:
                break
        return elements

    def has_emendation(self, target: str) -> bool:
        """
        True if the span target addresses contains an editorial emendation
        (<choice> with <corr>, <surplus>, or a non-reconstruction <supplied>),
        i.e. its lemma must be shown emended and the base text's own,
        uncorrected reading added as the first reading.
        """
        spec = parse_location_token(target or '')
        if not spec:
            return False
        try:
            for el in self._span_elements(spec):
                if any(is_emendation_element(d) for d in el.iter()):
                    return True
                if local_name(el) in ('w', 'pc') and _emendation_context(el):
                    return True
            return False
        except Exception as e:
            print(f"WARNING: Could not check emendation for {target}: {str(e)}")
            return False

    def emendation_units(self, prefix: str) -> list[tuple[str, et.Element]]:
        """
        Every editorial emendation in the witness behind prefix (normally the
        base text), in document order, as (target, element) pairs - the
        target an <app> recording it would use:
        - a token-spanning <choice>/<surplus> with an xml:id -> its own id
          ("a:choice_1"); without one, the range of its tokens;
        - an emendation inside a token -> the token ("a:w_1_4"), once per
          token even if it holds several emendations.
        """
        fragment = self._get_fragment(prefix)
        if not fragment:
            return []
        units: list[tuple[str, et.Element]] = []
        seen: set = set()
        for el in fragment['root'].iter():
            if not is_emendation_element(el) or any(a in seen for a in el.iterancestors()):
                continue
            token = next((a for a in el.iterancestors() if local_name(a) in ('w', 'pc')), None)
            if token is not None:
                unit = token
                target_id = token.get(XML_ID)
                target = f'{prefix}:{target_id}' if target_id else None
            else:
                unit = el
                tokens = [t for t in el.iter() if isinstance(t.tag, str)
                          and local_name(t) in ('w', 'pc') and t.get(XML_ID)]
                if el.get(XML_ID):
                    target = f'{prefix}:{el.get(XML_ID)}'
                elif len(tokens) == 1:
                    target = f'{prefix}:{tokens[0].get(XML_ID)}'
                elif tokens:
                    target = f'{prefix}:range({tokens[0].get(XML_ID)}, {tokens[-1].get(XML_ID)})'
                else:
                    target = None
            if unit in seen:
                continue
            seen.add(unit)
            if target:
                units.append((target, unit))
        return units

    def covered_elements(self, target: str) -> set:
        """
        Every element inside the span target addresses (including the span
        elements themselves) - used to tell whether an emendation is already
        recorded by an <app>.
        """
        spec = parse_location_token(target or '')
        if not spec:
            return set()
        return {d for el in self._span_elements(spec) for d in el.iter()}

    def emendation_container_for(self, target: str) -> str | None:
        """
        Lift a token selection to the token-spanning emendation container it
        exactly covers: the tokens of a whole-token <surplus xml:id>, or
        either side (sic or corr) of a <choice xml:id> with <corr>. Returns
        the lifted "prefix:container_id" target, or None if target doesn't
        exactly cover such a container (or the container has no xml:id).
        """
        spec = parse_location_token(target or '')
        if not spec or spec['kind'] not in ('single', 'range'):
            return None
        span = self._span_elements(spec)
        selected = [el for el in span if local_name(el) in ('w', 'pc')]
        # Only plain tokens (and the <c> spacing between them) can be lifted.
        if not selected or any(local_name(el) not in ('w', 'pc', 'c') for el in span):
            return None
        for container in selected[0].iterancestors():
            tag = local_name(container)
            if tag == 'l':
                break
            if tag == 'surplus':
                candidates = [container]
            elif tag in ('sic', 'corr') and _in_correction_choice(container):
                candidates = [container]
                container = container.getparent()
            else:
                continue
            container_id = container.get(XML_ID)
            for side in candidates:
                side_tokens = [t for t in side.iter() if isinstance(t.tag, str) and local_name(t) in ('w', 'pc')]
                if side_tokens != selected:
                    continue
                if container_id:
                    return f"{spec['prefix']}:{container_id}"
                if local_name(container) == 'choice':
                    # No id to point at: a range over BOTH sides of the
                    # choice addresses it just as well.
                    all_ids = [t.get(XML_ID) for t in container.iter() if isinstance(t.tag, str)
                               and local_name(t) in ('w', 'pc') and t.get(XML_ID)]
                    if len(all_ids) >= 2:
                        return f"{spec['prefix']}:range({all_ids[0]}, {all_ids[-1]})"
            return None
        return None
