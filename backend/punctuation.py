"""
Punctuation editing for the Base Text panel.

Lets the frontend's "Edit Punctuation" overlay insert, correct, and remove
punctuation marks (<pc>) in the base/leithandschrift witness's own source
XML file, writing changes straight back to disk. Deliberately separate from
apparatus.py: this edits a witness text file, not the apparatus file, the
same way location_resolver.py and load_functions.py are split out by concern.

Edits only ever touch the regularized/editorial side of a plain orig/reg
<choice> (or a bare <pc> with no orig/reg split at all) - never <orig>, per
the "Regularized/editorial only" scope decision. See
/home/gustavo/.claude/plans/deep-herding-galaxy.md for the full design,
including the slot-based spacing model below (real data shows a mark's
surrounding whitespace is an independent, per-slot fact of the source, not
something inferable from the mark character).
"""

from __future__ import annotations

import hashlib
from lxml import etree as et
from load_functions import local_name
from apparatus import XML_ID

PUNCT_CONTAINER_TAGS = {'l', 'p', 'titlePart'}
_STANDARD_REG_ANA = 'hc:StandardMHGRegularization'


def find_container_by_id(root: et.Element, container_id: str) -> et.Element | None:
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if local_name(el) in PUNCT_CONTAINER_TAGS and el.get(XML_ID) == container_id:
            return el
    return None


def _is_punct_choice(el: et.Element) -> bool:
    """Bare <pc>, or a <choice> whose element children are only orig/reg -
    mirrors process_synoptic_token's own 'plain orig/reg alternation' test."""
    children = [c for c in el if isinstance(c.tag, str)]
    child_tags = {local_name(c) for c in children}
    return bool(children) and child_tags <= {'orig', 'reg'}


def _select_reg(choice: et.Element) -> et.Element | None:
    """Pick the <reg> the Base Text panel actually renders for a plain
    orig/reg <choice> (mirrors reduce_markup.xsl's own reg template): the
    sole <reg> if there is only one, else the one flagged as the standard
    regularization."""
    regs = [c for c in choice if isinstance(c.tag, str) and local_name(c) == 'reg']
    if len(regs) == 1:
        return regs[0]
    for reg in regs:
        if reg.get('ana') == 'hc:StandardMHGRegularization':
            return reg
    return regs[0] if regs else None


def _pc_in_reg(reg: et.Element | None) -> et.Element | None:
    """The single <pc> inside a chosen <reg>, if any - a <reg> with no <pc>
    at all is real (e.g. B_100.xml's l_100_14, the middle of three marks)
    and renders as nothing; build_edit_tokens still represents it (as an
    empty-text mark) so occurrence numbering always matches _locate_gap."""
    if reg is None:
        return None
    for c in reg:
        if isinstance(c.tag, str) and local_name(c) == 'pc':
            return c
    return None


def _orig_of(choice: et.Element) -> et.Element | None:
    return next((c for c in choice if isinstance(c.tag, str) and local_name(c) == 'orig'), None)


def _orig_is_empty(orig: et.Element | None) -> bool:
    return orig is None or (not (orig.text or '').strip() and len(orig) == 0)


def _is_space_c(el: et.Element) -> bool:
    """True for a <c> that is actually just spacing (the established
    convention: exactly one whitespace character). Real data has at least
    one <c> carrying real text instead (H3_28.xml's l_28_21: <c>b</c>, a
    pre-existing data oddity) - never treated as a space to insert/remove,
    so this feature can't silently destroy content it doesn't understand."""
    return local_name(el) == 'c' and not (el.text or '').strip()


def _remove_preserving_tail(parent: et.Element, el: et.Element) -> None:
    """lxml silently drops an element's .tail text on remove() - fold it into
    the previous sibling's tail (or the parent's own text) first, the same
    way write_apparatus_file_and_refresh's callers already have to be careful
    about tail text when mutating a tree."""
    tail = el.tail
    if tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or '') + tail
        else:
            parent.text = (parent.text or '') + tail
    parent.remove(el)


def _long_s(text: str | None) -> str:
    return (text or '').replace('ſ', 's')


def _reg_is_shown(reg_el: et.Element) -> bool:
    """Mirrors reduce_markup.xsl's reg template: with only one <reg> sibling,
    show it regardless of @ana; with more than one, show only the one
    flagged as the standard regularization."""
    parent = reg_el.getparent()
    siblings = [c for c in parent if isinstance(c.tag, str) and local_name(c) == 'reg'] if parent is not None else [reg_el]
    return len(siblings) == 1 or reg_el.get('ana') == _STANDARD_REG_ANA


