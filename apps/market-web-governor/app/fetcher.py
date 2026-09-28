"""Governor-side document fetch: the service downloads one public HTTPS document itself, so the text a model reads is
exactly the text the service stores and hashes."""
from __future__ import annotations

import hashlib
import io
import ipaddress
import re
import socket
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from .config import Settings
from .models import validate_fetch_url

USER_AGENT = "SanitiMarketWebGovernor/1.0 (research evidence fetch)"
HTML_TYPES = {"text/html", "application/xhtml+xml"}
MIN_USEFUL_CHARACTERS = 200

Resolver = Callable[[str, int], list[str]]


class FetchError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FetchedDocument:
    requested_url: str
    final_url: str
    http_status: int
    media_type: str
    content_type: str
    byte_length: int
    raw_sha256: str
    text: str
    text_sha256: str
    truncated: bool
    page_count: int | None
    pages_read: int | None
    title: str
    retrieved_at: str
    redirects: list[str] = field(default_factory=list)

    @property
    def useful(self) -> bool:
        return len(self.text.strip()) >= MIN_USEFUL_CHARACTERS

    def metadata(self) -> dict[str, object]:
        return {
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "http_status": self.http_status,
            "media_type": self.media_type,
            "content_type": self.content_type,
            "byte_length": self.byte_length,
            "raw_sha256": self.raw_sha256,
            "text_sha256": self.text_sha256,
            "text_characters": len(self.text),
            "truncated": self.truncated,
            "page_count": self.page_count,
            "pages_read": self.pages_read,
            "title": self.title,
            "redirects": self.redirects,
            "retrieved_at": self.retrieved_at,
        }


