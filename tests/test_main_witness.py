"""
The main witness of a multi-witness reading is the one whose <ptr> is the
first child of the <rdg>: the reading shows its text and lists its siglum
first. It can be changed with /apparatus/reading/main-witness.
"""

import os
import shutil
import sys

import pytest
from lxml import etree as et

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from apparatus import Apparatus, set_main_witness  # noqa: E402

PROJECT = os.path.join(ROOT, 'test_data', 'emendatio')
TEI = 'http://www.tei-c.org/ns/1.0'

# B reads "alle", C (in the copy) "allen"; @wit lists b first, the ptrs c first.
APP = ('<app target="a:w_7_3"><rdg wit="#b #c" ana="hc:SubstitutionVariant">'
       '<ptr target="c:w_7_3"/><ptr target="b:w_7_3"/><note>Notiz</note></rdg></app>')


def _project(tmp_path):
    project = tmp_path / 'emendatio'
    shutil.copytree(PROJECT, project)
    c_text = project / 'texts' / 'C' / 'C_1.xml'
    c_text.write_text(c_text.read_text(encoding='utf-8').replace(
        '<w xml:id="w_7_3">alle</w>', '<w xml:id="w_7_3">allen</w>', 1), encoding='utf-8')
    app_path = project / 'apparatus' / 'app_emendatio.xml'
    xml = app_path.read_text(encoding='utf-8')
    app_path.write_text(xml.replace('</listApp>', f'{APP}</listApp>', 1), encoding='utf-8')
    return project, app_path


def _reading(app_path):
    entries = Apparatus(str(app_path)).get_entries()
    entry = [e for e in entries if e['target'] == 'a:w_7_3'][-1]
    return entry['readings'][0]


def test_first_ptr_is_main_witness(tmp_path):
    _, app_path = _project(tmp_path)
    reading = _reading(app_path)
    assert reading['main_wit'] == 'c'
    assert reading['attributes']['wit'] == '#c #b'
    assert reading['text'] == 'allen'


def _rdg(xml):
    return et.fromstring(f'<rdg xmlns="{TEI}" {xml}</rdg>')


def test_set_main_witness_moves_ptrs_and_wit():
    rdg = _rdg('wit="#c #b #d"><ptr target="c:w_1"/><ptr target="b:w_1"/>'
               '<ptr target="d:w_1"/><ptr target="b:w_2"/><note>n</note>')
    assert set_main_witness(rdg, 'b', 'b')
    assert [p.get('target') for p in rdg.findall(f'{{{TEI}}}ptr')] == ['b:w_1', 'b:w_2', 'c:w_1', 'd:w_1']
    assert rdg.get('wit') == '#b #c #d'
    assert et.QName(rdg[-1]).localname == 'note'


@pytest.mark.parametrize('xml', [
    'wit="#c"><ptr target="c:w_1"/>',                                     # witness not in the reading
    'wit="#b #c" ana="hc:TranspositionVariant"><link target="a:w_1 b:w_2"/>',  # transposition
])
def test_set_main_witness_refuses(xml):
    rdg = _rdg(xml)
    before = et.tostring(rdg)
    assert not set_main_witness(rdg, 'b', 'b')
    assert et.tostring(rdg) == before


def test_route_sets_main_witness(tmp_path):
    from app import create_app

    project, app_path = _project(tmp_path)
    files = {str(p.relative_to(tmp_path)): {'content': p.read_text(encoding='utf-8')}
             for p in project.rglob('*.xml')}
    client = create_app().test_client()
    response = client.post('/api/project/open', json={
        'apparatus_filepath': 'emendatio/apparatus/app_emendatio.xml', 'project_files': files})
    assert response.status_code == 200

    entry_index = len(Apparatus(str(app_path)).get_entries()) - 1
    response = client.post('/api/apparatus/reading/main-witness', json={
        'apparatus_file': 'apparatus/app_emendatio.xml', 'project_directory': str(project),
        'entry_index': entry_index, 'reading_index': 0, 'witness_id': 'b'})
    data = response.get_json()
    assert response.status_code == 200, data
    entry = next(e for e in data['apparatus_entries'] if e.get('id') == entry_index + 1)
    assert entry['readings'][0]['main_wit'] == 'b'
    assert entry['readings'][0]['text'] == 'alle'
    assert '<rdg wit="#b #c" ana="hc:SubstitutionVariant"><ptr target="b:w_7_3"/><ptr target="c:w_7_3"/>' \
        in app_path.read_text(encoding='utf-8')

    response = client.post('/api/apparatus/reading/main-witness', json={
        'apparatus_file': 'apparatus/app_emendatio.xml', 'project_directory': str(project),
        'entry_index': entry_index, 'reading_index': 0, 'witness_id': 'd'})
    assert response.status_code == 400
