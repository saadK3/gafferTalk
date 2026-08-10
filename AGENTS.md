# GafferTalk Repository Instructions

## Standing authorization

Codex is authorized to maintain this workspace and the `saadK3/gafferTalk`
GitHub repository for ordinary software-development work. This includes:

- Creating, reading, editing, moving, and organizing repository files
- Installing normal project dependencies
- Running local development servers, tests, linters, type checks, builds, and
  non-production database migrations
- Creating and updating branches and commits
- Pushing non-destructive changes to the remote repository
- Creating and maintaining GitHub issues, labels, milestones, project metadata,
  and pull requests
- Updating documentation, automation, and continuous-integration workflows
- Performing read-only repository and GitHub inspection

Routine actions within this scope do not require separate confirmation from the
repository owner, although the Codex sandbox or GitHub authentication layer may
still require an approval prompt.

## Confirmation required

Codex must obtain explicit confirmation immediately before:

- Force-pushing or rewriting published Git history
- Deleting remote branches, tags, releases, issues, or material project data
- Merging a pull request into `main`
- Publishing a release or deploying to a hosted or production environment
- Creating, exposing, rotating, or deleting credentials and secrets
- Changing billing, paid services, repository ownership, or repository visibility
- Weakening branch protection or required security checks
- Performing materially destructive actions outside ordinary reversible editing

## Engineering workflow

- GitHub Issues are the source of truth for planned work and defects.
- Use short-lived branches created from an up-to-date `main` branch.
- Use Conventional Commits.
- Link pull requests to their corresponding issues.
- Prefer squash merging unless the repository owner decides otherwise.
- Do not commit credentials, private user data, generated dependency folders, or
  local environment files.
- Preserve unrelated user changes in a dirty working tree.
- Treat transfer legality and numerical recommendation logic as deterministic,
  tested backend behavior rather than language-model judgment.
- Make missing FPL state and recommendation assumptions explicit.

## Definition of done

Work is complete only when its acceptance criteria are satisfied, relevant
checks pass, errors and missing-data behavior are considered, and documentation
is updated when contracts or operating procedures change.
