from heipy.synopse import create_synopse_graph

import test_config

sigla_mapping = test_config.mapping

create_synopse_graph(
    # [f"texts/{x}" for x in os.listdir('texts') if 'tr' not in x], 
    ["texts/test.xml", "texts/test2.xml", "texts/test3.xml"],
               sigla_mapping,
               map_criterion= 'xml:id'
               )
