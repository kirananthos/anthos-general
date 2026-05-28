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

testMode = False

# TODO: IMPLEMENT DELETION OF WITHDRAWN/GRADUATED PARTICIPANTS

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
    currentExternalPhoneNumbers = set()

    while shouldFetchMoreExternalContacts:

        externalContactsRawData = get_external_contacts(accessToken, nextPageToken)
        currentExternalContacts = externalContactsRawData['external_contacts']

        nextPageToken = externalContactsRawData['next_page_token']
        if nextPageToken == "":
            shouldFetchMoreExternalContacts = False

        print(f"Collecting external contacts: adding {len(currentExternalContacts)} numbers...")

        for external_contact in currentExternalContacts:
            for phone_number in external_contact['phone_numbers']:
                currentExternalPhoneNumbers.add(phone_number)

    print(f"{len(currentExternalPhoneNumbers)} total external contacts currently exist...")

    url = "https://api.zoom.us/v2/phone/external_contacts"

    headers = {
        "Authorization": f"Bearer {accessToken}",
        "Content-Type": "application/json",
    }

    results = []
    rows = get_salesforce_report_rows()
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
            continue
        elif phone in currentExternalPhoneNumbers:
            print(f"Skipping {name}: already exists '{raw_phone}'")
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

    return results

if __name__ == "__main__":
    if testMode:
        print("[TEST] STARTING SCRIPT IN TEST MODE...")
    else:
        print("[PROD] !!!!!!!!! STARTING SCRIPT IN PRODUCTION MODE... !!!!!!!!!")

    contacts = set_external_contacts()

    if testMode:
        print("[TEST] SCRIPT FINISHED")
    else:
        print("[PROD] !!!!!!!!! FINISHED UPDATING CONTACTS !!!!!!!!!")
        print(f"[PROD] {len(contacts)} contacts updated ----------------------")

    pprint.pprint(contacts)