def _ws_text(text: str | None, parent: et.Element) -> str:
    """Mirrors reduce_markup.xsl's whitespace-only text() suppression: a
    whitespace-only text/tail node is pretty-printing indentation and is
    dropped, unless its parent is <c> (real spacing) or a <reg> with no
    element children (a regularization-only word-boundary space)."""
    if text is None:
        return ''
    if text.strip() == '' and not (local_name(parent) == 'c' or (local_name(parent) == 'reg' and len(parent) == 0)):
        return ''
    return _long_s(text)


def _render_word_node(el: et.Element) -> str:
    """Text contribution of one element and its subtree, mirroring
    reduce_markup.xsl's rules (orig always dropped, reg selection per
    _reg_is_shown, sic/abbr/am pass through, corr/expan/ex/surplus dropped,
    long-s normalized, pretty-print whitespace stripped) - $editorial is
    always false for the Base Text panel, so sic/abbr/am show and
    corr/expan/ex don't."""
    if not isinstance(el.tag, str):
        return ''
    tag = local_name(el)

    if tag == 'orig' or tag in ('corr', 'expan', 'ex', 'surplus'):
        return ''
    if tag == 'reg' and not _reg_is_shown(el):
        return ''

    result = _ws_text(el.text, el)
    for child in el:
        result += _render_word_node(child)
        result += _ws_text(child.tail, el)
    return result


def _plain_word_text(w_el: et.Element) -> str:
    """Plain-text rendering of a <w>, matching what the Base Text panel's
    own XSLT pipeline (reduce_markup.xsl) actually shows for it, so the
    punctuation-edit overlay's word spans read the same as the static
    render underneath them."""
    return _render_word_node(w_el).strip()


def _signature(container: et.Element) -> str:
    return hashlib.sha256(et.tostring(container, encoding='unicode').encode('utf-8')).hexdigest()


def build_edit_tokens(container: et.Element) -> dict:
    """
    Walk container's direct children in document order (w/pc/c/choice are
    always direct children of l|p|titlePart in the real data) and describe
    every word and every inter-word punctuation gap.

    A gap of N marks has N+1 "slots" (before mark 0, between each adjacent
    pair, after the last mark) - real data confirms a <c> may or may not
    appear at any of them independently of the mark character involved
    (e.g. a semicolon sometimes has a trailing space, sometimes not). Each
    mark's own 'space_before' captures the slot immediately preceding it;
    a boundary's 'space_before_next_word' captures the trailing slot after
    its last mark (or, when it has no marks at all, whether any <c> sits in
    the gap at all). A run of 2+ consecutive <c> collapses to True.
    """
    tokens: list[dict] = []
    boundaries: list[dict] = []
    current = {'after_w_id': None, 'editable': True, 'marks': []}
    pending_space = False

    def flush():
        current['space_before_next_word'] = pending_space
        boundaries.append(current)

    for child in container:
        if not isinstance(child.tag, str):
            continue
        tag = local_name(child)

        if tag == 'w':
            flush()
            xml_id = child.get(XML_ID)
            tokens.append({
                'type': 'word',
                'xml_id': xml_id,
                'text': _plain_word_text(child),
            })
            current = {'after_w_id': xml_id, 'editable': xml_id is not None, 'marks': []}
            pending_space = False
        elif tag == 'c':
            if _is_space_c(child):
                pending_space = True
            # else: a <c> carrying real (non-whitespace) content - a rare
            # pre-existing data oddity, not spacing; left untouched and
            # ignored here rather than misread as a space.
        elif tag == 'pc':
            current['marks'].append({
                'occurrence': len(current['marks']),
                'text': child.text or '',
                'shape': 'bare',
                'space_before': pending_space,
            })
            pending_space = False
        elif tag == 'choice' and _is_punct_choice(child):
            reg = _select_reg(child)
            pc = _pc_in_reg(reg)
            shape = 'choice_reg_only' if _orig_is_empty(_orig_of(child)) else 'choice_orig_reg'
            current['marks'].append({
                'occurrence': len(current['marks']),
                'text': pc.text if pc is not None else '',
                'shape': shape,
                'space_before': pending_space,
            })
            pending_space = False
        else:
            continue

    flush()

    return {
        'container_id': container.get(XML_ID),
        'signature': _signature(container),
        'tokens': tokens,
        'boundaries': boundaries,
    }


