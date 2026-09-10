from pathlib import Path

root = Path('.')

# Ignore the complete local runtime credential directory.
gitignore = root / '.gitignore'
text = gitignore.read_text()
if '.local/\n' not in text:
    text = text.replace(
        '# Secrets and environment files\n',
        '# Local orchestrator credentials and machine-specific runtime configuration\n.local/\n\n# Secrets and environment files\n',
        1,
    )
gitignore.write_text(text)

# Allow the GitHub App key either outside the repository or under the explicitly ignored .local directory.
auth = root / 'scripts/orchestrator/github_auth.py'
text = auth.read_text()
text = text.replace('import shutil\n', 'import shutil\nimport stat\n', 1)
old = '''def _outside_repository(path: Path, root: Path | None) -> Path:\n    resolved = path.expanduser().resolve()\n    if root is None:\n        return resolved\n    try:\n        resolved.relative_to(root.resolve())\n    except ValueError:\n        return resolved\n    raise ValueError("GitHub App private key must be stored outside the repository")\n'''
new = '''def _trusted_private_key_path(path: Path, root: Path | None) -> Path:\n    """Allow the PEM outside the repo or inside the explicitly ignored local secret directory."""\n    resolved = path.expanduser().resolve()\n    if root is not None:\n        repository_root = root.resolve()\n        try:\n            resolved.relative_to(repository_root)\n        except ValueError:\n            pass\n        else:\n            local_secret_root = repository_root / ".local"\n            try:\n                resolved.relative_to(local_secret_root)\n            except ValueError as exc:\n                raise ValueError(\n                    "GitHub App private key inside the repository must be stored under .local/"\n                ) from exc\n\n    if resolved.exists() and stat.S_IMODE(resolved.stat().st_mode) & 0o077:\n        raise ValueError("GitHub App private key permissions must not allow group/world access")\n    return resolved\n'''
if old not in text:
    raise SystemExit('github_auth private-key helper marker not found')
text = text.replace(old, new, 1)
text = text.replace(
    'private_key_path = _outside_repository(Path(key_path_raw), root)',
    'private_key_path = _trusted_private_key_path(Path(key_path_raw), root)',
    1,
)
auth.write_text(text)

# Update auth tests for the local ignored secret directory boundary.
test_auth = root / 'tests/test_github_auth.py'
text = test_auth.read_text()
text = text.replace('    _outside_repository,\n', '    _trusted_private_key_path,\n', 1)
old_test = '''def test_private_key_path_inside_repository_is_rejected(tmp_path: Path) -> None:\n    key = tmp_path / "secrets" / "app.pem"\n    key.parent.mkdir()\n    key.write_text("test-only-placeholder", encoding="utf-8")\n\n    with pytest.raises(ValueError, match="outside the repository"):\n        _outside_repository(key, tmp_path)\n'''
new_test = '''def test_private_key_path_inside_repository_is_rejected_outside_local_dir(tmp_path: Path) -> None:\n    key = tmp_path / "secrets" / "app.pem"\n    key.parent.mkdir()\n    key.write_text("test-only-placeholder", encoding="utf-8")\n    key.chmod(0o600)\n\n    with pytest.raises(ValueError, match="stored under .local"):\n        _trusted_private_key_path(key, tmp_path)\n\n\ndef test_private_key_path_inside_local_dir_is_allowed(tmp_path: Path) -> None:\n    key = tmp_path / ".local" / "github-app.pem"\n    key.parent.mkdir()\n    key.write_text("test-only-placeholder", encoding="utf-8")\n    key.chmod(0o600)\n\n    assert _trusted_private_key_path(key, tmp_path) == key.resolve()\n\n\ndef test_private_key_path_rejects_group_or_world_permissions(tmp_path: Path) -> None:\n    key = tmp_path / ".local" / "github-app.pem"\n    key.parent.mkdir()\n    key.write_text("test-only-placeholder", encoding="utf-8")\n    key.chmod(0o644)\n\n    with pytest.raises(ValueError, match="group/world"):\n        _trusted_private_key_path(key, tmp_path)\n'''
if old_test not in text:
    raise SystemExit('github_auth test marker not found')
