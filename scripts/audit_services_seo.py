#!/usr/bin/env python3
"""Read-only 315-service SEO audit. Run: python3 scripts/audit_services_seo.py"""
from __future__ import annotations
import json, re, sys
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://eternity-call-playlist.github.io/eternity-events-website/"
SERVICES = ROOT / "services"
REPORT = ROOT / "seo-audit-report.json"
NAME_RE = re.compile(r"-ee-(\d+)\.html$")
GENERIC = re.compile(r"Explore [^<]{2,100} with Eternity Events\.", re.I)

class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = []
        self.h1 = []
        self.meta = defaultdict(list)
        self.canonical = []
        self.links = []
        self.assets = []
        self.schema = []
        self._capture = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title": self._capture = "title"
        elif tag == "h1": self._capture = "h1"
        elif tag == "script" and a.get("type") == "application/ld+json": self._capture = "schema"
        if tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key: self.meta[key].append(a.get("content", ""))
        if tag == "link" and a.get("rel") == "canonical": self.canonical.append(a.get("href", ""))
        if tag == "a" and a.get("href"): self.links.append(a["href"])
        if tag in ("img", "script") and a.get("src"): self.assets.append(a["src"])

    def handle_endtag(self, tag):
        if tag == self._capture or (tag == "script" and self._capture == "schema"):
            self._capture = None

    def handle_data(self, data):
        if self._capture == "title": self.title.append(data)
        if self._capture == "h1": self.h1.append(data)
        if self._capture == "schema": self.schema.append(data)
        self._text.append(data)

def local_file(href, current):
    u = urlsplit(href)
    if u.scheme or u.netloc or href.startswith(("#", "mailto:", "tel:", "javascript:")): return None
    p = unquote(u.path)
    if not p: return None
    if p.startswith("/"):
        # GitHub Pages project URL
        prefix = "/eternity-events-website/"
        if not p.startswith(prefix): return None
        p = p[len(prefix):]
        return ROOT / p
    return current.parent / p

def report():
    files = sorted((f for f in SERVICES.glob("*.html") if NAME_RE.search(f.name)), key=lambda f: int(NAME_RE.search(f.name).group(1)))
    issues, warnings, ids, descriptions, titles = [], [], [], [], []
    checks = 0
    if len(files) != 315: issues.append(f"Expected 315 service files; found {len(files)}")
    for f in files:
        ident = int(NAME_RE.search(f.name).group(1)); ids.append(ident)
        html = f.read_text(encoding="utf-8")
        p = Page()
        try: p.feed(html)
        except Exception as e: issues.append(f"{f.name}: HTML parsing failed: {e}"); continue
        checks += 1
        title = "".join(p.title).strip()
        h1 = "".join(p.h1).strip()
        expected = BASE + "services/" + f.name
        if not title: issues.append(f"{f.name}: missing title")
        if not h1: issues.append(f"{f.name}: missing H1")
        if len(p.canonical) != 1 or p.canonical[0] != expected: issues.append(f"{f.name}: canonical mismatch")
        if len(p.meta["description"]) != 1 or not p.meta["description"][0]: issues.append(f"{f.name}: missing or duplicate meta description")
        if len(p.meta["og:description"]) != 1 or not p.meta["og:description"][0]: issues.append(f"{f.name}: missing or duplicate OG description")
        if len(p.meta["description"]) == 1 and len(p.meta["description"][0]) > 175:
            warnings.append(f"{f.name}: long meta description ({len(p.meta['description'][0])} characters)")
        if len(p.meta["description"]) == 1: descriptions.append((p.meta["description"][0].casefold(), f.name))
        if title: titles.append((title.casefold(), f.name))
        if not p.schema: issues.append(f"{f.name}: missing JSON-LD")
        else:
            try:
                block = json.loads("".join(p.schema))
                if block.get("@type") != "Service": issues.append(f"{f.name}: JSON-LD type not Service")
                if block.get("url") != expected: issues.append(f"{f.name}: JSON-LD URL mismatch")
                if not block.get("description"): issues.append(f"{f.name}: missing JSON-LD Service description")
                provider = block.get("provider")
                if not isinstance(provider, dict) or provider.get("name") != "Eternity Events":
                    issues.append(f"{f.name}: missing or incorrect JSON-LD provider")
            except (ValueError, TypeError) as e: issues.append(f"{f.name}: invalid JSON-LD: {e}")
        if GENERIC.search(html) and "<p>Explore " in html:
            warnings.append(f"{f.name}: generic visible description — editorial review needed")
        if "Bridal Makeup Artist" in h1 and ("performance duration" in html or "continuous performance" in html):
            issues.append(f"{f.name}: irrelevant performer language")
        if "<h2>FAQs</h2>" not in html: warnings.append(f"{f.name}: missing FAQs heading")
        for href in p.links + p.assets:
            dest = local_file(href, f)
            if dest is None: continue
            try: dest = dest.resolve()
            except OSError: continue
            if not dest.is_relative_to(ROOT): continue
            if dest.is_file() or (dest.is_dir() and (dest / "index.html").is_file()): continue
            issues.append(f"{f.name}: broken internal link or asset => {href}")
    if len(ids) != len(set(ids)): issues.append("Duplicate numeric EE IDs")
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.is_file(): issues.append("Missing sitemap.xml")
    else:
        try:
            xml = ElementTree.parse(sitemap)
            urls = [x.text.strip() for x in xml.iter() if x.tag.endswith("loc") and x.text]
            if len(urls) != len(set(urls)): issues.append("Exact duplicate sitemap URLs")
            page_urls = [x for x in urls if re.search(r"/services/.+-ee-\d+\.html$", x)]
            expected_urls = {BASE + "services/" + f.name for f in files}
            for url in sorted(expected_urls - set(page_urls)): issues.append("Not in sitemap: " + url)
            for url in sorted(set(page_urls) - expected_urls): issues.append("Sitemap URL without service file: " + url)
        except (ElementTree.ParseError, OSError) as e: issues.append(f"Cannot parse sitemap: {e}")
    for kind, items in (("meta description", descriptions), ("title", titles)):
        grouped = defaultdict(list)
        for value, fname in items: grouped[value].append(fname)
        for group in grouped.values():
            if len(group) > 1: warnings.append(f"Duplicate {kind}: {', '.join(group)}")
    result = {
        "scope": "technical checks of the current 315 service HTML files",
        "files_checked": checks, "files_expected": 315,
        "issues": sorted(set(issues)), "warnings": sorted(set(warnings)),
        "issue_count": len(set(issues)), "warning_count": len(set(warnings)),
        "technical_pass": checks == 315 and not issues,
        "note": "Technical pass does not imply Google indexing, ranking or editorial quality approval."
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("files_checked","issue_count","warning_count","technical_pass")}, indent=2))
    for item in result["issues"][:50]: print("ERROR:", item)
    for item in result["warnings"][:20]: print("REVIEW:", item)
    return 1 if issues else 0

if __name__ == "__main__":
    sys.exit(report())
