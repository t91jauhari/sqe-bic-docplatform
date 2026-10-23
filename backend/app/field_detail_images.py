"""Enlarged original-page regions for small handwriting; full pages remain evidence."""
import base64
import fitz
from .storage import store, original_key, fitz_open_original

REGIONS={
 'application': [({'beneficiary','beneficiary_bank','beneficiary_account_number'},(0.07,0.10,0.46,0.24)),
                 ({'charges','transaction_type'},(0.08,0.05,0.95,0.41))],
 'lld': [({'beneficiary_address'},(0.34,0.155,0.985,0.215)),
         ({'payer_address'},(0.30,0.45,0.97,0.59)),
         ({'bank_officer_signature','purpose','financial_relationship'},(0.30,0.68,1.0,1.0))],
 'valas_declaration_1': [({'customer_address'},(0.10,0.08,0.98,0.50))],
}

def configured_regions(profile):
    configured=profile.get('policy',{}).get('extraction_detail_regions')
    return configured if isinstance(configured,list) else []

def detail_images(doc,fields,page_number,heartbeat,*,profile=None,max_bytes=180000):
    regions=[]
    entries=[(set(item['fields']),item['box']) for item in configured_regions(profile)] if profile is not None else REGIONS.get(doc.doc_type,[])
    for keys,box in entries:
        if set(fields)&keys:regions.append(box)
    if not regions:return []
    result=[]
    with fitz_open_original(store().read(original_key(doc))) as pdf:
        page=pdf[page_number-1]
        for box in regions[:3]:
            heartbeat()
            r=page.rect
            clip=fitz.Rect(r.x0+box[0]*r.width,r.y0+box[1]*r.height,r.x0+box[2]*r.width,r.y0+box[3]*r.height)
            scale=min(1800/max(clip.width,clip.height),4)
            pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,alpha=False)
            data=pix.tobytes('jpg',jpg_quality=90)
            while len(data)>max_bytes and scale>0.5:
                scale*=0.8;pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),clip=clip,alpha=False);data=pix.tobytes('jpg',jpg_quality=85)
            result.extend([{'type':'text','text':f'Enlarged detail from the SAME original physical page {page_number}, normalized region {box}. Use alongside the full page; printed labels and handwriting may cross.'},
                           {'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(data).decode(),'detail':'high'}}])
    return result
