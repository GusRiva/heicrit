"""
Emendations in the critical text: see test_data/emendatio/spec/app_emendatio.xml
for the rules and examples; test_data/emendatio/ holds one example per line.
"""

import os
import sys

import pytest
from lxml import etree as et

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from apparatus import Apparatus, is_valid_reading_ana, process_synoptic_unit_for_comparison  # noqa: E402

PROJECT = os.path.join(ROOT, 'test_data', 'emendatio')
APPARATUS_FILE = os.path.join(PROJECT, 'apparatus', 'app_emendatio.xml')
TEI = {'t': 'http://www.tei-c.org/ns/1.0'}


@pytest.fixture(scope='module')
def apparatus():
    return Apparatus(APPARATUS_FILE)


@pytest.fixture(scope='module')
def entries(apparatus):
    return {e['target']: e for e in apparatus.get_entries()}


@pytest.mark.parametrize('target, lemma_html, base_text, base_wits', [
    # *K*atzen] Tatzen A
    ('a:w_1_4', '<em>K</em>atzen', 'Tatzen', ['a']),
    ('a:w_2_4', '<em>K</em>atzen', 'Tatzen', ['a']),
    # supporting witness B joins the base reading: Tatzen A B
    ('a:w_3_4', '<em>K</em>atzen', 'Tatzen', ['a', 'b']),
    # surplus inside a word: grau[ ] ] grauenhaft A
    ('a:w_4_5', 'grau[ ]', 'grauenhaft', ['a']),
    # whole-token surplus: *vor* grau ] Katzen A
    ('a:surplus_1', '<em>vor</em> grau', 'Katzen', ['a']),
    # token-spanning choice: *keine Hunde* ] alle Katzen A
    ('a:choice_1', '<em>keine Hunde</em>', 'alle Katzen', ['a']),
    # mixed: al*l*e] ale A; *K*atz[ ]*e*n] Tatzzn A
    ('a:w_7_3', 'al<em>l</em>e', 'ale', ['a']),
    ('a:w_7_4', '<em>K</em>atz[ ]<em>e</em>n', 'Tatzzn', ['a']),
])
def test_emended_lemma_and_base_reading(entries, target, lemma_html, base_text, base_wits):
    entry = entries[target]
    assert entry['is_emendation'] is True
    assert entry['lemma']['html'] == lemma_html
    assert entry['base_reading']['text'] == base_text
    assert entry['base_reading']['wit_ids'] == base_wits


def test_other_readings_keep_their_typology(entries):
    readings = entries['a:w_3_4']['readings']
    assert [(r['text'], r['attributes']['ana']) for r in readings] == [
        ('Tatzen', 'hc:BaseTextSupportingVariant'),
        ('Katzen', 'hc:SubstitutionVariant hc:CorrectionVariant'),
        ('om.', 'hc:OmissionVariant'),
    ]
    # an omission marked as correction source is still rendered as om.
    assert entries['a:surplus_1']['readings'][0]['text'] == 'om.'


def test_container_targets_anchor_and_highlight(entries):
    assert entries['a:surplus_1']['loc'] == '5'
    assert entries['a:surplus_1']['lemma']['attributes']['corresp'] == 'a:w_5_4'
    assert entries['a:choice_1']['lemma']['attributes']['corresp'] == 'a:w_6_3 a:w_6_4 a:w_6_5 a:w_6_6'


def test_wit_derived_from_ptrs_when_missing():
    content = open(APPARATUS_FILE, encoding='utf-8').read().replace(' wit="#b #c #d"', '')
    path = os.path.join(PROJECT, 'apparatus', '_tmp_no_wit.xml')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        entry = Apparatus(path).get_entries()[0]
        assert entry['readings'][0]['attributes']['wit'] == '#b #c #d'
    finally:
        os.remove(path)


@pytest.mark.parametrize('selection, lifted', [
    ('a:w_5_4', 'a:surplus_1'),
    ('a:range(w_6_3, w_6_4)', 'a:choice_1'),
    ('a:range(w_6_5,w_6_6)', 'a:choice_1'),
    ('a:w_6_3', 'a:w_6_3'),            # only part of the choice
    ('a:w_1_4', 'a:w_1_4'),            # token-internal emendation: no container
    ('a:left(w_5_5)', 'a:left(w_5_5)'),
])
def test_lift_emendation_target(apparatus, selection, lifted):
    assert apparatus.lift_emendation_target(selection) == lifted


