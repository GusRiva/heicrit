"""
Whole-verse apparatus entries: targets/pointers that address <l> elements
instead of word tokens, and the suggestions generated from the synoptic map
for verses a witness lacks (omissions) or the base lacks (additions).
"""

import os
import shutil
import sys

import pytest
from lxml import etree as et

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from apparatus import Apparatus, build_new_format_app_element  # noqa: E402

PROJECT = os.path.join(ROOT, 'test_data', 'emendatio')
ADDED_VERSE = '<l n="8a" xml:id="l_8a"><w xml:id="w_8a_1">Hinzu</w><c> </c><w xml:id="w_8a_2">gesetzt</w></l>'


def _project(tmp_path, apps: str = '') -> Apparatus:
    """Copy of test_data/emendatio with verse 8a added to B and D, and extra <app>s."""
    project = tmp_path / 'emendatio'
    shutil.copytree(PROJECT, project)
    for wit in ('B', 'D'):
        path = project / 'texts' / wit / f'{wit}_1.xml'
        xml = path.read_text(encoding='utf-8')
        xml = xml.replace('</lg>', f'{ADDED_VERSE}</lg>', 1)
        path.write_text(xml, encoding='utf-8')
    app_path = project / 'apparatus' / 'app_emendatio.xml'
    if apps:
        xml = app_path.read_text(encoding='utf-8')
        app_path.write_text(xml.replace('</listApp>', f'{apps}</listApp>', 1), encoding='utf-8')
    return Apparatus(str(app_path))


def _loci():
    """Synoptic loci: C lacks 5-6, D lacks 6, B and D add 8a, C has a lacuna at 7."""
    loci = {}
    for n in range(1, 9):
        targets = [f'a:l_{n}', f'b:l_{n}', f'c:l_{n}', f'd:l_{n}']
        if n in (5, 6):
            targets[2] = 'c:right(l_4)'
        if n == 6:
            targets[3] = 'd:right(l_5)'
        if n == 7:
            targets[2] = 'c:gap_leaf_1'
        loci[f'a:l_{n}'] = {'n': str(n), 'target': targets}
    loci['a:right(l_8)'] = {'n': '8a', 'target': ['a:right(l_8)', 'b:l_8a', 'c:right(l_8)', 'd:l_8a']}
    return loci


@pytest.fixture
def apparatus(tmp_path):
    return _project(tmp_path)


def test_verse_rendering(apparatus):
    resolver = apparatus.get_resolver()
    assert resolver.resolve_text_html(['b:l_8a'])[0] == 'Hinzu gesetzt'
    text = resolver.resolve_text_html(['b:range(l_8, l_8a)'])[0]
    assert text.endswith(' / Hinzu gesetzt') and ' / ' in text
    # ptrs of two verses of one witness are joined like a range
    assert resolver.resolve_text_html(['b:l_8a', 'b:l_8'])[0] == text


def test_verse_tokens(apparatus):
    resolver = apparatus.get_resolver()
    assert resolver.is_verse_token('a:l_5')
    assert resolver.is_verse_token('a:range(l_5, l_6)')
    assert resolver.is_verse_token('c:right(l_4)')
    assert resolver.is_absent_verse_token('c:right(l_4)')
    assert not resolver.is_absent_verse_token('a:l_5')
    assert not resolver.is_verse_token('a:w_5_1')
    assert not resolver.is_verse_token('a:right(w_5_1)')
    assert resolver.normalize_corresp_token('a:range(l_5, l_7)') == 'a:l_5 a:l_6 a:l_7'


def test_collapse_verse_ptrs(apparatus):
    resolver = apparatus.get_resolver()
    assert resolver.collapse_verse_ptrs(['a:l_6', 'a:l_5']) == ['a:range(l_5, l_6)']
    assert resolver.collapse_verse_ptrs(['a:l_1', 'a:l_3', 'a:l_4']) == ['a:l_1', 'a:range(l_3, l_4)']
    assert resolver.collapse_verse_ptrs(['c:right(l_4)', 'c:right(l_4)']) == ['c:right(l_4)']
    assert resolver.collapse_verse_ptrs(['b:l_8', 'd:l_8', 'b:l_8a', 'd:l_8a']) == [
        'b:range(l_8, l_8a)', 'd:range(l_8, l_8a)']


def test_prepare_verse_entry_types(apparatus):
    readings = [
        {'wit': ['c'], 'ana': 'hc:SubstitutionVariant', 'ptrs': ['c:right(l_4)', 'c:right(l_4)']},
        {'wit': ['b'], 'ana': 'hc:SubstitutionVariant', 'ptrs': ['b:l_5', 'b:l_6']},
    ]
    target, error = apparatus.prepare_verse_entry(['a:l_6', 'a:l_5'], readings)
    assert error is None
    assert target == 'a:range(l_5, l_6)'
    assert [(r['ana'], r['ptrs']) for r in readings] == [
        ('hc:OmissionVariant', ['c:right(l_4)']),
        ('hc:SubstitutionVariant', ['b:range(l_5, l_6)']),
    ]

    additions = [{'wit': ['b'], 'ana': 'hc:SubstitutionVariant', 'ptrs': ['b:l_8a']}]
    target, error = apparatus.prepare_verse_entry(['a:right(l_8)'], additions)
    assert error is None and target == 'a:right(l_8)'
    assert additions[0]['ana'] == 'hc:AdditionVariant'


