# TBO AI Review

Kimi reviews every pull request in TBO's repositories and posts one comment, updated on every push. Blockers fail the `ai-review / review` check; warnings and notes don't. A person still approves the merge.

## How a repository uses it

Copy [`caller.yml`](caller.yml) to `.github/workflows/ai-review.yml` in the repository. The default branch's ruleset requires a pull request, one approval and the `ai-review / review` check.

The review reads the repository's `AGENTS.md` (or `CLAUDE.md`) as its rules, if there is one.

## Setup (once per GitHub organisation)

```sh
gh secret set KIMI_API_KEY --org tbocloud --visibility all
gh secret set KIMI_API_KEY --org teambackoffice --visibility all
```

Until the secret exists the check passes with a notice, so nothing is blocked. Optional organisation variables: `AI_REVIEW_MODEL` (default `kimi-k2.6`) and `AI_REVIEW_BASE_URL` (default `https://api.moonshot.ai/v1`).

Pull requests from forks get no secrets, so they are left to people. Drafts are reviewed once they are marked ready. If Kimi is down, the review says so and passes.

## Merge bot (CodeRabbit approves, the bot merges)

`.github/workflows/merge-bot.yml` runs `merge_bot.py` every 10 minutes over every repository of tbocloud and teambackoffice, so a new repository is covered without adding anything to it. It merges an open pull request only when:

- it isn't a draft, comes from a branch of the same repository (not a fork) and has no `no-auto-merge` label;
- CodeRabbit's latest decision is **Approved**, for the commit now at the head;
- every check run and commit status on that commit is green;
- GitHub says it is mergeable (`clean`), so each repository's own branch rules still apply.

It uses the repository's allowed merge method (merge commit first).

**Setup:** add a token that can merge in both organisations as the `MERGE_BOT_TOKEN` secret of this repository. Until it exists, runs do nothing. Use a classic token with the `repo` scope, or better, a GitHub App installed on both organisations with Contents, Pull requests, Checks and Commit statuses permissions.

**Stop it for one pull request:** add the `no-auto-merge` label. **Try it safely:** Actions → merge-bot → Run workflow; "dry run" is ticked by default and only lists what would merge.

## Changing the reviewer

Callers use the `v1` tag. Change `ai_review.py` through a pull request here, then move the tag: `git tag -f v1 && git push -f origin v1`.
