"""Merge every open pull request that CodeRabbit approved and whose checks passed.

Runs on a schedule across whole organisations, so a new repository is covered the
moment it exists: nothing has to be added to it. A pull request is merged only when
all of these hold:

- it isn't a draft, doesn't carry the `no-auto-merge` label and comes from a branch
  of the same repository (never a fork);
- CodeRabbit's latest decision on it is APPROVED, for the commit now at its head
  (or for an earlier commit followed only by merge commits, which CodeRabbit
  reviews without approving again);
- every check run and commit status on that commit finished green;
- GitHub reports it mergeable ("clean"), so branch rules still apply.

Env: GH_TOKEN (a token that can merge in every repository of ORGS), ORGS (comma
separated), DRY_RUN ("1" lists what would merge without merging).
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
REVIEWER = "coderabbitai[bot]"
SKIP_LABEL = "no-auto-merge"
GREEN = {"success", "neutral", "skipped"}
# this workflow's own run must not block the merge it is about to make
SELF_CHECKS = {"merge", "merge-bot"}


def call(method, path, body=None):
    request = urllib.request.Request(
        path if path.startswith("http") else API + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        link = response.headers.get("Link", "")
        return json.loads(response.read() or "null"), link


def pages(path):
    """Every item of a paginated list endpoint."""
    url = API + path + ("&" if "?" in path else "?") + "per_page=100"
    while url:
        data, link = call("GET", url)
        yield from data.get("check_runs", []) if isinstance(data, dict) else data
        url = next(
            (
                part.split(";")[0].strip(" <>")
                for part in link.split(",")
                if 'rel="next"' in part
            ),
            None,
        )


def coderabbit_approved(repo, pr):
    decisions = [
        r
        for r in pages(f"/repos/{repo}/pulls/{pr['number']}/reviews")
        if r["user"]["login"] == REVIEWER
        and r["state"] in ("APPROVED", "CHANGES_REQUESTED")
    ]
    if not decisions:
        return False
    last = decisions[-1]
    if last["state"] != "APPROVED":
        return False
    if last["commit_id"] == pr["head"]["sha"]:
        return True
    return only_merge_commits_since(repo, pr, last["commit_id"])


MAX_MERGES_AFTER_APPROVAL = 20


def only_merge_commits_since(repo, pr, approved_sha):
    """CodeRabbit doesn't re-approve a commit that only merges the base branch in
    ("Already reviewed the last commit"), so its approval still counts when the pull
    request's own history after the approved commit is nothing but merges of the base
    branch: walking first parents from the head reaches the approved commit, and every
    commit on the way is a merge whose other parent is already in the base branch."""
    sha = pr["head"]["sha"]
    base = pr["base"]["ref"]
    try:
        for _ in range(MAX_MERGES_AFTER_APPROVAL):
            if sha == approved_sha:
                return True
            commit, _ = call("GET", f"/repos/{repo}/commits/{sha}")
            parents = [p["sha"] for p in commit["parents"]]
            if len(parents) < 2:
                return False
            # base...merged is "ahead"/"identical" when the merged side is in base
            merged, _ = call("GET", f"/repos/{repo}/compare/{parents[1]}...{base}")
            if merged["status"] not in ("ahead", "identical"):
                return False
            sha = parents[0]
    except urllib.error.HTTPError:
        return False
    # too many merges to follow, or the approved commit isn't on the first-parent path
    return False


def checks_green(repo, sha):
    runs = [
        run
        for run in pages(f"/repos/{repo}/commits/{sha}/check-runs")
        if run["name"] not in SELF_CHECKS
    ]
    if any(
        run["status"] != "completed" or run["conclusion"] not in GREEN for run in runs
    ):
        return False
    status, _ = call("GET", f"/repos/{repo}/commits/{sha}/status")
    return status["total_count"] == 0 or status["state"] == "success"


def merge_method(repo):
    settings, _ = call("GET", f"/repos/{repo}")
    for method, allowed in (
        ("merge", "allow_merge_commit"),
        ("squash", "allow_squash_merge"),
        ("rebase", "allow_rebase_merge"),
    ):
        if settings.get(allowed):
            return method
    return "merge"


def blocker(repo, pr):
    """Why the pull request can't merge yet, or None when it can."""
    if pr["draft"]:
        return "draft"
    if any(label["name"] == SKIP_LABEL for label in pr["labels"]):
        return SKIP_LABEL
    if pr["head"]["repo"] is None or pr["head"]["repo"]["full_name"] != repo:
        return "from a fork"
    if not coderabbit_approved(repo, pr):
        return "not approved by CodeRabbit"
    if not checks_green(repo, pr["head"]["sha"]):
        return "checks not green"
    detail, _ = call("GET", f"/repos/{repo}/pulls/{pr['number']}")
    if detail["mergeable_state"] != "clean":
        return f"GitHub says {detail['mergeable_state']}"
    return None


def main():
    dry_run = os.environ.get("DRY_RUN") == "1"
    merged = failed = 0
    for org in filter(None, (o.strip() for o in os.environ["ORGS"].split(","))):
        for repository in pages(f"/orgs/{org}/repos?type=all"):
            if repository["archived"] or repository["fork"] or repository["disabled"]:
                continue
            repo = repository["full_name"]
            for pr in pages(f"/repos/{repo}/pulls?state=open"):
                try:
                    reason = blocker(repo, pr)
                    if reason:
                        print(f"skip  {repo}#{pr['number']}: {reason}")
                        continue
                    if dry_run:
                        print(f"would merge {repo}#{pr['number']} {pr['title']}")
                        continue
                    call(
                        "PUT",
                        f"/repos/{repo}/pulls/{pr['number']}/merge",
                        {"merge_method": merge_method(repo), "sha": pr["head"]["sha"]},
                    )
                    merged += 1
                    print(f"MERGED {repo}#{pr['number']} {pr['title']}")
                except urllib.error.HTTPError as error:
                    failed += 1
                    print(f"error {repo}#{pr['number']}: HTTP {error.code}")
    print(f"done: {merged} merged, {failed} errors")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
