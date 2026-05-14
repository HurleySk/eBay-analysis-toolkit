import atexit
import os
import sys
import threading

from ebay_tracker.server import mcp


def _cleanup_browser():
    from ebay_tracker.scraper import _browser_fetcher
    if _browser_fetcher is not None:
        try:
            _browser_fetcher.stop()
        except Exception:
            pass


def _parent_alive(ppid: int) -> bool:
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, ppid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(ppid, 0)
        return True
    except OSError:
        return False


def _parent_watchdog():
    import time
    ppid = os.getppid()
    while _parent_alive(ppid):
        time.sleep(2)
    os._exit(0)


atexit.register(_cleanup_browser)

_watchdog = threading.Thread(target=_parent_watchdog, daemon=True)
_watchdog.start()

mcp.run()
