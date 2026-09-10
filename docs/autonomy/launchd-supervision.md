# Optional launchd supervision

The orchestrator does not require automatic startup. On macOS, `./orch init` offers launchd as an
optional local runtime supervisor using two independent opt-in questions.

## Global command

The one-time `./orch init` command also installs a user-scoped global `orch` launcher at
`~/.local/bin/orch`. The launcher contains no secrets; it forwards commands to the initialized
repository checkout. If `~/.local/bin` is not already on `PATH`, initialization adds it
idempotently to the current user's shell profile (`~/.zshrc` for zsh, `~/.bashrc` for bash, or
`~/.profile` otherwise).

A shell process cannot modify its parent's environment, so when initialization adds the PATH entry
for the first time, open a new terminal or source the profile once. Every later terminal session,
including after a computer restart, can invoke the orchestrator from any directory using `orch`.
Re-running `./orch init` refreshes the managed global launcher if the repository path changes.
Initialization refuses to overwrite an existing `~/.local/bin/orch` command that is not managed by
this project.

## Setup choices

During `./orch init`:

1. **Create launchd supervision?**
   - Default: **No**.
   - If No, `orch` runs the continuous worker in the foreground as before.
   - If Yes, a LaunchAgent plist is generated under the gitignored `.local/launchd/` directory.
2. **Start automatically after login following a computer restart?**
   - Asked only when launchd supervision was enabled.
   - Default: **No**.
   - If No, the plist remains only under `.local/launchd/`. macOS does not auto-load it after a
     reboot/login. Running `orch` manually bootstraps the job for the current login session.
   - If Yes, a copy is installed under `~/Library/LaunchAgents/`, so macOS starts it after the user
     logs in following a restart.

The automatic-start choice never changes the crash-recovery policy of a running supervised worker.
Once manually or automatically loaded, launchd keeps the worker alive and restarts it if the process
terminates unexpectedly. `orch stop` unloads the job intentionally and therefore prevents a restart
in the current login session.

## Commands

After initialization, these commands work from any directory. When launchd supervision is enabled:

```bash
orch          # manually start the supervised worker
orch start    # same explicit start operation
orch status   # show launchd job state
orch restart  # restart the supervised worker
orch logs     # follow local stdout/stderr logs
orch stop     # stop and unload the supervised worker
```

`orch run` always remains available as a foreground/debug mode and is not supervised by launchd.
When launchd supervision is disabled, `orch` and `orch start` run the foreground worker. All other
local commands, such as `orch doctor`, `orch project-bootstrap`, `orch usage`, `orch policy`, and
`orch iteration`, are also global after initialization.

## Local files

All generated runtime files are machine-local and excluded by `.gitignore`:

```text
.local/orchestrator.env
.local/github-app.pem
.local/launchd/com.nikolaytashev.ai-first-learning.orchestrator.plist
.local/logs/orchestrator.stdout.log
.local/logs/orchestrator.stderr.log
```

The global launcher is stored separately at `~/.local/bin/orch`; it contains only the absolute path
to the repository launcher and no credential material.

`./orch init` also captures the interactive runtime `PATH` in `.local/orchestrator.env`. This allows
a LaunchAgent to find user-installed tools such as Codex, Homebrew binaries, .NET or Flutter even
though launchd normally starts jobs with a minimal environment.

The LaunchAgent is user-scoped. Automatic startup therefore means startup after the user logs in
following a reboot, not a root-level system daemon that starts before login.
