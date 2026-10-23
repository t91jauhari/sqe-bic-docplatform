import copy
from types import SimpleNamespace

import pytest

from app.configuration.codec import fingerprint
from app.extraction.contracts import ProcessingIssue
from app.extraction.service import extract_document
from app.provider import run_provider


class Adapter:
    def __init__(self, response=({"extract_result": {"name": "Synthetic"}}, {"type": "custom"})):
        self.requests = []
        self.response = response

    def extract(self, request):
        self.requests.append(request)
        request.heartbeat()
        request.configuration["profiles"]["custom"]["system_prompt"] = "Adapter-local change"
        return self.response


def payload():
    return {"provider": "synthetic", "profiles": {"custom": {"system_prompt": "Pinned instructions"}}}


def test_request_copies_pinned_configuration_without_changing_document_identity():
    cfg = payload()
    original = copy.deepcopy(cfg)
    doc = SimpleNamespace(id="doc", doc_type="custom")
    adapter = Adapter()
    beats = []
    result = extract_document(doc, cfg, lambda: beats.append(True), adapters={"synthetic": adapter})
    assert result.response["extract_result"]["name"] == "Synthetic"
    assert cfg == original and adapter.requests[0].document is doc
    assert adapter.requests[0].configuration_sha256 == fingerprint(original)
    assert beats == [True]


def test_unknown_provider_does_not_fall_back_to_a_paid_integration():
    adapter = Adapter()
    with pytest.raises(ProcessingIssue, match="not registered"):
        extract_document(SimpleNamespace(), payload(), lambda: None, adapters={"llama": adapter})
    assert adapter.requests == []


@pytest.mark.parametrize("response", [None, ({}, {}), ({"extract_result": []}, {}), ({"extract_result": {}}, None)])
def test_invalid_provider_contract_fails(response):
    with pytest.raises(ProcessingIssue, match="contract"):
        extract_document(SimpleNamespace(), payload(), lambda: None, adapters={"synthetic": Adapter(response)})


def test_classification_only_result_and_provider_exception_are_preserved():
    result = extract_document(SimpleNamespace(), payload(), lambda: None, adapters={"synthetic": Adapter((None, {"confirmed": False}))})
    assert result.response is None and result.classification == {"confirmed": False}
    failure = ProcessingIssue("Submission outcome is uncertain")
    class Failing:
        def extract(self, request):
            raise failure
    with pytest.raises(ProcessingIssue) as caught:
        extract_document(SimpleNamespace(), payload(), lambda: None, adapters={"synthetic": Failing()})
    assert caught.value is failure


@pytest.mark.parametrize("provider,target", [("fixture", "app.provider.run_fixture"), ("spider-ai", "app.spider_provider.run_spider")])
def test_legacy_facade_dispatches_through_registered_adapters(monkeypatch, provider, target):
    called = []
    def run(doc, cfg, heartbeat):
        called.append((doc.id, cfg["provider"]))
        return {"extract_result": {}}, {"type": "custom"}
    monkeypatch.setattr(target, run)
    assert run_provider(SimpleNamespace(id="doc"), {"provider": provider}, lambda: None) == ({"extract_result": {}}, {"type": "custom"})
    assert called == [("doc", provider)]


def test_removed_llama_cannot_dispatch_even_with_injected_adapter():
    adapter = Adapter()
    cfg = {"provider": "llama", "profiles": {}}
    with pytest.raises(ProcessingIssue, match="removed"):
        extract_document(SimpleNamespace(), cfg, lambda: None, adapters={"llama": adapter})
    assert adapter.requests == []
    assert cfg["provider"] == "llama"


def test_supported_registry_excludes_llama():
    from app.extraction.adapters import default_adapters
    assert set(default_adapters()) == {"spider-ai", "fixture"}


def test_removed_llama_compatibility_entry_point_cannot_submit():
    from app.provider import run_llama
    with pytest.raises(ProcessingIssue, match="removed"):
        run_llama(None, {}, None)


def test_removed_connector_rejects_reads_and_writes(signed):
    for method in (signed.get, signed.put):
        response = method("/api/connector")
        assert response.status_code == 410
        assert "removed" in response.json()["detail"]


def test_removed_llama_selected_fields_fail_before_database_or_provider_access():
    from app.field_reprocessing import extract_selected
    with pytest.raises(ProcessingIssue, match="removed"):
        extract_selected(None, SimpleNamespace(payload={"config": {"provider": "llama"}}), None)
