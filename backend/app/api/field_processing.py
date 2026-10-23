"""Field Processing HTTP boundary."""
from fastapi import APIRouter
from app.configuration.repository import get_revision
from app.configuration.profiles import profile_schema
import copy
from fastapi import Depends, HTTPException
from sqlalchemy import select
from app.db import Case, Document, Job, SessionLocal
from app.domain import audit, enqueue, latest_config, refresh_case, validate_config
from app.security import authorized, current_user
from app.api.dependencies import WRITE
from app.api.contracts import ReprocessFieldsInput, RetryFieldsInput

router = APIRouter(tags=['field processing'])

@router.post('/api/documents/{doc_id}/reprocess-fields', status_code=202)
def reprocess_document_fields(doc_id: str, data: ReprocessFieldsInput, user=Depends(WRITE)):
    from app.db import FieldReprocess
    with SessionLocal.begin() as db:
        d = authorized(db, Document, doc_id, user)
        d = db.scalar(select(Document).where(Document.id==d.id).with_for_update())
        if d.status != 'COMPLETED' or not d.raw:
            raise HTTPException(409, 'Wait for extraction to complete before reprocessing fields.')
        if d.provider_state.get('pending_create'):
            raise HTTPException(409, 'Reconcile the pending provider submission first.')
        if db.scalar(select(Job).where(Job.document_id==d.id,Job.status.in_(['QUEUED','DISPATCHED','RUNNING']))):
            raise HTTPException(409, 'A document job is already active.')
        case=db.get(Case,d.case_id)
        pinned=get_revision(db, case.config_id)
        instruction=data.instruction.strip()
        save_guidance=bool(instruction and data.save_to_profile)
        if save_guidance and user.role != 'bank_admin':
            raise HTTPException(403, 'Only a bank administrator can save shared document-profile instructions. Use request-only guidance or ask an administrator.')
        if save_guidance and not data.use_latest_config:
            raise HTTPException(422, 'Use the latest published profile when saving reusable guidance.')
        from app.profile_guidance import locked_latest_config, append_profile_guidance
        config=(locked_latest_config(db,user.org) if save_guidance else latest_config(db,user.org)) if data.use_latest_config else pinned
        payload=copy.deepcopy(config.payload)
        # Use the new profile, but retain the document's original provider/connector family.
        payload['provider']=pinned.payload['provider']
        try:
            validate_config(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, 'Published profile is incompatible with this document provider: '+str(exc))
        profile=payload['profiles'].get(d.doc_type,{})
        fields=list(dict.fromkeys(data.fields))
        if set(fields)-set(profile.get('schema',profile_schema(payload, d.doc_type))['properties']):
            raise HTTPException(422, 'Select existing fields from this document profile.')
        if set(fields)&set(d.overrides) and not data.replace_overrides:
            raise HTTPException(409, 'Selected fields have reviewer overrides; resolve those corrections before reprocessing.')
        if set(fields)&set(d.overrides) and data.replace_overrides and user.role not in {'bank_admin','branch_admin','reviewer'}:
            raise HTTPException(403,'A reviewer must authorize replacing reviewer corrections.')
        guidance_appended=False
        if save_guidance:
            try:
                config,guidance_appended=append_profile_guidance(db,config,d,fields,instruction,user)
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(422, 'Cannot save profile guidance: '+str(exc))
            payload=copy.deepcopy(config.payload)
            payload['provider']=pinned.payload['provider']
            validate_config(payload)
            profile=payload['profiles'][d.doc_type]
        profile.setdefault('schema',copy.deepcopy(profile_schema(payload, d.doc_type)))
        job=enqueue(db,d,action='reprocess_fields');db.flush()
        req=FieldReprocess(org=d.org,branch_id=d.branch_id,document_id=d.id,job_id=job.id,requested_by=user.id,
            payload={'fields':fields,'instruction':instruction,'reason':data.reason,
                     'guidance_saved_to_profile':save_guidance,'guidance_appended':guidance_appended,
                     'config':payload,'config_version':config.version,'replace_overrides':data.replace_overrides,
                     'input_values':{k:copy.deepcopy(d.raw[k]) for k in fields if k in d.raw},
                     'input_overrides':{k:copy.deepcopy(d.overrides[k]) for k in fields if k in d.overrides}})
        db.add(req);db.flush()
        audit(db,d.org,user.id,'document.fields_reprocess_requested',d.branch_id,d.case_id,
              document_id=d.id,request_id=req.id,fields=fields,reason=data.reason,config_version=config.version)
        return {'job_id':job.id,'request_id':req.id,'fields':fields,'config_version':config.version,
                'guidance_saved_to_profile':save_guidance,'guidance_appended':guidance_appended}

