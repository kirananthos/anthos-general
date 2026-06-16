# Salesforce → Zoom Phone Contact Sync

Automatically syncs active aftercare participant contact info from a Salesforce report into Zoom Phone external contacts. Field staff on the aftercare team see participant full names when calling or texting from the Zoom Phone app — no manual steps required.

---

## How it works

1. **Fetches all existing Zoom external contacts** (paginated)
2. **Pulls active participants from a Salesforce report** via the Salesforce Analytics API
3. **Deletes** any Zoom contacts whose phone number no longer appears in the Salesforce report (i.e. graduated or withdrawn participants). Also deletes any other contacts with the same name, to clean up stale entries from previous phone numbers.
4. **Adds** any Salesforce participants not yet in Zoom Phone
5. **Sends a Slack notification** with a summary of what was added, deleted, and skipped

The script runs automatically every day at **8am ET** via GitHub Actions. It can also be triggered manually from the Actions tab.

---

## Project structure
```
salesforce-zoom-sync/
├── sync.py # Main sync script
├── requirements.txt # Python dependencies
└── .env.example # Template for local credentials

.github/workflows/
└── salesforce-zoom-sync.yml # GitHub Actions workflow
```

---

## Credentials & secrets

All credentials are stored as **GitHub Actions secrets** in the `kirananthos/anthos-general` repo (Settings → Secrets and variables → Actions). They are never committed to the repo.

| Secret | Description |
|---|---|
| `ZOOM_ACCOUNT_ID` | Found in the Zoom Marketplace app settings |
| `ZOOM_CLIENT_ID` | Found in the Zoom Marketplace app settings |
| `ZOOM_CLIENT_SECRET` | Found in the Zoom Marketplace app settings |
| `SALESFORCE_USERNAME` | Salesforce login email used to authenticate the API |
| `SALESFORCE_PASSWORD` | Salesforce password for that account |
| `SALESFORCE_TOKEN` | Salesforce security token (Settings → My Personal Information → Reset My Security Token) |
| `SALESFORCE_REPORT_ID` | The 15 or 18-character ID from the Salesforce report URL (starts with `00O`) |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL from the Slack app used to send notifications |
| `STAFF_SLACK_USER_ID` | Slack member ID of the person who should be tagged in notifications (e.g. `U02ABC12DEF`) |

For **local development**, copy `.env.example` to `.env`, fill in the values, and run `python sync.py`. The script loads `.env` automatically. Never commit `.env`.

---

## Zoom app setup

The script authenticates to Zoom using a **Server-to-Server OAuth app** in the Zoom Marketplace. The app requires the following scopes:

- `phone:write:external_contact:admin` — create contacts
- `phone:delete:external_contact:admin` — delete contacts
- `phone:read:list_external_contacts:admin` — list existing contacts

To manage the app: [marketplace.zoom.us](https://marketplace.zoom.us) → Develop → your app.

> **Important:** The Zoom app is currently owned by a specific user account. If that account is deactivated, the app may stop working or become unmanageable by other admins. Before the owning account is deactivated, the app should either be recreated under a shared/service Zoom account, or Zoom support should be contacted to confirm another admin can take ownership.

---

## Running manually

From the GitHub Actions tab: select **"Sync Salesforce contacts to Zoom"** → **Run workflow** → select branch `main`.

Logs show each contact added, deleted, or skipped and why.

---

## Test mode

To do a dry run without writing any changes to Zoom, set `TEST_MODE = True` at the top of `sync.py`. All actions will be logged as `[TEST] Would add / Would delete` with no API calls made. **Remember to set it back to `False` before merging — otherwise the scheduled run won't make real changes.**
