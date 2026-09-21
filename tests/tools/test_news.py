from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from app.tools.errors import ToolPolicyViolation
from app.tools.news import (
    ArticleFetchTool,
    FetchArticleArguments,
    NewsSearchTool,
    SearchNewsArguments,
)


@pytest.mark.asyncio
async def test_news_search_filters_old_items_normalizes_and_deduplicates() -> None:
    recent = format_datetime(datetime.now(UTC) - timedelta(hours=1))
    old = format_datetime(datetime.now(UTC) - timedelta(days=3))
    rss = f"""<?xml version="1.0"?>
    <rss version="2.0"><channel><title>AI News</title>
      <item><title>Fresh Agent News</title>
        <link>https://example.com/fresh?utm_source=rss</link>
        <pubDate>{recent}</pubDate><description>New tool calling release</description></item>
      <item><title>Duplicate</title>
        <link>https://example.com/fresh</link><pubDate>{recent}</pubDate></item>
      <item><title>Old News</title>
        <link>https://example.com/old</link><pubDate>{old}</pubDate></item>
    </channel></rss>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "AI agents"
        return httpx.Response(
            200,
            content=rss.encode(),
            headers={"content-type": "application/rss+xml"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = NewsSearchTool(
            endpoints=("https://search.test/rss?q={query}",),
            client=client,
        )
        result = await tool.search_news(SearchNewsArguments(query="AI agents", hours=24, limit=10))

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Fresh Agent News"  # type: ignore[index]
    assert result["items"][0]["url"] == "https://example.com/fresh"  # type: ignore[index]


@pytest.mark.asyncio
async def test_news_search_understands_atom_iso_dates() -> None:
    published = (datetime.now(UTC) - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    atom = f"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>Research</title>
      <entry><title>Agent Evaluation</title>
        <link href="https://example.com/paper"/>
        <published>{published}</published><summary>Evaluation research</summary></entry>
    </feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=atom.encode())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = NewsSearchTool(endpoints=("https://research.test/?q={query}",), client=client)
        result = await tool.search_news(SearchNewsArguments(query="agent", hours=24))

    assert len(result["items"]) == 1
    assert result["items"][0]["published_at"] is not None  # type: ignore[index]


async def public_resolver(hostname: str) -> tuple[str, ...]:
    assert hostname == "example.com"
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_article_fetch_extracts_readable_html() -> None:
    html = """
    <html><head><title>Agent Release</title><script>secret()</script></head>
    <body><nav>Navigation</nav><p>First paragraph.</p><p>Second paragraph.</p></body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=html, headers={"content-type": "text/html; charset=utf-8"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = ArticleFetchTool(client=client, resolver=public_resolver)
        result = await tool.fetch_article(FetchArticleArguments(url="https://example.com/article"))

    assert result["title"] == "Agent Release"
    assert result["content"] == "First paragraph.\n\nSecond paragraph."
    assert "secret" not in str(result["content"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://10.0.0.1/internal",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/admin",
    ],
)
async def test_article_fetch_rejects_private_and_local_addresses(url: str) -> None:
    tool = ArticleFetchTool()

    with pytest.raises(ToolPolicyViolation) as error:
        await tool.fetch_article(FetchArticleArguments(url=url))

    assert error.value.code == "private_network_denied"


@pytest.mark.asyncio
async def test_article_fetch_revalidates_redirect_target() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = ArticleFetchTool(client=client, resolver=public_resolver)
        with pytest.raises(ToolPolicyViolation) as error:
            await tool.fetch_article(FetchArticleArguments(url="https://example.com/start"))

    assert error.value.code == "private_network_denied"


@pytest.mark.asyncio
async def test_article_fetch_enforces_streamed_response_size_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"12345", headers={"content-type": "text/plain"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tool = ArticleFetchTool(
            client=client,
            resolver=public_resolver,
            max_response_bytes=4,
        )
        with pytest.raises(ToolPolicyViolation) as error:
            await tool.fetch_article(FetchArticleArguments(url="https://example.com/large"))

    assert error.value.code == "response_too_large"