text = text.replace(old_test, new_test, 1)
test_auth.write_text(text)

# Add the one-command launcher. init is one-time; every later invocation restores its own environment.
(root / 'orch').write_text(r'''#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

LOCAL_DIR="$ROOT/.local"
ENV_FILE="$LOCAL_DIR/orchestrator.env"
KEY_FILE="$LOCAL_DIR/github-app.pem"
VENV_DIR="$ROOT/.venv"
PYTHON="$VENV_DIR/bin/python"
REQUIREMENTS_MARKER="$VENV_DIR/.requirements-installed"

fail() {
  printf 'orchestrator: %s\n' "$*" >&2
  exit 1
}

require_python() {
  command -v python3 >/dev/null 2>&1 || fail "python3 is required (Python 3.12+)"
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' \
    || fail "Python 3.12+ is required"
}

ensure_runtime() {
  require_python
  if [[ ! -x "$PYTHON" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  if [[ ! -f "$REQUIREMENTS_MARKER" || "$ROOT/requirements-dev.lock" -nt "$REQUIREMENTS_MARKER" ]]; then
    "$PYTHON" -m pip install -r "$ROOT/requirements-dev.lock"
    touch "$REQUIREMENTS_MARKER"
  fi
}

initialize_local_secrets() {
  mkdir -p "$LOCAL_DIR"
  chmod 700 "$LOCAL_DIR"

  if [[ ! -f "$KEY_FILE" ]]; then
    printf 'Path to the GitHub App PEM private key: '
    IFS= read -r source_key
    [[ -n "$source_key" ]] || fail "PEM path is required"
    source_key="${source_key/#\~/$HOME}"
    [[ -f "$source_key" ]] || fail "PEM file not found: $source_key"
    cp "$source_key" "$KEY_FILE"
  fi
  chmod 600 "$KEY_FILE"

  printf 'GitHub Project token (classic PAT, project scope only): '
  IFS= read -r -s project_token
  printf '\n'
  [[ -n "$project_token" ]] || fail "Project token is required"
  printf 'GITHUB_PROJECT_TOKEN=%q\n' "$project_token" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"

  ensure_runtime
  printf 'Local orchestrator runtime initialized. Secrets are stored only in %s\n' "$LOCAL_DIR"
  printf 'Run ./orch doctor, ./orch project-bootstrap, or ./orch (continuous run).\n'
}

if [[ "${1:-}" == "init" ]]; then
  shift
  [[ $# -eq 0 ]] || fail "init does not accept additional arguments"
  initialize_local_secrets
  exit 0
fi

[[ -f "$ENV_FILE" ]] || fail "missing $ENV_FILE; run ./orch init once"
[[ -f "$KEY_FILE" ]] || fail "missing $KEY_FILE; run ./orch init once"
chmod 700 "$LOCAL_DIR"
chmod 600 "$ENV_FILE" "$KEY_FILE"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
export GITHUB_APP_PRIVATE_KEY_PATH="$KEY_FILE"

ensure_runtime

if [[ $# -eq 0 ]]; then
  set -- run
fi
exec "$PYTHON" -m scripts.run_orchestrator "$@"
''')

# Contract test for the launcher/ignore relationship.
(root / 'tests/test_local_launcher.py').write_text('''"""Contracts for the persistent local orchestrator launcher."""\n\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_local_runtime_directory_is_gitignored() -> None:\n    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")\n    assert ".local/" in gitignore.splitlines()\n\n\ndef test_launcher_loads_local_secrets_and_defaults_to_continuous_run() -> None:\n    launcher = (ROOT / "orch").read_text(encoding="utf-8")\n    assert ".local/orchestrator.env" not in launcher  # paths are composed from LOCAL_DIR\n    assert 'ENV_FILE="$LOCAL_DIR/orchestrator.env"' in launcher\n    assert 'KEY_FILE="$LOCAL_DIR/github-app.pem"' in launcher\n    assert 'export GITHUB_APP_PRIVATE_KEY_PATH="$KEY_FILE"' in launcher\n    assert 'set -- run' in launcher\n    assert 'python3 -m venv' in launcher\n''')

