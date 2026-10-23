"""Distinguish proven pre-connection rejection from uncertain model submissions."""
import json


def failure_details(status, body=None):
    error=body.get('error') if isinstance(body,dict) else None
    message=error.get('message','') if isinstance(error,dict) else ''
    if not isinstance(message,str):message=''
    # This gateway explicitly reports a failed connection to its upstream model.
    # Do not generalize this to arbitrary 5xx, read timeouts, or non-JSON replies.
    if status in (502,503) and '[502]' in message and 'fetch connect timeout' in message.lower():
        return {'kind':'UPSTREAM_CONNECT_TIMEOUT','retry_safe':True,
                'message':f'Spider-AI HTTP {status}: the gateway could not connect to the model before its connection timeout. Retry the failed request; existing extraction is preserved.'}
    if status in (502,503,504):
        return {'kind':'UPSTREAM_UNAVAILABLE','retry_safe':False,
                'message':f'Spider-AI HTTP {status}: the model gateway is unavailable or timed out. The submission outcome is uncertain; use the recovery action for this request.'}
    return {'kind':'HTTP_ERROR','retry_safe':status<500,
            'message':f'Spider-AI HTTP {status}. Check credentials, model and provider limits.'}


def confirmed_connection_rejection(state):
    """Read legacy saved responses only when they match the exact pending request."""
    pending=str(state.get('pending_create') or '')
    saved=state.get('spider_http_response') or {}
    if not pending.startswith('spider_') or saved.get('stage')!=pending[len('spider_'):]:return None
    if not saved.get('request_id') or saved['request_id']!=state.get('spider_request_id'):return None
    if saved.get('status') not in (502,503):return None
    try:
        from .storage import store
        body=json.loads(store().read(saved['body_key']))
    except Exception:
        return None
    result=failure_details(saved['status'],body)
    return result if result['retry_safe'] else None
