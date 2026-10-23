"""Link actual Parse visual/form regions; never crop label text as a mark."""
import math
import re

ALIASES = {
    'customer_signature': ['signature of customer','customer signature','tanda tangan nasabah'],
    'owner_signature': ['owner signature','cardholder signature','tanda tangan pemilik'],
    'bank_officer_signature': ['officer signature','bank official signature','tanda tangan petugas','tanda tangan pejabat bank'],
    'bank_approval': ['bank approval','persetujuan bank'],
    'owner_photo': ['owner photo','portrait','foto pemilik','foto nasabah'],
    'customer_stamp': ['customer stamp','stempel nasabah'],
    'cs_stamp': ['cs stamp','stempel cs','customer service stamp'],
    'stamp_duty': ['meterai','materai','stamp duty'],
    'stamp_verification': ['stamp verification','company stamp','stempel perusahaan'],
    'signatory_signature': ['signatory signature','tanda tangan penandatangan'],
}

def number(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)


def parse_box(boxes, page, path):
    """Convert provider page points + optional clockwise rotation to normalized AABB."""
    width,height=page.get('page_width'),page.get('page_height')
    if not number(width) or not number(height) or min(width,height)<=0:
        raise ValueError('Parse page dimensions unavailable')
    if isinstance(boxes,dict):boxes=[boxes]
    if not isinstance(boxes,list) or not boxes:raise ValueError('Region has no Parse box')
    corners=[]
    for b in boxes:
        if not isinstance(b,dict) or not all(number(b.get(k)) for k in ('x','y','w','h')):
            raise ValueError('Invalid Parse point box')
        x,y,w,h=(b[k] for k in ('x','y','w','h'))
        if w<=0 or h<=0:raise ValueError('Empty Parse point box')
        rotation=b.get('r') or 0
        if not number(rotation):raise ValueError('Invalid Parse rotation')
        angle=math.radians(rotation);cx,cy=x+w/2,y+h/2
        for px,py in [(x,y),(x+w,y),(x+w,y+h),(x,y+h)]:
            dx,dy=px-cx,py-cy
            corners.append((cx+dx*math.cos(angle)-dy*math.sin(angle),cy+dx*math.sin(angle)+dy*math.cos(angle)))
    x0,y0=min(p[0] for p in corners),min(p[1] for p in corners)
    x1,y1=max(p[0] for p in corners),max(p[1] for p in corners)
    if x0<0 or y0<0 or x1>width or y1>height:raise ValueError('Parse region outside page')
    return {'page_number':page['page_number'],'bbox':[x0/width,y0/height,x1/width,y1/height],
            'units':'normalized','origin':'top_left','parse_boxes':boxes,'source_width':width,
            'source_height':height,'source_path':path,'source':'parse','link_review_required':True}


def nodes(value,path):
    if isinstance(value,dict):
        yield value,path
        for k,v in value.items():
            if isinstance(v,(list,dict)):yield from nodes(v,path+'.'+k)
    elif isinstance(value,list):
        for i,v in enumerate(value):yield from nodes(v,path+f'[{i}]')


def link_parse_evidence(raw, parsed):
    from .evidence import visual_fields
    links,candidates={},{}
    observations=list(visual_fields(raw))
    for section in ('forms','items'):
        pages=(parsed.get(section) or {}).get('pages',[])
        for page_index,page in enumerate(pages):
            if not isinstance(page,dict):continue
            page_number=page.get('page_number')
            if not isinstance(page_number,int) or isinstance(page_number,bool):continue
            for node,path in nodes(page,f'{section}.pages[{page_index}]'):
                # Ordinary text boxes locate labels/prose, not handwritten marks.
                if section=='items' and node.get('type') not in {'image','signature','stamp','photo'}:continue
                if section=='forms' and node.get('type')!='field':continue
                label=' '.join(str(node.get(k) or '') for k in ('field','label','caption')).casefold()
                label=re.sub(r'\s+',' ',label)
                for field,observation in observations:
                    expected=observation.get('page_number') if isinstance(observation,dict) else None
                    if expected is not None and expected!=page_number:continue
                    aliases=ALIASES.get(field,[])
                    if field.startswith('page_initials.'):
                        aliases=['customer initial','customer initials','paraf nasabah','paraf','initials']
                    if not any(alias in label for alias in aliases):continue
                    item={'source_path':path,'page_number':page_number,'label':label}
                    boxes=node.get('bbox')
                    if isinstance(node.get('value_items'),list):
                        value_boxes=[]
                        for v in node['value_items']:
                            if isinstance(v,dict) and v.get('bbox'):
                                vb=v['bbox'];value_boxes.extend(vb if isinstance(vb,list) else [vb])
                        if value_boxes:boxes=value_boxes
                    try:
                        box=parse_box(boxes,page,path)
                        if field.startswith('page_initials.') and (box['bbox'][0]<.5 or box['bbox'][1]<.7):
                            raise ValueError('Initial candidate outside bottom-right region')
                        item['box']=box
                    except (ValueError,KeyError,TypeError) as exc:
                        item['error']=str(exc)
                    candidates.setdefault(field,[]).append(item)
    for field,items in candidates.items():
        # Count even unlocalized matching fields; missing boxes cannot break a tie.
        unique={json_key(i):i for i in items}
        if len(unique)==1:
            candidate=next(iter(unique.values()))
            if 'box' in candidate:links[field]=candidate['box']
    return links,candidates


def json_key(item):
    import json
    return json.dumps({'label':item['label'],'page_number':item['page_number'],'box':item.get('box',{}).get('bbox')},sort_keys=True)
