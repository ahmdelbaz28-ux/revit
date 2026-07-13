#!/usr/bin/env python3
"""
BAZSPARK — API Key Generator Script

This script connects to the BAZSPARK backend (HuggingFace Space) and generates
new API keys for users. You need an ADMIN API key to generate new keys.

USAGE:
  # Generate an engineer key (default)
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --role engineer --description "John Doe"

  # Generate an admin key
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --role admin --description "Site Admin"

  # Generate a viewer key (read-only)
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --role viewer --description "Guest User"

  # List all existing keys
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --list

  # Delete a key by hash
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --delete "key_hash_here"

  # Use a custom backend URL (default: https://ahmdelbaz28-bazspark.hf.space)
  python3 scripts/generate_api_key.py --admin-key "fireai_xxx" --backend "http://localhost:8000" --role engineer

PREREQUISITES:
  - You need the ADMIN API key (set as FIREAI_API_KEY in HuggingFace Space secrets)
  - If you don't have the admin key, see README_API_KEYS.md for how to get it

ROLES:
  - admin    : Full access (manage keys, all features)
  - engineer : Engineering access (design, calculate, export — no key management)
  - viewer   : Read-only access (view projects, reports — no modifications)
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

DEFAULT_BACKEND = "https://ahmdelbaz28-bazspark.hf.space"
VALID_ROLES = ["admin", "engineer", "viewer"]


def api_call(backend: str, admin_key: str, method: str, path: str, body: dict = None) -> dict:
	"""Make an authenticated API call to the BAZSPARK backend."""
	url = f"{backend}/api/v1{path}"
	headers = {
		"X-API-Key": admin_key,
		"Content-Type": "application/json",
	}
	data = json.dumps(body).encode("utf-8") if body else None

	req = urllib.request.Request(url, data=data, method=method, headers=headers)
	try:
		with urllib.request.urlopen(req, timeout=30) as response:
			return json.loads(response.read().decode("utf-8"))
	except urllib.error.HTTPError as e:
		error_body = e.read().decode("utf-8", errors="replace")
		try:
			error_data = json.loads(error_body)
			error_msg = error_data.get("detail") or error_data.get("message") or error_body
		except json.JSONDecodeError:
			error_msg = error_body
		print(f"\n❌ Error ({e.code}): {error_msg}", file=sys.stderr)
		if e.code == 401:
			print("   → The admin API key is invalid or expired.", file=sys.stderr)
		elif e.code == 403:
			print("   → The API key does not have admin permissions.", file=sys.stderr)
		elif e.code == 429:
			print("   → Too many requests. Wait a few minutes and try again.", file=sys.stderr)
		sys.exit(1)
	except urllib.error.URLError as e:
		print(f"\n❌ Cannot connect to backend: {e}", file=sys.stderr)
		print(f"   → Check your internet connection or backend URL: {backend}", file=sys.stderr)
		sys.exit(1)


def generate_key(backend: str, admin_key: str, role: str, description: str) -> None:
	"""Generate a new API key."""
	if role not in VALID_ROLES:
		print(f"❌ Invalid role '{role}'. Valid roles: {', '.join(VALID_ROLES)}", file=sys.stderr)
		sys.exit(1)

	print(f"\n🔑 Generating {role.upper()} API key...")
	print(f"   Description: {description or '(none)'}")
	print(f"   Backend: {backend}")
	print()

	result = api_call(backend, admin_key, "POST", "/admin/keys", {
		"role": role,
		"description": description,
	})

	if result.get("success"):
		key_data = result.get("data", {})
		plaintext_key = key_data.get("key")

		print("✅ API Key Generated Successfully!")
		print("=" * 60)
		print(f"  Role:        {key_data.get('role', role)}")
		print(f"  Description: {key_data.get('description', description)}")
		print()
		print("  🔑 YOUR API KEY (save this — it cannot be retrieved later):")
		print()
		print(f"     {plaintext_key}")
		print()
		print("  ⚠️  Store this key securely. You will NOT see it again.")
		print("=" * 60)
		print()
		print("To use this key:")
		print(f"  1. Go to: https://ba-zspark.vercel.app")
		print(f"  2. Paste the key in the 'API Key' field")
		print(f"  3. Click 'Sign In'")
	else:
		print(f"❌ Failed: {result}", file=sys.stderr)
		sys.exit(1)


def list_keys(backend: str, admin_key: str) -> None:
	"""List all API keys."""
	print(f"\n📋 Listing all API keys from {backend}...")
	print()

	result = api_call(backend, admin_key, "GET", "/admin/keys")

	if result.get("success"):
		keys = result.get("data", [])
		if not keys:
			print("  No API keys found.")
			return

		print(f"  Found {len(keys)} API key(s):")
		print()
		print(f"  {'#':<4} {'Role':<12} {'Description':<30} {'Key Hash (first 16 chars)'}")
		print(f"  {'-'*4} {'-'*12} {'-'*30} {'-'*24}")
		for i, key in enumerate(keys, 1):
			role = key.get("role", "?")
			desc = key.get("description", "") or "(no description)"
			kh = key.get("key_hash", "")[:16]
			print(f"  {i:<4} {role:<12} {desc[:30]:<30} {kh}...")
		print()
		print("  Note: Full key values are never stored — only hashes.")
	else:
		print(f"❌ Failed: {result}", file=sys.stderr)
		sys.exit(1)


def delete_key(backend: str, admin_key: str, key_hash: str) -> None:
	"""Delete an API key by hash."""
	print(f"\n🗑️  Deleting API key {key_hash[:16]}...")
	print()

	result = api_call(backend, admin_key, "DELETE", f"/admin/keys/{key_hash}")

	if result.get("success"):
		print("✅ API key deleted successfully.")
	else:
		print(f"❌ Failed: {result}", file=sys.stderr)
		sys.exit(1)


def list_roles(backend: str, admin_key: str) -> None:
	"""List available roles and permissions."""
	print(f"\n👥 Available roles and permissions...")
	print()

	result = api_call(backend, admin_key, "GET", "/admin/keys/roles")

	if result.get("success"):
		roles = result.get("data", {})
		for role_name, role_info in roles.items():
			perms = role_info.get("permissions", [])
			print(f"  {role_name.upper()}")
			print(f"    Permissions ({role_info.get('permission_count', 0)}):")
			for perm in perms:
				print(f"      • {perm}")
			print()
	else:
		print(f"❌ Failed: {result}", file=sys.stderr)
		sys.exit(1)


def main() -> None:
	parser = argparse.ArgumentParser(
		description="BAZSPARK API Key Generator",
		formatter_class=argparse.RawDescriptionHelpFormatter,
		epilog=__doc__,
	)
	parser.add_argument(
		"--admin-key",
		required=True,
		help="The ADMIN API key (required to manage keys)",
	)
	parser.add_argument(
		"--backend",
		default=DEFAULT_BACKEND,
		help=f"Backend URL (default: {DEFAULT_BACKEND})",
	)
	parser.add_argument(
		"--role",
		choices=VALID_ROLES,
		help="Role for the new key (admin, engineer, viewer)",
	)
	parser.add_argument(
		"--description",
		default="",
		help="Description for the new key (e.g., user name)",
	)
	parser.add_argument(
		"--list",
		action="store_true",
		help="List all existing API keys",
	)
	parser.add_argument(
		"--roles",
		action="store_true",
		help="List available roles and permissions",
	)
	parser.add_argument(
		"--delete",
		metavar="KEY_HASH",
		help="Delete an API key by its hash",
	)

	args = parser.parse_args()

	# Validate: must specify exactly one action
	actions = [args.role, args.list, args.roles, args.delete]
	active_actions = sum(1 for a in actions if a)
	if active_actions == 0:
		parser.error("Specify an action: --role, --list, --roles, or --delete")
	if active_actions > 1:
		parser.error("Specify only ONE action at a time")

	if args.list:
		list_keys(args.backend, args.admin_key)
	elif args.roles:
		list_roles(args.backend, args.admin_key)
	elif args.delete:
		delete_key(args.backend, args.admin_key, args.delete)
	elif args.role:
		generate_key(args.backend, args.admin_key, args.role, args.description)


if __name__ == "__main__":
	main()
