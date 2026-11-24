"""
Loci other than verses: a synoptic map can link <head>, <label>, <seg>, <s>,
<div> (and <p>/<titlePart>) as well as <l>. An apparatus entry belongs to the
nearest element around its lemma that the map links - loci can nest (<div> >
<l> > <seg>) - and must be shown at that locus, labelled by its @n or kind.
"""

import os
import shutil
import sys

import pytest
from lxml import etree as et

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from heipy.heipipe.steps import PythonStep  # noqa: E402
from apparatus import Apparatus  # noqa: E402
from heicrit_pipeline import HeiCritPipe, append_synoptic_links_funct  # noqa: E402
from punctuation import build_all_containers_tokens  # noqa: E402
from synoptic_map import SynopticMap  # noqa: E402

PROJECT = os.path.join(ROOT, 'test_data', 'emendatio')
WITNESSES = ('A', 'B', 'C', 'D')
PREFIXES = ('a', 'b', 'c', 'd')

HEAD = ('<head xml:id="head_1"{n}><hi><w xml:id="w_head_1_1">Von</w><c> </c>'
        '<w xml:id="w_head_1_2">Katzen</w></hi></head>')
LABEL = '<label xml:id="label_1"><w xml:id="w_label_1_1">Erstens</w></label>'
PARAGRAPHS = ('<p xml:id="p_1"><w xml:id="w_p_1_1">Ende</w></p>'
              '<p xml:id="p_2"><w xml:id="w_p_2_1">gut</w></p>')

APPS = '''
<app target="a:w_head_1_2"><rdg><ptr target="b:w_head_1_2"/></rdg></app>
<app target="a:w_label_1_1"><rdg><ptr target="b:w_label_1_1"/></rdg></app>
<app target="a:w_2_1"><rdg><ptr target="b:w_2_1"/></rdg></app>
<app target="a:w_3_1"><rdg><ptr target="b:w_3_1"/></rdg></app>
<app target="a:head_1"><rdg><ptr target="b:head_1"/></rdg></app>
<app target="a:seg_2_1"><rdg><ptr target="b:seg_2_1"/></rdg></app>
<app target="a:div_1"><rdg><ptr target="b:div_1"/></rdg></app>
<app target="a:range(p_1, p_2)"><rdg><ptr target="b:range(p_1, p_2)"/></rdg></app>
'''


def _link(xml_id):
    return '<link target="{}"/>'.format(' '.join(f'{p}:{xml_id}' for p in PREFIXES))


def _project(tmp_path, head_n='', link_seg=True, link_div=True):
    """
    Copy of test_data/emendatio where every witness has <div xml:id="div_1">
    around a heading, a label, the verses and two paragraphs, and <seg
    xml:id="seg_2_1"> around the first word of verse 2. The synoptic map
    links the heading, the label and the paragraphs, and (optionally) the
    div and the seg.
    Returns (apparatus, synoptic map, project dir).
    """
    project = tmp_path / 'emendatio'
    shutil.copytree(PROJECT, project)
    head = HEAD.format(n=f' n="{head_n}"' if head_n else '')
    for wit in WITNESSES:
        path = project / 'texts' / wit / f'{wit}_1.xml'
        xml = path.read_text(encoding='utf-8')
        xml = xml.replace('<body>', f'<body><div xml:id="div_1">{head}{LABEL}', 1)
        xml = xml.replace('</body>', f'{PARAGRAPHS}</div></body>', 1)
        xml = xml.replace('<w xml:id="w_2_1">Nachts</w>',
                          '<seg xml:id="seg_2_1"><w xml:id="w_2_1">Nachts</w></seg>', 1)
        path.write_text(xml, encoding='utf-8')

    # Links deliberately out of document order: the list must still read in order.
    links = [_link('label_1'), _link('head_1'), _link('p_2'), _link('p_1')]
    if link_div:
        links.append(_link('div_1'))
    if link_seg:
        links.append(_link('seg_2_1'))
    map_path = project / 'synopses' / 'synoptic_map.xml'
    xml = map_path.read_text(encoding='utf-8')
    map_path.write_text(xml.replace('<standOff>', '<standOff>' + ''.join(links), 1), encoding='utf-8')

    app_path = project / 'apparatus' / 'app_emendatio.xml'
    xml = app_path.read_text(encoding='utf-8')
    app_path.write_text(xml.replace('</listApp>', f'{APPS}</listApp>', 1), encoding='utf-8')

    project_files = {str(p): {'content': p.read_text(encoding='utf-8')}
                     for p in project.rglob('*.xml')}
    apparatus = Apparatus(str(app_path))
    synoptic_map = SynopticMap()
    assert synoptic_map.parse_content(map_path.read_text(encoding='utf-8'), 'a', str(app_path),
                                      project_files, apparatus.get_witness_to_prefix_mapping())
    return apparatus, synoptic_map, project


