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


def _render_token(element) -> tuple[str, str]:
    """
    Render a witness token element (<w>/<pc>) to (text, html), preferring the
    diplomatic <orig> form over <reg> when a <choice> is present, and mapping
    <emph> to <em> in the html output (matching apparatus._inline_to_html's
    convention for editorial emphasis).
    """
    text_parts: list[str] = []
    html_parts: list[str] = []

    def walk(el):
        if el.text:
            text_parts.append(el.text)
            html_parts.append(html_escape(el.text))
        for child in el:
            if not isinstance(child.tag, str):
                continue
            tag = local_name(child)
            if tag == 'reg':
                if child.tail:
                    text_parts.append(child.tail)
                    html_parts.append(html_escape(child.tail))
                continue
            if tag == 'emph':
                inner_text_start = len(text_parts)
                inner_html_start = len(html_parts)
                walk(child)
                inner_text = ''.join(text_parts[inner_text_start:])
                inner_html = ''.join(html_parts[inner_html_start:])
                del text_parts[inner_text_start:]
                del html_parts[inner_html_start:]
                text_parts.append(inner_text)
                html_parts.append(f'<em>{inner_html}</em>')
            else:
                walk(child)
            if child.tail:
                text_parts.append(child.tail)
                html_parts.append(html_escape(child.tail))

    walk(element)
    return ''.join(text_parts).strip(), ''.join(html_parts).strip()


def _render_container(container) -> tuple[str, str]:
    """
    Render a non-token container element (e.g. a whole <l>) by joining the
    rendered text/html of its direct <w>/<pc> children - avoids picking up the
    raw pretty-printing whitespace between them that a naive text-node walk
    over the whole subtree would include.
    """
    texts: list[str] = []
    htmls: list[str] = []
    for child in container:
        if not isinstance(child.tag, str):
            continue
        if local_name(child) in ('w', 'pc'):
            text, html = _render_token(child)
            if text:
                texts.append(text)
            if html:
                htmls.append(html)
    return ' '.join(texts), ' '.join(htmls)


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

    def _render_token_range(self, prefix: str, start_id: str, end_id: str) -> tuple[str, str]:
        fragment = self._get_fragment(prefix)
        if not fragment:
            return '', ''
        start_el = fragment['by_id'].get(start_id)
        end_el = fragment['by_id'].get(end_id)
        if start_el is None or end_el is None:
            return '', ''

        parent = start_el.getparent()
        if parent is None or end_el.getparent() is not parent:
            texts, htmls = [], []
            for el in (start_el, end_el):
                t, h = _render_token(el)
                if t:
                    texts.append(t)
                if h:
                    htmls.append(h)
            return ' '.join(texts), ' '.join(htmls)

        collecting = False
        texts, htmls = [], []
        for child in parent:
            if child is start_el:
                collecting = True
            if collecting and isinstance(child.tag, str) and local_name(child) in ('w', 'pc'):
                t, h = _render_token(child)
                if t:
                    texts.append(t)
                if h:
                    htmls.append(h)
            if child is end_el:
                break
        return ' '.join(texts), ' '.join(htmls)

    def _resolve_id(self, prefix: str, xml_id: str) -> tuple[str, str]:
        el = self.resolve_element(prefix, xml_id)
        if el is None:
            return '', ''
        if local_name(el) in ('w', 'pc'):
            return _render_token(el)
        return _render_container(el)

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

    def _resolve_spec(self, spec: dict) -> tuple[str, str]:
        prefix = spec['prefix']
        kind = spec['kind']
        try:
            if kind == 'single':
                return self._resolve_id(prefix, spec['id'])
            if kind == 'range':
                return self._render_token_range(prefix, spec['start'], spec['end'])
            if kind in ('left', 'right'):
                # left(id)/right(id) mark a gap position relative to an anchor token
                # that DOES exist (id itself resolves fine) - render it the same way
                # the old format's editors wrote it inline: "vor <anchor>" / "nach
                # <anchor>" (before/after), e.g. docs/data.md's "<emph>vor</emph>
                # miſlichen". Shows WHERE the gap is, instead of a bare 'om.'.
                text, html = self._resolve_id(prefix, spec['id'])
                if not text:
                    return '', ''
                marker = 'vor' if kind == 'left' else 'nach'
                return f'{marker} {text}', f'<em>{marker}</em> {html}'
        except Exception as e:
            print(f"WARNING: Could not resolve text for token spec {spec}: {str(e)}")
        return '', ''

    def resolve_text_html(self, target_tokens: list[str]) -> tuple[str, str]:
        """
        Resolve the first target token (in order) that yields non-empty text/html.
        """
        for token in target_tokens:
            spec = parse_location_token(token)
            if not spec:
                continue
            text, html = self._resolve_spec(spec)
            if text or html:
                return text, html
        return '', ''
