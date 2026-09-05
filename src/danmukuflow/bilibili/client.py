import json
import socket
import threading
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from danmukuflow.bilibili.credentials import BilibiliCredentials
from danmukuflow.services.errors import (
    BilibiliDataError,
    BilibiliHttpError,
    BilibiliNetworkError,
    BilibiliTimeoutError,
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict = field(default_factory=dict)
    content: bytes = b""


class RequestRateLimiter:
    def __init__(self, interval, sleeper):
        self.interval = max(0.0, float(interval))
        self.sleeper = sleeper
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self):
        if self.interval <= 0.0:
            return
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval
        if delay > 0.0:
            self.sleeper(delay)


class UrllibTransport:
    def request(self, method, url, params=None, headers=None, timeout=10.0):
        if params:
            url = "{}{}{}".format(url, "&" if "?" in url else "?", urlencode(params))
        request = Request(url, headers=headers or {}, method=method)
        try:
            with urlopen(request, timeout=timeout) as response:
                return HttpResponse(
                    status_code=response.getcode(),
                    headers=dict(response.headers.items()),
                    content=response.read(),
                )
        except HTTPError as exc:
            return HttpResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()) if exc.headers else {},
                content=exc.read(),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise BilibiliTimeoutError("Bilibili request timed out") from exc
        except URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise BilibiliTimeoutError("Bilibili request timed out") from exc
            raise BilibiliNetworkError("Bilibili request failed: {}".format(exc)) from exc


class HttpxTransport:
    def __init__(self, transport=None):
        try:
            import httpx
        except ImportError as exc:
            raise ImportError("httpx is not installed") from exc
        self._httpx = httpx
        self._client = httpx.Client(transport=transport)

    def request(self, method, url, params=None, headers=None, timeout=10.0):
        try:
            response = self._client.request(
                method,
                url,
                params=params,
                headers=headers,
                timeout=timeout,
            )
        except self._httpx.TimeoutException as exc:
            raise BilibiliTimeoutError("Bilibili request timed out") from exc
        except self._httpx.RequestError as exc:
            raise BilibiliNetworkError("Bilibili request failed: {}".format(exc)) from exc
        return HttpResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content=response.content,
        )

    def close(self):
        self._client.close()


class BilibiliClient:
    def __init__(
        self,
        transport=None,
        timeout=10.0,
        max_attempts=3,
        sleeper=None,
        credentials=None,
        request_interval=1.0,
        api_retry_delays=(2.0, 5.0),
    ):
        if transport is None:
            try:
                transport = HttpxTransport()
            except ImportError:
                transport = UrllibTransport()
        elif hasattr(transport, "handle_request") and not hasattr(
            transport, "request"
        ):
            transport = HttpxTransport(transport=transport)
        self.transport = transport
        self.timeout = timeout
        self.max_attempts = max(1, int(max_attempts))
        self.sleeper = sleeper or time.sleep
        self.credentials = credentials or BilibiliCredentials.from_env()
        self.rate_limiter = RequestRateLimiter(request_interval, self.sleeper)
        self.api_retry_delays = tuple(float(item) for item in api_retry_delays)
        self.headers = {
            "User-Agent": "Mozilla/5.0 DanmukuFlow/0.1",
            "Accept": "application/json, application/octet-stream",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self.credentials.cookie_header:
            self.headers["Cookie"] = self.credentials.cookie_header

    def set_cookie(self, cookie):
        """Update the Cookie header for requests made after this call."""
        self.credentials = BilibiliCredentials.from_cookie(cookie)
        self.headers["Cookie"] = self.credentials.cookie_header

    def get_json(self, url, params=None):
        response = self.get(url, params=params)
        try:
            payload = json.loads(response.content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BilibiliDataError("Bilibili response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise BilibiliDataError("Bilibili JSON response must be an object")
        return payload

    def get(self, url, params=None):
        last_error = None
        for attempt in range(self.max_attempts):
            self.rate_limiter.wait()
            try:
                response = self.transport.request(
                    "GET",
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                )
            except (BilibiliTimeoutError, BilibiliNetworkError) as exc:
                last_error = exc
                if attempt + 1 >= self.max_attempts:
                    raise
                self.sleeper(0.25 * (2 ** attempt))
                continue

            if response.status_code in (502, 503, 504):
                last_error = BilibiliHttpError(
                    "temporary Bilibili HTTP error: {}".format(response.status_code)
                )
                if attempt + 1 < self.max_attempts:
                    self.sleeper(0.25 * (2 ** attempt))
                    continue
                raise last_error

            if response.status_code >= 400 and response.status_code != 304:
                raise BilibiliHttpError(
                    "Bilibili HTTP error: {}".format(response.status_code)
                )
            if _response_api_code(response) == -352:
                if attempt + 1 < self.max_attempts:
                    self.sleeper(self._api_retry_delay(attempt))
                    continue
                return response
            return response

        if last_error is not None:
            raise last_error
        raise BilibiliNetworkError("Bilibili request failed")

    def _api_retry_delay(self, attempt):
        if self.api_retry_delays:
            if attempt < len(self.api_retry_delays):
                return self.api_retry_delays[attempt]
            return self.api_retry_delays[-1]
        return 0.0


def _response_api_code(response):
    content_type = next(
        (
            str(value)
            for key, value in response.headers.items()
            if str(key).lower() == "content-type"
        ),
        "",
    )
    if "json" not in content_type.lower() and not response.content.lstrip().startswith(
        b"{"
    ):
        return None
    try:
        payload = json.loads(response.content.decode("utf-8"))
        return int(payload.get("code")) if isinstance(payload, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
