import os
import codecs
import json
from lxml import etree as et 

from heipy.parsers import HeiEditionsParser
from heipy.namespaces import ns

import config

sigla_mapping = config.sigla_mapping

root = et.parse('synopses/synoptic_map.xml', parser=HeiEditionsParser())

prefixdefs = root.findall('.//tei:prefixDef[@ana="hc:SynopticTextPrefixDefinition"]', ns)
for prefixdef in prefixdefs:
    old_rp = prefixdef.attrib.get('replacementPattern')
    rp_ending = old_rp[9:]
    ident = prefixdef.attrib.get('ident')
    prefixdef.set('replacementPattern', f"{sigla_mapping.get(ident, ident)}/{rp_ending}")

output_file_path = 'converted/texts/synoptic/default'
os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
# tree = et.ElementTree(root)
root.write(f"{output_file_path}/synoptic.xml", pretty_print=True)