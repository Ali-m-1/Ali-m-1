# Language Territory Setup

The `Language Territory` chart is generated weekly by GitHub Actions. It uses a repository-scoped personal access token with private-repository read access and never commits repository names or raw API responses.

## Required secret

Create a fine-grained personal access token named `LANGUAGE_STATS_TOKEN` in the repository's GitHub Actions secrets.

The token needs read access to:

- Repository metadata
- Contents
- Private repositories whose language statistics should be included

For a fine-grained token, select this profile repository's owned private repositories and any private repositories you own. A classic token can use the `repo` scope, but a fine-grained token is preferred.

## Add public collaborative repositories

Add one teammate repository per line in `config/public_collaborations.txt`:

```text
owner/repository
```

Only public repositories should be listed. New repositories you own are discovered automatically; they do not need to be added manually.

## Exclude repositories

Add either `owner/repository` or a repository name to `config/excluded_repositories.txt`, one per line. Archived repositories, forks, and the profile repository are excluded automatically.

## Run manually

Open **Actions** > **Update language territory** > **Run workflow**. The workflow runs Monday at 07:17 UTC automatically.

## Troubleshooting

- **401 or 403:** Recreate `LANGUAGE_STATS_TOKEN`, verify repository access, and confirm the token has not expired.
- **Rate limit:** Wait for the rate-limit reset shown by GitHub or run the workflow later.
- **No repositories included:** Confirm the token can access private repositories and that no broad exclusions match them.
- **Collection failure:** The workflow stops before generation, so the previously committed SVG remains unchanged.
