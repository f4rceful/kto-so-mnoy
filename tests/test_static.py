import gzip

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import GZipUnlessRange
from app.static import PrecompressedFiles, accepted_encodings

JS = ("console.log('привет, мир');\n" * 120).encode()
CSS = (".card { color: #123456; }\n" * 120).encode()
INDEX = "<!doctype html><title>Кто со мной?</title><div id=root></div>".encode()


@pytest.fixture()
def site(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_bytes(JS)
    (assets / "app.js.gz").write_bytes(gzip.compress(JS))
    (assets / "app.js.br").write_bytes(b"fake-brotli-payload")
    (assets / "only-gz.css").write_bytes(CSS)
    (assets / "only-gz.css.gz").write_bytes(gzip.compress(CSS))
    (assets / "plain.js").write_bytes(JS)
    (assets / "ghost.js.br").write_bytes(b"orphan")
    (assets / "logo.png").write_bytes(b"\x89PNG" * 400)
    (assets / "logo.png.gz").write_bytes(b"not-used")
    (tmp_path / "index.html").write_bytes(INDEX)
    app = FastAPI()
    app.add_middleware(GZipUnlessRange, minimum_size=500)
    app.mount("/", PrecompressedFiles(directory=tmp_path, html=True), name="webapp")
    return TestClient(app)


def get(site, path, accept, **headers):
    return site.get(path, headers={"Accept-Encoding": accept, **headers})


def test_brotli_is_preferred_when_the_browser_accepts_it(site):
    r = get(site, "/assets/app.js", "gzip, deflate, br")
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "br"
    assert r.headers["content-type"] == "text/javascript; charset=utf-8"
    assert r.headers["vary"] == "Accept-Encoding"
    assert int(r.headers["content-length"]) == len(b"fake-brotli-payload")


def test_gzip_variant_is_used_when_brotli_is_not_accepted(site):
    r = get(site, "/assets/app.js", "gzip")
    assert r.headers["content-encoding"] == "gzip" and r.headers["content-type"].startswith("text/javascript")
    assert r.content == JS, "содержимое должно распаковаться ровно один раз"
    assert int(r.headers["content-length"]) == len(gzip.compress(JS))


def test_plain_file_without_accept_encoding(site):
    r = get(site, "/assets/app.js", "identity")
    assert "content-encoding" not in r.headers
    assert r.content == JS and r.headers["content-type"].startswith("text/javascript")


def test_missing_variant_falls_back_to_the_next_one(site):
    r = get(site, "/assets/only-gz.css", "br, gzip")
    assert r.headers["content-encoding"] == "gzip" and r.content == CSS
    assert r.headers["content-type"] == "text/css; charset=utf-8"


def test_file_without_any_variant_is_compressed_on_the_fly(site):
    r = get(site, "/assets/plain.js", "gzip")
    assert r.headers["content-encoding"] == "gzip" and r.content == JS
    assert int(r.headers["content-length"]) < len(JS)


def test_orphan_variant_does_not_expose_a_missing_file(site):
    assert get(site, "/assets/ghost.js", "br").status_code == 404
    assert get(site, "/assets/ghost.js.br", "identity").status_code == 200


def test_only_known_text_types_use_precompressed_files(site):
    r = get(site, "/assets/logo.png", "gzip, br")
    assert r.headers["content-type"] == "image/png"
    assert r.content == b"\x89PNG" * 400


def test_conditional_request_returns_304_with_vary(site):
    first = get(site, "/assets/app.js", "br")
    again = get(site, "/assets/app.js", "br", **{"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304 and again.content == b""
    assert again.headers["vary"] == "Accept-Encoding"
    other = get(site, "/assets/app.js", "gzip", **{"If-None-Match": first.headers["etag"]})
    assert other.status_code == 200, "ETag сжатой копии не подходит для другой кодировки"


def test_variants_have_different_etags(site):
    br = get(site, "/assets/app.js", "br").headers["etag"]
    gz = get(site, "/assets/app.js", "gzip").headers["etag"]
    plain = get(site, "/assets/app.js", "identity").headers["etag"]
    assert len({br, gz, plain}) == 3


def test_head_request_is_answered_without_a_body(site):
    r = site.head("/assets/app.js", headers={"Accept-Encoding": "br"})
    assert r.status_code == 200 and r.headers["content-encoding"] == "br" and r.content == b""


def test_index_page_and_unknown_paths(site):
    assert get(site, "/", "gzip").content == INDEX
    assert get(site, "/assets/nope.js", "br").status_code == 404
    assert get(site, "/assets/../../etc/passwd", "br").status_code in (400, 404)


def test_post_is_still_rejected(site):
    assert site.post("/assets/app.js").status_code == 405


@pytest.mark.parametrize("header, expected", [("gzip, deflate, br", {"gzip", "deflate", "br"}), ("br;q=1.0, gzip;q=0.8", {"br", "gzip"}), ("", set()), ("  BR ", {"br"})])
def test_accept_encoding_parsing(header, expected):
    assert accepted_encodings({"type": "http", "headers": [(b"accept-encoding", header.encode())]}) == expected
