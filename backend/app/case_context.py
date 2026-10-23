"""Conservative context suggestions; bank policy decides acceptance."""
def suggestions(documents):
    values=[]
    for doc in documents:
        if doc.status != 'COMPLETED':continue
        if doc.doc_type in {'valas_declaration_1','valas_declaration_2'}:
            values.append({'field':'threshold_state','value':'ABOVE' if doc.doc_type.endswith('_1') else 'WITHIN','document_id':doc.id,'source':'classified declaration variant','requires_acceptance':True})
        if doc.doc_type == 'ektp':
            values.append({'field':'customer_type','value':'INDIVIDUAL','document_id':doc.id,'source':'identity document present; does not prove transaction party ownership','requires_acceptance':True})
    # Different declarations must remain ambiguous, never silently pick one.
    for value in values:
        value['conflict']=len({x['value'] for x in values if x['field']==value['field']})>1
    return values
