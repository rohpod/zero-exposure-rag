# Contributing

Four of us are building this project in parallel during the IBM Z Datathon 2026. These rules keep us from breaking each other's work. They are short on purpose, so read them once.

## Ground rules

1. **Originality.** All project code is written by the team during the event window (17 to 18 October 2026). Libraries, models and public datasets are allowed, and each one goes into [THIRD_PARTY.md](THIRD_PARTY.md) as soon as we use it.
2. **Synthetic data only.** Never put real personal data in the repository, on the VM or in a test.
3. **No secrets in git.** Tokens, passwords, SSH keys and API keys stay in environment variables or git-ignored local config files. If you commit one by mistake, tell the group straight away so it can be rotated.
4. **No hosted LLM APIs.** The model runs on the LinuxONE VM so that no data leaves the platform.
5. **Be kind.** Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting set up

1. Accept the repository invite and clone the repo.
2. Set your git identity. Use the email address verified on your GitHub account so your commits are credited to you.

   ```
   git config user.name "Your Name"
   git config user.email "you@example.com"
   ```

3. Read [docs/PROJECT.docx](docs/PROJECT.docx) and [docs/PLAN.docx](docs/PLAN.docx).
4. Confirm you can SSH into the team VM and clone the repo there.

## Workflow

1. Pick an issue, or create one from the Task template, and assign it to yourself.
2. Create a branch from an up-to-date `main`.
3. Commit small and often.
4. Push the branch and open a pull request using the template.
5. Your review partner reviews it. When the checks in the template are met, they squash and merge.
6. Delete the branch after merging.

`main` must always run. Never force-push to `main`.

### Branch names

```
stage<N>/<short-description>
```

Examples: `stage1/pii-detector`, `stage2/swap-real-retriever`, `stage4/evidence-screenshots`.

### Commit messages

```
stage<N> <component>: <imperative summary>
```

Components: `platform`, `data`, `retrieval`, `guards`, `redteam`, `dashboard`, `docs`, `infra`.

Examples:

```
stage1 guards: add Luhn check for card numbers
stage1 retrieval: filter by clearance before ranking
stage3 redteam: score results by category
```

Keep the summary under about 70 characters. Add a body if the reason is not obvious.

### Pull requests

- One purpose per pull request. Keep them small enough to review quickly.
- Fill in the template. Say how you tested it.
- Do not mix unrelated changes. If you spot a separate problem, open an issue for it.
- Interface changes (anything in the shared interfaces section of the plan) must be announced to the whole group before the change is merged, and the plan must be updated in the same pull request.

### Reviews

| Author's track | Review partner |
|---|---|
| Platform (Member 1) | Member 2 |
| Data and retrieval (Member 2) | Member 1 |
| Guards (Member 3) | Member 4 |
| Red team and product (Member 4) | Member 3 |

The reviewer checks that the tests pass, the interface is respected, no secrets or real data are included and THIRD_PARTY.md is updated if a new resource was added. Review for correctness first. Style comes second.

If your review partner is busy or blocked, ask anyone else on the team. Do not leave a pull request waiting.

## Testing

- Write tests alongside your code under `tests/<component>/` and run them with pytest before opening a pull request.
- Anything that produces a trained model file or a number we will quote must be run on the VM, which is s390x and big-endian.
- Each stage has its own tests listed in the plan. A track is finished only when they pass.

## Dependencies and third-party resources

- Add every new library, model or dataset to [THIRD_PARTY.md](THIRD_PARTY.md) with its version, licence and link.
- Pin versions in `requirements.txt` once we start using a package.
- Check the licence of any dataset before using it.
- If a package does not install on s390x, say so in the group and use the fallback from the plan.

## Decisions and environment notes

- Record decisions that affect more than one person in [docs/decisions.md](docs/decisions.md).
- Record facts about the VM in [docs/environment.md](docs/environment.md). Facts only, no guesses.

## Reporting problems

Open an issue using the Bug template. If you are blocked, also say so in the group chat. Do not wait quietly.

## Definition of done

A task is done when the code is merged to `main`, its tests pass, its docs are updated and it works on the VM.
