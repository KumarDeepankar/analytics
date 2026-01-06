#!/usr/bin/env python3
"""
Test script for LDAP connection with forumsys.com test server
"""

import sys
import logging
from ad_integration import ad_integration

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Forumsys LDAP test server credentials
LDAP_SERVER = "ldap.forumsys.com"
LDAP_PORT = 389
BIND_DN = "cn=read-only-admin,dc=example,dc=com"
BIND_PASSWORD = "password"
BASE_DN = "dc=example,dc=com"
GROUP_FILTER = "(|(objectClass=organizationalUnit)(objectClass=groupOfUniqueNames))"

def test_query_groups():
    """Test querying LDAP groups from forumsys"""
    print("\n" + "="*60)
    print("Testing LDAP Group Query - forumsys.com")
    print("="*60)

    try:
        print(f"\nConnecting to: {LDAP_SERVER}:{LDAP_PORT}")
        print(f"Bind DN: {BIND_DN}")
        print(f"Base DN: {BASE_DN}")
        print(f"Filter: {GROUP_FILTER}")

        groups = ad_integration.query_groups(
            server=LDAP_SERVER,
            port=LDAP_PORT,
            bind_dn=BIND_DN,
            bind_password=BIND_PASSWORD,
            base_dn=BASE_DN,
            group_filter=GROUP_FILTER,
            use_ssl=False
        )

        print(f"\n✅ SUCCESS! Found {len(groups)} groups:")
        print("-" * 60)
        for group in groups:
            print(f"\nGroup: {group.name}")
            print(f"  DN: {group.dn}")
            print(f"  Members: {group.member_count}")

        return groups

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        logger.exception("Failed to query groups")
        return None

def test_query_group_members(group_dn, group_name):
    """Test querying group members from forumsys"""
    print("\n" + "="*60)
    print(f"Testing LDAP Group Members - {group_name}")
    print("="*60)

    try:
        print(f"\nGroup DN: {group_dn}")

        members = ad_integration.get_group_members(
            server=LDAP_SERVER,
            port=LDAP_PORT,
            bind_dn=BIND_DN,
            bind_password=BIND_PASSWORD,
            group_dn=group_dn,
            use_ssl=False
        )

        print(f"\n✅ SUCCESS! Found {len(members)} members:")
        print("-" * 60)
        for member in members:
            print(f"\nUser: {member.username}")
            print(f"  Email: {member.email}")
            print(f"  Name: {member.display_name}")
            print(f"  DN: {member.dn}")

        return members

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        logger.exception("Failed to query group members")
        return None

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("LDAP Integration Test - forumsys.com")
    print("="*60)

    # Test 1: Query groups
    groups = test_query_groups()

    if not groups:
        print("\n❌ Failed to retrieve groups. Exiting.")
        return 1

    # Test 2: Query members from each group
    for group in groups:
        members = test_query_group_members(group.dn, group.name)
        if members:
            print(f"\n✅ Group '{group.name}' has {len(members)} members")

    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
    print("="*60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
