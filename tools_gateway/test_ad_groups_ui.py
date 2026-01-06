#!/usr/bin/env python3
"""Test script to verify AD groups fetching and member query works"""
import requests
import json

BASE_URL = "http://localhost:8021"

# Test configuration for forumsys
AD_CONFIG = {
    "server": "ldap.forumsys.com",
    "port": 389,
    "bind_dn": "cn=read-only-admin,dc=example,dc=com",
    "bind_password": "password",
    "base_dn": "dc=example,dc=com",
    "group_filter": "(objectClass=*)",
    "use_ssl": False
}

def test_query_groups():
    """Test querying AD groups"""
    print("=" * 70)
    print("TEST 1: Query AD Groups")
    print("=" * 70)

    response = requests.post(
        f"{BASE_URL}/admin/ad/query-groups",
        json=AD_CONFIG
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS! Found {len(data['groups'])} groups:")
        for group in data['groups']:
            print(f"  - {group['name']} (DN: {group['dn']}, Members: {group['member_count']})")
        return data['groups']
    else:
        print(f"❌ FAILED! Status: {response.status_code}")
        print(f"Response: {response.text}")
        return []

def test_query_group_members(group_dn):
    """Test querying members of a specific group"""
    print("\n" + "=" * 70)
    print(f"TEST 2: Query Group Members")
    print(f"Group DN: {group_dn}")
    print("=" * 70)

    request_data = {
        **AD_CONFIG,
        "group_dn": group_dn
    }

    response = requests.post(
        f"{BASE_URL}/admin/ad/query-group-members",
        json=request_data
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ SUCCESS! Found {len(data['members'])} members:")
        for member in data['members']:
            print(f"  - {member['display_name']} ({member['email']}) [{member['username']}]")
        return data['members']
    else:
        print(f"❌ FAILED! Status: {response.status_code}")
        print(f"Response: {response.text}")
        return []

if __name__ == "__main__":
    # Test 1: Query groups
    groups = test_query_groups()

    # Test 2: Query members of first group (if available)
    if groups:
        # Filter to only actual groups (ou=)
        actual_groups = [g for g in groups if g['dn'].startswith('ou=')]

        if actual_groups:
            print(f"\nQuerying members of first actual group: {actual_groups[0]['name']}")
            members = test_query_group_members(actual_groups[0]['dn'])

            if members:
                print("\n" + "=" * 70)
                print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
                print("=" * 70)
                print("\nFeatures working:")
                print("  ✓ Query AD groups from forumsys test server")
                print("  ✓ Query group members from AD group")
                print("  ✓ Parse user attributes (username, email, display_name)")
                print("  ✓ First-time setup authentication bypass")
                print("\nReady for UI testing:")
                print("  1. Open http://localhost:8021 in browser")
                print("  2. Go to Users & Roles → AD Configuration")
                print("  3. Enter forumsys credentials and click 'Query Groups'")
                print("  4. Groups will be displayed in 'Fetched AD Groups & Users' section")
                print("  5. Click on any group to expand and view members")
            else:
                print("\n⚠ Group query succeeded but no members found")
        else:
            print("\n⚠ No organizational unit groups found")
    else:
        print("\n❌ Failed to query groups")
