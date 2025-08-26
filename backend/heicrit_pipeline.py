from lxml import etree as et

from heipy.namespaces import prefix_format
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
    synoptic_map = parameters.get('synoptic_map')
    
    if not synoptic_map:
        return root
    
    # Create a dictionary of all elements with xml:id: {xml:id: element}
    elements_by_id = {}
    for element in root.xpath('//*[@xml:id]'):
        xml_id = element.get('{http://www.w3.org/XML/1998/namespace}id')
        if xml_id:
            elements_by_id[xml_id] = element
    
    # Iterate through synoptic_map and find corresponding elements
    for key, synoptic_entry in synoptic_map.items():
        # Extract xml:id (remove prefix if present)
        if ':' in key:
            xml_id = key.split(':', 1)[1]  # Get part after first colon
        else:
            xml_id = key
        
        # Find element in our dictionary
        element = elements_by_id.get(xml_id)
        if element is None:
            continue
        gap = et.Element(prefix_format('tei', 'gap'))
        
        # Add corresp attribute with the target value
        if 'target' in synoptic_entry:
            target_value = synoptic_entry['target']
            if isinstance(target_value, list):
                # Join list elements with spaces
                corresp_value = ' '.join(target_value)
            else:
                corresp_value = str(target_value)
            gap.set('corresp', corresp_value)
        
        # Insert gap before any text content by handling text and tail
        if element.text and element.text.strip():
            # If element has text content, move it after the gap
            gap.tail = element.text
            element.text = None
        
        element.insert(0, gap)  # Insert as first child
    
    return root