def _entry(entries, target):
    return next(e for e in entries if e.get('target') == target)


@pytest.fixture
def setup(tmp_path):
    return _project(tmp_path)


def test_head_and_label_entries_are_located(setup):
    apparatus, synoptic_map, _ = setup
    entries = apparatus.get_display_entries(synoptic_map.get_loci())
    head = _entry(entries, 'a:w_head_1_2')
    assert (head['corresp'], head['loc']) == ('a:head_1', 'Head')
    label = _entry(entries, 'a:w_label_1_1')
    assert (label['corresp'], label['loc']) == ('a:label_1', 'Label')


def test_head_label_uses_its_n(tmp_path):
    apparatus, synoptic_map, _ = _project(tmp_path, head_n='Ü')
    entries = apparatus.get_display_entries(synoptic_map.get_loci())
    assert _entry(entries, 'a:w_head_1_2')['loc'] == 'Ü'
    assert synoptic_map.get_loci()['a:head_1']['n'] == 'Ü'


def test_nearest_linked_locus_wins(setup):
    apparatus, synoptic_map, _ = setup
    entries = apparatus.get_display_entries(synoptic_map.get_loci())
    # a linked <seg> inside verse 2 is the word's locus ...
    assert _entry(entries, 'a:w_2_1')['corresp'] == 'a:seg_2_1'
    # ... a verse inside the linked <div> is its own locus, not the div
    entry = _entry(entries, 'a:w_3_1')
    assert (entry['corresp'], entry['loc']) == ('a:l_3', '3')


def test_unlinked_seg_falls_back_to_its_verse(tmp_path):
    apparatus, synoptic_map, _ = _project(tmp_path, link_seg=False)
    entries = apparatus.get_display_entries(synoptic_map.get_loci())
    assert _entry(entries, 'a:w_2_1')['corresp'] == 'a:l_2'


def test_without_synoptic_map(setup):
    apparatus, _, _ = setup
    entries = apparatus.get_display_entries()
    # verses as before; other loci by their element, never a <div>
    assert _entry(entries, 'a:w_2_1')['corresp'] == 'a:l_2'
    assert _entry(entries, 'a:w_head_1_2')['corresp'] == 'a:head_1'
    assert _entry(entries, 'a:w_1_4')['corresp'] == 'a:l_1'


def test_synoptic_loci_labels_and_order(setup):
    _, synoptic_map, _ = setup
    loci = synoptic_map.get_loci()
    assert loci['a:head_1']['n'] == 'Head'
    assert loci['a:label_1']['n'] == 'Label'
    assert loci['a:l_1']['n'] == '1'
    ordered = sorted(loci, key=lambda k: loci[k]['order'])
    assert ordered[:5] == ['a:div_1', 'a:head_1', 'a:label_1', 'a:l_1', 'a:l_2']
    assert ordered.index('a:seg_2_1') == ordered.index('a:l_2') + 1


def _base_text_html(project, synoptic_map):
    pipeline = HeiCritPipe()
    pipeline.add_step(PythonStep(append_synoptic_links_funct, name='heicrit_append_synoptic_links'),
                      before_step='create_html',
                      parameters={'witness_mapping': {}, 'synoptic_map': synoptic_map.get_loci()})
    content = (project / 'texts' / 'A' / 'A_1.xml').read_text(encoding='utf-8')
    return et.HTML(str(pipeline.execute(content, input_format='xml_string')))


