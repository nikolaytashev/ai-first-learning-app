# Optional launchd supervision

The orchestrator does not require automatic startup. On macOS, `./orch init` offers launchd as an
optional local runtime supervisor using two independent opt-in questions.

## Setup choices

During `./orch init`:

1. **Create launchd supervision?**
   - Default: **No**.
   - If No, `./orch` runs the continuous worker in the foreground as before.
   - If Yes, a LaunchAgent plist is generated under the gitignored `.local/launchd/` directory.
2. **Start automatically after login following a computer restart?**
   - Asked only when launchd supervision was enabled.
   - Default: **No**.
   - If No, the plist remains only under `.local/launchd/`. macOS does not auto-load it after a
     reboot/login. Running `./orch` manually bootstraps the job for the current login session.
   - If Yes, a copy is installed under `~/Library/LaunchAgents/`, so macOS starts it after the user
     logs in following a restart.

The automatic-start choice never changes the crash-recovery policy of a running supervised worker.
Once manually or automatically loaded, launchd keeps the worker alive and restarts it if the process
terminates unexpectedly. `./orch stop` unloads the job intentionally and therefore prevents a
restart in the current login session.

## Commands

When launchd supervision is enabled:

```bash
./orch          # manually start the supervised worker
./orch start    # same explicit start operation
./orch status   # show launchd job state
./orch restart  # restart the supervised worker
./orch logs     # follow local stdout/stderr logs
./orch stop     # stop and unload the supervised worker
```

`./orch run` always remains available as a foreground/debug mode and is not supervised by launchd.
When launchd supervision is disabled, `./orch` and `./orch start` run the foreground worker.

## Local files

All generated runtime files are machine-local and excluded by `.gitignore`:

```text
.local/orchestrator.env
.local/github-app.pem
.local/launchd/com.nikolaytashev.ai-first-learning.orchestrator.plist
.local/logs/orchestrator.stdout.log
.local/logs/orchestrator.stderr.log
```

`./orch init` also captures the interactive runtime `PATH` in `.local/orchestrator.env`. This allows
a LaunchAgent to find user-installed tools such as Codex, Homebrew binaries, .NET or Flutter even
though launchd normally starts jobs with a minimal environment.

The LaunchAgent is user-scoped. Automatic startup therefore means startup after the user logs in
following a reboot, not a root-level system daemon that starts before login.
