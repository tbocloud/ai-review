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

Pull requests from forks get no secrets, so they are left to people. If Kimi is down, the review says so and passes.

## Changing the reviewer

Callers use the `v1` tag. Change `ai_review.py` through a pull request here, then move the tag: `git tag -f v1 && git push -f origin v1`.
