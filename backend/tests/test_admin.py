from app.config import get_settings
from app.services import admin_auth_service
from app.services import request_log_service


def test_password_verification_toggle(monkeypatch):
    import bcrypt

    settings = get_settings()

    # Disabled when no hash configured.
    monkeypatch.setattr(settings, "admin_password_hash", "")
    assert admin_auth_service.password_matches("anything") is False

    # Enabled: verify against a hash we generate now.
    h = bcrypt.hashpw(b"test-password", bcrypt.gensalt(12)).decode()
    monkeypatch.setattr(settings, "admin_password_hash", h)
    assert admin_auth_service.password_matches("test-password") is True
    assert admin_auth_service.password_matches("wrong") is False


def test_admin_rate_limiting():
    ip = "203.0.113.5"
    for _ in range(10):
        admin_auth_service.record_failed(ip)
    assert admin_auth_service.is_rate_limited(ip)
    admin_auth_service.record_success(ip)
    assert not admin_auth_service.is_rate_limited(ip)


def test_request_log_window_stats():
    request_log_service.reset_window()
    # Seed the sliding window with fixed timestamps.
    import time as _t

    now = _t.time()
    with request_log_service._LOCK:
        request_log_service._WINDOW.append((now, 100))
        request_log_service._WINDOW.append((now - 5, 200))
        request_log_service._WINDOW.append((now - 120, 999))  # outside window

    stats = request_log_service.get_live_stats()
    # Two records within the 60s window -> avg 150ms.
    assert stats["requests_last_60s"] == 2
    assert stats["avg_latency_ms"] == 150.0
    assert stats["window_seconds"] == 60


def test_login_admin_wrong_password(monkeypatch):
    settings = get_settings()
    # No hash configured -> login reports None, not raises.
    monkeypatch.setattr(settings, "admin_password_hash", "")
    assert admin_auth_service.login_admin("admin", "x", "10.0.0.1") is None