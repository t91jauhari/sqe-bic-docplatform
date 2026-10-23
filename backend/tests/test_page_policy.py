"""Required-page policies preserve physical numbering and exempt only the final page."""
from types import SimpleNamespace
import pytest
from page_policy import required_initial_pages, initial_page_records
from app.configuration.sop_policies import VisualPolicy, evaluate_policy
from app.configuration.dataset_policy import comparison_policy
from app.dataset_comparison import project

@pytest.mark.parametrize('count', [1,2,3,4,12])
def test_final_page_selection_is_dynamic(count):
    assert required_initial_pages(count,exclude_final_page=True)==list(range(1,count))

@pytest.mark.parametrize('count', [None,0,-1,True,'3',1001])
def test_unknown_or_invalid_physical_count_is_not_guessed(count):
    with pytest.raises(ValueError):required_initial_pages(count,exclude_final_page=True)

def pages(count):
    return [{'page_number':n,'footer_present':True,'non_text':True,'complete':True,'evidence':'Visible handwritten initials.'} for n in range(1,count)]

@pytest.mark.parametrize('count',[2,3,4])
def test_final_observation_optional_but_earlier_pages_required(count):
    marked=pages(count)
    assert len(initial_page_records(count,marked,exclude_final_page=True))==count-1
    for invalid in (marked[1:],marked+[marked[0]],marked+[{'page_number':count+1}]):
        with pytest.raises(ValueError):initial_page_records(count,invalid,exclude_final_page=True)
    with pytest.raises(ValueError):initial_page_records(count,marked)

def test_visual_and_reference_checks_share_exemption():
    value={'page_count':3,'pages':pages(3)+[{'page_number':3,'footer_present':False}]}
    docs=[{'doc_type':'form','status':'COMPLETED','normalized':{'marks':value}}]
    policy=VisualPolicy(type='visual',check='all_pages',left='form.marks',right='form.marks',exclude_final_page=True)
    assert evaluate_policy(policy,docs)[0]=='PASS'
    compare_policy=comparison_policy().model_copy(update={'exclude_final_page':True})
    assert project(SimpleNamespace(normalized={'marks':value}),'marks','initials',policy=compare_policy) is True
    value['pages'][0]['footer_present']=False
    assert evaluate_policy(policy,docs)[0]=='FAIL'
    assert project(SimpleNamespace(normalized={'marks':value}),'marks','initials',policy=compare_policy) is False
    value['pages']=pages(3)[1:]
    assert evaluate_policy(policy,docs)[0]=='REVIEW'
    assert project(SimpleNamespace(normalized={'marks':value}),'marks','initials',policy=compare_policy) is None

def test_single_final_page_is_not_applicable():
    policy=VisualPolicy(type='visual',check='all_pages',left='form.marks',right='form.marks',exclude_final_page=True)
    docs=[{'doc_type':'form','status':'COMPLETED','normalized':{'marks':{'page_count':1,'pages':[]}}}]
    assert evaluate_policy(policy,docs)==('NOT_APPLICABLE','NO_INITIAL_PAGES_REQUIRED')

def test_exemption_cannot_be_applied_to_unrelated_signature_checks():
    with pytest.raises(ValueError):VisualPolicy(type='visual',check='presence',left='form.mark',right='form.mark',exclude_final_page=True)
