from typing import Any

from supabase import Client, create_client

from app.config import settings


def get_client() -> Client:
    """Create a Supabase client bound to the service role.

    The service role is used by the backend for server-side database access and
    queueing. It is NEVER exposed to the frontend.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase URL and service role key are required")
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
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
