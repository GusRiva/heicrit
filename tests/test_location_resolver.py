"""
WitnessFragmentResolver.resolve_text_html: a reading addressed by several
parts of one witness must render all of them, in the witness's own word
order - whatever the ids look like.
"""

import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))

from apparatus import Apparatus  # noqa: E402

PROJECT = os.path.join(ROOT, 'test_data', 'emendatio')
APPARATUS_FILE = os.path.join(PROJECT, 'apparatus', 'app_emendatio.xml')


@pytest.fixture(scope='module')
def resolver():
    return Apparatus(APPARATUS_FILE).get_resolver()


def test_single_token(resolver):
    assert resolver.resolve_text_html(['b:w_1_4'])[0] == 'Katzen'


def test_several_ptrs_of_one_witness(resolver):
    assert resolver.resolve_text_html(['b:w_1_4', 'b:w_1_5'])[0] == 'Katzen grau'


def test_parts_ordered_by_document_not_listing(resolver):
    assert resolver.resolve_text_html(['b:w_1_5', 'b:w_1_4'])[0] == 'Katzen grau'


def test_only_first_witness_rendered(resolver):
    text = resolver.resolve_text_html(['b:w_1_4', 'b:w_1_5', 'c:w_1_4', 'c:w_1_5'])[0]
    assert text == 'Katzen grau'


def test_single_token_plus_range(resolver):
    text = resolver.resolve_text_html(['b:range(w_1_3, w_1_4)', 'b:w_1_1'])[0]
    assert text == 'Nachts alle Katzen'


def test_unresolvable_part_is_skipped(resolver):
    assert resolver.resolve_text_html(['b:None', 'b:range(w_1_4, w_1_5)'])[0] == 'Katzen grau'


def test_arbitrary_ids(tmp_path):
    # Ids with no numeric pattern, alphabetically in reverse of text order.
    project = tmp_path / 'emendatio'
    shutil.copytree(PROJECT, project)
    text_file = project / 'texts' / 'B' / 'B_1.xml'
    xml = text_file.read_text(encoding='utf-8')
    xml = xml.replace('xml:id="w_1_4"', 'xml:id="zeta"').replace('xml:id="w_1_5"', 'xml:id="alpha"')
    text_file.write_text(xml, encoding='utf-8')

    resolver = Apparatus(str(project / 'apparatus' / 'app_emendatio.xml')).get_resolver()
    assert resolver.resolve_text_html(['b:alpha', 'b:zeta'])[0] == 'Katzen grau'
