import os
import subprocess
import sys
from typing import Optional
import uuid

import requests
from constants import REPO
from github import get_last_build_version, get_release_by_tag

FLARESOLVERR_URL = os.environ.get("FLARESOLVERR_URL", "http://localhost:8191")


class FlareSolverrSession:
    """Manages a FlareSolverr session for cookie reuse across multiple requests."""
    
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self._created = False
    
    def create(self) -> None:
        """Create a new session in FlareSolverr."""
        if self._created:
            return
        
        flaresolverr_endpoint = f"{FLARESOLVERR_URL}/v1"
        payload = {
            "cmd": "sessions.create",
            "session": self.session_id,
        }
        
        response = requests.post(flaresolverr_endpoint, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        if result.get("status") != "ok":
            raise RuntimeError(f"Failed to create FlareSolverr session: {result.get('message', 'Unknown error')}")
        
        self._created = True
        print(f"FlareSolverr session created: {self.session_id}")
    
    def destroy(self) -> None:
        """Destroy the session in FlareSolverr."""
        if not self._created:
            return
        
        flaresolverr_endpoint = f"{FLARESOLVERR_URL}/v1"
        payload = {
            "cmd": "sessions.destroy",
            "session": self.session_id,
        }
        
        try:
            response = requests.post(flaresolverr_endpoint, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            if result.get("status") == "ok":
                print(f"FlareSolverr session destroyed: {self.session_id}")
        except Exception as e:
            print(f"Warning: Failed to destroy FlareSolverr session {self.session_id}: {e}")
        finally:
            self._created = False
    
    def __enter__(self):
        self.create()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.destroy()


def flaresolverr_request(
    url: str, 
    method: str = "GET", 
    headers: Optional[dict] = None, 
    data: Optional[dict] = None,
    session: Optional[FlareSolverrSession] = None,
    return_cookies: bool = False
) -> requests.Response:
    """
    Make a request through FlareSolverr to bypass Cloudflare protection.
    
    Args:
        url: The URL to request
        method: HTTP method (GET or POST)
        headers: Optional headers to send
        data: Optional data for POST requests
        session: Optional FlareSolverrSession for cookie reuse
        return_cookies: If True, return cookies from the solution for use in subsequent requests
    
    Returns:
        requests.Response object with the response
    """
    flaresolverr_endpoint = f"{FLARESOLVERR_URL}/v1"
    
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 60000,
    }
    
    if session is not None:
        if not session._created:
            session.create()
        payload["session"] = session.session_id
    
    if headers:
        payload["headers"] = headers
    
    if method == "POST" and data:
        payload["postData"] = data
    
    response = requests.post(flaresolverr_endpoint, json=payload, timeout=120)
    response.raise_for_status()
    
    result = response.json()
    if result.get("status") != "ok":
        raise RuntimeError(f"FlareSolverr failed: {result.get('message', 'Unknown error')}")
    
    # Check if solution exists and contains required fields
    solution = result.get("solution")
    if solution is None:
        raise RuntimeError(f"FlareSolverr returned no solution: {result}")
    
    status_code = solution.get("status")
    if status_code is None:
        raise RuntimeError(f"FlareSolverr solution missing status: {solution}")
    
    # Create a fake Response object from FlareSolverr result
    fake_response = requests.Response()
    fake_response.status_code = status_code
    fake_response._content = solution["response"].encode("utf-8") if isinstance(solution["response"], str) else solution["response"]
    fake_response.url = url
    fake_response.headers.update(solution.get("headers", {}))
    
    # Store cookies for potential reuse
    if return_cookies and "cookies" in solution:
        fake_response.cookies = solution["cookies"]
    
    return fake_response


def panic(message: str):
    print(message, file=sys.stderr)
    exit(1)


def send_message(message: str, token: str, chat_id: str, thread_id: str):
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"

    data = {
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
        "text": message,
        "message_thread_id": thread_id,
        "chat_id": chat_id,
    }

    response = requests.post(endpoint, data=data)
    response.raise_for_status()


def report_to_telegram(tag: str | None = None):
    tg_token = os.environ["TG_TOKEN"]
    tg_chat_id = os.environ["TG_CHAT_ID"]
    tg_thread_id = os.environ["TG_THREAD_ID"]

    release = get_release_by_tag(REPO, tag) if tag else get_last_build_version(REPO)

    if release is None and tag:
        raise RuntimeError(f"Could not fetch release for tag: {tag}")

    if release is None:
        raise RuntimeError("Could not fetch latest release")

    downloads = [
        f"[{asset.name}]({asset.browser_download_url})" for asset in release.assets
    ]

    message = f"""
[New Update Released !]({release.html_url})

▼ Downloads ▼

{"\n\n".join(downloads)}
"""

    print(message)

    send_message(message, tg_token, tg_chat_id, tg_thread_id)


def download(link, out, headers=None, use_scraper=False, session=None):
    dir_name = os.path.dirname(out)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    if os.path.exists(out):
        print(f"{out} already exists skipping download")
        return

    if use_scraper:
        print(f"Downloading with FlareSolverr: {link}")
        # Use FlareSolverr to bypass Cloudflare and get the actual file content
        response = flaresolverr_request(link, method="GET", headers=headers, session=session)
        response.raise_for_status()
        
        # Check if we got HTML instead of binary content (indicates wrong URL or redirect needed)
        if response.content.startswith(b'<!DOCTYPE') or response.content.startswith(b'<html'):
            raise RuntimeError(f"Downloaded HTML instead of APK file. Got URL: {link}. FlareSolverr final URL: {response.url}")
        
        with open(out, "wb") as f:
            f.write(response.content)
    else:
        session_requests = requests.Session()
        # https://www.slingacademy.com/article/python-requests-module-how-to-download-files-from-urls/#Streaming_Large_Files
        with session_requests.get(link, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(out, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)


def run_command(command: list[str]):
    cmd = subprocess.run(command, capture_output=True, shell=True)

    try:
        cmd.check_returncode()
    except subprocess.CalledProcessError:
        print(cmd.stdout)
        print(cmd.stderr)
        exit(1)


def patch_apk(
    cli: str,
    patches: str,
    apk: str,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    out: str | None = None,
):
    command = [
        "java",
        "-jar",
        cli,
        "patch",
        "-p",
        patches,
        # use j-hc's keystore so we wouldn't need to reinstall
        "--keystore",
        "ks.keystore",
        "--keystore-entry-password",
        "123456789",
        "--keystore-password",
        "123456789",
        "--signer",
        "jhc",
        "--keystore-entry-alias",
        "jhc",
    ]

    if includes is not None:
        for i in includes:
            command.append("-e")
            command.append(i)

    if excludes is not None:
        for e in excludes:
            command.append("-d")
            command.append(e)

    if out is not None:
        command.extend(["--out", out])

    command.append(apk)
    subprocess.run(command).check_returncode()

    if out is not None and not os.path.exists(out):
        raise FileNotFoundError(f"Morphe did not create the expected output: {out}")


def publish_release(tag: str, files: list[str], message: str, title = ""):
    key = os.environ.get("GITHUB_TOKEN")
    if key is None:
        raise Exception("GITHUB_TOKEN is not set")

    command = ["gh", "release", "create", "--latest", tag, "--notes", message, "--title", title]

    if len(files) == 0:
        raise Exception("Files should have atleast one item")

    for file in files:
        command.append(file)

    subprocess.run(command, env=os.environ.copy()).check_returncode()
