import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from backend.config import Settings
from backend.knowledge_store import file_hash, read_json
from backend.main import create_app
from backend.search_service import SearchService, SearchUnavailable
from backend.web_ingest import canonical_url, crawl, extract_html, validate_web, web_directory
from tests.corpus_fixture import FakeEmbedder, make_corpus


HTML = '''<html><head><title>Laboratory</title><script>ignore()</script></head><body>
<header><p>Ignore navigation</p></header><main><h1>Laboratory</h1><h2 id="raman">Raman instrument</h2>
<p>Raman spectroscopy uses a 785 nm laser for measurements of powder samples.</p>
<p>share this post:</p>
<form><p>Ignore newsletter and personal information</p></form>
<a href="/products/">Product</a><a href="/blocked/">Blocked</a><a href="https://elsewhere.test/">External</a>
<a href="/privacy-policy">Legal</a><a href="/paper.pdf">PDF</a></main><footer><p>Ignore footer</p></footer></body></html>'''


def test_html_blocks_and_origin_scope():
    page = extract_html(HTML, "https://example.test/laboratory/")
    assert page["title"] == "Laboratory"
    assert [b["text"] for b in page["blocks"]] == ["Laboratory", "Raman instrument", "Raman spectroscopy uses a 785 nm laser for measurements of powder samples."]
    assert page["blocks"][2]["heading"] == "Raman instrument"
    assert "main:nth-of-type(1)" in page["blocks"][2]["selector"]
    for url in ["http://example.test/", "https://elsewhere.test/", "https://example.test/a.pdf", "https://example.test/?search=x", "https://example.test/wp-admin/", "https://example.test/privacy-policy"]:
        assert canonical_url(url, "https://example.test") is None
    assert canonical_url("https://example.test/laboratory/#raman", "https://example.test") == "https://example.test/laboratory/"


@pytest.fixture
def web_fixture(tmp_path, monkeypatch):
    source = tmp_path / "sources"
    source.mkdir()
    (source / "S06_Laboratory_Link.txt").write_text("https://example.test/laboratory/")
    config = Settings(_env_file=None, source_dir=source, corpus_dir=tmp_path / "technical", web_corpus_dir=tmp_path / "web", embedding_cache_dir=tmp_path / "embeddings")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /blocked/\n")
        if request.url.path == "/products/":
            html = '<main><h1>Product</h1><p>Fiber cables connect the laboratory to remote measuring points.</p></main>'
        else:
            html = HTML
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    monkeypatch.setattr("backend.web_ingest.time.sleep", lambda delay: None)
    monkeypatch.setattr("backend.web_ingest.Embedder", lambda *a, **kw: FakeEmbedder())
    transport = httpx.MockTransport(handler)
    result = crawl(config, max_pages=4, max_depth=2, transport=transport)
    return config, calls, result, transport


def test_crawl_robots_stable_ids_scope_and_tamper(web_fixture):
    config, calls, result, transport = web_fixture
    assert result["pages"] == 2 and result["records"] == 2
    assert not any("blocked" in url or "elsewhere" in url or "privacy" in url or "pdf" in url for url in calls)
    directory = web_directory(config.web_corpus_dir)
    records = read_json(directory / "records.json")
    assert all(r["source_id"] == "S06" and r["evidence_scope"] == "business_context" and not r["retrieval_eligible"] for r in records)
    ids = [(r["evidence_id"], r["revision"]) for r in records]
    again = crawl(config, max_pages=4, max_depth=2, transport=transport)
    assert again["corpus_version"] == result["corpus_version"]
    assert ids == [(r["evidence_id"], r["revision"]) for r in read_json(directory / "records.json")]
    html = directory / read_json(directory / "pages.json")[0]["html_file"]
    html.write_text("changed")
    with pytest.raises(ValueError, match="HTML checksum"):
        validate_web(directory)


def test_search_modes_and_business_opt_in(web_fixture, monkeypatch):
    config, _, _, _ = web_fixture
    make_corpus(config.corpus_dir)
    monkeypatch.setattr("backend.search_service.Embedder", lambda *a, **kw: pytest.fail("BM25 must not load embeddings"))
    service = SearchService(config)
    keyword = service.compare("Raman powder", mode="bm25")
    assert set(keyword["rankings"]) == {"bm25"} and keyword["rankings"]["bm25"]
    assert all(hit["evidence"]["source_id"] != "S06" for hit in keyword["rankings"]["bm25"])
    assert service.compare("unfindablezzzz", mode="bm25")["rankings"]["bm25"] == []
    monkeypatch.setattr("backend.search_service.Embedder", lambda *a, **kw: FakeEmbedder())
    combined = service.compare("Raman powder", dataset="all")
    assert set(combined["rankings"]) == {"bm25", "qdrant", "hybrid"}
    assert combined["model_calls"] == 0 and combined["warnings"]
    assert set(combined["versions"]) == {"technical", "website"}
    website = service.compare("Raman", mode="qdrant", dataset="website")
    assert all(not h["evidence"]["retrieval_eligible"] and h["evidence"]["context_search_eligible"] for h in website["rankings"]["qdrant"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(r["rankings"]["qdrant"] for r in pool.map(lambda _: service.compare("Raman", mode="qdrant"), range(2)))


def test_api_input_validation_and_missing_dataset(tmp_path):
    config = Settings(_env_file=None, corpus_dir=tmp_path, web_corpus_dir=tmp_path / "website")
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(config)), base_url="http://test") as client:
            for body in [{"query": " "}, {"query": "x", "mode": "other"}, {"query": "x", "limit": 9}, {"query": "x", "url": "https://elsewhere.test"}, {"query": "x" * 2001}]:
                assert (await client.post("/api/search", json=body)).status_code == 422
            response = await client.post("/api/search", json={"query": "Raman"})
            assert response.status_code == 503 and str(tmp_path) not in response.text
            assert (await client.get("/api/search/status")).json()["website"]["status"] == "unavailable"
    asyncio.run(run())


def test_missing_embedding_is_unavailable_but_long_query_is_input_error(web_fixture, monkeypatch):
    config, _, _, _ = web_fixture
    make_corpus(config.corpus_dir)
    def missing(*args, **kwargs):
        raise ValueError("private local embedding path")
    monkeypatch.setattr("backend.search_service.Embedder", missing)
    with pytest.raises(SearchUnavailable) as error:
        SearchService(config).compare("Raman", mode="qdrant")
    assert "private" not in str(error.value)
    monkeypatch.setattr("backend.search_service.Embedder", lambda *args, **kwargs: FakeEmbedder())
    with pytest.raises(ValueError, match="512 tokens"):
        SearchService(config).compare("x " * 600, mode="qdrant")
