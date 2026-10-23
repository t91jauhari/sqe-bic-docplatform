"""Useful API validation diagnostics without request bodies, headers or secrets."""
import json
import re
from urllib.parse import urlsplit


def clean(text):
    text = re.sub(r'(?i)(bearer\s+|llx-)[A-Za-z0-9._~+/=-]+', '[redacted]', str(text))
    text = re.sub(r'https?://[^\s"<>]+', '[url omitted]', text)
    return text[:1200]


def api_diagnostic(exc, stage):
    allowed = {'message','detail','error','code','type','loc','msg','errors'}
    def trim(value):
        if isinstance(value, dict):return {k:trim(v) for k,v in value.items() if k in allowed}
        if isinstance(value, list):return [trim(v) for v in value[:10]]
        return clean(value)
    body = getattr(exc,'body', None)
    detail = trim(body) if isinstance(body,(dict,list)) else 'Provider returned no structured error detail.'
    request = getattr(exc,'request',None)
    endpoint = urlsplit(str(getattr(request,'url',''))).path or 'unknown'
    return {'stage':stage,'status':getattr(exc,'status_code','unknown'),'endpoint':endpoint,
            'request_id':clean(getattr(exc,'request_id','') or ''),
            'detail':clean(json.dumps(detail,ensure_ascii=False))}