def test_base_text_units(setup):
    _, synoptic_map, project = setup
    html = _base_text_html(project, synoptic_map)

    def label(xml_id):
        return html.xpath(f'//div[@class="tei-container-n"][@data-container-id="{xml_id}"]')

    def unit(xml_id):
        return label(xml_id)[0].getparent()

    for xml_id, text in (('head_1', 'Head'), ('label_1', 'Label'), ('seg_2_1', 'Seg'), ('l_3', '3')):
        assert len(label(xml_id)) == 1, xml_id
        assert label(xml_id)[0].text.strip() == text
    assert 'Katzen' in ''.join(unit('head_1').itertext())
    # verse 2 holds the linked seg: an outer unit, the seg carries the content
    assert 'synoptic-unit-outer' in unit('l_2').get('class')
    assert unit('seg_2_1').xpath('div[@class="tei-container-content"]')
    # the div is an outer unit around everything
    assert 'synoptic-unit-outer' in unit('div_1').get('class')
    assert not html.xpath('//head//*[contains(., "Katzen")]')


def test_base_text_units_without_map(setup):
    _, _, project = setup
    html = _base_text_html(project, SynopticMap())
    assert html.xpath('//div[@class="tei-container-n"][@data-container-id="l_2"]')
    assert not html.xpath('//*[@data-container-id="head_1"]')
    assert html.xpath('//div[@class="tei-head"][contains(., "Katzen")]')


def test_punctuation_containers(setup):
    _, _, project = setup
    root = et.parse(str(project / 'texts' / 'A' / 'A_1.xml')).getroot()
    ids = {c['container_id'] for c in build_all_containers_tokens(root)}
    assert 'label_1' in ids and 'l_1' in ids
    # words wrapped in <hi>: left static rather than rendered empty
    assert 'head_1' not in ids
    assert 'div_1' not in ids


# --- Whole-unit entries (clicking a row's siglum) ------------------------------

def _substitution(ptrs):
    return [{'wit': ['b'], 'ana': 'hc:SubstitutionVariant', 'ptrs': ptrs}]


@pytest.mark.parametrize('target_verses, ptrs, expected', [
    (['a:head_1'], ['b:head_1'], 'a:head_1'),
    (['a:label_1'], ['b:label_1'], 'a:label_1'),
    (['a:seg_2_1'], ['b:seg_2_1'], 'a:seg_2_1'),
    (['a:div_1'], ['b:div_1'], 'a:div_1'),
    (['a:p_2', 'a:p_1'], ['b:p_1', 'b:p_2'], 'a:range(p_1, p_2)'),
    # a <seg> inside verse 2 doesn't break the run of verses
    (['a:l_2', 'a:l_1', 'a:l_3'], ['b:l_1'], 'a:range(l_1, l_3)'),
])
def test_prepare_whole_unit_entry(setup, target_verses, ptrs, expected):
    apparatus, _, _ = setup
    readings = _substitution(ptrs)
    target, error = apparatus.prepare_verse_entry(target_verses, readings)
    assert error is None
    assert target == expected
    assert readings[0]['ana'] == 'hc:SubstitutionVariant'


def test_whole_unit_span_must_be_one_kind(setup):
    apparatus, _, _ = setup
    target, error = apparatus.prepare_verse_entry(['a:head_1', 'a:label_1'], _substitution(['b:head_1']))
    assert target is None and error


def test_whole_unit_entries_are_located(setup):
    apparatus, synoptic_map, _ = setup
    entries = apparatus.get_display_entries(synoptic_map.get_loci())
    for target, corresp, loc in (('a:head_1', 'a:head_1', 'Head'),
                                 ('a:seg_2_1', 'a:seg_2_1', 'Seg'),
                                 ('a:div_1', 'a:div_1', 'Div'),
                                 ('a:range(p_1, p_2)', 'a:p_1', 'P')):
        entry = _entry(entries, target)
        assert entry['is_verse_entry'] is True, target
        assert (entry['corresp'], entry['loc']) == (corresp, loc), target
    paragraphs = _entry(entries, 'a:range(p_1, p_2)')
    assert paragraphs['lemma']['attributes']['corresp'] == 'a:p_1 a:p_2'
    assert paragraphs['readings'][0]['text'] == 'Ende / gut'
