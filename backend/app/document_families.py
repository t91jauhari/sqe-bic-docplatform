"""Document-family catalog, validation and extraction defaults."""
import copy
import re

from .configuration.native_catalog import native_catalog

DEFAULTS = native_catalog()['families']

def families(cfg):
    return {**copy.deepcopy(DEFAULTS), **cfg.get('document_families', {})}

def validate_families(cfg):
    raw=cfg.get('document_families',{})
    if not isinstance(raw,dict) or len(raw)>100:raise ValueError('Configure at most 100 document families.')
    labels=set()
    rules={r['id'] for r in cfg.get('sop_rules',[])+cfg.get('generic_sop_rules',[])}
    for key,f in families(cfg).items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',key):raise ValueError('Family IDs must start with a lowercase letter and contain at most 40 letters, digits, underscores or hyphens.')
        if not isinstance(f,dict) or not isinstance(f.get('label'),str) or not 1<=len(f['label'].strip())<=120:raise ValueError('Document family names require 1–120 characters.')
        if f['label'].strip().casefold() in labels:raise ValueError('Document family names must be unique.')
        labels.add(f['label'].strip().casefold())
        if not isinstance(f.get('enabled',True),bool):raise ValueError('Family enabled status must be boolean.')
        for k,limit in [('description',2000),('extraction_guidance',10000)]:
            if not isinstance(f.get(k,''),str) or len(f.get(k,''))>limit:raise ValueError(f'{key}: invalid {k}.')
        profiles=f.get('profiles')
        if not isinstance(profiles,list) or not profiles or any(not isinstance(p,str) or p not in cfg['profiles'] for p in profiles) or len(profiles)!=len(set(profiles)):raise ValueError(f'{key}: choose at least one distinct registered document profile.')
        required=f.get('required',[])
        if not isinstance(required,list) or any(p not in profiles for p in required) or len(required)!=len(set(required)):raise ValueError(f'{key}: default required documents must belong to this family.')
        selected=f.get('sop_rule_ids',[])
        if not isinstance(selected,list) or any(r not in rules for r in selected) or len(selected)!=len(set(selected)):raise ValueError(f'{key}: select distinct existing SOP checks.')
        dataset_id=f.get('dataset_id')
        if dataset_id is not None and (not isinstance(dataset_id,str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,119}',dataset_id)):raise ValueError(f'{key}: invalid reference dataset ID.')
        if f.get('report_layout','forex') not in {'forex','account_opening'}:raise ValueError(f'{key}: unknown report layout.')
        for k in ['sequential_page_extraction','cross_page_reference']:
            if k in f and not isinstance(f[k],bool):raise ValueError(f'{key}: {k} must be boolean.')
        context=f.get('report_context',{})
        if not isinstance(context,dict) or any(k not in {'region_name','category','activity','inspection_type','period'} or not isinstance(v,str) or len(v)>500 for k,v in context.items()):raise ValueError(f'{key}: invalid report context.')

def extraction_config(cfg, flow_id):
    flow=cfg['templates'].get(flow_id)
    if not flow:return copy.deepcopy(cfg)
    family=families(cfg)[flow.get('document_family','forex')]
    result=copy.deepcopy(cfg)
    for flag in ['sequential_page_extraction','cross_page_reference']:
        if flag in family:result[flag]=family[flag]
    guidance=family.get('extraction_guidance','').strip()
    if guidance:
        from .extraction_prompts import system_instruction
        for key in family['profiles']:
            p=result['profiles'][key]
            p['system_instruction']=system_instruction(p)+'\n\nDocument family reading guidance:\n'+guidance
    return result