# Environment example describes the persistent launcher-managed values without containing secrets.
env_example = root / '.env.example'
text = env_example.read_text()
text = text.replace(
    '# The PEM private key itself must live outside the repository with restrictive permissions.\nGITHUB_APP_PRIVATE_KEY_PATH=\n',
    '# ./orch sets this automatically to the gitignored .local/github-app.pem.\n# An explicit environment override is still supported for non-launcher use.\nGITHUB_APP_PRIVATE_KEY_PATH=\n',
    1,
)
text = text.replace(
    '# User-owned GitHub Projects currently require a personal access token (classic) for\n# mutations. Keep this secret outside the repository and grant only the `project` scope.\nGITHUB_PROJECT_TOKEN=\n',
    '# User-owned Projects require a classic PAT with only the `project` scope.\n# ./orch init persists it in gitignored .local/orchestrator.env with mode 600.\nGITHUB_PROJECT_TOKEN=\n',
    1,
)
env_example.write_text(text)

# README: make ./orch the canonical interface and document one-time initialization.
readme = root / 'README.md'
text = readme.read_text()
text = text.replace(
    'These commands are machine/bootstrap controls; product commands belong in GitHub comments.\n',
    'These commands are machine/bootstrap controls; product commands belong in GitHub comments. '\
    'Run `./orch init` once on a machine. After that the launcher restores local secrets, activates '\
    'the virtual environment and installs updated locked dependencies automatically after restarts.\n\n'\
    'Running `./orch` with no arguments starts the continuous worker.\n',
    1,
)
for before, after in {
    '`python scripts/run_orchestrator.py doctor`': '`./orch doctor`',
    '`python -m scripts.run_orchestrator project-bootstrap`': '`./orch project-bootstrap`',
    '`python scripts/run_orchestrator.py usage`': '`./orch usage`',
    '`python scripts/run_orchestrator.py policy`': '`./orch policy`',
    '`python scripts/run_orchestrator.py iteration`': '`./orch iteration`',
    '`python scripts/run_orchestrator.py run`': '`./orch run`',
    '`python scripts/run_orchestrator.py resume`': '`./orch resume`',
    '`python scripts/run_orchestrator.py proposal`': '`./orch proposal`',
}.items():
    text = text.replace(before, after)
text = text.replace(
    '6. Keep the GitHub App private key outside the repository and set only\n   `GITHUB_APP_PRIVATE_KEY_PATH`; the non-secret Client ID is checked into `config/github.yaml`.\n7. Run `./orch doctor` until it reports `ready`.\n',
    '6. Run `./orch init` once. It copies the App PEM to gitignored `.local/github-app.pem`, stores '\
    'the Project token in `.local/orchestrator.env`, applies restrictive filesystem permissions, '\
    'and prepares `.venv`.\n7. Run `./orch doctor` until it reports `ready`.\n',
    1,
)
text = text.replace(
    'Project V2. For `/users/.../projects/...`, inject `GITHUB_PROJECT_TOKEN` as a personal access\n'\
    'token (classic) with only the `project` scope. Do not grant `repo` scope and do not commit the\n'\
    'token. Organization-owned Projects continue to use the GitHub App token.\n',
    'Project V2. For `/users/.../projects/...`, `./orch init` stores a personal access token '\
    '(classic) with only the `project` scope in gitignored `.local/orchestrator.env`. Do not grant '\
    '`repo` scope. Organization-owned Projects continue to use the GitHub App token.\n',
    1,
)
readme.write_text(text)

