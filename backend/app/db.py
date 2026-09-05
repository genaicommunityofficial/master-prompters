from typing import Any

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.config import settings


def get_client() -> Client:
    """Create a Supabase client bound to the service role.

    The service role is used by the backend for server-side database access and
    queueing. It is NEVER exposed to the frontend.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase URL and service role key are required")

    # Supabase's edge proxy intermittently terminates HTTP/2 keep-alive
    # connections (httpcore.ConnectionTerminated / RemoteProtocolError), which
    # surfaces as sporadic 500s on heavy admin aggregations.
    # Force HTTP/1.1 and add connection retries to make reads/writes resilient.
    transport = httpx.HTTPTransport(retries=2)
    http_client = httpx.Client(http2=False, transport=transport, timeout=60.0)
    options = SyncClientOptions(
        httpx_client=http_client,
        postgrest_client_timeout=60,
    )
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=options,
    )


# Reusable client (stateless; PostgREST requests are idempotent per query).
_client: Client | None = None


def db() -> Client:
    global _client
    if _client is None:
        _client = get_client()
    return _client


REST_PAGE = 1000


def fetch_all(
    table: str,
    select: str,
    *,
    eq: dict[str, Any] | None = None,
    order: str | None = None,
    descending: bool = False,
) -> list[dict[str, Any]]:
    """Range-paginate every matching row past PostgREST's 1000-row cap."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        builder = db().table(table).select(select)
        for key, value in (eq or {}).items():
            builder = builder.eq(key, value)
        if order:
            builder = builder.order(order, desc=descending)
        page = builder.range(offset, offset + REST_PAGE - 1).execute().data or []
        rows.extend(page)
        if len(page) < REST_PAGE:
            break
        offset += REST_PAGE
    return rows


def fetch_in(
    table: str,
    select: str,
    column: str,
    values: list[str],
    *,
    order: str | None = None,
    descending: bool = False,
    page_size: int = 200,
) -> list[dict[str, Any]]:
    """Fetch rows where ``column`` is any of ``values``.

    Values are chunked, and each chunk is range-paginated so a single PostgREST
    request never silently truncates at the 1000-row default cap (e.g. 300
    submissions × 5 responses = 1500 rows).
    """
    rows: list[dict[str, Any]] = []
    for i in range(0, len(values), page_size):
        chunk = values[i : i + page_size]
        offset = 0
        while True:
            builder = db().table(table).select(select).in_(column, chunk)
            if order:
                builder = builder.order(order, desc=descending)
            page = builder.range(offset, offset + REST_PAGE - 1).execute().data or []
            rows.extend(page)
            if len(page) < REST_PAGE:
                break
            offset += REST_PAGE
    return rows


def rpc(procedure: str, params: dict[str, Any] | None = None) -> Any:
    return db().rpc(procedure, params or {}).execute()
