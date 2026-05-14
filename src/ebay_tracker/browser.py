import random
import threading
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


def parse_proxy_url(proxy_url: str | None) -> dict | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    result = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        result["username"] = parsed.username
        result["password"] = parsed.password or ""
    return result


_STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--no-first-run",
    "--no-default-browser-check",
]

_STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
"""


class BrowserFetcher:
    def __init__(self, proxy_url: str | None, idle_timeout: float = 300.0):
        self._proxy_url = proxy_url
        self._idle_timeout = idle_timeout
        self._playwright = None
        self._browser = None
        self._context = None
        self._idle_timer: threading.Timer | None = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._browser is not None

    def start(self, warmup_url: str | None = "https://www.ebay.com/") -> None:
        with self._lock:
            if self._browser is not None:
                return

            proxy_config = parse_proxy_url(self._proxy_url)
            width = random.randint(1280, 1920)
            height = random.randint(720, 1080)

            self._playwright = sync_playwright().start()
            launch_kwargs = {
                "headless": True,
                "args": _STEALTH_ARGS,
            }
            if proxy_config:
                launch_kwargs["proxy"] = proxy_config

            self._browser = self._playwright.chromium.launch(**launch_kwargs)
            self._context = self._browser.new_context(
                viewport={"width": width, "height": height},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
            )
            self._context.add_init_script(_STEALTH_SCRIPT)

        # Akamai requires session cookies before allowing sold listing pages
        if warmup_url:
            page = self._context.new_page()
            try:
                page.goto(warmup_url, wait_until="commit", timeout=15000)
                page.wait_for_selector("input, a[href]", timeout=10000)
            except Exception:
                page.wait_for_timeout(3000)
            finally:
                page.close()

    def stop(self) -> None:
        with self._lock:
            self._cancel_idle_timer()
            if self._context:
                self._context.close()
                self._context = None
            if self._browser:
                self._browser.close()
                self._browser = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None

    def fetch(self, url: str, wait_selector: str | None = None) -> str:
        if not self.is_running:
            self.start()
        self._reset_idle_timer()

        with self._lock:
            context = self._context
        if context is None:
            self.start()
            with self._lock:
                context = self._context

        page = context.new_page()
        try:
            page.goto(url, wait_until="commit", timeout=30000)
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=20000)
                except Exception:
                    page.wait_for_timeout(3000)
            else:
                page.wait_for_timeout(random.randint(1000, 3000))
            return page.content()
        finally:
            page.close()

    def _reset_idle_timer(self) -> None:
        self._cancel_idle_timer()
        self._idle_timer = threading.Timer(self._idle_timeout, self._idle_shutdown)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_shutdown(self) -> None:
        self.stop()