def resolve_host(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("SOURCE_DNS_FAILED", "the source host could not be resolved") from exc
    return sorted({info[4][0] for info in infos})


class DocumentFetcher:
    def __init__(self, settings: Settings, client: httpx.Client | None = None, resolver: Resolver | None = None):
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.fetch_timeout_seconds, follow_redirects=False)
        self.resolver = resolver or resolve_host

    def close(self) -> None:
        self.client.close()

    def fetch(self, url: str) -> FetchedDocument:
        current = url
        redirects: list[str] = []
        for _ in range(self.settings.fetch_max_redirects + 1):
            self._check_destination(current)
            try:
                with self.client.stream(
                    "GET", current, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/*"}
                ) as response:
                    if 300 <= response.status_code < 400 and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        redirects.append(current)
                        continue
                    if response.status_code >= 400:
                        raise FetchError("SOURCE_HTTP_ERROR", f"the source returned HTTP {response.status_code}")
                    body = self._read_limited(response)
                    return self._document(url, current, response, body, redirects)
            except httpx.TimeoutException as exc:
                raise FetchError("SOURCE_TIMEOUT", "the source did not respond in time") from exc
            except httpx.HTTPError as exc:
                raise FetchError("SOURCE_UNREACHABLE", "the source could not be reached") from exc
        raise FetchError("TOO_MANY_REDIRECTS", "the source redirected too many times")

    def _check_destination(self, url: str) -> None:
        try:
            validate_fetch_url(url)
        except ValueError as exc:
            raise FetchError("URL_NOT_ALLOWED", str(exc)) from exc
        parsed = urlsplit(url)
        addresses = self.resolver(parsed.hostname or "", parsed.port or 443)
        if not addresses:
            raise FetchError("SOURCE_DNS_FAILED", "the source host could not be resolved")
        for address in addresses:
            if not ipaddress.ip_address(address).is_global:
                raise FetchError("PRIVATE_ADDRESS_BLOCKED", "the source host resolves to a non-public address")

    def _read_limited(self, response: httpx.Response) -> bytes:
        limit = self.settings.fetch_max_bytes
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise FetchError("SOURCE_TOO_LARGE", f"the source is larger than {limit} bytes")
        chunks = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > limit:
                raise FetchError("SOURCE_TOO_LARGE", f"the source is larger than {limit} bytes")
            chunks.append(chunk)
        return b"".join(chunks)

    def _document(
        self, requested: str, final: str, response: httpx.Response, body: bytes, redirects: list[str]
    ) -> FetchedDocument:
        header = response.headers.get("content-type", "")
        media_type = header.split(";")[0].strip().lower()
        charset_match = re.search(r"charset=([\w.-]+)", header, re.IGNORECASE)
        charset = charset_match.group(1) if charset_match else "utf-8"
        page_count = pages_read = None
        if body.startswith(b"%PDF") or media_type == "application/pdf":
            text, title, page_count, pages_read = _pdf_text(body, self.settings.fetch_max_pdf_pages)
            content_type = "PDF"
        elif media_type in HTML_TYPES or (not media_type and b"<html" in body[:2048].lower()):
            text, title = _html_text(_decode(body, charset))
            content_type = "WEB_PAGE"
        elif media_type.startswith("text/"):
            text, title = _decode(body, charset), ""
            content_type = "TEXT"
        else:
            raise FetchError("UNSUPPORTED_CONTENT_TYPE", f"content type {media_type or 'unknown'} is not supported")
        text = normalize_document_text(text)
        truncated = len(text) > self.settings.fetch_max_characters or (
            page_count is not None and pages_read is not None and pages_read < page_count
        )
        text = text[: self.settings.fetch_max_characters]
        return FetchedDocument(
            requested_url=requested,
            final_url=final,
            http_status=response.status_code,
            media_type=media_type or "unknown",
            content_type=content_type,
            byte_length=len(body),
            raw_sha256=hashlib.sha256(body).hexdigest(),
            text=text,
            text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            truncated=truncated,
            page_count=page_count,
            pages_read=pages_read,
            title=title.strip()[:500],
            retrieved_at=datetime.now(UTC).isoformat(),
            redirects=redirects,
        )


def _decode(body: bytes, charset: str) -> str:
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "canvas", "object"}
    BLOCK = {
        "p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol",
        "header", "footer", "nav", "main", "aside", "blockquote", "pre", "hr", "dd", "dt", "form", "figure",
        "figcaption", "caption", "tbody", "thead",
    }
    CELL = {"td", "th"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.in_title = False
        self.title = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP:
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")
        elif tag in self.CELL:
            self.parts.append(" | ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag == "title":
            self.in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title += data
        elif not self.skip_depth:
            self.parts.append(data)


def _html_text(html: str) -> tuple[str, str]:
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return "".join(extractor.parts), extractor.title


def _pdf_text(body: bytes, max_pages: int) -> tuple[str, str, int, int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted and not reader.decrypt(""):
            raise FetchError("PDF_ENCRYPTED", "the PDF is encrypted")
        total = len(reader.pages)
        parts = []
        for index in range(min(total, max_pages)):
            parts.append(f"\n[page {index + 1}]\n{reader.pages[index].extract_text() or ''}")
        title = ""
        if reader.metadata and isinstance(reader.metadata.title, str):
            title = reader.metadata.title
    except FetchError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError) as exc:
        raise FetchError("PDF_UNREADABLE", "the PDF could not be read") from exc
    return "".join(parts), title, total, min(total, max_pages)


def normalize_document_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _quote_form(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'",
                                         "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", text).strip()


def verify_quotes(document_text: str, quotes: list[str], *, minimum: int = 12, limit: int = 8) -> tuple[
    list[dict[str, object]], list[str]
]:
    """Return the quotes found verbatim in the document (whitespace- and typography-insensitive) with their offsets
    in the normalized text, and the quotes that were not found."""
    haystack = _quote_form(document_text)
    verified: list[dict[str, object]] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in quotes:
        quote = _quote_form(raw).strip('"').strip("'").strip()
        if len(quote) < minimum or quote in seen:
            if quote and quote not in seen:
                rejected.append(raw)
            continue
        seen.add(quote)
        start = haystack.find(quote)
        if start < 0:
            rejected.append(raw)
            continue
        verified.append({"text": haystack[start:start + len(quote)], "start": start, "end": start + len(quote)})
        if len(verified) >= limit:
            break
    return verified, rejected