# Local operation guide: persistent local secrets + launcher are now canonical.
local_doc = root / 'docs/autonomy/local-operation.md'
text = local_doc.read_text()
text = text.replace(
    'Raw credentials must never be stored in the repository or forwarded to Codex.\n',
    'Raw credentials must never be tracked by Git. Machine-local credentials may be stored only '\
    'under the gitignored `.local/` directory with restrictive filesystem permissions and are never '\
    'forwarded to Codex.\n',
    1,
)
text = text.replace(
    'For `github_app`, keep the PEM private key outside the repository with restrictive filesystem\n'\
    'permissions. `GITHUB_APP_INSTALLATION_ID` is optional because the worker can discover the App\n'\
    'installation from the configured repository.\n',
    'The canonical launcher stores the PEM at gitignored `.local/github-app.pem` with mode 600. '\
    '`GITHUB_APP_INSTALLATION_ID` is optional because the worker can discover the App installation '\
    'from the configured repository.\n\nFor a user-owned Project, `./orch init` also stores '\
    '`GITHUB_PROJECT_TOKEN` in gitignored `.local/orchestrator.env` with mode 600. The token must be '\
    'a classic PAT with only the `project` scope.\n',
    1,
)
bootstrap_marker = '## Local bootstrap\n\nUse Python 3.12 or later from a clean checkout of `main`:\n'
replacement = '''## Local bootstrap\n\nUse Python 3.12 or later from a clean checkout of `main`. The preferred one-time setup is:\n\n```bash\n./orch init\n```\n\nIt securely prompts for the Project token and the existing GitHub App PEM path, copies secrets into\n`.local/`, fixes permissions and creates/updates `.venv`. The `.local/` directory is gitignored.\n\nManual validation remains available:\n'''
if bootstrap_marker not in text:
    raise SystemExit('local operation bootstrap marker not found')
text = text.replace(bootstrap_marker, replacement, 1)
for before, after in {
    'python scripts/run_orchestrator.py doctor': './orch doctor',
    'python scripts/run_orchestrator.py usage': './orch usage',
    'python scripts/run_orchestrator.py policy': './orch policy',
    'python scripts/run_orchestrator.py iteration': './orch iteration',
    'python scripts/run_orchestrator.py run': './orch run',
    '`python scripts/run_orchestrator.py proposal`': '`./orch proposal`',
}.items():
    text = text.replace(before, after)
text = text.replace(
    '## Restart and recovery behaviour\n',
    '## Restart and recovery behaviour\n\nAfter a machine restart, no exports or virtual-environment activation are needed. From the '\
    'repository root, `./orch` starts the continuous worker and `./orch <command>` runs any local '\
    'control command. The launcher reloads `.local/orchestrator.env`, supplies the App PEM path and '\
    'refreshes locked Python dependencies when needed.\n\n',
    1,
)
local_doc.write_text(text)

# GitHub App setup guide now points to the one-time initializer.
app_doc = root / 'docs/autonomy/github-app-setup.md'
text = app_doc.read_text()
old_local = '''After creating the App:\n\n1. Generate one private key from the App settings page.\n2. Move the downloaded PEM outside the repository, for example:\n\n   ```bash\n   mkdir -p ~/.config/ai-first-learning\n   mv ~/Downloads/*.private-key.pem ~/.config/ai-first-learning/github-app.pem\n   chmod 600 ~/.config/ai-first-learning/github-app.pem\n   ```\n\n3. Configure the trusted orchestrator shell/service:\n\n   ```bash\n   export GITHUB_APP_PRIVATE_KEY_PATH="$HOME/.config/ai-first-learning/github-app.pem"\n   ```\n\n`GITHUB_APP_INSTALLATION_ID` is optional; the worker discovers the installation from the configured\nrepository when it is omitted.\n\nNever paste the PEM private-key contents into an issue, pull request, chat, log, `.env` file or\nrepository file.\n'''
new_local = '''After creating the App:\n\n1. Generate one private key from the App settings page.\n2. Create a personal access token (classic) with only the `project` scope for the user-owned Project.\n3. From the repository root run `./orch init` once. It asks for the downloaded PEM path and Project\n   token, copies the PEM to `.local/github-app.pem`, writes `.local/orchestrator.env`, sets restrictive\n   permissions and prepares `.venv`. The complete `.local/` directory is gitignored.\n\n`GITHUB_APP_INSTALLATION_ID` is optional; the worker discovers the installation from the configured\nrepository when it is omitted.\n\nNever paste either secret into an issue, pull request, chat or tracked repository file. Do not grant\nthe Project token `repo` scope.\n'''
if old_local not in text:
    raise SystemExit('github app local credentials marker not found')
text = text.replace(old_local, new_local, 1)
text = text.replace('python scripts/run_orchestrator.py doctor', './orch doctor')
app_doc.write_text(text)
