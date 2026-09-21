from app.agent.types import TraceEvent, TraceEventType
from app.db.models import DigestStatus
from app.services.digest import DigestService


def test_digest_extraction_collects_sources_and_delivery_state() -> None:
    trace = (
        TraceEvent(
            sequence=1,
            event_type=TraceEventType.TOOL_COMPLETED,
            tool_name="search_news",
            tool_call_id="search-1",
            data={
                "success": True,
                "output": {
                    "items": [
                        {
                            "url": "https://example.com/agent",
                            "title": "Agent Release",
                            "source": "Example",
                            "published_at": "2026-09-21T00:00:00+00:00",
                        }
                    ]
                },
            },
        ),
        TraceEvent(
            sequence=2,
            event_type=TraceEventType.TOOL_STARTED,
            tool_name="send_digest",
            tool_call_id="send-1",
            data={"arguments": {"subject": "Custom Brief", "content": "Brief body"}},
        ),
        TraceEvent(
            sequence=3,
            event_type=TraceEventType.TOOL_COMPLETED,
            tool_name="send_digest",
            tool_call_id="send-1",
            data={"success": True, "output": {"mode": "outbox", "delivered": False}},
        ),
    )

    result = DigestService._digest_from_trace("Final status", trace)

    assert result["title"] == "Custom Brief"
    assert result["content"] == "Brief body"
    assert result["status"] == DigestStatus.OUTBOX
    assert result["sources"] == [
        {
            "url": "https://example.com/agent",
            "title": "Agent Release",
            "source": "Example",
            "published_at": "2026-09-21T00:00:00+00:00",
        }
    ]
