from heipy.synopse import create_synopse_graphs
import os

import test_config
import config

# sigla_mapping = test_config.mapping
sigla_mapping = config.mapping

create_synopse_graphs(
    [f"texts/{x}" for x in os.listdir('texts') if 'tr' not in x and 'AH' in x], 
    # ["texts/test.xml", "texts/test2.xml", "texts/test3.xml"],
               sigla_mapping,
               map_criterion= 'xml:id'
               )
