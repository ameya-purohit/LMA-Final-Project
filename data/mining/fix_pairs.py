"""Step 1 of the data pipeline: find issue-fix pairs on GitHub (CLAUDE.md §6.9).

The SWE-bench recipe: an issue is the question; the merged pull request that
fixed it, and that PR's own test, are the answer key. A person, not our tool,
decided which lines matter, so the gold cannot favour the mutation check.

Funnel (every drop gets a reason; `data/mining_report.md` shows the counts):
    closed PRs -> merged since the cutoff -> linked to an issue
    -> issue not created by a bot -> changes source AND tests -> at most N source files

Every raw API response is cached under `.cache/github/`, so re-runs make no
API calls. The cache is git-ignored: raw responses never reach the public repo.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import requests

from core.config import REPO_ROOT, load_config
from core.env import require_key

API = "https://api.github.com"
LINK_RE = re.compile(r"\b(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved)\s*:?\s+"
                     r"(?:https://github\.com/[\w.-]+/[\w.-]+/issues/|#)(\d+)", re.IGNORECASE)


class GitHub:
    """Minimal cached GitHub REST client. `session` can be injected for tests."""

    def __init__(self, cache_dir: str | Path, token: str | None = None, session: Any = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.session = session or requests.Session()
        self.sleep = sleep
        self.api_calls = 0

    def _path(self, url: str, params: dict[str, Any]) -> Path:
        key = json.dumps([url, params], sort_keys=True)
        return self.cache_dir / (hashlib.sha256(key.encode()).hexdigest() + ".json")

    def get(self, path: str, **params: Any) -> Any:
        url = f"{API}{path}"
        cached = self._path(url, params)
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        for attempt in range(6):
            self.api_calls += 1
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=60)
            except requests.RequestException:
                self.sleep(2 ** attempt)
                continue
            if r.status_code == 404:
                data: Any = None
                break
            if r.status_code in (403, 429) and r.headers.get("X-RateLimit-Remaining") == "0":
                wait = max(1.0, float(r.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time())
                self.sleep(wait + 1)
                continue
            if r.status_code >= 500 or r.status_code == 429:
                self.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            break
        else:
            raise RuntimeError(f"GitHub request failed after retries: {path}")
        cached.write_text(json.dumps(data), encoding="utf-8")
        return data

    def paginate(self, path: str, **params: Any) -> Iterator[dict[str, Any]]:
        page = 1
        while True:
            items = self.get(path, per_page=100, page=page, **params) or []
            yield from items
            if len(items) < 100:
                return
            page += 1


def linked_issue_numbers(pr: dict[str, Any]) -> list[int]:
    """Issue numbers named by a closing keyword in the PR title or body, in order."""
    text = f"{pr.get('title') or ''}\n{pr.get('body') or ''}"
    seen: list[int] = []
    for m in LINK_RE.finditer(text):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def is_bot(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    login = user.get("login") or ""
    return user.get("type") == "Bot" or login.endswith("[bot]") or login in ("dependabot", "pre-commit-ci")


def classify_files(files: list[dict[str, Any]], package: str, tests_dir: str) -> dict[str, list[str]]:
    """Split changed paths into source (inside the package), test, docs and other files."""
    out: dict[str, list[str]] = {"source": [], "test": [], "docs": [], "other": []}
    for f in files:
        path = f["filename"]
        if path.startswith((f"src/{package}/", f"{package}/")):
            out["source"].append(path)
        elif path.startswith(f"{tests_dir}/"):
            out["test"].append(path)
        elif path.startswith("docs/") or fnmatch.fnmatch(path.lower(), "*.rst") or path.lower().endswith(".md"):
            out["docs"].append(path)
        else:
            out["other"].append(path)
    return out


def find_issue_via_timeline(gh: GitHub, owner: str, repo: str, pr_number: int) -> int | None:
    """Fallback link: an issue, later closed, whose timeline cross-references this PR."""
    for ev in gh.paginate(f"/repos/{owner}/{repo}/issues/{pr_number}/timeline"):
        if ev.get("event") != "cross-referenced":
            continue
        source = (ev.get("source") or {}).get("issue") or {}
        if source and "pull_request" not in source and source.get("state") == "closed" \
                and source.get("repository", {}).get("full_name", f"{owner}/{repo}") == f"{owner}/{repo}":
            return int(source["number"])
    return None


def mine_library(gh: GitHub, lib: str, spec: dict[str, Any], *, merged_since: str, max_source_files: int,
                 drop: Callable[[dict[str, Any]], None], counts: dict[str, int]) -> list[dict[str, Any]]:
    """Run the funnel for one library; return candidate pairs. `drop` receives each dropped item."""
    owner, repo = spec["owner"], spec["repo"]
    pairs: list[dict[str, Any]] = []

    def dropped(pr_number: int, reason: str, **extra: Any) -> None:
        drop({"library": lib, "pr": pr_number, "stage": "mining", "reason": reason, **extra})

    for pr in gh.paginate(f"/repos/{owner}/{repo}/pulls", state="closed", sort="created", direction="desc"):
        counts["closed_prs"] = counts.get("closed_prs", 0) + 1
        n = pr["number"]
        merged_at = pr.get("merged_at")
        if not merged_at:
            continue  # closed without merging: never a candidate, not worth a drop record
        counts["merged_prs_all_time"] = counts.get("merged_prs_all_time", 0) + 1
        if merged_at < merged_since:
            continue  # before the cutoff (older versions need older interpreters)
        counts["merged_prs"] = counts.get("merged_prs", 0) + 1

        issue, link_kind = None, None
        for number in linked_issue_numbers(pr):
            candidate = gh.get(f"/repos/{owner}/{repo}/issues/{number}")
            if candidate and "pull_request" not in candidate:
                issue, link_kind = candidate, "keyword"
                break
        if issue is None:
            number = find_issue_via_timeline(gh, owner, repo, n)
            if number is not None:
                candidate = gh.get(f"/repos/{owner}/{repo}/issues/{number}")
                if candidate and "pull_request" not in candidate:
                    issue, link_kind = candidate, "timeline"
        if issue is None:
            dropped(n, "no_linked_issue")
            continue
        counts["linked_issue"] = counts.get("linked_issue", 0) + 1

        if is_bot(issue.get("user")):
            dropped(n, "issue_by_bot", issue=issue["number"])
            continue
        counts["issue_not_bot"] = counts.get("issue_not_bot", 0) + 1

        files = list(gh.paginate(f"/repos/{owner}/{repo}/pulls/{n}/files"))
        groups = classify_files(files, spec["package"], spec["tests_dir"])
        if not groups["source"]:
            dropped(n, "no_source_change", issue=issue["number"])
            continue
        if not groups["test"]:
            dropped(n, "no_test_change", issue=issue["number"])
            continue
        counts["source_and_test"] = counts.get("source_and_test", 0) + 1
        if len(groups["source"]) > max_source_files:
            dropped(n, "too_many_source_files", issue=issue["number"], source_files=len(groups["source"]))
            continue
        counts["candidates"] = counts.get("candidates", 0) + 1
        # The list endpoint omits the commit count, which freeze.py needs for rebase merges.
        detail = gh.get(f"/repos/{owner}/{repo}/pulls/{n}") or {}
        pairs.append({
            "library": lib, "owner": owner, "repo": repo, "package": spec["package"], "tests_dir": spec["tests_dir"],
            "issue_number": issue["number"], "issue_url": issue["html_url"], "created_at": issue["created_at"],
            "issue_title": issue.get("title") or "", "issue_body": issue.get("body") or "",
            "pr_number": n, "pr_url": pr["html_url"], "pr_title": pr.get("title") or "",
            "merged_at": merged_at, "merge_commit": pr["merge_commit_sha"], "base_ref": pr["base"]["ref"],
            "base_sha": pr["base"]["sha"], "pr_commits": detail.get("commits"), "link_kind": link_kind,
            "source_files": groups["source"], "test_files": groups["test"], "docs_files": groups["docs"],
        })
    return pairs


def mine(libraries: list[str] | None = None, config: dict[str, Any] | None = None,
         gh: GitHub | None = None) -> dict[str, Any]:
    """Mine the configured libraries. Returns {"pairs", "dropped", "counts": {lib: {...}}}."""
    cfg = config or load_config()
    data_cfg = cfg["data"]
    gh = gh or GitHub(REPO_ROOT / cfg["paths"]["github_cache"], token=require_key("GITHUB_TOKEN"))
    pairs: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for lib in libraries or data_cfg["active_libraries"]:
        counts[lib] = {}
        pairs += mine_library(gh, lib, data_cfg["libraries"][lib], merged_since=data_cfg["merged_since"],
                              max_source_files=data_cfg["max_source_files"], drop=dropped.append, counts=counts[lib])
    return {"pairs": pairs, "dropped": dropped, "counts": counts, "api_calls": gh.api_calls}
