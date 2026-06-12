import requests
import os
import pprint
import re
import sys
from dotenv import load_dotenv
from simple_salesforce import Salesforce

load_dotenv()

SALESFORCE_USERNAME = os.environ["SALESFORCE_USERNAME"]
SALESFORCE_PASSWORD = os.environ["SALESFORCE_PASSWORD"]
SALESFORCE_TOKEN = os.environ["SALESFORCE_TOKEN"]
SALESFORCE_REPORT_ID = os.environ["SALESFORCE_REPORT_ID"]

ZOOM_ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
ZOOM_CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
ZOOM_CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]
ZOOM_EXTERNAL_CONTACTS_URL = "https://api.zoom.us/v2/phone/external_contacts"

TEST_MODE = True
MODE = "TEST" if TEST_MODE else "PROD"

def get_zoom_token():
    print("Getting Zoom access token...")
    response = requests.post(
        f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}",
        auth=(ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET),
    )
    return response.json()["access_token"]


def fetch_contacts_page(token, next_page_token=""):
    params = {"next_page_token": next_page_token} if next_page_token else {}
    response = requests.get(
        ZOOM_EXTERNAL_CONTACTS_URL,
        headers=zoom_headers(token),
        params=params,
    )
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 429:
        sys.exit("Rate limited by Zoom API (429). Try again later.")
    else:
        sys.exit(f"Failed to fetch contacts: {response.status_code} {response.text}")


def zoom_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None


def filter_org_email(email):
    return "" if email.endswith(".org") else email


def parse_sf_row(row):
    first = row.get("Primary Contact: First Name", "").strip().capitalize()
    last = row.get("Primary Contact: Last Name", "").strip().capitalize()
    return {
        "name": f"{first} {last}".strip(),
        "phone": normalize_phone(row.get("Phone", "").strip()),
        "email": filter_org_email(row.get("Primary Contact: Email", "").strip()),
    }


def get_salesforce_rows():
    print("Fetching Salesforce report...")
    sf = Salesforce(
        username=SALESFORCE_USERNAME,
        password=SALESFORCE_PASSWORD,
        security_token=SALESFORCE_TOKEN,
    )

    report = sf.restful(f"analytics/reports/{SALESFORCE_REPORT_ID}?includeDetails=true")

    columns = report["reportMetadata"]["detailColumns"]
    column_info = report["reportExtendedMetadata"]["detailColumnInfo"]
    column_labels = [column_info[col]["label"] for col in columns]

    rows = []
    for key, group in report["factMap"].items():
        if key == "T!T":
            continue
        for row_data in group.get("rows", []):
            cells = row_data["dataCells"]
            rows.append({column_labels[i]: cells[i].get("label", "") for i in range(len(columns))})

    print(f"Fetched {len(rows)} rows from Salesforce")
    return rows


