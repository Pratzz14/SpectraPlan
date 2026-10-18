"""Bounded S06 same-site HTML crawl. python -m backend.web_ingest crawl|validate"""
import argparse
import json
import os
import re
import shutil
import time
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4

import httpx

from backend.config import Settings
from backend.knowledge_store import digest, file_hash, inside, read_json, write_json
from backend.retrieval import Embedder, build_indexes

AGENT = "SpectraPlanKnowledgeBot/1.0"
EXTRACTOR = "html-blocks-v2"
BOILERPLATE = {"share this post", "share this article", "read more", "learn more", "related posts", "previous post", "next post", "follow us", "print this page", "sign up", "subscribe"}
SKIP = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "input", "template"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "pre", "blockquote"}


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def excluded(self):
        return (self.tag in SKIP or self.attrs.get("aria-hidden") == "true" or "hidden" in self.attrs
                or self.attrs.get("data-elementor-type") in {"header", "footer", "popup"}
                or self.attrs.get("role") == "navigation")

    def text(self):
        if self.excluded():
            return ""
        return " ".join(" ".join(c.text() if isinstance(c, Node) else c for c in self.children).split())

    def nodes(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.nodes()

    def selector(self):
        parts, node = [], self
        while node.parent:
            siblings = [c for c in node.parent.children if isinstance(c, Node) and c.tag == node.tag]
            parts.append(f"{node.tag}:nth-of-type({siblings.index(node) + 1})")
            node = node.parent
        return " > ".join(reversed(parts))


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def canonical_url(value, origin):
    parts, allowed = urlsplit(urldefrag(value)[0]), urlsplit(origin)
    if (parts.scheme != "https" or parts.netloc.lower() != allowed.netloc.lower()
            or parts.username or parts.password or parts.query):
        return None
    path = parts.path or "/"
    if re.search(r"\.(?:pdf|jpe?g|png|svg|gif|webp|zip|xml|json|css|js|mp4|docx?|xlsx?)$", path, re.I):
        return None
    if any(p in path.lower().split("/") for p in ("wp-admin", "wp-json", "feed", "privacy-policy", "terms-of-service", "contact", "cart")):
        return None
    return urlunsplit(("https", allowed.netloc.lower(), path, "", ""))


def extract_html(html, url):
    doc = Document(html)
    nodes = list(doc.root.nodes())
    title = next((n.text() for n in nodes if n.tag == "title"), url)
    main = next((n for n in nodes if n.tag == "main"), None)
    main = main or next((n for n in nodes if n.attrs.get("id") == "content"), doc.root)
    blocks, heading = [], title

    def walk(node):
        nonlocal heading
        if node.excluded():
            return
        if node.tag in BLOCKS:
            text = node.text()
            if text.casefold().strip(" :\t") in BOILERPLATE:
                return
            if text:
                if re.fullmatch(r"h[1-6]", node.tag):
                    heading = text
                ancestor = node
                while ancestor.parent and not ancestor.attrs.get("id"):
                    ancestor = ancestor.parent
                anchor = ancestor.attrs.get("id")
                blocks.append({"block_id": f"b{len(blocks) + 1:04}", "tag": node.tag, "text": text,
                    "heading": heading, "selector": node.selector(), "anchor": anchor,
                    "location_url": url + ("#" + quote(anchor, safe="-_") if anchor else "")})
            return
        for child in node.children:
            if isinstance(child, Node):
                walk(child)
    walk(main)
    links = sorted({urljoin(url, n.attrs["href"]) for n in nodes if n.tag == "a" and n.attrs.get("href")})
    return {"title": title, "blocks": blocks, "links": links}


def web_directory(root):
    pointer = read_json(root / "current.json")
    directory = inside(root, pointer["directory"])
    if read_json(directory / "manifest.json")["corpus_version"] != pointer["corpus_version"]:
        raise ValueError("Website snapshot pointer mismatch")
    return directory


def validate_web(directory):
    manifest, records = read_json(directory / "manifest.json"), read_json(directory / "records.json")
    for name, expected in manifest["artifacts"].items():
        if file_hash(inside(directory, name)) != expected:
            raise ValueError("Website snapshot checksum mismatch")
    pages = {p["url"]: p for p in read_json(directory / "pages.json")}
    if not pages or len(pages) != manifest["page_count"] or len({r["evidence_id"] for r in records}) != len(records):
        raise ValueError("Website snapshot pages or evidence IDs are invalid")
    for page in pages.values():
        if file_hash(inside(directory, page["html_file"])) != page["sha256"]:
            raise ValueError("Website HTML checksum mismatch")
    for record in records:
        page = pages[record["url"]]
        block = next(b for b in page["blocks"] if b["block_id"] == record["block_id"])
        if (record["text"] != block["text"] or record["source_sha256"] != page["sha256"]
                or record["retrieval_eligible"] or not record["context_search_eligible"]
                or record["evidence_scope"] != "business_context"):
            raise ValueError("Website provenance/scope differs from snapshot")
    index = read_json(directory / "index_manifest.json")
    expected_ids = {r["evidence_id"] for r in records}
    if (index["corpus_version"] != manifest["corpus_version"]
            or {r["evidence_id"] for r in read_json(directory / "segments.json")} != expected_ids
            or {r["evidence_id"] for r in read_json(directory / "bm25.json")["documents"]} != expected_ids):
        raise ValueError("Website index membership mismatch")
    for name, expected in index["qdrant_files"].items():
        if file_hash(inside(directory, name)) != expected:
            raise ValueError("Website Qdrant checksum mismatch")
    return {"status": "ready", "corpus_version": manifest["corpus_version"], "pages": len(pages), "records": len(records),
            "seed_url": manifest["seed_url"], "fetched_at": manifest["fetched_at"], "scope": "business_context"}


def crawl(settings, *, max_pages=20, max_depth=2, transport=None):
    if not 1 <= max_pages <= 40 or not 0 <= max_depth <= 3:
        raise ValueError("Use 1–40 pages and depth 0–3")
    seed = (settings.source_dir / "S06_Laboratory_Link.txt").read_text(encoding="utf-8").strip()
    seed = canonical_url(seed, seed)
    if not seed:
        raise ValueError("S06 must name a public HTTPS website page")
    origin = "https://" + urlsplit(seed).netloc
    root = settings.web_corpus_dir
    staged = root / ".staging" / uuid4().hex
    staged.mkdir(parents=True)
    fetched_at = datetime.now(timezone.utc).isoformat()
    pages, skipped, seen = [], [], set()
    with httpx.Client(transport=transport, timeout=30, follow_redirects=False, headers={"User-Agent": AGENT, "Accept": "text/html"}) as client:
        robots_response = client.get(origin + "/robots.txt")
        if robots_response.status_code not in {200, 404, 410}:
            raise ValueError("Cannot establish robots policy; crawl not started")
        robots_text = robots_response.text if robots_response.status_code == 200 else ""
        (staged / "robots.txt").write_text(robots_text, encoding="utf-8")
        robots = RobotFileParser(origin + "/robots.txt")
        robots.parse(robots_text.splitlines())
        delay = max(1, robots.crawl_delay(AGENT) or robots.crawl_delay("*") or 0)
        queue = deque([(seed, 0)])
        while queue and len(pages) < max_pages:
            url, depth = queue.popleft()
            url = canonical_url(url, origin)
            if not url or url in seen:
                continue
            seen.add(url)
            if not robots.can_fetch(AGENT, url):
                skipped.append({"url": url, "reason": "robots_disallowed"})
                continue
            time.sleep(delay)
            try:
                for redirect in range(4):
                    with client.stream("GET", url) as response:
                        if response.is_redirect:
                            target = canonical_url(urljoin(url, response.headers.get("location", "")), origin)
                            if not target or not robots.can_fetch(AGENT, target) or redirect == 3:
                                raise ValueError("Redirect outside crawl scope or redirect limit")
                            url = target
                            continue
                        if response.status_code != 200 or "html" not in response.headers.get("content-type", "").lower():
                            raise ValueError("Page is unavailable or is not HTML")
                        chunks, size = [], 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > 4 * 1024 * 1024:
                                raise ValueError("HTML exceeds 4 MiB limit")
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                    break
                extracted = extract_html(raw.decode("utf-8", errors="replace"), url)
                if any(p["url"] == url for p in pages):
                    continue
                name = "html/" + digest(url)[:20] + ".html"
                inside(staged, name).parent.mkdir(exist_ok=True)
                inside(staged, name).write_bytes(raw)
                page = {"url": url, "title": extracted["title"], "sha256": file_hash(staged / name), "html_file": name,
                        "fetched_at": fetched_at, "depth": depth, "blocks": extracted["blocks"]}
                pages.append(page)
                print(f"Saved {url}: {len(page['blocks'])} blocks", flush=True)
                if depth < max_depth:
                    queue.extend((link, depth + 1) for link in extracted["links"] if canonical_url(link, origin))
            except (httpx.HTTPError, ValueError) as error:
                skipped.append({"url": url, "reason": type(error).__name__})
        if not any(p["url"].rstrip("/") == seed.rstrip("/") for p in pages):
            raise ValueError("The supplied S06 page was not saved; previous snapshot retained")
    records = []
    for page in pages:
        for block in page["blocks"]:
            if block["tag"].startswith("h") or len(block["text"]) < 15:
                continue
            identity = {"url": page["url"], "selector": block["selector"], "text": block["text"]}
            records.append({"evidence_id": "S06:web:" + digest(identity)[:20], "source_id": "S06", "url": page["url"],
                "location_url": block["location_url"], "page_title": page["title"], "section": block["heading"],
                "text": block["text"], "content_kind": "website_text", "evidence_scope": "business_context",
                "source_sha256": page["sha256"], "fetched_at": fetched_at, "block_id": block["block_id"],
                "selector": block["selector"], "revision": digest({**identity, "sha256": page["sha256"], "extractor": EXTRACTOR})[:24],
                "validation_status": "passed", "validation_basis": "Exact HTML snapshot block; vendor claim, not independent validation",
                "human_review_status": "not_reviewed", "retrieval_eligible": False, "context_search_eligible": True, "issues": []})
    if not records:
        raise ValueError("No meaningful website text found; previous snapshot retained")
    embedder = Embedder(settings.embedding_cache_dir, local_only=True)
    version = "web-" + digest({"pages": [{k: p[k] for k in ("url", "sha256")} for p in pages],
                              "extractor": EXTRACTOR, "embedding": embedder.fingerprint})[:20]
    write_json(staged / "pages.json", pages)
    write_json(staged / "records.json", records)
    # Business context gets its own index; technical retrieval eligibility stays false in stored records.
    build_indexes(staged, [{**r, "retrieval_eligible": True} for r in records], version, embedder)
    names = ["pages.json", "records.json", "robots.txt", "segments.json", "bm25.json", "index_manifest.json"]
    manifest = {"corpus_version": version, "seed_url": seed, "origin": origin, "fetched_at": fetched_at,
        "extractor": EXTRACTOR, "page_count": len(pages), "record_count": len(records), "skipped": skipped,
        "policy": {"max_pages": max_pages, "max_depth": max_depth, "same_origin_only": True, "robots_respected": True,
                   "request_delay_s": delay, "technical_corpus_modified": False, "qwen_calls": 0},
        "artifacts": {name: file_hash(staged / name) for name in names}}
    write_json(staged / "manifest.json", manifest)
    result = validate_web(staged)
    final = root / "versions" / version
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists():
        validate_web(final)
        shutil.rmtree(staged)
    else:
        os.replace(staged, final)
    write_json(root / "current.json", {"corpus_version": version, "directory": final.relative_to(root).as_posix()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["crawl", "validate"])
    parser.add_argument("--max-pages", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=2)
    args = parser.parse_args()
    settings = Settings()
    result = crawl(settings, max_pages=args.max_pages, max_depth=args.max_depth) if args.command == "crawl" else validate_web(web_directory(settings.web_corpus_dir))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
