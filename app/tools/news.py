from __future__ import annotations

import asyncio
import calendar
import ipaddress
import socket
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, HttpUrl

from app.tools.errors import ToolFailure, ToolPolicyViolation

DEFAULT_NEWS_ENDPOINTS = (
    "https://export.arxiv.org/api/query?search_query=all%3A{query}"
    "&start=0&max_results=25&sortBy=submittedDate&sortOrder=descending",
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
)
TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"gclid", "fbclid", "mc_cid", "mc_eid"}


class SearchNewsArguments(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    hours: int = Field(default=24, ge=1, le=24 * 30)
    limit: int = Field(default=10, ge=1, le=50)
    include_keywords: list[str] = Field(default_factory=list, max_length=100)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=100)


class FetchArticleArguments(BaseModel):
    url: HttpUrl


class NewsSearchTool:
    def __init__(
        self,
        *,
        endpoints: Sequence[str] = DEFAULT_NEWS_ENDPOINTS,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10,
        max_feed_bytes: int = 2_000_000,
    ) -> None:
        self._endpoints = tuple(endpoints)
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._max_feed_bytes = max_feed_bytes

    async def search_news(self, arguments: SearchNewsArguments) -> dict[str, object]:
        encoded_query = quote_plus(arguments.query)
        urls = [endpoint.format(query=encoded_query) for endpoint in self._endpoints]
        if self._client is not None:
            responses = await asyncio.gather(*(self._fetch(self._client, url) for url in urls))
        else:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                headers={"User-Agent": "AI-Daily-Brief/0.1"},
            ) as client:
                responses = await asyncio.gather(*(self._fetch(client, url) for url in urls))

        cutoff = datetime.now(UTC) - timedelta(hours=arguments.hours)
        items: list[dict[str, object]] = []
        seen: set[str] = set()
        failed_sources = 0
        for response in responses:
            if isinstance(response, Exception):
                failed_sources += 1
                continue
            parsed = feedparser.parse(response)
            for entry in parsed.entries:
                link = str(entry.get("link", "")).strip()
                title = unescape(str(entry.get("title", "")).strip())
                if not link or not title:
                    continue
                summary = BeautifulSoup(str(entry.get("summary", "")), "html.parser").get_text(
                    " ", strip=True
                )[:500]
                if not self._matches_preferences(
                    title,
                    summary,
                    include_keywords=arguments.include_keywords,
                    exclude_keywords=arguments.exclude_keywords,
                ):
                    continue
                published_at = self._published_at(entry)
                if published_at is not None and published_at < cutoff:
                    continue
                normalized_link = self._normalize_url(link)
                dedupe_key = normalized_link or title.casefold()
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                source = entry.get("source", {})
                source_name = (
                    str(source.get("title", "")).strip() if isinstance(source, dict) else ""
                )
                items.append(
                    {
                        "title": title,
                        "url": normalized_link,
                        "source": source_name or urlsplit(link).hostname or "unknown",
                        "published_at": published_at.isoformat() if published_at else None,
                        "summary": summary,
                    }
                )

        items.sort(key=lambda item: str(item["published_at"] or ""), reverse=True)
        return {
            "query": arguments.query,
            "items": items[: arguments.limit],
            "failed_sources": failed_sources,
        }

    @staticmethod
    def _matches_preferences(
        title: str,
        summary: str,
        *,
        include_keywords: Sequence[str],
        exclude_keywords: Sequence[str],
    ) -> bool:
        searchable = f"{title}\n{summary}".casefold()
        includes = tuple(
            keyword.strip().casefold() for keyword in include_keywords if keyword.strip()
        )
        excludes = tuple(
            keyword.strip().casefold() for keyword in exclude_keywords if keyword.strip()
        )
        if any(keyword in searchable for keyword in excludes):
            return False
        return not includes or any(keyword in searchable for keyword in includes)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> bytes | Exception:
        try:
            response = await client.get(url)
            response.raise_for_status()
            if len(response.content) > self._max_feed_bytes:
                raise ToolPolicyViolation("feed_too_large", "RSS response exceeded size limit")
            return response.content
        except (httpx.HTTPError, ToolPolicyViolation) as exc:
            return exc

    @staticmethod
    def _published_at(entry: object) -> datetime | None:
        if not hasattr(entry, "get"):
            return None
        parsed_tuple = entry.get("published_parsed") or entry.get(  # type: ignore[union-attr]
            "updated_parsed"
        )
        if parsed_tuple:
            return datetime.fromtimestamp(calendar.timegm(parsed_tuple), tz=UTC)
        raw_value = entry.get("published") or entry.get("updated")  # type: ignore[union-attr]
        if not raw_value:
            return None
        try:
            parsed = parsedate_to_datetime(str(raw_value))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _normalize_url(url: str) -> str:
        parts = urlsplit(url)
        filtered_query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in TRACKING_QUERY_KEYS
            and not any(key.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
        ]
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(filtered_query), "")
        )