def test_ana_suggestions_for_auto_readings(apparatus):
    readings = [
        {'ana': 'hc:SubstitutionVariant', 'ptrs': ['b:w_3_4'], 'ana_auto': True},   # Tatzen
        {'ana': 'hc:SubstitutionVariant', 'ptrs': ['c:w_3_4'], 'ana_auto': True},   # Katzen
        {'ana': 'hc:OmissionVariant', 'ptrs': ['d:right(w_3_3)'], 'ana_auto': True},
        {'ana': 'hc:SubstitutionVariant', 'ptrs': ['c:w_3_4'], 'ana_auto': False},  # explicit
    ]
    apparatus.apply_emendation_ana_suggestions('a:w_3_4', readings)
    assert [r['ana'] for r in readings] == [
        'hc:BaseTextSupportingVariant',
        'hc:SubstitutionVariant hc:CorrectionVariant',
        'hc:OmissionVariant',
        'hc:SubstitutionVariant',
    ]


@pytest.mark.parametrize('ana, valid', [
    ('hc:SubstitutionVariant', True),
    ('hc:SubstitutionVariant hc:CorrectionVariant', True),
    ('hc:OmissionVariant hc:CorrectionVariant', True),
    ('hc:BaseTextSupportingVariant', True),
    ('hc:TranspositionVariant', True),
    ('hc:TranspositionVariant hc:CorrectionVariant', False),
    ('hc:CorrectionVariant', False),
    ('hc:SubstitutionVariant hc:OmissionVariant', False),
    ('hc:Bogus', False),
    (None, False),
])
def test_reading_ana_validation(ana, valid):
    assert is_valid_reading_ana(ana) is valid


def _line(witness, n):
    doc = et.parse(os.path.join(PROJECT, 'texts', witness, f'{witness}_1.xml'))
    return doc.find(f'.//t:l[@n="{n}"]', TEI)


def test_location_details_rows():
    line = _line('A', 1)
    diplomatic = process_synoptic_unit_for_comparison(line)
    regularized = process_synoptic_unit_for_comparison(line, prefer_reg=True)
    assert 'Tatzen' in diplomatic and 'Katzen' not in diplomatic
    assert "<em class='syn-emendation'>K</em>atzen" in regularized

    spanning = process_synoptic_unit_for_comparison(_line('A', 6), prefer_reg=True)
    assert 'keine' in spanning and 'alle' not in spanning
    surplus = process_synoptic_unit_for_comparison(_line('A', 5), prefer_reg=True)
    assert "<span class='syn-surplus'>" in surplus


def test_existing_projects_unaffected_except_real_emendations():
    """AH_A's only emendation (w_14_1 Un<sic/><corr>d) is the only changed lemma
    (normalized: <orig>U</orig><reg>u</reg>)."""
    entries = Apparatus(os.path.join(ROOT, 'test_data', 'apparatus', 'AH_A_app.xml')).get_entries()
    emended = [e for e in entries if e['is_emendation']]
    assert [(e['target'], e['lemma']['html'], e['base_reading']['text']) for e in emended] == [
        ('a:w_14_1', 'un<em>d</em>', 'Un'),
    ]


# --- Emendations without an <app>: generated (unsaved) entries -------------

@pytest.fixture(scope='module')
def ah_a():
    return Apparatus(os.path.join(ROOT, 'test_data', 'apparatus', 'AH_A_app.xml'))


def test_generated_entry_for_unrecorded_emendation(apparatus):
    # line 6's "Nachts<surplus>s</surplus>" has no <app> in the test file,
    # although another emendation in the same line (choice_1) has one
    generated = apparatus.get_generated_entries()
    assert [(e['target'], e['loc'], e['corresp'], e['lemma']['html'], e['base_reading']['text'])
            for e in generated if e['loc'] == '6'] == [('a:w_6_1', '6', 'a:l_6', 'Nachts[ ]', 'Nachtss')]
    entry = generated[0]
    assert entry['is_generated'] and entry['id'] is None and entry['readings'] == []
    assert entry['base_reading']['wit_ids'] == ['a']


def test_generated_entries_stay_out_of_indexed_entries(apparatus):
    # write routes map get_entries() positions onto <app> elements
    assert not any(e.get('is_generated') for e in apparatus.get_entries())
    assert apparatus.get_display_entries()[-1]['is_generated']


def test_no_generated_entries_once_everything_is_recorded():
    content = open(APPARATUS_FILE, encoding='utf-8').read().replace(
        '</listApp>',
        '<app target="a:w_6_1"><rdg wit="#b #c #d" ana="hc:SubstitutionVariant">'
        '<ptr target="b:w_6_1"/></rdg></app>'
        '<app target="a:w_8_4"><rdg wit="#b #c #d" ana="hc:SubstitutionVariant">'
        '<ptr target="b:w_8_4"/></rdg></app>'
        '<app target="a:surplus_2"><rdg wit="#b #c #d" ana="hc:OmissionVariant">'
        '<ptr target="b:left(w_8_5)"/></rdg></app></listApp>')
    path = os.path.join(PROJECT, 'apparatus', '_tmp_all_recorded.xml')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        assert Apparatus(path).get_generated_entries() == []
    finally:
        os.remove(path)


