import sys
import os
import codecs
from pathlib import Path
import shutil

from heipy.heipipe.steps import XsltStep
from heipy.heipipe.pipeline_library.sourcedoc import SourceDocPipe
from heipy.heipipe.pipeline_library.semantic import SemanticPipe
from heipy.heipipe.pipeline_library.synoptic import SynopticPipe
from heipy.heipipe.step_library import append_synoptic_links

import config

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit()
    
    # Set up all the global variables
    mapping = config.mapping
    sigla_mapping = {x[1].get('siglum'): x[1].get('synoptic_pre') for x in mapping.items()} # z.B. {A: a+}
    changed_files = sys.argv[1:]
    synoptic_map_changed = True if "synopses/synoptic_map.xml" in changed_files else False
    
    # Main function to setup and run pipelines
    def pipe_setup_and_run(arg, type):
        file_name = os.path.basename(arg)
        file_config = mapping.get(file_name)
        if file_config is None:
            print(f"Could not find {file_name} in configuration file when attempting {type} pipeline, skipping")
            return
        ind_sigle = file_config.get('siglum')
        manuscript = file_config.get('dwork_project')
        result = None
        match type:
            case 'semantic':
                # Prepare the semantic pipelne
                semantic_pipe = SemanticPipe()
                structure_file = os.path.abspath(f'configurations/structure_{file_name}')
                if os.path.isfile(structure_file):
                    semantic_pipe = SemanticPipe(parameters={'inject_structure': True})
                    inject_str = semantic_pipe.get_step_by_name('inject_structure')
                    inject_str.add_parameter({'structure': os.path.abspath(f'configurations/structure_{file_name}')})
                app2note_step = XsltStep(['local_transformations/app2note_standoff.xsl'], 
                                parameters=[{'varianten_doc_path': '../VariantenApparat/App_ArmerHeinrich_text.xml'}],
                                name='app2note')
                semantic_pipe.add_step(app2note_step,1)
                result = semantic_pipe.execute(arg, xinclude=False)
            case 'sourceDoc':
                if manuscript == "" or manuscript is None:
                    return
                sourcedoc_pipe = SourceDocPipe()    
                result = sourcedoc_pipe.execute(arg, xinclude=False)
            case 'synoptic':
                # Prepare synoptic pipeline
                pipe_synoptic = SynopticPipe()
                pipe_synoptic.add_step(append_synoptic_links.get_step(), 
                                parameters={'synoptic_map': 'synopses/synoptic_map.xml',
                                            'base_file': arg,
                                            'sigla_mapping': sigla_mapping})
                result = pipe_synoptic.execute(arg)
        if result is not None:
            output_dir = f"converted/texts/{type}/"
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            output_file = codecs.open(f'{output_dir}/{ind_sigle}.xml', "w", "utf-8")
            output_file.write(result)
        
    for arg in changed_files:
        if not arg.startswith('texts/'):
            continue
        for type in ['semantic', 'sourceDoc', 'synoptic']:
            pipe_setup_and_run(arg, type)

    
    # If the synoptic map was changed, do all the remaining ones
    if synoptic_map_changed:
        all_text_files = [f'texts/{x}' for x in os.listdir('texts')]
        not_changed_files = [item for item in all_text_files if item not in changed_files]
        for file in not_changed_files:
            pipe_setup_and_run(file, 'synoptic')
        synoptic_output_dir = "converted/synoptic_map/"
        Path(synoptic_output_dir).mkdir(parents=True, exist_ok=True)
        shutil.copy("synopses/synoptic_map.xml", "converted/synoptic_map/synoptic.xml")
