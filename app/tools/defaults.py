from __future__ import annotations

from pathlib import Path

from app.settings import Settings
from app.tools.delivery import DigestDeliveryTool, SendDigestArguments, SMTPConfig
from app.tools.filesystem import (
    FilesystemTools,
    ListDirArguments,
    ReadFileArguments,
    SearchContentArguments,
    WorkspacePolicy,
    WriteFileArguments,
)
from app.tools.news import (
    ArticleFetchTool,
    FetchArticleArguments,
    NewsSearchTool,
    SearchNewsArguments,
)
from app.tools.registry import ToolRegistry
from app.tools.shell import BashArguments, RestrictedShellTool, ShellPolicy
from app.tools.subscription import (
    GetSubscriptionArguments,
    InMemorySubscriptionProvider,
    SubscriptionProvider,
    SubscriptionTool,
)


def build_default_tool_registry(
    settings: Settings,
    *,
    subscriptions: SubscriptionProvider | None = None,
    news: NewsSearchTool | None = None,
    articles: ArticleFetchTool | None = None,
    delivery: DigestDeliveryTool | None = None,
) -> ToolRegistry:
    workspace = WorkspacePolicy(
        root=Path(settings.app_workspace_dir),
        max_read_bytes=settings.tool_max_read_bytes,
        max_write_bytes=settings.tool_max_write_bytes,
    )
    filesystem = FilesystemTools(workspace)
    shell = RestrictedShellTool(
        ShellPolicy(workspace=workspace, max_output_chars=settings.tool_max_output_chars)
    )
    subscription_provider = subscriptions or InMemorySubscriptionProvider()
    subscription_tool = SubscriptionTool(subscription_provider)
    news_tool = news or NewsSearchTool(timeout_seconds=settings.tool_timeout_seconds)
    article_tool = articles or ArticleFetchTool(
        timeout_seconds=settings.tool_timeout_seconds,
        max_response_bytes=settings.fetch_max_response_bytes,
        max_article_chars=settings.fetch_max_article_chars,
    )
    delivery_tool = delivery or DigestDeliveryTool(
        subscriptions=subscription_provider,
        outbox_dir=workspace.root / "outbox",
        smtp=SMTPConfig(
            enabled=settings.smtp_enabled,
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.smtp_from,
            use_tls=settings.smtp_use_tls,
        ),
    )

    registry = ToolRegistry()
    registry.register(
        name="list_dir",
        description="List files and directories inside the agent workspace.",
        arguments_model=ListDirArguments,
        handler=filesystem.list_dir,
    )
    registry.register(
        name="read_file",
        description="Read a UTF-8 text file from the agent workspace.",
        arguments_model=ReadFileArguments,
        handler=filesystem.read_file,
    )
    registry.register(
        name="search_content",
        description="Search UTF-8 workspace files for a case-insensitive keyword.",
        arguments_model=SearchContentArguments,
        handler=filesystem.search_content,
    )
    registry.register(
        name="write_file",
        description="Atomically write a UTF-8 text file inside the agent workspace.",
        arguments_model=WriteFileArguments,
        handler=filesystem.write_file,
    )
    registry.register(
        name="bash",
        description="Run one allowlisted, non-shell command inside the agent workspace.",
        arguments_model=BashArguments,
        handler=shell.bash,
    )
    registry.register(
        name="get_subscription",
        description="Load a user's identity and AI-news subscription preferences.",
        arguments_model=GetSubscriptionArguments,
        handler=subscription_tool.get_subscription,
    )
    registry.register(
        name="search_news",
        description="Search recent RSS news for a query and return normalized sources.",
        arguments_model=SearchNewsArguments,
        handler=news_tool.search_news,
    )
    registry.register(
        name="fetch_article",
        description="Fetch and extract readable text from a public HTTP(S) article URL.",
        arguments_model=FetchArticleArguments,
        handler=article_tool.fetch_article,
    )
    registry.register(
        name="send_digest",
        description="Deliver a completed digest by SMTP or the development outbox.",
        arguments_model=SendDigestArguments,
        handler=delivery_tool.send_digest,
    )
    return registry