@pytest.mark.parametrize('target_verses, ptrs', [
    (['a:l_1', 'a:l_3'], ['b:l_1']),          # lemma verses not consecutive
    (['b:l_1'], ['c:l_1']),                   # lemma not on the base row
    (['a:l_1'], ['b:w_1_1']),                 # word token in a verse entry
    (['a:right(l_8)'], ['c:right(l_8)']),     # both sides lack the verse
])
def test_prepare_verse_entry_errors(apparatus, target_verses, ptrs):
    target, error = apparatus.prepare_verse_entry(target_verses, [{'wit': ['x'], 'ana': '', 'ptrs': ptrs}])
    assert target is None and error


def test_written_entry_reads_back_as_verse_entry(tmp_path):
    readings = [{'wit': ['c'], 'ana': '', 'ptrs': ['c:right(l_4)']}]
    target, _ = _project(tmp_path / 'one').prepare_verse_entry(['a:l_5', 'a:l_6'], readings)
    xml = et.tostring(build_new_format_app_element(target, readings), encoding='unicode')
    assert 'target="a:range(l_5, l_6)"' in xml and 'c:right(l_4)' in xml

    entry = next(e for e in _project(tmp_path / 'two', xml).get_entries() if e['target'] == target)
    assert entry['is_verse_entry'] is True
    assert entry['is_emendation'] is False
    assert entry['lemma']['text'] == '5–6'
    assert entry['lemma']['attributes']['corresp'] == 'a:l_5 a:l_6'
    assert (entry['loc'], entry['corresp']) == ('5', 'a:l_5')
    assert entry['readings'][0]['text'] == 'om.'


def test_single_verse_substitution_has_no_lemma_text(tmp_path):
    app = '<app target="a:l_2"><rdg wit="#b" ana="hc:SubstitutionVariant"><ptr target="b:l_2"/></rdg></app>'
    entry = next(e for e in _project(tmp_path, app).get_entries() if e['target'] == 'a:l_2')
    assert entry['is_verse_entry'] and entry['lemma']['text'] == ''
    assert entry['readings'][0]['text']


def _verse_suggestions(apparatus):
    return [e for e in apparatus.get_display_entries(_loci()) if e.get('is_generated') and e.get('is_verse_entry')]


def test_suggested_omissions_and_additions(apparatus):
    suggestions = {(e['target'], e['corresp']): e for e in _verse_suggestions(apparatus)}
    assert set(suggestions) == {
        ('a:range(l_5, l_6)', 'a:l_5'),     # C lacks 5-6
        ('a:l_6', 'a:l_6'),                 # D lacks 6 only
        ('a:right(l_8)', 'a:right(l_8)'),   # B and D add 8a
    }  # the lacuna in C at 7 is no omission

    c_omission = suggestions[('a:range(l_5, l_6)', 'a:l_5')]
    assert c_omission['lemma']['text'] == '5–6'
    [reading] = c_omission['readings']
    assert (reading['text'], reading['attributes']['wit'], reading['attributes']['ana'], reading['ptrs']) == (
        'om.', '#c', 'hc:OmissionVariant', ['c:right(l_4)'])

    addition = suggestions[('a:right(l_8)', 'a:right(l_8)')]
    [reading] = addition['readings']
    assert addition['loc'] == '8a' and addition['lemma']['text'] == ''
    assert (reading['text'], reading['attributes']['wit'], reading['attributes']['ana']) == (
        'Hinzu gesetzt', '#b #d', 'hc:AdditionVariant')


def test_recorded_verse_entries_remove_only_their_suggestion(tmp_path):
    apps = ('<app target="a:l_5"><rdg wit="#c" ana="hc:OmissionVariant"><ptr target="c:right(l_4)"/></rdg></app>'
            '<app target="a:right(l_8)"><rdg wit="#b #d" ana="hc:AdditionVariant">'
            '<ptr target="b:l_8a"/><ptr target="d:l_8a"/></rdg></app>')
    apparatus = _project(tmp_path, apps)
    remaining = {e['target'] for e in _verse_suggestions(apparatus)}
    # C's 5 is recorded: only verse 6 remains, now shared by C and D
    assert remaining == {'a:l_6'}
    [six] = [e for e in _verse_suggestions(apparatus)]
    assert six['readings'][0]['attributes']['wit'] == '#c #d'

    # the recorded addition is placed at its added locus
    recorded = next(e for e in apparatus.get_display_entries(_loci()) if e.get('target') == 'a:right(l_8)')
    assert (recorded['loc'], recorded['corresp']) == ('8a', 'a:right(l_8)')
