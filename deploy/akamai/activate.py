#!/usr/bin/env python3
"""
Akamai Property deployment script.

Automates the deployment of BAZSPARK's Akamai configuration:
  1. Creates a new Property (or reuses existing one)
  2. Imports the rules from deploy/akamai/property-main.json
  3. Adds the hostnames
  4. Activates on staging, waits for activation, then activates on production
  5. Returns the edge hostname for DNS configuration

PREREQUISITES:
  - Akamai API credentials (EdgeGrid authentication):
      Host:     AKAMAI_HOST (e.g., "akab-xxxx.luna.akamaiapis.net")
      Client token:  AKAMAI_CLIENT_TOKEN
      Client secret: AKAMAI_CLIENT_SECRET
      Access token:  AKAMAI_ACCESS_TOKEN
  - Set these as environment variables OR in ~/.edgerc file under [papi] section.
  - Python packages: pip install edgegrid-python requests

USAGE:
  python deploy/akamai/activate.py --contract-id ctr_X-123 --group-id grp_456
  python deploy/akamai/activate.py --contract-id ctr_X-123 --group-id grp_456 --activate-production
  python deploy/akamai/activate.py --contract-id ctr_X-123 --group-id grp_456 --property-id prp_123 --update-only

NOTE: This script does NOT modify DNS. After activation, you must point
      api.bazspark.com CNAME → {edge_hostname}.edgeservices.net at your DNS provider.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

try:
    import requests
    from akamai.edgegrid import EdgeGridAuth
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install edgegrid-python requests")
    sys.exit(1)


# ── Configuration ────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent
REPO_ROOT = SCRIPT_DIR.parent.parent
PROPERTY_MAIN_JSON = SCRIPT_DIR / "property-main.json"
HOSTNAMES_JSON = SCRIPT_DIR / "hostnames.json"

API_BASE = "https://{host}/papi/v1"
POLL_INTERVAL_SECONDS = 30
POLL_MAX_ATTEMPTS = 60  # 30 min total

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("akamai-deploy")

# Placeholder tokens replaced inside the Akamai JSON templates. Defined as
# constants so the literal strings are not duplicated across the script
# (SonarCloud python:S1192) and so the placeholder names are discoverable.
_EDGE_HOSTNAME_PLACEHOLDER = "{EDGE_HOSTNAME}"
_ORIGIN_HOSTNAME_PLACEHOLDER = "{ORIGIN_HOSTNAME}"
_ORIGIN_TOKEN_PLACEHOLDER = "{AKAMAI_ORIGIN_TOKEN}"


def _edge_hostname() -> str:
    """Resolve the edge hostname from env, defaulting to 'bazspark'."""
    return os.getenv("AKAMAI_EDGE_HOSTNAME", "bazspark")


def _origin_hostname() -> str:
    """Resolve the origin hostname from env, defaulting to the HF Space."""
    return os.getenv(
        "AKAMAI_ORIGIN_HOSTNAME", "ahmdelbaz28-bazspark.hf.space"
    )


def _origin_token() -> str:
    """Resolve the Akamai origin token from env (placeholder until rotated)."""
    return os.getenv("AKAMAI_REQUIRE_ORIGIN_TOKEN", "REPLACE_ME")


# ── EdgeGrid auth ────────────────────────────────────────────────────────────


def get_session() -> requests.Session:
    """Create an authenticated session from env vars or ~/.edgerc."""
    host = os.getenv("AKAMAI_HOST")
    client_token = os.getenv("AKAMAI_CLIENT_TOKEN")
    client_secret = os.getenv("AKAMAI_CLIENT_SECRET")
    access_token = os.getenv("AKAMAI_ACCESS_TOKEN")

    if not all([host, client_token, client_secret, access_token]):
        # Try ~/.edgerc
        edgerc_path = os.path.expanduser("~/.edgerc")
        if not os.path.exists(edgerc_path):
            log.error(
                "Missing Akamai credentials. Set env vars AKAMAI_HOST, "
                "AKAMAI_CLIENT_TOKEN, AKAMAI_CLIENT_SECRET, AKAMAI_ACCESS_TOKEN "
                "OR create ~/.edgerc with [papi] section."
            )
            sys.exit(1)
        from configparser import ConfigParser

        cfg = ConfigParser()
        cfg.read(edgerc_path)
        section = "papi"
        host = cfg.get(section, "host")
        client_token = cfg.get(section, "client_token")
        client_secret = cfg.get(section, "client_secret")
        access_token = cfg.get(section, "access_token")

    session = requests.Session()
    session.auth = EdgeGridAuth(client_token, client_secret, access_token)
    session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
    log.info("Akamai session established (host=%s)", host)
    return session


# ── API helpers ──────────────────────────────────────────────────────────────


def _api(session: requests.Session, method: str, path: str, **kwargs) -> dict:
    """Call Akamai Property Manager API."""
    host = os.getenv("AKAMAI_HOST")
    url = f"https://{host}{path}"
    resp = session.request(method, url, timeout=60, **kwargs)
    if resp.status_code >= 400:
        log.error("API %s %s failed: HTTP %d — %s", method, path, resp.status_code, resp.text[:500])
        resp.raise_for_status()
    if not resp.text:
        return {}
    return resp.json()


def find_or_create_property(
    session: requests.Session,
    contract_id: str,
    group_id: str,
    property_name: str = "BAZSPARK",
) -> tuple[str, int]:
    """Find an existing property by name, or create a new one. Returns (property_id, latest_version)."""
    # List existing properties
    data = _api(
        session,
        "GET",
        f"/papi/v1/properties?contractId={contract_id}&groupId={group_id}",
    )
    for prop in data.get("properties", {}).get("items", []):
        if prop["propertyName"] == property_name:
            prop_id = prop["propertyId"]
            # Get latest version
            v_data = _api(
                session,
                "GET",
                f"/papi/v1/properties/{prop_id}/versions?contractId={contract_id}&groupId={group_id}",
            )
            versions = v_data.get("versions", {}).get("items", [])
            latest_version = max(v["propertyVersion"] for v in versions) if versions else 1
            log.info("Found existing property %s (v%d)", prop_id, latest_version)
            return prop_id, latest_version

    # Create new property
    log.info("Creating new property %s ...", property_name)
    body = {
        "propertyName": property_name,
        "contractId": contract_id,
        "groupId": group_id,
        "productId": "prd_SPM",  # Akamai Secure Property Manager
    }
    data = _api(
        session,
        "POST",
        f"/papi/v1/properties?contractId={contract_id}&groupId={group_id}",
        json=body,
    )
    prop_id = data["propertyId"]
    log.info("Created property %s", prop_id)
    return prop_id, 1


def import_rules(
    session: requests.Session,
    contract_id: str,
    group_id: str,
    property_id: str,
    base_version: int,
    rules_json_path: Path,
) -> int:
    """Import rules from a JSON file into a new property version. Returns the new version number."""
    # Create new version from base
    body = {"createFromVersion": base_version}
    data = _api(
        session,
        "POST",
        f"/papi/v1/properties/{property_id}/versions?contractId={contract_id}&groupId={group_id}",
        json=body,
    )
    new_version = data["versionLink"].split("/")[-1]
    new_version = int(new_version)
    log.info("Created new property version %d (from v%d)", new_version, base_version)

    # Update rules
    rules = json.loads(rules_json_path.read_text())
    # Strip the metadata fields — only "rules" is accepted
    if "rules" in rules:
        rules = rules["rules"]
    # Replace placeholders
    rules_str = json.dumps(rules)
    rules_str = rules_str.replace(_ORIGIN_HOSTNAME_PLACEHOLDER, _origin_hostname())
    rules_str = rules_str.replace(_EDGE_HOSTNAME_PLACEHOLDER, _edge_hostname())
    rules_str = rules_str.replace(_ORIGIN_TOKEN_PLACEHOLDER, _origin_token())
    rules = json.loads(rules_str)

    _api(
        session,
        "PUT",
        f"/papi/v1/properties/{property_id}/versions/{new_version}/rules?contractId={contract_id}&groupId={group_id}",
        json=rules,
    )
    log.info("Imported rules into version %d", new_version)
    return new_version


def add_hostnames(
    session: requests.Session,
    contract_id: str,
    group_id: str,
    property_id: str,
    version: int,
) -> list[dict]:
    """Add hostnames to the property version."""
    hostnames_data = json.loads(HOSTNAMES_JSON.read_text())
    added = []
    for hn in hostnames_data.get("hostnames", []):
        cname_from = hn["cnameFrom"].replace(_EDGE_HOSTNAME_PLACEHOLDER, _edge_hostname())
        body = {
            "cnameFrom": cname_from,
            "cnameTo": hn["cnameTo"].replace(_EDGE_HOSTNAME_PLACEHOLDER, _edge_hostname()),
            "certProvisioningType": hn.get("certProvisioningType", "CPS_MANAGED"),
        }
        try:
            _api(
                session,
                "POST",
                f"/papi/v1/properties/{property_id}/versions/{version}/hostnames?contractId={contract_id}&groupId={group_id}",
                json=body,
            )
            log.info("Added hostname %s", cname_from)
            added.append(body)
        except requests.HTTPError as e:
            if e.response.status_code == 409:
                log.info("Hostname %s already exists", cname_from)
            else:
                raise
    return added


def activate(
    session: requests.Session,
    contract_id: str,
    group_id: str,
    property_id: str,
    version: int,
    network: str,  # "STAGING" or "PRODUCTION"
    notify_emails: list[str],
) -> str:
    """Activate a property version on the given network. Returns activation ID."""
    body = {
        "propertyVersion": version,
        "network": network,
        "note": f"BAZSPARK deployment via deploy/akamai/activate.py — {network}",
        "notifyEmails": notify_emails,
        "useFastRules": False,
        "acknowledgeAllWarnings": True,
    }
    data = _api(
        session,
        "POST",
        f"/papi/v1/properties/{property_id}/activations?contractId={contract_id}&groupId={group_id}",
        json=body,
    )
    activation_id = data["activationId"]
    log.info("Activation %s requested on %s", activation_id, network)

    # Poll for completion
    for attempt in range(POLL_MAX_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        data = _api(
            session,
            "GET",
            f"/papi/v1/properties/{property_id}/activations/{activation_id}?contractId={contract_id}&groupId={group_id}",
        )
        status = data.get("status", "")
        log.info("Activation %s status: %s (attempt %d)", activation_id, status, attempt + 1)
        if status == "ACTIVE":
            log.info("✓ Activation %s complete on %s", activation_id, network)
            return activation_id
        if status in ("FAILED", "ABORTED"):
            log.error("✗ Activation %s %s", activation_id, status)
            sys.exit(1)
    log.error("Activation timed out after %d attempts", POLL_MAX_ATTEMPTS)
    sys.exit(1)


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy BAZSPARK Akamai configuration")
    parser.add_argument("--contract-id", required=True, help="Akamai contract ID (ctr_X-...)")
    parser.add_argument("--group-id", required=True, help="Akamai group ID (grp_...)")
    parser.add_argument("--property-id", help="Existing property ID (skip creation)")
    parser.add_argument("--property-name", default="BAZSPARK", help="Property name (default: BAZSPARK)")
    parser.add_argument("--activate-staging", action="store_true", help="Activate on STAGING network")
    parser.add_argument("--activate-production", action="store_true", help="Activate on PRODUCTION network")
    parser.add_argument("--notify-email", action="append", default=[], help="Email for activation notifications")
    parser.add_argument("--update-only", action="store_true", help="Only update rules, don't create new version")
    args = parser.parse_args()

    if not args.notify_email:
        args.notify_email = ["eng.ahmed.elbaz@gmail.com"]

    session = get_session()

    # Step 1: Find or create property
    if args.property_id:
        property_id = args.property_id
        log.info("Using existing property %s", property_id)
        # Get latest version
        v_data = _api(
            session,
            "GET",
            f"/papi/v1/properties/{property_id}/versions?contractId={args.contract_id}&groupId={args.group_id}",
        )
        versions = v_data.get("versions", {}).get("items", [])
        latest_version = max(v["propertyVersion"] for v in versions) if versions else 1
    else:
        property_id, latest_version = find_or_create_property(
            session, args.contract_id, args.group_id, args.property_name
        )

    # Step 2: Import rules (creates new version)
    if args.update_only:
        log.info("--update-only: skipping rule import")
        new_version = latest_version
    else:
        new_version = import_rules(
            session, args.contract_id, args.group_id, property_id, latest_version, PROPERTY_MAIN_JSON
        )

    # Step 3: Add hostnames
    add_hostnames(session, args.contract_id, args.group_id, property_id, new_version)

    # Step 4: Activate
    if args.activate_staging:
        activate(session, args.contract_id, args.group_id, property_id, new_version, "STAGING", args.notify_email)
    if args.activate_production:
        if not args.activate_staging:
            log.warning("Activating production without staging — recommended to test on staging first")
        activate(session, args.contract_id, args.group_id, property_id, new_version, "PRODUCTION", args.notify_email)

    # Step 5: Output DNS instructions
    edge_hostname = os.getenv("AKAMAI_EDGE_HOSTNAME", "bazspark") + ".edgeservices.net"
    print()
    print("=" * 70)
    print("AKAMAI DEPLOYMENT COMPLETE")
    print("=" * 70)
    print(f"Property ID : {property_id}")
    print(f"Version     : {new_version}")
    print(f"Staging     : {'activated' if args.activate_staging else 'NOT activated'}")
    print(f"Production  : {'activated' if args.activate_production else 'NOT activated'}")
    print()
    print("DNS CONFIGURATION REQUIRED:")
    print(f"  api.bazspark.com  CNAME  {edge_hostname}")
    print()
    print("Verification:")
    print("  curl -I https://api.bazspark.com/api/health")
    print("  # Should return 200 with X-Akamai-EdgeWorker: inject-headers")


if __name__ == "__main__":
    main()