def build_all_containers_tokens(root: et.Element) -> list[dict]:
    """One build_edit_tokens() per addressable l|p|titlePart in the file
    (those with no xml:id - a genuine pre-existing data gap, see
    Bn_32.xml:815-831 - are skipped: they simply never appear as an editable
    container, matching this feature's exclusion of unreachable content)."""
    result = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if local_name(el) in PUNCT_CONTAINER_TAGS and el.get(XML_ID):
            result.append(build_edit_tokens(el))
    return result


def _locate_gap(container: et.Element, after_w_id: str | None) -> dict:
    """
    Describes the gap immediately following the <w xml:id=after_w_id> (or
    before the first <w>, when after_w_id is None), for mutation purposes:
    {
      'start': int, 'end': int,          # index range into list(container)
      'marks': [et.Element],             # ordered mark elements in the gap
      'mark_index': [int],               # each mark's index into list(container)
    }
    Raises ValueError if after_w_id doesn't match any <w>. Mirrors
    build_edit_tokens's own gap-walk exactly, so occurrence/slot numbering
    always agrees between a fetch and the save that follows it.
    """
    children = list(container)

    if after_w_id is None:
        start = 0
    else:
        start = None
        for idx, child in enumerate(children):
            if isinstance(child.tag, str) and local_name(child) == 'w' and child.get(XML_ID) == after_w_id:
                start = idx + 1
                break
        if start is None:
            raise ValueError(f"No <w xml:id='{after_w_id}'> found in container")

    end = start
    while end < len(children) and not (isinstance(children[end].tag, str) and local_name(children[end]) == 'w'):
        end += 1

    marks, mark_index = [], []
    for idx in range(start, end):
        c = children[idx]
        if not isinstance(c.tag, str):
            continue
        tag = local_name(c)
        if tag == 'pc' or (tag == 'choice' and _is_punct_choice(c)):
            marks.append(c)
            mark_index.append(idx)

    return {'start': start, 'end': end, 'marks': marks, 'mark_index': mark_index}


def _slot_range(gap: dict, slot: int) -> tuple[int, int]:
    """The [lo, hi) index range (into the container's current child list, as
    it was when `gap` was computed) spanned by slot `slot`, using the
    uniform 0..len(marks) convention: slot 0 = before marks[0], slot i =
    between marks[i-1] and marks[i], slot len(marks) = after the last mark
    (or, with no marks at all, the sole slot spans the whole gap)."""
    marks_idx = gap['mark_index']
    n = len(marks_idx)
    if slot < 0 or slot > n:
        raise ValueError(f'No slot {slot} in this gap (has {n} marks)')
    lo = gap['start'] if slot == 0 else marks_idx[slot - 1] + 1
    hi = gap['end'] if slot == n else marks_idx[slot]
    return lo, hi


def _clear_slot_spaces(container: et.Element, lo: int, hi: int) -> None:
    """Remove every <c> in list(container)[lo:hi) (there may be more than
    one - rare but real, e.g. H3_28.xml's l_28_21). Removes right-to-left
    so earlier indices in the snapshot stay valid throughout."""
    children = list(container)
    for idx in range(hi - 1, lo - 1, -1):
        c = children[idx]
        if isinstance(c.tag, str) and _is_space_c(c):
            _remove_preserving_tail(container, c)


def _slot_anchor(container: et.Element, hi: int) -> et.Element | None:
    """The element sitting immediately after a slot's [lo, hi) range - i.e.
    what new content should be inserted before - captured by identity
    BEFORE any mutation (must be called before _clear_slot_spaces, using
    the same hi), so it can be safely re-located afterward even though
    _clear_slot_spaces shifts numeric indices. None means the gap ran to
    the end of the container (append instead of insert-before)."""
    children = list(container)
    return children[hi] if hi < len(children) else None


def _insert_before_anchor(container: et.Element, anchor: et.Element | None, el: et.Element) -> None:
    if anchor is not None:
        container.insert(list(container).index(anchor), el)
    else:
        container.append(el)


def _set_slot_space(container: et.Element, gap: dict, slot: int, want_space: bool) -> None:
    lo, hi = _slot_range(gap, slot)
    anchor = _slot_anchor(container, hi)
    _clear_slot_spaces(container, lo, hi)
    if want_space:
        c_el = et.Element('c')
        c_el.text = ' '
        _insert_before_anchor(container, anchor, c_el)


