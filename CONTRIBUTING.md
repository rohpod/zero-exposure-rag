# Contributing

Zero-Exposure RAG is a small open project: an assistant for bank staff that keeps restricted documents and personal data away from people who are not cleared to see them. These rules keep contributions easy to review. They are short on purpose.

## Ground rules

1. **Synthetic data only.** Never put real personal data in the repository, in a test or in a prompt.
2. **No secrets in git.** Tokens, passwords and API keys stay in environment variables or git-ignored files (`.env`, `app/auth_tokens.local.json`). If you commit one by mistake, tell a maintainer straight away so it can be rotated.
3. **Dependencies are tracked.** Adding a library, model or dataset means adding a row to [THIRD_PARTY.md](THIRD_PARTY.md) with its version, licence and link, and pinning the version in `requirements.txt` (runtime) or `requirements-dev.txt` (tests).
4. **Be kind.** Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Setup

See [docs/development.md](docs/development.md) for the Python environment, the `.env` file, data generation, classifier training, running the server and running the tests.

## Branches

Branch from an up-to-date `main`:

```
git switch main && git pull && git switch -c <type>/<short-name>
```

Types: `feat`, `fix`, `docs`, `chore`, `ci`, `test`, `refactor`. Example: `fix/phone-pattern`.

## Commits

Use [Conventional Commits](https://www.conventionalcommits.org/): `type(scope): summary`, in the imperative, under about 70 characters. Keep commits small.

Scopes: `app`, `guards`, `retrieval`, `data`, `redteam`, `dashboard`, `docs`, `ci`, `docker`.

```
fix(guards): detect +CC-NNN-NNNN phone numbers
feat(redteam): add --shard option to the runner
docs(docs): describe the security model
```

## Pull requests

1. Push your branch and open a pull request with the template. The title is a Conventional Commit.
2. Fill in the task IDs, paste the test output and list any deviations from the plan.
3. Tests are required. Every bug fix needs a test that fails without the fix.
4. Before opening the PR, run `pytest -q`, `python data/generate.py` and `python app/guards/train_injection.py`.
5. One maintainer approval is required. The maintainer squash-merges, and you delete the branch afterwards.

`main` must always work. Never force-push to `main`.

## Decisions

Record decisions that affect more than one person in [docs/decisions.md](docs/decisions.md). Security invariants live in [docs/security-model.md](docs/security-model.md); change them only deliberately and update that document in the same PR.

## Reporting problems

Open an issue with the Bug template. For anything that looks like a security problem, contact a maintainer directly instead of posting details publicly.
