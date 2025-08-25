from heipy.heipipe.steps import Pipeline, DeleteStep, XsltStep
from heipy.heipipe.step_library import container2milestone, whitespaces, move_layout_milestones, number_line_segment_beginnings, suppress_first_cb
from heipy.heipipe.pipeline_library.synoptic import milestone_element_map

reduce_markup = XsltStep(files=['xslt/reduce_markup.xsl'],
                            name="reduce_markup",)

create_html = XsltStep(files=['xslt/create_html.xsl'],
                            name="create_html",)


class HeiCritPipe(Pipeline):
    def __init__(self):
        # Add any steps that need specific parameters
        container2milestone_step = container2milestone.get_step()
        container2milestone_step.set_parameter_by_name('element_map', milestone_element_map)
        
        # SourceDoc Pipeline Standard
        pipe_steps = [
            # Index: 0
            DeleteStep(elements=['tei:facsimile', 'tei:metamark', 'tei:fw', 'tei:note', 'tei:teiHeader'], name="delete_basic"),
            reduce_markup,
            whitespaces.get_step(),
            move_layout_milestones.get_step(),
            container2milestone_step,
            
            number_line_segment_beginnings.get_step(),
            # AddAttribute(match='tei:text', att_name=prefix_format('xml','space'), att_val='preserve'),

            # For first gap we add xml:id gap_leaf_1 if missing
            # AddAttribute()

            suppress_first_cb.get_step(),
            create_html
            ]
        
        description = "heiCRIT Pipeline"
        super().__init__(steps=pipe_steps, name="heicrit_pipe", desc=description, serial=False)

def append_synoptic_links_funct(root, parameters): 
    sigla_mapping = parameters.get('sigla_mapping')
    synoptic_map = parameters.get('synoptic_map')
    # for item_n, item in synoptic_map.items():
    #     print(item)
    return root
