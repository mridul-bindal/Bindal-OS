"""Robots-aware, size-bounded HTTP adapter; redirects receive the same checks."""
import time
from urllib.parse import urlsplit

import httpx
from protego import Protego

from .fetch import CrawlError
from .urls import allowed_url, domain_of, normalize_url


class PolicySkipped(CrawlError):
    def __init__(self, reason, url):
        self.reason = reason
        super().__init__(f"{reason}: {url}")


class RequestBudgetExceeded(CrawlError):
    pass


class PolicyClient:
    def __init__(self, client, config, *, sleep=time.sleep, clock=time.monotonic):
        self.client, self.config = client, config
        self.sleep, self.clock = sleep, clock
        self.last_request, self.robots = {}, {}
        self.last_response = None
        self.requests = 0
        self.before_request = None

    def _request(self, url, delay):
        if self.requests >= self.config.max_requests:
            raise RequestBudgetExceeded("HTTP request safety limit reached")
        if self.before_request is not None:
            self.before_request()
        domain = domain_of(url)
        remaining = self.last_request.get(domain, -float("inf")) + delay - self.clock()
        if remaining > 0:
            self.sleep(remaining)
        self.last_request[domain] = self.clock()
        self.requests += 1
        with self.client.stream("GET", url, timeout=self.config.timeout, follow_redirects=False,
                                headers={"User-Agent": self.config.user_agent,
                                         "Accept": "text/html,application/xhtml+xml,application/xml,text/plain,*/*;q=0.1"}) as response:
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self.config.max_response_bytes:
                    raise CrawlError("Response exceeds max_response_bytes")
                chunks.append(chunk)
            # Bytes are already HTTP-decompressed; prevent httpx decoding them twice.
            headers = dict(response.headers)
            headers.pop("content-encoding", None)
            return httpx.Response(response.status_code, headers=headers, content=b"".join(chunks), request=response.request)

    def robots_for(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            robot_url = origin + "/robots.txt"
            try:
                for _ in range(6):
                    response = self._request(robot_url, self.config.request_delay)
                    if response.is_redirect:
                        target = normalize_url(response.headers.get("location", ""), robot_url)
                        # Fail closed on cross-origin robots redirects.
                        if urlsplit(target)[:2] != parts[:2]:
                            raise CrawlError("Cross-origin robots redirect")
                        robot_url = target
                        continue
                    if response.status_code in (404, 410):
                        rules = Protego.parse("")
                    elif response.is_success:
                        if "<html" in response.text[:500].lower():
                            raise CrawlError("HTML returned instead of robots.txt")
                        rules = Protego.parse(response.text)
                    else:
                        raise CrawlError(f"robots HTTP {response.status_code}")
                    self.robots[origin] = (rules, None)
                    break
                else:
                    raise CrawlError("Too many robots redirects")
            except RequestBudgetExceeded:
                raise
            except (httpx.HTTPError, CrawlError, ValueError) as exc:
                self.robots[origin] = (None, str(exc))
        rules, error = self.robots[origin]
        if error:
            raise PolicySkipped("robots_unavailable", url)
        return rules

    def check(self, url):
        if not allowed_url(url, self.config.allowed_domains):
            raise PolicySkipped("domain", url)
        rules = self.robots_for(url)
        if not rules.can_fetch(url, self.config.user_agent):
            raise PolicySkipped("robots", url)
        return rules

    def get(self, url, **_kwargs):
        url = normalize_url(url)
        self.last_response = None
        visited = set()
        for _ in range(11):
            if url in visited:
                raise CrawlError("Redirect loop")
            visited.add(url)
            rules = self.check(url)
            delay = max(self.config.request_delay, rules.crawl_delay(self.config.user_agent) or 0)
            rate = rules.request_rate(self.config.user_agent)
            if rate:
                delay = max(delay, rate.seconds / rate.requests)
            response = self._request(url, delay)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise CrawlError("Redirect missing Location header")
                url = normalize_url(location, url)
                continue
            self.last_response = response
            return response
        raise CrawlError("Too many redirects")
