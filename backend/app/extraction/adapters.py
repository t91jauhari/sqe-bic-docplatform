"""Code-owned integrations; configuration selects IDs, never executable paths."""
from .contracts import ExtractionRequest


class SpiderAdapter:
    def extract(self, request: ExtractionRequest):
        from app.spider_provider import run_spider
        return run_spider(request.document, request.configuration, request.heartbeat)


class FixtureAdapter:
    def extract(self, request: ExtractionRequest):
        from app.provider import run_fixture
        return run_fixture(request.document, request.configuration, request.heartbeat)


def default_adapters():
    return {"spider-ai": SpiderAdapter(), "fixture": FixtureAdapter()}
