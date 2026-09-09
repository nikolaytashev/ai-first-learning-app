# GitHub App Setup

This project uses a repository-scoped GitHub App as the preferred autonomous GitHub identity.

## Registration

Create the App under the `nikolaytashev` personal account.

Recommended registration values:

- GitHub App name: a globally unique name such as `ai-first-learning-orchestrator-nt`;
- Homepage URL: `https://github.com/nikolaytashev/ai-first-learning-app`;
- Callback URL: leave empty;
- Setup URL: leave empty;
- Webhooks: inactive. The local worker polls GitHub and does not require inbound webhooks.

## Permissions

Grant only:

Repository permissions:

- Contents: Read and write;
- Issues: Read and write;
- Pull requests: Read and write;
- Checks: Read-only;
- Metadata: Read-only.

Projects:

- Projects: Read and write.

Do not grant repository Administration or unrelated write permissions.

## Installation

Install the App on the `nikolaytashev` account with **Only select repositories**, selecting only:

- `nikolaytashev/ai-first-learning-app`

## Local credentials

The App Client ID is non-secret and is checked into `config/github.yaml`. The current configured
Client ID is `Iv23ling22Lvmau5uLUJ`. `GITHUB_APP_CLIENT_ID` remains available only as an optional
local override.

After creating the App:

1. Generate one private key from the App settings page.
2. Move the downloaded PEM outside the repository, for example:

   ```bash
   mkdir -p ~/.config/ai-first-learning
   mv ~/Downloads/*.private-key.pem ~/.config/ai-first-learning/github-app.pem
   chmod 600 ~/.config/ai-first-learning/github-app.pem
   ```

3. Configure the trusted orchestrator shell/service:

   ```bash
   export GITHUB_APP_PRIVATE_KEY_PATH="$HOME/.config/ai-first-learning/github-app.pem"
   ```

`GITHUB_APP_INSTALLATION_ID` is optional; the worker discovers the installation from the configured
repository when it is omitted.

Never paste the PEM private-key contents into an issue, pull request, chat, log, `.env` file or
repository file.

## Verification

From a clean `main` checkout after the GitHub App runtime-auth changes are merged:

```bash
openssl version
python scripts/run_orchestrator.py doctor
```

Do not start `iteration` or `run` until `doctor` reports `status: ready`.