def _insert_mark_at_slot(container: et.Element, gap: dict, slot: int, new_text: str,
                          space_before: bool, space_after: bool) -> None:
    lo, hi = _slot_range(gap, slot)
    anchor = _slot_anchor(container, hi)
    # A single old slot is being replaced by up to two new, independently
    # controlled ones flanking the new mark - clear whatever was there first.
    _clear_slot_spaces(container, lo, hi)

    choice = et.Element('choice')
    et.SubElement(choice, 'orig')
    reg = et.SubElement(choice, 'reg')
    pc = et.SubElement(reg, 'pc')
    pc.text = new_text

    # _insert_before_anchor always lands its element immediately next to the
    # (re-located) anchor, so repeated calls stack up in REVERSE of call
    # order (the most-recently-inserted item ends up closest to anchor) -
    # insert space_before first, then the mark, then space_after last, so
    # the final order reads space_before, mark, space_after, anchor.
    if space_before:
        c_before = et.Element('c')
        c_before.text = ' '
        _insert_before_anchor(container, anchor, c_before)
    _insert_before_anchor(container, anchor, choice)
    if space_after:
        c_after = et.Element('c')
        c_after.text = ' '
        _insert_before_anchor(container, anchor, c_after)


def _change_mark(container: et.Element, gap: dict, occurrence: int | None,
                  new_text: str | None, space_before: bool | None) -> None:
    marks = gap['marks']
    if occurrence is None or occurrence < 0 or occurrence >= len(marks):
        raise ValueError(f'No punctuation mark at occurrence {occurrence}')
    if not new_text or not new_text.strip():
        raise ValueError('new_text is required to change a punctuation mark')
    el = marks[occurrence]
    tag = local_name(el)
    if tag == 'pc':
        el.text = new_text
    else:
        pc = _pc_in_reg(_select_reg(el))
        if pc is None:
            raise ValueError('Malformed punctuation <choice>: no <pc> in <reg>')
        pc.text = new_text

    if space_before is not None:
        _set_slot_space(container, gap, occurrence, space_before)


def _remove_mark(container: et.Element, gap: dict, occurrence: int | None) -> None:
    marks = gap['marks']
    if occurrence is None or occurrence < 0 or occurrence >= len(marks):
        raise ValueError(f'No punctuation mark at occurrence {occurrence}')
    el = marks[occurrence]
    tag = local_name(el)

    # Collapse this mark's own preceding space (slot `occurrence`, i.e. the
    # gap immediately before it) - the following slot's space is left as-is.
    lo, hi = _slot_range(gap, occurrence)
    _clear_slot_spaces(container, lo, hi)

    if tag == 'pc':
        _remove_preserving_tail(container, el)
    else:
        reg = _select_reg(el)
        pc = _pc_in_reg(reg)
        if pc is not None:
            _remove_preserving_tail(reg, pc)
        if _orig_is_empty(_orig_of(el)):
            _remove_preserving_tail(container, el)
        # else: the rare orig != reg shape - keep the <choice> with its
        # now-empty <reg>, never discard real diplomatic content.


def apply_punctuation_edit(container: et.Element, after_w_id: str | None, action: str, *,
                            occurrence: int | None = None, slot: int | None = None,
                            new_text: str | None = None,
                            space_before: bool | None = None,
                            space_after: bool | None = None) -> None:
    """
    action='insert':    requires slot, new_text; space_before/space_after
                         (default False) independently control the two
                         slots flanking the new mark.
    action='change':     requires occurrence, new_text; optional
                         space_before toggles that mark's own preceding slot.
    action='remove':     requires occurrence. Removes the mark and its own
                         preceding <c>; the following slot is left as-is.
    action='set_space':  requires slot and space_before (the desired state
                         of that slot) - the only action that touches
                         nothing but a <c>, used by a plain slot click with
                         no mark text entered.
    Raises ValueError on a bad anchor/slot/occurrence or missing required
    fields - callers should map that to 404.
    """
    gap = _locate_gap(container, after_w_id)

    if action == 'insert':
        if slot is None:
            raise ValueError('slot is required to insert a punctuation mark')
        if not new_text or not new_text.strip():
            raise ValueError('new_text is required to insert a punctuation mark')
        _insert_mark_at_slot(container, gap, slot, new_text, bool(space_before), bool(space_after))
        return

    if action == 'change':
        _change_mark(container, gap, occurrence, new_text, space_before)
        return

    if action == 'remove':
        _remove_mark(container, gap, occurrence)
        return

    if action == 'set_space':
        if slot is None or space_before is None:
            raise ValueError('slot and space_before are required to toggle a space')
        _set_slot_space(container, gap, slot, bool(space_before))
        return

    raise ValueError(f'Unknown action: {action}')
