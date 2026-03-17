# EmailCleaner

Bulk-clean marketing emails from Gmail. Scans your inbox, groups senders by domain, and lets you trash or permanently delete entire sender groups at once.

## Prerequisites

- Python 3.10+
- A Google account (Gmail)
- A free Google Cloud project with the Gmail API enabled

---

## Setup

### 1. Create Google Cloud credentials

1. Go to [console.cloud.google.com](https://console.cloud.google.com/) and create a new project (e.g. `EmailCleaner`)
2. Navigate to **APIs & Services → Library**, search for **Gmail API**, and click **Enable**
3. Go to **APIs & Services → Credentials** and click **Create Credentials → OAuth client ID**
4. If prompted to configure the consent screen first:
   - User type: **External**
   - Fill in an app name (e.g. `EmailCleaner`)
   - Under **Test users**, add your own Gmail address
   - Save and continue through the remaining screens
5. Back in Create Credentials, choose application type: **Desktop app**, then click **Create**
6. Click **Download JSON** — save the file as `credentials.json` in the project root

### 2. Install

```bash
cd /path/to/EmailCleaner
pip install -e .
```

### 3. Authenticate

On the first run, a browser window will open asking you to sign in with Google and grant access. After approving, a token is saved to `~/.emailcleaner/token.json` and reused for future runs.

---

## Usage

### Dry run — scan only, no changes

```bash
emailcleaner --dry-run
```

### Scan a specific category

```bash
emailcleaner --dry-run --query "category:promotions"
emailcleaner --dry-run --query "category:promotions OR category:updates"
```

### Scan all mail (no limit)

```bash
emailcleaner --dry-run --limit 0
```

### Trash emails from specific domains (non-interactive)

```bash
emailcleaner --domains "mailchimp.com,substack.com"
```

### Permanently delete instead of trash

```bash
emailcleaner --delete --domains "mailchimp.com"
```

> **Note:** `--delete` requires confirming a second prompt and uses a broader OAuth scope (`mail.google.com`). Prefer `--trash` (the default) unless you are certain.

### Apply a label to matched emails

Label all emails matching a query in one shot — no interactive sender selection needed. The label must already exist in your Gmail account.

```bash
emailcleaner --label "Internship / Job Hunting" --query "internship OR hiring OR job application"
```

Use `--dry-run` to preview the count before applying:

```bash
emailcleaner --label "Internship / Job Hunting" --query "internship OR hiring" --dry-run
```

If the label name isn't found, the tool prints all available label names so you can check the exact spelling.

---

## Multiple accounts

EmailCleaner stores its auth token in `~/.emailcleaner/` by default. To use a different Gmail account, point `--token-dir` at a separate directory:

```bash
# Personal account (default)
emailcleaner --dry-run

# Second account — triggers its own OAuth flow on first use
emailcleaner --token-dir ~/.emailcleaner/work/ --dry-run
```

Each directory holds an independent token, so you can switch between accounts without re-authenticating.

---

## All options

| Flag | Default | Description |
|------|---------|-------------|
| `--credentials` | `credentials.json` | Path to OAuth2 client secrets JSON |
| `--token-dir` | `~/.emailcleaner/` | Directory to store the auth token |
| `-q / --query` | *(all mail)* | Gmail search query |
| `--label` | off | Apply a named Gmail label to all matched emails |
| `--dry-run` | off | Scan and display only, no modifications |
| `--delete` | off | Permanently delete instead of trashing |
| `--min-count` | `2` | Only show senders with at least N emails |
| `--sort` | `count` | Sort summary by `count` or `domain` |
| `--limit` | `0` (unlimited) | Max messages to scan |
| `--domains` | *(interactive)* | Comma-separated domains to clean |
| `--include-receipts` | off | Include transactional emails in sender counts |
| `--output` | off | Write results to a CSV file |

---

## Token & access management

- The OAuth token is stored at `~/.emailcleaner/token.json` with `600` permissions (owner read/write only)
- To revoke access: delete `~/.emailcleaner/token.json` and visit [myaccount.google.com/permissions](https://myaccount.google.com/permissions) to remove the app
- The default scope (`gmail.modify`) allows reading and trashing but not permanent deletion; `--delete` upgrades to full mail scope

---

## Privacy

`credentials.json` and `token.json` are listed in `.gitignore` and will never be committed to version control.