Resolver = Callable[[str], Awaitable[Sequence[str]]]


class ArticleFetchTool:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        resolver: Resolver | None = None,
        timeout_seconds: float = 10,
        max_response_bytes: int = 2_000_000,
        max_article_chars: int = 20_000,
        max_redirects: int = 3,
    ) -> None:
        self._client = client
        self._resolver = resolver or self._resolve_host
        self._timeout_seconds = timeout_seconds
        self._max_response_bytes = max_response_bytes
        self._max_article_chars = max_article_chars
        self._max_redirects = max_redirects

    async def fetch_article(self, arguments: FetchArticleArguments) -> dict[str, object]:
        url = str(arguments.url)
        if self._client is not None:
            return await self._fetch_with_client(self._client, url)
        async with httpx.AsyncClient(
            timeout=self._timeout_seconds,
            headers={"User-Agent": "AI-Daily-Brief/0.1"},
        ) as client:
            return await self._fetch_with_client(client, url)

    async def _fetch_with_client(
        self,
        client: httpx.AsyncClient,
        initial_url: str,
    ) -> dict[str, object]:
        current_url = initial_url
        for _redirect_count in range(self._max_redirects + 1):
            await self._validate_public_url(current_url)
            request = client.build_request("GET", current_url)
            try:
                response = await client.send(request, stream=True, follow_redirects=False)
            except httpx.HTTPError as exc:
                raise ToolFailure("fetch_failed", f"Article request failed: {exc}") from exc
            try:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ToolFailure("invalid_redirect", "Redirect has no Location header")
                    current_url = urljoin(current_url, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                is_supported = content_type.startswith(("text/html", "text/plain"))
                if not is_supported:
                    raise ToolFailure(
                        "unsupported_content_type",
                        f"Unsupported article content type: {content_type or 'unknown'}",
                    )
                body = await self._read_limited(response)
                return self._extract_article(current_url, body, content_type)
            except httpx.HTTPStatusError as exc:
                raise ToolFailure(
                    "fetch_failed",
                    f"Article returned HTTP {exc.response.status_code}",
                ) from exc
            finally:
                await response.aclose()

        raise ToolPolicyViolation("too_many_redirects", "Article exceeded redirect limit")

    async def _read_limited(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > self._max_response_bytes
        ):
            raise ToolPolicyViolation("response_too_large", "Article exceeded size limit")
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._max_response_bytes:
                raise ToolPolicyViolation("response_too_large", "Article exceeded size limit")
            chunks.append(chunk)
        return b"".join(chunks)

    def _extract_article(self, url: str, body: bytes, content_type: str) -> dict[str, object]:
        encoding = "utf-8"
        text = body.decode(encoding, errors="replace")
        if content_type.startswith("text/plain"):
            title = ""
            content = text
        else:
            soup = BeautifulSoup(text, "html.parser")
            for element in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
                element.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            paragraphs = [
                paragraph.get_text(" ", strip=True)
                for paragraph in soup.find_all("p")
                if paragraph.get_text(" ", strip=True)
            ]
            content = "\n\n".join(paragraphs) or soup.get_text(" ", strip=True)
        truncated = len(content) > self._max_article_chars
        return {
            "url": url,
            "title": title[:500],
            "content": content[: self._max_article_chars],
            "truncated": truncated,
        }

    async def _validate_public_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise ToolPolicyViolation("url_denied", "Only HTTP(S) URLs are allowed")
        if parts.username or parts.password:
            raise ToolPolicyViolation("url_denied", "URL credentials are not allowed")
        try:
            port = parts.port
        except ValueError as exc:
            raise ToolPolicyViolation("url_denied", "URL has an invalid port") from exc
        if port not in {None, 80, 443}:
            raise ToolPolicyViolation("url_denied", "Only ports 80 and 443 are allowed")

        addresses: Sequence[str]
        try:
            ipaddress.ip_address(parts.hostname)
            addresses = (parts.hostname,)
        except ValueError:
            try:
                addresses = await self._resolver(parts.hostname)
            except OSError as exc:
                raise ToolFailure("dns_failed", f"Could not resolve article host: {exc}") from exc
        if not addresses:
            raise ToolFailure("dns_failed", "Article host resolved to no addresses")
        for raw_address in addresses:
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError as exc:
                raise ToolFailure("dns_failed", "Resolver returned an invalid address") from exc
            if not address.is_global:
                raise ToolPolicyViolation(
                    "private_network_denied",
                    "Article URL resolves to a non-public network address",
                )

    @staticmethod
    async def _resolve_host(hostname: str) -> Sequence[str]:
        loop = asyncio.get_running_loop()
        records = await loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        return tuple({record[4][0] for record in records})
