"""Explicit profile policy for same-case near-identical address reconciliation."""
import copy,re
from difflib import SequenceMatcher
from sqlalchemy import select
from .db import Document

def address_text(value):
    return value.get('raw') if isinstance(value,dict) else value if isinstance(value,str) else None

def address_numbers(value):
    return re.findall(r'\d+[a-z]*',value.casefold())

def apply_context(db,doc,cfg,report,selected=None,effective_overrides=None):
    rule=cfg['profiles'][doc.doc_type].get('policy',{}).get('case_address_reconciliation',{})
    if not rule.get('enabled'):return report
    field=rule['target_field']
    overrides=doc.overrides if effective_overrides is None else effective_overrides
    if field in overrides or (selected is not None and field not in selected):return report
    before=report['normalized'].get(field);text=address_text(before)
    if not isinstance(text,str) or not re.findall(r'\d+',text):return report
    sources=list(db.scalars(select(Document).where(Document.case_id==doc.case_id,Document.org==doc.org,
        Document.branch_id==doc.branch_id,Document.doc_type==rule['source_profile'],Document.status=='COMPLETED',Document.id!=doc.id)))
    observations=[]
    for source in sources:
        if rule['source_field'] in source.overrides:continue
        value=address_text(source.normalized.get(rule['source_field']))
        if not isinstance(value,str) or address_numbers(value)!=address_numbers(text):continue
        a,b=[re.sub(r'\W','',v.casefold()) for v in (text,value)]
        similarity=SequenceMatcher(None,a,b).ratio()
        if similarity>=rule.get('minimum_similarity',0.85):observations.append((source,value,similarity))
    if not observations:return report
    values={re.sub(r'\W','',v.casefold()) for _,v,_ in observations}
    if len(values)!=1:
        report['automatic_context']={'status':'CONFLICT','field':field,'source_document_ids':[s.id for s,_,_ in observations]}
        return report
    source,value,similarity=observations[0]
    replacement={**copy.deepcopy(before),'raw':value,'complete':True} if isinstance(before,dict) else value
    if replacement==before:return report
    report['normalized'][field]=replacement
    if field in report.get('fields',{}):report['fields'][field]['normalized_value']=copy.deepcopy(replacement)
    report['automatic_context']={'status':'APPLIED','field':field,'before':copy.deepcopy(before),'after':copy.deepcopy(replacement),
        'source_document_id':source.id,'source_field':rule['source_field'],'similarity':round(similarity,5),'policy':'same_case_near_match_matching_address_numbers'}
    report.setdefault('corrections',[]).append({'field':field,'kind':'automatic_case_address','source_document_id':source.id})
    report['normalization']={'status':'PROFILE_CONTEXT_APPLIED','handled_by':'published_case_address_policy'}
    return report

def queue_dependents(db,source,cfg):
    from .domain import enqueue
    for doc in db.scalars(select(Document).where(Document.case_id==source.case_id,Document.org==source.org,
            Document.branch_id==source.branch_id,Document.status=='COMPLETED',Document.id!=source.id)):
        if doc.doc_type==source.doc_type:continue
        rule=cfg['profiles'].get(doc.doc_type,{}).get('policy',{}).get('case_address_reconciliation',{})
        if rule.get('enabled') and rule.get('source_profile')==source.doc_type:
            enqueue(db,doc,'revalidate')
