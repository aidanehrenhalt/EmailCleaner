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

## Modes

EmailCleaner has two independent modes. **They cannot run simultaneously in one command** — run them as separate commands if you need both.

| Mode | Trigger | What it does |
|------|---------|--------------|
| **Junk sender** | no `--label` flag (default) | Groups inbox by sender domain, lets you select and trash/delete |
| **Label filtering** | `--label "Name"` | Applies a Gmail label to all emails matching your query |

---

## Usage

### Junk sender filtering only

Scan your inbox and interactively select sender domains to trash:

```bash
# Preview — writes junk_senders.csv, no emails modified
emailcleaner --dry-run --query "category:promotions" --limit 0

# Trash emails from selected domains (always writes junk_senders.csv)
emailcleaner --query "category:promotions"

# Trash specific domains non-interactively
emailcleaner --domains "mailchimp.com,substack.com"

# Write to a custom filename instead of the default
emailcleaner --dry-run --query "category:promotions" --output my_report.csv

# Keep a new timestamped file each run instead of overwriting
emailcleaner --dry-run --query "category:promotions" --new-file
# → writes junk_senders_20260317_143022.csv
```

### Label filtering only

Apply a Gmail label to all emails matching a query. The label must already exist in your Gmail account:

```bash
# Preview — shows count and output path, no changes made
emailcleaner --label "Internship / Job Hunting" \
  --query "internship OR hiring OR job application" --dry-run

# Apply the label (always writes labeled_emails.csv)
emailcleaner --label "Internship / Job Hunting" \
  --query "internship OR hiring OR job application"

# Keep a new timestamped file each run
emailcleaner --label "Internship / Job Hunting" \
  --query "internship OR hiring OR job application" --new-file
# → writes labeled_emails_20260317_143022.csv
```

If the label name isn't found, the tool prints all available label names so you can check the exact spelling.

### Running both modes

The two modes are mutually exclusive per run. To apply both, run them as two separate commands:

```bash
# Step 1 — label job-related emails
emailcleaner --label "Internship / Job Hunting" \
  --query "internship OR hiring OR job application"

# Step 2 — clean up junk senders
emailcleaner --query "category:promotions"
```

### Permanently delete instead of trash

```bash
emailcleaner --delete --domains "mailchimp.com"
```

> **Note:** `--delete` requires confirming a second prompt and uses a broader OAuth scope (`mail.google.com`). Prefer trash (the default) unless you are certain.

---

## Multiple accounts

EmailCleaner stores its auth token in `~/.emailcleaner/` by default. Each account gets its own token directory — one directory per account.

### Add a second account

```bash
# Personal account (default token dir)
emailcleaner --dry-run

# Second account — triggers its own OAuth flow on first use
emailcleaner --token-dir ~/.emailcleaner/work/ --dry-run
```

### Check which account a token belongs to

```bash
# Default account
emailcleaner --whoami

# Named token directory
emailcleaner --token-dir ~/.emailcleaner/work/ --whoami
```

Output:
```
Signed in as: you@gmail.com
Token dir:    ~/.emailcleaner/work/
```

Each `--token-dir` holds an independent token, so you can switch between accounts by changing the flag — no re-authentication needed unless the token expires.

---

## All options

| Flag | Default | Description |
|------|---------|-------------|
| `--credentials` | `credentials.json` | Path to OAuth2 client secrets JSON |
| `--token-dir` | `~/.emailcleaner/` | Directory to store the auth token |
| `--whoami` | off | Print the email address for the current token and exit |
| `-q / --query` | *(all mail)* | Gmail search query |
| `--label` | off | Apply a named Gmail label to all matched emails (label mode) |
| `--dry-run` | off | Scan and display only, no modifications |
| `--delete` | off | Permanently delete instead of trashing (junk mode) |
| `--min-count` | `2` | Only show senders with at least N emails (junk mode) |
| `--sort` | `count` | Sort summary by `count` or `domain` (junk mode) |
| `--limit` | `0` (unlimited) | Max messages to scan |
| `--domains` | *(interactive)* | Comma-separated domains to clean (junk mode) |
| `--include-receipts` | off | Include transactional emails in counts/labeling |
| `--output` | `junk_senders.csv` / `labeled_emails.csv` | Override the default CSV output filename |
| `--new-file` | off | Write to a new timestamped CSV instead of overwriting |

---

## Token & access management

- The OAuth token is stored at `~/.emailcleaner/token.json` with `600` permissions (owner read/write only)
- To revoke access: delete `~/.emailcleaner/token.json` and visit [myaccount.google.com/permissions](https://myaccount.google.com/permissions) to remove the app
- The default scope (`gmail.modify`) allows reading and trashing but not permanent deletion; `--delete` upgrades to full mail scope

---

## Privacy

`credentials.json` and `token.json` are listed in `.gitignore` and will never be committed to version control.
