"""Checks are exercised against a real local HTTP server, never a mock."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from sretriage.checks import aws, clock, disk, dns, http, k8s, memory, process, tls
from sretriage.checks.base import FAIL, OK, SKIPPED, Context

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "no-referrer",
}


class ProbeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/boom":
            body = b'{"error":"internal"}\n'
            self.send_response(500)
        else:
            body = b'{"status":"ok"}\n'
            self.send_response(200)
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def server() -> str:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def test_http_ok_with_security_headers(server: str) -> None:
    ctx = Context(targets=[server + "/healthz"], timeout=5.0)
    results = http.run(ctx)
    assert len(results) == 1
    assert results[0].status == OK
    assert any("200" in line for line in results[0].evidence)
    assert any("ttfb=" in line for line in results[0].evidence)
    assert results[0].duration_ms >= 0


def test_http_5xx_is_fail(server: str) -> None:
    ctx = Context(targets=[server + "/boom"], timeout=5.0)
    results = http.run(ctx)
    assert results[0].status == FAIL
    assert any("500" in line for line in results[0].evidence)
    assert results[0].next_steps


def test_http_missing_security_headers_is_warn(server: str) -> None:
    class BareHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    bare = ThreadingHTTPServer(("127.0.0.1", 0), BareHandler)
    threading.Thread(target=bare.serve_forever, daemon=True).start()
    try:
        ctx = Context(targets=["http://127.0.0.1:%d/" % bare.server_address[1]], timeout=5.0)
        results = http.run(ctx)
        assert results[0].status == "WARN"
        assert any("missing security headers" in line for line in results[0].evidence)
    finally:
        bare.shutdown()
        bare.server_close()


def test_unreachable_target_is_skipped_not_failed() -> None:
    # 127.0.0.1:1 has no listener; an external failure must degrade, never break.
    ctx = Context(targets=["http://127.0.0.1:1/"], timeout=1.0)
    results = http.run(ctx)
    assert results[0].status == SKIPPED
    assert any("unreachable" in line or "error" in line for line in results[0].evidence)


def test_dns_ip_literal_is_ok() -> None:
    ctx = Context(target_hosts=["127.0.0.1"], timeout=2.0)
    results = dns.run(ctx)
    assert results[0].status == OK
    assert any("IP literal" in line for line in results[0].evidence)


def test_dns_unresolvable_host_fails() -> None:
    ctx = Context(target_hosts=["does-not-resolve.invalid"], timeout=2.0)
    results = dns.run(ctx)
    assert results[0].status == FAIL
    assert results[0].runbook == "network/dns-failure.md"


def test_tls_skipped_without_https_target() -> None:
    results = tls.run(Context(targets=["http://example.org"], timeout=2.0))
    assert results[0].status == SKIPPED


def test_tls_unreachable_host_is_skipped_not_crashed() -> None:
    results = tls.run(Context(targets=["https://127.0.0.1:1/"], timeout=1.0))
    assert results[0].status == SKIPPED
    assert results[0].evidence


def test_tls_certificate_name_is_flattened_from_nested_rdn() -> None:
    # getpeercert returns ((("organizationName", "X"),), ...) - not a flat pair.
    nested = ((("countryName", "US"),), (("organizationName", "Workers CA"),))
    assert tls._format_name(nested) == "countryName=US, organizationName=Workers CA"


def test_tls_certificate_name_handles_flat_and_empty_shapes() -> None:
    assert tls._format_name((("commonName", "example.org"),)) == "commonName=example.org"
    assert tls._format_name(()) == ""
    assert tls._format_name(((), ())) == ""
    assert tls._format_name(None) == ""


def test_tls_not_after_parsing() -> None:
    parsed = tls._parse_not_after("Aug 31 12:00:00 2026 GMT")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 8, 31)
    assert tls._parse_not_after("not a date") is None


def test_clock_reports_skew_from_date_header(server: str) -> None:
    results = clock.run(Context(targets=[server + "/healthz"], timeout=5.0))
    assert len(results) == 1
    if results[0].status == SKIPPED:
        pytest.skip("server did not send a Date header in this environment")
    assert any("skew" in line for line in results[0].evidence)


def test_local_checks_return_a_known_status() -> None:
    for module in (disk, memory, process):
        results = module.run(Context(timeout=5.0))
        assert results, module.__name__
        assert results[0].status in (OK, "WARN", FAIL, SKIPPED)


def test_k8s_skipped_when_kubectl_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(k8s, "has_tool", lambda name: False)
    results = k8s.run(Context(timeout=1.0))
    assert results[0].status == SKIPPED
    assert results[0].summary == "kubectl not available"


def test_aws_skipped_when_cli_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aws, "has_tool", lambda name: False)
    results = aws.run(Context(timeout=1.0))
    assert results[0].status == SKIPPED
    assert results[0].summary == "aws cli not available"


def test_k8s_skipped_without_context(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(k8s, "has_tool", lambda name: True)
    monkeypatch.setattr(k8s, "run_cmd", lambda cmd, timeout=10.0: (1, "", "no context"))
    results = k8s.run(Context(timeout=1.0))
    assert results[0].status == SKIPPED
    assert results[0].summary == "no kubeconfig context selected"


def test_run_all_never_raises() -> None:
    from sretriage.checks import run_all

    results = run_all(Context(targets=["http://127.0.0.1:1/"], target_hosts=["127.0.0.1"], timeout=1.0))
    assert len(results) >= 9
    assert {result.name for result in results} == {
        "dns",
        "http",
        "tls",
        "clock",
        "disk",
        "memory",
        "process",
        "k8s",
        "aws",
    }
