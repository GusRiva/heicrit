
def local_name(el):
    """
    Return an lxml element's tag without its namespace prefix.
    """
    tag = el.tag
    return tag.split('}')[-1] if isinstance(tag, str) and '}' in tag else tag


# Elements a synoptic map can link as a location (locus) of the text. They can
# nest (a <div> holding <l>s, a <seg> inside an <l>), so which one a token
# belongs to is decided by the synoptic map: its nearest ancestor that the map
# links (see base_locus_ids and WitnessFragmentResolver.resolve_line_locator).
LOCUS_TAGS = frozenset({'l', 'head', 'p', 'titlePart', 's', 'seg', 'label', 'div'})

# Loci that bound a token's surroundings (its neighbour tokens, the emendation
# it sits in). <s>/<seg> lie inside these and <div> around them, so neither
# narrows that scope.
BLOCK_LOCUS_TAGS = frozenset({'l', 'head', 'p', 'titlePart', 'label'})

# Location label for a locus without @n (an <l> without @n stays unlabelled).
LOCUS_LABELS = {
    'head': 'Head',
    'label': 'Label',
    'seg': 'Seg',
    's': 'S',
    'div': 'Div',
    'p': 'P',
    'titlePart': 'Title',
}


def locus_label(el):
    """A locus element's location label: its @n, else a label for its kind."""
    if el is None:
        return None
    return el.get('n') or LOCUS_LABELS.get(local_name(el))


def base_locus_ids(loci, base_prefix):
    """
    The xml:ids of the base-text elements that synoptic loci (SynopticMap.
    get_loci(), keyed by their base-text anchor) address directly, e.g.
    {"l_5", "head_71_1"} for keys "b:l_5", "b:head_71_1". Anchors of units
    the base text lacks ("b:right(l_4)") address no element and are skipped.
    """
    ids = set()
    if not loci or not base_prefix:
        return ids
    for key in loci:
        spec = parse_location_token(key.split('#', 1)[0])
        if spec and spec['kind'] == 'single' and spec['prefix'] == base_prefix:
            ids.add(spec['id'])
    return ids


def parse_location_token(token):
    """
    Parse a "prefix:spec" location token (e.g. "a:w_5_1", "a:range(w_5_1,w_5_4)",
    "a:left(w_7_2)", "a:right(w_23_1)") into its prefix and address kind.

    Returns:
        dict with 'prefix' and 'kind' ('single' | 'range' | 'left' | 'right').
        'single'/'left'/'right' entries also have 'id'; 'range' entries have
        'start' and 'end'. Returns None if the token has no "prefix:" part.
    """
    if ':' not in token:
        return None
    prefix, spec = token.split(':', 1)
    spec = spec.strip()

    if spec.startswith('left(') and spec.endswith(')'):
        return {'prefix': prefix, 'kind': 'left', 'id': spec[5:-1].strip()}
    if spec.startswith('right(') and spec.endswith(')'):
        return {'prefix': prefix, 'kind': 'right', 'id': spec[6:-1].strip()}
    if spec.startswith('range(') and spec.endswith(')'):
        start, end = spec[6:-1].split(',', 1)
        return {'prefix': prefix, 'kind': 'range', 'start': start.strip(), 'end': end.strip()}
    return {'prefix': prefix, 'kind': 'single', 'id': spec}


def resolve_relative_path(target_path, base_filepath):
    """
    Resolve a relative path based on a base file path
    """
    # Get the directory of the base file
    base_dir = '/'.join(base_filepath.split('/')[:-1])
    
    if target_path.startswith('../'):
        # Handle relative paths like ../synopses/synoptic_map.xml
        path_parts = base_dir.split('/') if base_dir else []
        target_parts = target_path.split('/')
        
        for part in target_parts:
            if part == '..':
                if path_parts:
                    path_parts.pop()
            elif part and part != '.':
                path_parts.append(part)
        
        return '/'.join(path_parts)
    else:
        # Handle absolute or simple relative paths
        return target_path


def find_file_in_project(resolved_path, project_files):
    """
    Find a file in project files using exact and fuzzy matching
    """
    # First try exact match
    for project_path, file_data in project_files.items():
        if project_path.endswith(resolved_path) or project_path == resolved_path:
            return file_data
    
    # If exact match not found, try fuzzy matching, but only trust it when
    # it is unambiguous (exactly one candidate) - otherwise report not found
    # rather than silently guessing among several same-named files.
    fuzzy_matches = [
        file_data for project_path, file_data in project_files.items()
        if resolved_path in project_path or project_path.endswith(resolved_path.split('/')[-1])
    ]
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]

    return None

