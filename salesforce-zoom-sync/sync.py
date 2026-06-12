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

ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]

testMode = True

def get_access_token():
    print("GETTING ACCESS TOKEN...")
    url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ACCOUNT_ID}"
    response = requests.post(url, auth=(CLIENT_ID, CLIENT_SECRET))
    return response.json()['access_token']

def get_external_contacts(access_token = "", nextPageToken = ""):

    if access_token:
        token = access_token
    else:
        token = get_access_token()

    url = f"https://api.zoom.us/v2/phone/external_contacts"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    params = {}

    if nextPageToken:
        params['next_page_token'] = nextPageToken

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        print("External contacts fetched successfully!")
        return response.json()
    elif response.status_code == 429:
        sys.exit("***** TOO MANY REQUESTS - got rate-limited response code 429")
    else:
        return f"Error: {response.status_code}, {response.text}"

def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return None

def parse_email(email):
    if email.endswith(".org"):
        return ""
    return email

def get_salesforce_report_rows():
    print("FETCHING SALESFORCE REPORT...")
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
            row_dict = {column_labels[i]: cells[i].get("label", "") for i in range(len(columns))}
            rows.append(row_dict)

    print(f"Fetched {len(rows)} rows from Salesforce")
    return rows

def set_external_contacts(limit=1000):
    accessToken = get_access_token()
    nextPageToken = ""
    shouldFetchMoreExternalContacts = True
    allExistingContacts = []
    currentExternalPhoneNumbers = set()

    while shouldFetchMoreExternalContacts:

        externalContactsRawData = get_external_contacts(accessToken, nextPageToken)
        currentExternalContacts = externalContactsRawData['external_contacts']

        nextPageToken = externalContactsRawData['next_page_token']
        if nextPageToken == "":
            shouldFetchMoreExternalContacts = False

        print(f"Collecting external contacts: adding {len(currentExternalContacts)} numbers...")

        for external_contact in currentExternalContacts:
            phones = external_contact.get('phone_numbers', [])
            allExistingContacts.append({
                "id": external_contact['external_contact_id'],
                "name": external_contact.get('name', ''),
                "phones": phones,
            })
            for phone_number in phones:
                currentExternalPhoneNumbers.add(phone_number)

    print(f"{len(allExistingContacts)} total external contacts currently exist...")

    url = "https://api.zoom.us/v2/phone/external_contacts"

    headers = {
        "Authorization": f"Bearer {accessToken}",
        "Content-Type": "application/json",
    }

    rows = get_salesforce_report_rows()

    sf_normalized_phones = set()
    sf_names_no_phone = set()
    for row in rows:
        first = row.get("Primary Contact: First Name", "").strip().capitalize()
        last = row.get("Primary Contact: Last Name", "").strip().capitalize()
        name = f"{first} {last}".strip()
        phone = normalize_phone(row.get("Phone", "").strip())
        if phone:
            sf_normalized_phones.add(phone)
        else:
            sf_names_no_phone.add(name.lower())

    # Delete contacts not in SF
    deleted = []
    delete_failures = []
    for contact in allExistingContacts:
        contact_phones = set(contact['phones'])
        if not contact_phones.intersection(sf_normalized_phones):
            if contact['name'].lower() in sf_names_no_phone:
                print(f"Skipping delete for {contact['name']}: in SF but no phone")
                continue
            if testMode:
                print(f"[TEST] Would delete: {contact['name']} ({contact['phones']})")
            else:
                print(f"[PROD] Deleting: {contact['name']} ({contact['phones']})")
                response = requests.delete(
                    f"https://api.zoom.us/v2/phone/external_contacts/{contact['id']}",
                    headers=headers,
                )
                if response.status_code == 204:
                    print(f"[PROD] Deleted: {contact['name']}")
                    deleted.append(contact)
                elif response.status_code == 429:
                    sys.exit("***** TOO MANY REQUESTS - got rate-limited response code 429")
                else:
                    print(f"Failed to delete {contact['name']}: {response.status_code} {response.text}")
                    delete_failures.append(contact)

    results = []
    failures = []
    invalid_phone_count = 0
    already_exists_count = 0
    for i, row in enumerate(rows):
        if i >= limit:
            break

        first_name = row.get("Primary Contact: First Name", "").strip().capitalize()
        last_name = row.get("Primary Contact: Last Name", "").strip().capitalize()
        email = parse_email(row.get("Primary Contact: Email", "").strip())
        raw_phone = row.get("Phone", "").strip()

        name = f"{first_name} {last_name}".strip()
        phone = normalize_phone(raw_phone)

        if not phone:
            print(f"Skipping {name}: INVALID phone '{raw_phone}'")
            invalid_phone_count += 1
            continue
        elif phone in currentExternalPhoneNumbers:
            print(f"Skipping {name}: already exists '{raw_phone}'")
            already_exists_count += 1
            continue

        payload = {
            "name": name,
            "phone_numbers": [phone],
        }
        if email:
            payload["email"] = email

        if testMode:
            print(f"[TEST] Would add: {payload}")
            continue

        print(f"[PROD] Adding: {payload}")

        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 201:
            if email: print(f"[PROD] Added: {name} ({phone}, email: {email})")
            else: print(f"[PROD] Added: {name} ({phone})")
            results.append(response.json())
        elif response.status_code == 429:
            sys.exit("***** TOO MANY REQUESTS - got rate-limited response code 429")
        else:
            print(f"Failed for {name}: {response.status_code} {response.text}")
            failures.append({"name": name, "status": response.status_code, "error": response.text})

    return {
        "added": results,
        "failed": failures,
        "deleted": deleted,
        "delete_failures": delete_failures,
        "invalid_phone_count": invalid_phone_count,
        "already_exists_count": already_exists_count,
    }

if __name__ == "__main__":
    if testMode:
        print("[TEST] STARTING SCRIPT IN TEST MODE...")
    else:
        print("[PROD] !!!!!!!!! STARTING SCRIPT IN PRODUCTION MODE... !!!!!!!!!")

    summary = set_external_contacts()
    added = summary["added"]
    failed = summary["failed"]
    deleted = summary["deleted"]
    delete_failures = summary["delete_failures"]

    if testMode:
        print("[TEST] SCRIPT FINISHED")
    else:
        print("[PROD] !!!!!!!!! FINISHED UPDATING CONTACTS !!!!!!!!!")
        print(f"[PROD] Added: {len(added)}")
        print(f"[PROD] Deleted: {len(deleted)}")
        print(f"[PROD] Failed (add): {len(failed)}")
        print(f"[PROD] Failed (delete): {len(delete_failures)}")
        print(f"[PROD] Skipped (already exists): {summary['already_exists_count']}")
        print(f"[PROD] Skipped (invalid phone): {summary['invalid_phone_count']}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"added_count={len(added)}\n")
            f.write(f"failed_count={len(failed) + len(delete_failures)}\n")
            f.write(f"deleted_count={len(deleted)}\n")
            f.write(f"already_exists_count={summary['already_exists_count']}\n")
            f.write(f"invalid_phone_count={summary['invalid_phone_count']}\n")

    pprint.pprint(added)
    if deleted:
        print("\nDeleted:")
        pprint.pprint(deleted)
    if failed:
        print("\nFailed additions:")
        pprint.pprint(failed)
    if delete_failures:
        print("\nFailed deletions:")
        pprint.pprint(delete_failures)