def sync_contacts():
    token = get_zoom_token()

    # Fetch all existing Zoom external contacts
    existing_contacts = []
    existing_phones = set()
    next_page_token = ""

    while True:
        page = fetch_contacts_page(token, next_page_token)
        page_contacts = page["external_contacts"]
        print(f"Fetched page of {len(page_contacts)} existing contacts...")

        for contact in page_contacts:
            phones = contact.get("phone_numbers", [])
            existing_contacts.append({
                "id": contact["external_contact_id"],
                "name": contact.get("name", ""),
                "phones": phones,
            })
            existing_phones.update(phones)

        next_page_token = page["next_page_token"]
        if not next_page_token:
            break

    print(f"{len(existing_contacts)} total existing Zoom contacts")

    # Parse Salesforce rows
    sf_rows = get_salesforce_rows()
    sf_phones = set()
    sf_names_missing_phone = set()

    for row in sf_rows:
        parsed = parse_sf_row(row)
        if parsed["phone"]:
            sf_phones.add(parsed["phone"])
        else:
            sf_names_missing_phone.add(parsed["name"].lower())

    # Build name → contacts index for bulk deletion by name
    contacts_by_name = {}
    for contact in existing_contacts:
        contacts_by_name.setdefault(contact["name"].lower(), []).append(contact)

    # Delete contacts no longer in Salesforce
    deleted = []
    delete_failures = []
    deleted_ids = set()

    def delete_contact(contact):
        if contact["id"] in deleted_ids:
            return
        deleted_ids.add(contact["id"])
        if TEST_MODE:
            print(f"[{MODE}] Would delete: {contact['name']} ({contact['phones']})")
            return
        response = requests.delete(
            f"{ZOOM_EXTERNAL_CONTACTS_URL}/{contact['id']}",
            headers=zoom_headers(token),
        )
        if response.status_code == 204:
            print(f"[{MODE}] Deleted: {contact['name']} ({contact['phones']})")
            deleted.append(contact)
        elif response.status_code == 429:
            sys.exit("Rate limited by Zoom API (429). Try again later.")
        else:
            print(f"[{MODE}] Failed to delete {contact['name']}: {response.status_code} {response.text}")
            delete_failures.append(contact)

    for contact in existing_contacts:
        if contact["id"] in deleted_ids:
            continue
        if set(contact["phones"]).intersection(sf_phones):
            continue
        if contact["name"].lower() in sf_names_missing_phone:
            print(f"Skipping delete for {contact['name']}: in Salesforce but no phone on file")
            continue
        for c in contacts_by_name.get(contact["name"].lower(), []):
            delete_contact(c)

    # Add contacts from Salesforce not yet in Zoom
    added = []
    add_failures = []
    skipped_no_phone = 0
    skipped_already_exists = 0

    for row in sf_rows:
        parsed = parse_sf_row(row)
        name, phone, email = parsed["name"], parsed["phone"], parsed["email"]

        if not phone:
            print(f"Skipping {name}: no valid phone number")
            skipped_no_phone += 1
            continue
        if phone in existing_phones:
            print(f"Skipping {name}: already exists in Zoom")
            skipped_already_exists += 1
            continue

        payload = {"name": name, "phone_numbers": [phone]}
        if email:
            payload["email"] = email

        if TEST_MODE:
            print(f"[{MODE}] Would add: {payload}")
            continue

        response = requests.post(ZOOM_EXTERNAL_CONTACTS_URL, headers=zoom_headers(token), json=payload)

        if response.status_code == 201:
            print(f"[{MODE}] Added: {name} ({phone})" + (f", email: {email}" if email else ""))
            added.append(response.json())
        elif response.status_code == 429:
            sys.exit("Rate limited by Zoom API (429). Try again later.")
        else:
            print(f"[{MODE}] Failed to add {name}: {response.status_code} {response.text}")
            add_failures.append({"name": name, "status": response.status_code, "error": response.text})

    return {
        "added": added,
        "add_failures": add_failures,
        "deleted": deleted,
        "delete_failures": delete_failures,
        "skipped_no_phone": skipped_no_phone,
        "skipped_already_exists": skipped_already_exists,
    }


if __name__ == "__main__":
    print(f"[{MODE}] Starting Salesforce → Zoom contact sync...")

    summary = sync_contacts()
    added = summary["added"]
    add_failures = summary["add_failures"]
    deleted = summary["deleted"]
    delete_failures = summary["delete_failures"]

    print(f"\n[{MODE}] Sync complete")
    print(f"[{MODE}]   Added:                  {len(added)}")
    print(f"[{MODE}]   Deleted:                {len(deleted)}")
    print(f"[{MODE}]   Failed (add):           {len(add_failures)}")
    print(f"[{MODE}]   Failed (delete):        {len(delete_failures)}")
    print(f"[{MODE}]   Skipped (exists):       {summary['skipped_already_exists']}")
    print(f"[{MODE}]   Skipped (no phone):     {summary['skipped_no_phone']}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"added_count={len(added)}\n")
            f.write(f"deleted_count={len(deleted)}\n")
            f.write(f"failed_count={len(add_failures) + len(delete_failures)}\n")
            f.write(f"skipped_already_exists={summary['skipped_already_exists']}\n")
            f.write(f"skipped_no_phone={summary['skipped_no_phone']}\n")

    if added:
        print("\nAdded:")
        pprint.pprint(added)
    if deleted:
        print("\nDeleted:")
        pprint.pprint(deleted)
    if add_failures:
        print("\nFailed additions:")
        pprint.pprint(add_failures)
    if delete_failures:
        print("\nFailed deletions:")
        pprint.pprint(delete_failures)