@pytest.mark.parametrize('loc, lemma_html, base_html', [
    ('281', '<em>was</em>', '<i>om.</i>'),             # supplied word
    ('345', 'geriete[ ]', 'gerieter'),                  # empty <corr/> deletes
    ('480', '<em>si</em>', '<i>om.</i>'),               # word inside an id-less <corr>, long s normalized
    ('530', '<em>und fro</em>', 'unfro'),               # id-less token-spanning choice
    ('602', 'un<em>d</em>', 'Un'),                      # no whitespace leaking from <choice>; lemma uses <reg>
])
def test_generated_entries_real_data(ah_a, loc, lemma_html, base_html):
    entry = next(e for e in ah_a.get_generated_entries() if e['loc'] == loc)
    assert entry['lemma']['html'] == lemma_html
    assert entry['base_reading']['html'] == base_html


def test_lift_selection_of_one_side_of_idless_choice(ah_a):
    assert ah_a.lift_emendation_target('a:range(w_530_5, w_530_6)') == 'a:range(w_530_4, w_530_6)'
    entry = next(e for e in ah_a.get_generated_entries() if e['loc'] == '530')
    assert entry['lemma']['attributes']['corresp'] == 'a:w_530_4 a:w_530_5 a:w_530_6'


def test_example_line_without_any_app(apparatus):
    """
    Spec example "Emendationen ohne Apparateintrag" (line 8): the line has no
    <app> at all, yet both emendations show up as generated entries -
    *K*atzen] Tatzen A  and  *vor* grau] sehr A.
    """
    generated = [e for e in apparatus.get_generated_entries() if e['loc'] == '8']
    assert [(e['target'], e['corresp'], e['lemma']['html'], e['base_reading']['html'],
             e['base_reading']['wit_ids'], e['readings']) for e in generated] == [
        ('a:w_8_4', 'a:l_8', '<em>K</em>atzen', 'Tatzen', ['a'], []),
        ('a:surplus_2', 'a:l_8', '<em>vor</em> grau', 'sehr', ['a'], []),
    ]
    # their lemma selections lift back to the same targets when the entry is
    # created from them ("Create Entry"), so the generated entry disappears
    assert generated[1]['lemma']['attributes']['corresp'] == 'a:w_8_5'
    assert apparatus.lift_emendation_target('a:w_8_5') == 'a:surplus_2'
    # and the auto-classified readings of the other witnesses
    readings = [{'ana': 'hc:OmissionVariant', 'ptrs': ['b:left(w_8_5)'], 'ana_auto': True}]
    apparatus.apply_emendation_ana_suggestions('a:surplus_2', readings)
    assert readings[0]['ana'] == 'hc:OmissionVariant hc:CorrectionVariant'


def _tei_line(content: str):
    return et.fromstring(f'<l xmlns="http://www.tei-c.org/ns/1.0" xml:id="l_x">{content}</l>')


def test_subst_del_add_rows():
    """Regularized base row: add underlined, del dropped; other rows: del struck, add underlined."""
    in_word = _tei_line('<w xml:id="w_1">d<subst><del>o</del><add>a</add></subst>s</w>')
    regularized = process_synoptic_unit_for_comparison(in_word, prefer_reg=True)
    diplomatic = process_synoptic_unit_for_comparison(in_word)
    assert "d<span class='syn-add'>a</span>s" in regularized and 'o' not in regularized.split('syn-add')[0][-20:]
    assert "d<span class='syn-del'>o</span><span class='syn-add'>a</span>s" in diplomatic

    spanning = _tei_line('<subst><del><w>der</w></del><add><w>daz</w></add></subst>')
    regularized = process_synoptic_unit_for_comparison(spanning, prefer_reg=True)
    diplomatic = process_synoptic_unit_for_comparison(spanning)
    assert 'der' not in regularized and "<span class='syn-add'>" in regularized and 'daz' in regularized
    assert "<span class='syn-del'>" in diplomatic and 'der' in diplomatic and 'daz' in diplomatic

    standalone = _tei_line('<w xml:id="w_1">a<del>b</del>c<add>d</add>e</w>')
    assert ">ac<span class='syn-add'>d</span>e<" in process_synoptic_unit_for_comparison(standalone, prefer_reg=True)
    assert ("a<span class='syn-del'>b</span>c<span class='syn-add'>d</span>e"
            in process_synoptic_unit_for_comparison(standalone))

    empty = _tei_line('<w xml:id="w_1">bi<subst><del unit="character" quantity="1"/><add>d</add></subst>er</w>')
    diplomatic = process_synoptic_unit_for_comparison(empty)
    assert 'syn-del' not in diplomatic and "bi<span class='syn-add'>d</span>er" in diplomatic
