#!/usr/bin/env python3
"""Check a deployed Incident Atlas site, API, compiled API origin, and CORS."""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


class ScriptSources(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            attributes = dict(attrs)
            if attributes.get("src"):
                self.sources.append(attributes["src"] or "")


def _origin(value: str, name: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be a public HTTPS origin without credentials or a path")
    return f"https://{parsed.netloc}"


def _request(url: str, *, origin: str | None = None, method: str = "GET") -> tuple[int, str, bytes, dict[str, str]]:
    headers = {"Accept": "application/json, text/html, application/javascript"}
    if origin:
        headers["Origin"] = origin
    if method == "OPTIONS":
        headers.update(
            {
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,idempotency-key",
            }
        )
    request = Request(url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            return (
                response.status,
                response.headers.get("Content-Type", "").lower(),
                response.read(),
                {key.lower(): value for key, value in response.headers.items()},
            )
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code} while requesting {urlsplit(url).path}") from None
    except URLError:
        raise ValueError(f"Could not reach {urlsplit(url).netloc}{urlsplit(url).path}") from None


def _json_get(url: str, site_origin: str) -> dict[str, object]:
    status, content_type, body, headers = _request(url, origin=site_origin)
    if status != 200 or "application/json" not in content_type:
        raise ValueError(f"Expected a JSON 200 response from {urlsplit(url).path}")
    if headers.get("access-control-allow-origin") != site_origin:
        raise ValueError(f"CORS did not allow the configured site origin for {urlsplit(url).path}")
    try:
        value = json.loads(body)
    except json.JSONDecodeError:
        raise ValueError(f"Response from {urlsplit(url).path} was not valid JSON") from None
    if not isinstance(value, dict):
        raise ValueError(f"Response from {urlsplit(url).path} must be a JSON object")
    return value


def check_deployment(api_origin: str, site_origin: str) -> list[str]:
    api = _origin(api_origin, "--api-origin")
    site = _origin(site_origin, "--site-origin")

    _json_get(f"{api}/readyz", site)
    capabilities = _json_get(f"{api}/api/v1/demo-capabilities", site)
    if not isinstance(capabilities.get("live_ai_enabled"), bool):
        raise ValueError("Demo capabilities response is missing the live AI availability flag")
    incidents = _json_get(f"{api}/api/v1/incidents", site)
    if not ("items" in incidents or "incidents" in incidents):
        raise ValueError("Incident catalogue response is missing its items collection")

    site_status, site_type, site_body, _ = _request(site)
    if site_status != 200 or "text/html" not in site_type:
        raise ValueError("Site origin did not return an HTML HTTP 200 response")
    parser = ScriptSources()
    parser.feed(site_body.decode("utf-8", errors="replace"))
    javascript = [source for source in parser.sources if re.search(r"\.js(?:\?|$)", source)]
    if not javascript:
        raise ValueError("Site HTML did not contain a JavaScript application bundle")
    expected_api_base = f"{api}/api/v1"
    bundle_contains_api = False
    for source in javascript:
        bundle_url = urljoin(f"{site}/", source)
        bundle_status, bundle_type, bundle_body, _ = _request(bundle_url)
        if bundle_status != 200 or "javascript" not in bundle_type:
            raise ValueError("Site JavaScript bundle could not be loaded")
        if expected_api_base in bundle_body.decode("utf-8", errors="replace"):
            bundle_contains_api = True
    if not bundle_contains_api:
        raise ValueError(
            "Compiled frontend API URL does not match the configured API origin plus /api/v1"
        )

    status, _, _, headers = _request(
        f"{api}/api/v1/investigations", origin=site, method="OPTIONS"
    )
    if status not in {200, 204} or headers.get("access-control-allow-origin") != site:
        raise ValueError("Browser CORS preflight did not allow the exact frontend origin")
    allowed_methods = headers.get("access-control-allow-methods", "").upper()
    if "POST" not in allowed_methods:
        raise ValueError("Browser CORS preflight did not allow POST")
    return ["API readiness JSON", "API catalogue JSON and CORS", "compiled frontend API URL", "browser CORS preflight"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-origin", required=True, help="Public Render API HTTPS origin")
    parser.add_argument("--site-origin", required=True, help="Exact Netlify HTTPS site origin")
    args = parser.parse_args()
    try:
        checks = check_deployment(args.api_origin, args.site_origin)
    except (OSError, ValueError) as exc:
        print(f"Deployment smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {len(checks)} deployment checks:")
    for check in checks:
        print(f"- {check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
