#!/usr/bin/env python3
import os
import time
import json
from typing import Dict, Any, Optional

import pymysql
import requests


def getenv(name: str, default: Optional[str] = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def get_db_connection():
    host = getenv("AZURE_MYSQL_HOST", required=True)
    port = int(getenv("AZURE_MYSQL_PORT", "3306"))
    user = getenv("AZURE_MYSQL_USER", required=True)
    password = getenv("AZURE_MYSQL_PASSWORD", required=True)
    database = getenv("AZURE_MYSQL_DATABASE", required=True)

    # Azure MySQL typically requires TLS; PyMySQL uses it if ssl param passed.
    ssl_disabled = getenv("AZURE_MYSQL_SSL_DISABLED", "false").lower() in ("1", "true", "yes")
    ssl_params = None if ssl_disabled else {"ssl": {}}

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        cursorclass=pymysql.cursors.DictCursor,
        **(ssl_params or {})
    )
    return conn


def mautic_request(method: str, path: str, auth: requests.auth.AuthBase, base_url: str, **kwargs) -> requests.Response:
    url = base_url.rstrip("/") + path
    resp = requests.request(method, url, auth=auth, timeout=30, **kwargs)
    if not resp.ok:
        raise RuntimeError(f"Mautic API {method} {path} failed: {resp.status_code} {resp.text}")
    return resp


def find_contact_by_email(email: str, auth, base_url: str) -> Optional[int]:
    params = {"search": f"email:{email}"}
    r = mautic_request("GET", "/api/contacts", auth, base_url, params=params)
    data = r.json()
    contacts = data.get("contacts") or {}
    if not contacts:
        return None
    # Return the first key (ID)
    first_id = next(iter(contacts.keys()))
    try:
        return int(first_id)
    except Exception:
        return None


def normalize_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    # Map common columns; everything else goes into fields[all][alias]
    email = row.get("email") or row.get("Email")
    if not email:
        raise ValueError("Row missing required 'email' field")

    payload: Dict[str, Any] = {"email": email}
    mappings = {
        "firstname": ["firstname", "first_name", "firstName", "FirstName"],
        "lastname": ["lastname", "last_name", "lastName", "LastName"],
        "phone": ["phone", "Phone"],
        "company": ["company", "Company"],
    }
    # Core fields
    for target, aliases in mappings.items():
        for a in aliases:
            if a in row and row[a]:
                payload[target] = row[a]
                break

    # Additional fields get placed in the "all" group
    extra_fields: Dict[str, Any] = {}
    for k, v in row.items():
        if v is None:
            continue
        lk = k.lower()
        if lk in ("email",) or any(lk in [a.lower() for a in al] for al in mappings.values()):
            continue
        extra_fields[k] = v
    if extra_fields:
        # Mautic expects fields[group][alias]
        payload.update({f"fields[all][{k}]": str(v) for k, v in extra_fields.items()})

    return payload


def upsert_contact(row: Dict[str, Any], auth, base_url: str) -> str:
    payload = normalize_payload(row)
    email = payload["email"]
    contact_id = find_contact_by_email(email, auth, base_url)
    if contact_id is None:
        r = mautic_request("POST", "/api/contacts/new", auth, base_url, data=payload)
        return f"created:{email}"
    else:
        r = mautic_request("PATCH", f"/api/contacts/{contact_id}/edit", auth, base_url, data=payload)
        return f"updated:{email}"


def main():
    # Mautic API credentials (Basic Auth)
    base_url = getenv("MAUTIC_BASE_URL", "http://localhost:8080")
    api_user = getenv("MAUTIC_API_USER", required=True)
    api_password = getenv("MAUTIC_API_PASSWORD", required=True)
    auth = requests.auth.HTTPBasicAuth(api_user, api_password)

    query = getenv("AZURE_MYSQL_QUERY")
    table = getenv("AZURE_MYSQL_TABLE")
    if not query and not table:
        # Default: simple selection
        table = "users"
    if not query:
        query = f"SELECT * FROM `{table}`" if table else query

    batch_size = int(getenv("BATCH_SIZE", "500"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query)
            processed = 0
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    try:
                        result = upsert_contact(row, auth, base_url)
                        print(result)
                    except Exception as e:
                        print(f"error:{e}")
                processed += len(rows)
                # Gentle pacing
                time.sleep(0.2)
            print(f"done: {processed}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

