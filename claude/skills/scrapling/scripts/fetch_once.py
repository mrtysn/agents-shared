#!/usr/bin/env python3
# DESC: One Scrapling fetch per process — saves body and metadata so parsing iterates offline
"""Fetch a URL exactly once with a Scrapling fetcher and save the response to disk.

usage: fetch_once.py <plain|dynamic|stealthy> <url> <out-dir> [--name NAME] [--no-proxy-env]

Writes <out-dir>/<name>.html and <out-dir>/<name>.meta.json (status, headers, final URL,
redirect chain, elapsed). Exit 0 on a 2xx/3xx, 3 on any 4xx/5xx (never retries), 2 on an exception.
Browser fetchers ignore HTTPS_PROXY on their own; this script passes it explicitly unless --no-proxy-env.
"""
import argparse, json, os, pathlib, re, sys, time, logging

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("fetcher", choices=["plain", "dynamic", "stealthy"])
ap.add_argument("url")
ap.add_argument("out_dir", type=pathlib.Path)
ap.add_argument("--name", help="basename for the saved files (default: derived from the URL)")
ap.add_argument("--no-proxy-env", action="store_true", help="do not hand HTTPS_PROXY to the browser fetchers")
ap.add_argument("--wait-selector", help="browser fetchers: CSS selector to wait for before capturing")
ap.add_argument("--timeout", type=float, default=30, help="seconds (default 30)")
a = ap.parse_args()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
a.out_dir.mkdir(parents=True, exist_ok=True)
name = a.name or re.sub(r"[^A-Za-z0-9._-]+", "_", a.url.split("://", 1)[-1]).strip("_")[:120]
proxy_env = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
browser_kw = {"headless": True, "disable_resources": True, "timeout": int(a.timeout * 1000)}
if a.wait_selector:
    browser_kw["wait_selector"] = a.wait_selector
if proxy_env and not a.no_proxy_env:
    browser_kw["proxy"] = proxy_env

t0 = time.time()
try:
    if a.fetcher == "plain":
        from scrapling.fetchers import Fetcher
        resp = Fetcher.get(a.url, impersonate="chrome", stealthy_headers=True, timeout=a.timeout, retries=0)
    elif a.fetcher == "dynamic":
        from scrapling.fetchers import DynamicFetcher
        resp = DynamicFetcher.fetch(a.url, **browser_kw)
    else:
        from scrapling.fetchers import StealthyFetcher
        resp = StealthyFetcher.fetch(a.url, block_webrtc=True, solve_cloudflare=False, **browser_kw)
except Exception as e:
    (a.out_dir / f"{name}.error.txt").write_text(f"{type(e).__name__}: {e}\n")
    print(f"ERROR {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(2)

meta = {
    "fetcher": a.fetcher, "url": a.url, "final_url": getattr(resp, "url", None), "status": resp.status,
    "reason": getattr(resp, "reason", None), "elapsed_s": round(time.time() - t0, 2),
    "history": [getattr(h, "status", None) for h in (getattr(resp, "history", None) or [])],
    "headers": dict(resp.headers or {}), "encoding": getattr(resp, "encoding", None),
    "body_len": len(resp.body or b""), "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
}
(a.out_dir / f"{name}.html").write_bytes(resp.body or b"")
(a.out_dir / f"{name}.meta.json").write_text(json.dumps(meta, indent=1, default=str))
print(json.dumps({k: meta[k] for k in ("fetcher", "status", "elapsed_s", "body_len", "final_url")}))
print(f"saved: {a.out_dir / name}.html")
if resp.status >= 400:
    print(f"refused ({resp.status}); stop here, do not retry", file=sys.stderr)
    sys.exit(3)