@router.get('/api/documents/{doc_id}/reprocess-fields')
def field_reprocess_history(doc_id: str, user=Depends(current_user)):
    from app.db import FieldReprocess
    with SessionLocal() as db:
        d=authorized(db,Document,doc_id,user)
        requests=db.scalars(select(FieldReprocess).where(FieldReprocess.document_id==d.id).order_by(FieldReprocess.created_at.desc())).all()
        from app.spider_failures import confirmed_connection_rejection
        rejection=confirmed_connection_rejection(d.provider_state)
        pending=str(d.provider_state.get('pending_create') or '')
        return [{'id':r.id,'fields':r.payload['fields'],'config_version':r.payload['config_version'],
                 'instruction':r.payload.get('instruction',''),
                 'guidance_saved_to_profile':r.payload.get('guidance_saved_to_profile',False),
                 'reason':r.payload['reason'],'status':db.get(Job,r.job_id).status,'error':db.get(Job,r.job_id).error,'result':r.result,
                 'requires_duplicate_charge_ack':bool(pending and (pending.startswith('spider_fields_'+r.id+'_') or pending=='field_extract_'+r.id) and not rejection),
                 'can_retry':db.get(Job,r.job_id).status=='ERROR' and d.status=='COMPLETED' and (not pending or pending.startswith('spider_fields_'+r.id+'_') or pending=='field_extract_'+r.id),
                 'retry_explanation':rejection['message'] if rejection else ''} for r in requests]

@router.post('/api/documents/{doc_id}/reprocess-fields/{request_id}/retry',status_code=202)
def retry_field_request(doc_id: str, request_id: str, data: RetryFieldsInput = RetryFieldsInput(), user=Depends(WRITE)):
    from app.db import FieldReprocess
    with SessionLocal.begin() as db:
        d=authorized(db,Document,doc_id,user)
        d=db.scalar(select(Document).where(Document.id==d.id).with_for_update())
        req=db.get(FieldReprocess,request_id)
        if not req or req.document_id!=d.id:raise HTTPException(404,'Field request not found.')
        job=db.get(Job,req.job_id)
        if job.status!='ERROR' or d.status!='COMPLETED':raise HTTPException(409,'Only failed field requests can be resumed.')
        pending=d.provider_state.get('pending_create')
        if pending:
            if not (str(pending).startswith('spider_fields_'+request_id+'_') or pending=='field_extract_'+request_id):
                raise HTTPException(409,'A different provider request must be reconciled first.')
            from app.spider_failures import confirmed_connection_rejection
            rejection=confirmed_connection_rejection(d.provider_state)
            if not rejection and not data.accept_possible_duplicate_charge:
                raise HTTPException(409,'The last provider submission may have been processed. Acknowledge possible duplicate provider charges to resubmit this field request.')
            audit(db,d.org,user.id,'document.fields_resubmission_authorized',d.branch_id,d.case_id,request_id=req.id,pending_stage=pending,possible_duplicate_charge=not bool(rejection),confirmed_connection_rejection=bool(rejection))
            d.provider_state={**d.provider_state,'pending_create':None}
        if db.scalar(select(Job).where(Job.document_id==d.id,Job.status.in_(['QUEUED','DISPATCHED','RUNNING']))):raise HTTPException(409,'A document job is already active.')
        job=enqueue(db,d,action='reprocess_fields');db.flush()
        req.job_id=job.id
        refresh_case(db,d.case_id)
        audit(db,d.org,user.id,'document.fields_reprocess_resumed',d.branch_id,d.case_id,request_id=req.id)
        return {'job_id':job.id,'request_id':req.id}
