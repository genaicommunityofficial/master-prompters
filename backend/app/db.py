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
    # surfaces as sporadic 500s on heavy queries (e.g. /admin/test/status).
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


def rpc(procedure: str, params: dict[str, Any] | None = None) -> Any:
    return db().rpc(procedure, params or {}).execute()
