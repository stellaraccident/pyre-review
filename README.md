# pyre-review

Lightweight, local, browser-based code review for git topic branches.

pyre-review diffs a topic branch against a base, generates a syntax-highlighted
review UI, and persists comments and verdicts in `git notes`. It integrates
with [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`) for
issue-tracker-driven review workflows, but works fine standalone.

## Install

```bash
pip install -e .          # editable install
pip install -e '.[test]'  # with test dependencies
```

Requires Python 3.10+. The only runtime dependency is
[Pygments](https://pygments.org/) for syntax highlighting.

## Quick start

```bash
# Open a browser-based review of topic/foo against main
pyre-review topic/foo main

# Same thing, but target a repo that isn't cwd
pyre-review -C /path/to/repo topic/foo main

# Write a static HTML file instead of launching a server
pyre-review topic/foo main --static review.html
```

## Commands

### `pyre-review <topic> <base>` (default)

Generate a review and open it in the browser. A localhost HTTP server handles
comment and verdict persistence via `git notes`.

| Flag | Description |
|------|-------------|
| `-C`, `--repo PATH` | Git repository path (default: cwd) |
| `--static FILE` | Write self-contained HTML instead of starting a server |
| `--port PORT` | Server port (default: auto) |
| `--review-bead ID` | Link to a beads issue; verdict updates the bead |
| `--bead-tool br\|bd` | Beads CLI to use (default: `br`) |
| `--assignee NAME` | Reassign bead to this actor on verdict (default: `coder`) |

### `pyre-review comments <topic>`

Dump review comments as JSON to stdout.

| Flag | Description |
|------|-------------|
| `--unresolved` | Only show unresolved comments |

### `pyre-review resolve <topic> <comment_id>`

Mark a comment as resolved.

### `pyre-review add-comment <topic>`

Add a comment programmatically (useful from scripts and agents).

| Flag | Description |
|------|-------------|
| `--file FILE` | File path (required) |
| `--line LINE` | Line number (required) |
| `--body TEXT` | Comment body (required) |
| `--side left\|right` | Which side of the diff (default: `right`) |

### `pyre-review request <topic> <base>`

Create a beads issue requesting human review.

| Flag | Description |
|------|-------------|
| `--bead-tool br\|bd` | Beads CLI (default: `br`) |
| `--assignee NAME` | Reviewer actor (default: `human-review`) |
| `-p`, `--priority 0-4` | Bead priority (default: `1`) |
| `--bead-db PATH` | Custom beads database path |

## How it works

### Review UI

The generated HTML page is fully self-contained (no CDN dependencies).
It includes:

- File tree with change-type badges (A/M/D) and comment indicators
- Syntax-highlighted diff with full context
- Inline comment threads with resolve/unresolve
- Verdict dialog (approve / request changes) with summary field
- Keyboard navigation: `j`/`k` files, `n`/`N` comments, `]`/`[` changes

### Storage

Comments and verdicts are stored in `git notes` under the ref
`refs/notes/pyre-review`. Each entry is a JSON object with fields like
`id`, `type`, `author`, `timestamp`, `file`, `line`, `body`, `resolved`.

The author is determined from the `BR_ACTOR` environment variable, falling
back to `git config user.name`.

### Beads integration

pyre-review implements a single-bead review lifecycle:

1. **Request** (`pyre-review request`): creates a bead assigned to
   `@human-review`. The bead description contains the exact command to run.

2. **Review**: the reviewer runs the command from the bead description.
   The `--review-bead` flag links the session to the bead.

3. **Verdict**: on approve or request-changes, pyre-review updates the
   same bead -- title, description (with unresolved comments), and
   reassigns to `@coder`.

4. **Follow-up**: the coder picks up the bead via `br ready`, addresses
   comments, and closes it.

No child beads, no dependency chains. One bead tracks the full lifecycle.

## Agent integration

Agents interact with pyre-review through the CLI. Common patterns:

```bash
# Agent requests review after finishing a topic
pyre-review -C /path/to/repo request topic/foo main

# Agent reads review feedback from a bead
br show <bead-id>   # description contains verdict + comments

# Agent adds a comment programmatically
pyre-review -C /path/to/repo add-comment topic/foo \
  --file src/foo.cpp --line 42 --body "This needs a null check"

# Agent reads unresolved comments as JSON
pyre-review -C /path/to/repo comments topic/foo --unresolved
```

## Testing

```bash
pytest                # run all tests
pytest -x             # stop on first failure
pytest tests/test_beads.py  # run one module
```

Tests create temporary git repos with topic branches and exercise the
full pipeline: diff parsing, HTML generation, server API, and beads
integration (mocked).

## Architecture

```
pyre_review/
  cli.py       — Argument parsing and command dispatch
  git_ops.py   — Git diff, log, notes read/write
  generate.py  — Self-contained HTML generation with Pygments
  server.py    — Localhost HTTP server for interactive reviews
  beads.py     — Beads issue tracker integration
```

## License

TBD
