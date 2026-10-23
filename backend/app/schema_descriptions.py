"""Editable profile schemas with compatibility checks for registered native engines."""
import copy


def validate_profile_schema(profile, baseline, provider):
    """Allow additive native fields; Spider's JSON projection also supports edited types."""
    import re
    schema = profile.get('schema', baseline['schema'])
    if not isinstance(schema, dict) or schema.get('type') != 'object' or not isinstance(schema.get('properties'), dict):
        raise ValueError('Profile schema must be an object with properties.')
    props = schema['properties']
    if not 1 <= len(props) <= 250:
        raise ValueError('A profile requires 1–250 fields.')
    def check(node, depth=0):
        if depth > 15 or not isinstance(node, dict):
            raise ValueError('Invalid or excessively nested field schema.')
        types = node.get('type', 'object')
        types = types if isinstance(types, list) else [types]
        if not types or set(types) - {'object','array','string','number','integer','boolean','null'}:
            raise ValueError('Unsupported field type.')
        if '$ref' in node or '$defs' in node:
            raise ValueError('Use inline field definitions instead of references.')
        children = node.get('properties', {})
        if not isinstance(children, dict) or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', k) for k in children):
            raise ValueError('Field keys must use lowercase letters, digits and underscores.')
        required = node.get('required', [])
        if not isinstance(required, list) or any(not isinstance(k, str) or k not in children for k in required):
            raise ValueError('Required fields must exist in properties.')
        for child in children.values():
            check(child, depth+1)
        if 'items' in node:
            check(node['items'], depth+1)
    check(schema)
    if provider != 'spider-ai':
        # Native validators require their registered field shapes. New fields are projected separately.
        original = baseline['schema']['properties']
        if any(k not in props or contract(props[k]) != contract(v) for k,v in original.items()):
            raise ValueError('Native providers allow only field descriptions and additive fields; existing types are engine contracts.')
        if set(baseline['schema'].get('required', [])) - set(schema.get('required', [])):
            raise ValueError('Native required engine fields cannot be removed.')
    columns = profile.get('columns', [])
    if not isinstance(columns, list) or not columns or any(not isinstance(c, (list,tuple)) or len(c)!=2 or not all(isinstance(v,str) and v.strip() for v in c) or c[0] not in props for c in columns):
        raise ValueError('Display columns must name schema properties and have labels.')
    if len({c[0] for c in columns}) != len(columns):
        raise ValueError('Display field keys must be unique.')
    if set(props) != {c[0] for c in columns}:
        raise ValueError('Every schema field requires a display column.')
    policy=profile.get('policy',{})
    sampling=policy.get('extraction_sampling',{})
    if not isinstance(sampling,dict):raise ValueError('Extraction sampling must be an object.')
    for key,high in [('temperature',2),('top_p',1)]:
        if key in sampling and (type(sampling[key]) not in (int,float) or not 0<=sampling[key]<=high):raise ValueError('Invalid extraction sampling setting.')
    regions=policy.get('extraction_detail_regions',[])
    if not isinstance(regions,list) or len(regions)>3:raise ValueError('Use at most three extraction detail regions.')
    for region in regions:
        if not isinstance(region,dict) or not isinstance(region.get('fields'),list) or not region['fields'] or any(k not in props for k in region['fields']):raise ValueError('Detail regions must name existing profile fields.')
        box=region.get('box')
        if not isinstance(box,list) or len(box)!=4 or any(type(v) not in (int,float) or not 0<=v<=1 for v in box) or box[0]>=box[2] or box[1]>=box[3]:raise ValueError('Detail region coordinates must be ordered fractions between 0 and 1.')
    rule=policy.get('case_address_reconciliation',{})
    if rule:
        if not isinstance(rule,dict) or type(rule.get('enabled')) is not bool or rule.get('target_field')!='customer_address' or rule.get('target_field') not in props or rule.get('source_profile')!='lld' or rule.get('source_field')!='payer_address' or type(rule.get('minimum_similarity')) not in (int,float) or not .85<=rule['minimum_similarity']<=1:
            raise ValueError('Case address reconciliation requires an existing target, LLD payer_address, and similarity 0.85–1.')


def contract(value):
    if isinstance(value, list):
        return [contract(v) for v in value]
    if isinstance(value, dict):
        return {k: contract(v) for k, v in value.items() if not (k == "description" and isinstance(value.get("type"), (str, list)))}
    return value


def validate_extension_value(value, node, path):
    """Type-check added fields without changing a registered native validator."""
    types=node.get('type','object')
    allowed=types if isinstance(types,list) else [types]
    actual=('null' if value is None else 'boolean' if isinstance(value,bool) else
            'integer' if isinstance(value,int) else 'number' if isinstance(value,float) else
            'string' if isinstance(value,str) else 'array' if isinstance(value,list) else
            'object' if isinstance(value,dict) else 'unknown')
    if actual not in allowed and not (actual=='integer' and 'number' in allowed):
        raise ValueError(f'Added field {path}: expected {allowed}, got {actual}.')
    if 'enum' in node and value not in node['enum']:raise ValueError(f'Added field {path}: value is outside enum.')
    if actual=='object':
        if set(node.get('required',[]))-set(value):raise ValueError(f'Added field {path}: required child missing.')
        for key,child in node.get('properties',{}).items():
            if key in value:validate_extension_value(value[key],child,path+'.'+key)
    if actual=='array' and 'items' in node:
        for i,child in enumerate(value):validate_extension_value(child,node['items'],f'{path}[{i}]')


def validate_descriptions(value, path="$", total=None):
    total = total if total is not None else [0]
    if isinstance(value, dict):
        if isinstance(value.get("type"), (str, list)) and "description" in value:
            description = value["description"]
            if not isinstance(description, str) or not description.strip() or len(description) > 20000:
                raise ValueError(f"{path}: field description must contain 1–20000 characters.")
            total[0] += len(description)
            if total[0] > 500000:
                raise ValueError("Profile field descriptions exceed 500000 characters.")
        for key, item in value.items():
            validate_descriptions(item, f"{path}.{key}", total)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            validate_descriptions(item, f"{path}[{index}]", total)


def with_schemas(payload, profiles):
    result = copy.deepcopy(payload)
    for name, profile in result["profiles"].items():
        if "schema" not in profile:
            profile["schema"] = copy.deepcopy(profiles[name]["schema"])
    return result
