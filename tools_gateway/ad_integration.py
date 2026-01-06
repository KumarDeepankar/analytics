"""
Active Directory Integration Module

Provides LDAP/AD connectivity for:
- Querying AD groups
- Enumerating group members
- Syncing users from AD groups to RBAC system
- Managing group-to-role mappings
"""

import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field

from ldap3 import Server, Connection, ALL, SUBTREE, ALL_ATTRIBUTES
from ldap3.core.exceptions import LDAPException
from .database import database

logger = logging.getLogger(__name__)


@dataclass
class ADGroup:
    """Active Directory Group"""
    name: str
    dn: str  # Distinguished Name
    member_count: int = 0
    members: List[str] = field(default_factory=list)  # List of member DNs


@dataclass
class ADUser:
    """Active Directory User"""
    username: str
    email: str
    display_name: str
    dn: str


@dataclass
class GroupMapping:
    """Mapping between AD Group and RBAC Role"""
    mapping_id: str
    group_dn: str
    role_id: str
    auto_sync: bool = False
    last_sync: Optional[datetime] = None
    synced_users: int = 0


class ADIntegration:
    """
    Active Directory Integration Manager

    Handles LDAP connectivity, group queries, and user synchronization.
    Stores group-to-role mappings in SQLite database.
    """

    def __init__(self):
        self.mappings: Dict[str, GroupMapping] = {}
        self._load_mappings()

    def _load_mappings(self):
        """Load group-to-role mappings from database"""
        try:
            db_mappings = database.get_all_ad_mappings()
            self.mappings = {}
            for mapping_dict in db_mappings:
                # Convert database dict to GroupMapping object
                mapping = GroupMapping(
                    mapping_id=mapping_dict['mapping_id'],
                    group_dn=mapping_dict['group_dn'],
                    role_id=mapping_dict['role_id'],
                    auto_sync=bool(mapping_dict['auto_sync']),
                    last_sync=datetime.fromisoformat(mapping_dict['last_sync']) if mapping_dict.get('last_sync') else None,
                    synced_users=mapping_dict.get('synced_users', 0)
                )
                self.mappings[mapping.mapping_id] = mapping
            logger.info(f"Loaded {len(self.mappings)} AD group mappings from database")
        except Exception as e:
            logger.error(f"Error loading AD mappings from database: {e}")
            self.mappings = {}

    def _save_mappings(self):
        """Save group-to-role mappings to database"""
        try:
            for mapping_id, mapping in self.mappings.items():
                database.save_ad_mapping(
                    mapping_id=mapping.mapping_id,
                    group_dn=mapping.group_dn,
                    role_id=mapping.role_id,
                    auto_sync=mapping.auto_sync,
                    synced_users=mapping.synced_users
                )
            logger.info(f"Saved {len(self.mappings)} AD group mappings to database")
        except Exception as e:
            logger.error(f"Error saving AD mappings to database: {e}")

    def _connect_to_ad(
        self,
        server: str,
        port: int,
        bind_dn: str,
        bind_password: str,
        use_ssl: bool = False
    ) -> Optional[Connection]:
        """
        Establish connection to Active Directory

        Args:
            server: AD server hostname or IP
            port: LDAP port (389 for LDAP, 636 for LDAPS)
            bind_dn: Distinguished Name for binding
            bind_password: Password for binding
            use_ssl: Whether to use SSL/TLS

        Returns:
            LDAP Connection object or None if failed
        """
        try:
            ldap_server = Server(server, port=port, use_ssl=use_ssl, get_info=ALL)
            conn = Connection(
                ldap_server,
                user=bind_dn,
                password=bind_password,
                auto_bind=True
            )
            logger.info(f"Successfully connected to AD server: {server}")
            return conn
        except LDAPException as e:
            logger.error(f"LDAP connection error: {e}")
            raise Exception(f"Failed to connect to AD: {str(e)}")
        except Exception as e:
            logger.error(f"AD connection error: {e}")
            raise Exception(f"Failed to connect to AD: {str(e)}")

    def query_groups(
        self,
        server: str,
        port: int,
        bind_dn: str,
        bind_password: str,
        base_dn: str,
        group_filter: str = "(objectClass=group)",
        use_ssl: bool = False
    ) -> List[ADGroup]:
        """
        Query Active Directory for groups

        Args:
            server: AD server hostname or IP
            port: LDAP port
            bind_dn: Distinguished Name for binding
            bind_password: Password for binding
            base_dn: Base DN to search from
            group_filter: LDAP filter for groups
            use_ssl: Whether to use SSL/TLS

        Returns:
            List of ADGroup objects
        """
        conn = None
        try:
            conn = self._connect_to_ad(server, port, bind_dn, bind_password, use_ssl)

            # Search for groups - use flexible attributes for compatibility
            conn.search(
                search_base=base_dn,
                search_filter=group_filter,
                search_scope=SUBTREE,
                attributes=['cn', 'ou', 'distinguishedName', 'member', 'uniqueMember', 'memberUid']
            )

            groups = []
            for entry in conn.entries:
                # Get group name from cn or ou
                group_name = 'Unknown'
                if hasattr(entry, 'cn'):
                    group_name = str(entry.cn)
                elif hasattr(entry, 'ou'):
                    group_name = str(entry.ou)

                # Get DN - handle both distinguishedName and entry_dn
                group_dn = str(entry.entry_dn)

                # Get members - support multiple LDAP member attributes
                members = []
                if hasattr(entry, 'member'):
                    members = entry.member.values if entry.member else []
                elif hasattr(entry, 'uniqueMember'):
                    members = entry.uniqueMember.values if entry.uniqueMember else []
                elif hasattr(entry, 'memberUid'):
                    members = entry.memberUid.values if entry.memberUid else []

                groups.append(ADGroup(
                    name=group_name,
                    dn=group_dn,
                    member_count=len(members),
                    members=members
                ))

            logger.info(f"Found {len(groups)} groups in LDAP")
            return groups

        except Exception as e:
            logger.error(f"Error querying LDAP groups: {e}")
            raise
        finally:
            if conn:
                conn.unbind()

    def query_users(
        self,
        server: str,
        port: int,
        bind_dn: str,
        bind_password: str,
        base_dn: str,
        user_filter: str = "(objectClass=person)",
        use_ssl: bool = False
    ) -> List[ADUser]:
        """
        Query Active Directory for users directly

        Args:
            server: AD server hostname or IP
            port: LDAP port
            bind_dn: Distinguished Name for binding
            bind_password: Password for binding
            base_dn: Base DN to search from
            user_filter: LDAP filter for users
            use_ssl: Whether to use SSL/TLS

        Returns:
            List of ADUser objects
        """
        conn = None
        try:
            conn = self._connect_to_ad(server, port, bind_dn, bind_password, use_ssl)

            # Search for users - support multiple user object classes
            conn.search(
                search_base=base_dn,
                search_filter=user_filter,
                search_scope=SUBTREE,
                attributes=ALL_ATTRIBUTES
            )

            users = []
            for entry in conn.entries:
                try:
                    # Get username - support multiple attributes
                    username = None
                    if hasattr(entry, 'uid'):
                        username = str(entry.uid)
                    elif hasattr(entry, 'sAMAccountName'):
                        username = str(entry.sAMAccountName)
                    elif hasattr(entry, 'cn'):
                        username = str(entry.cn)

                    # Get email - support multiple attributes
                    email = None
                    if hasattr(entry, 'mail'):
                        email = str(entry.mail)

                    # Generate email if not present (for testing)
                    if not email and username:
                        email = f"{username}@example.com"

                    # Get display name - support multiple attributes
                    display_name = None
                    if hasattr(entry, 'displayName'):
                        display_name = str(entry.displayName)
                    elif hasattr(entry, 'cn'):
                        display_name = str(entry.cn)
                    elif hasattr(entry, 'givenName') and hasattr(entry, 'sn'):
                        display_name = f"{entry.givenName} {entry.sn}"

                    # Get DN
                    user_dn = str(entry.entry_dn)

                    if username:
                        users.append(ADUser(
                            username=username,
                            email=email or f"{username}@example.com",
                            display_name=display_name or username,
                            dn=user_dn
                        ))
                except Exception as e:
                    logger.warning(f"Error processing user entry: {e}")
                    continue

            logger.info(f"Found {len(users)} users in LDAP")
            return users

        except Exception as e:
            logger.error(f"Error querying LDAP users: {e}")
            raise
        finally:
            if conn:
                conn.unbind()

    def get_group_members(
        self,
        server: str,
        port: int,
        bind_dn: str,
        bind_password: str,
        group_dn: str,
        use_ssl: bool = False
    ) -> List[ADUser]:
        """
        Get all members of a specific LDAP/AD group

        Args:
            server: LDAP server hostname or IP
            port: LDAP port
            bind_dn: Distinguished Name for binding
            bind_password: Password for binding
            group_dn: Distinguished Name of the group
            use_ssl: Whether to use SSL/TLS

        Returns:
            List of ADUser objects
        """
        conn = None
        try:
            conn = self._connect_to_ad(server, port, bind_dn, bind_password, use_ssl)

            # First get the group and its members - support multiple group types
            conn.search(
                search_base=group_dn,
                search_filter='(objectClass=*)',
                search_scope=SUBTREE,
                attributes=['member', 'uniqueMember', 'memberUid']
            )

            if not conn.entries:
                logger.warning(f"Group not found: {group_dn}")
                return []

            # Extract member DNs - support different LDAP member attributes
            member_dns = []
            entry = conn.entries[0]
            if hasattr(entry, 'member') and entry.member:
                member_dns = entry.member.values
            elif hasattr(entry, 'uniqueMember') and entry.uniqueMember:
                member_dns = entry.uniqueMember.values
            elif hasattr(entry, 'memberUid') and entry.memberUid:
                # memberUid contains just usernames, not DNs - need to construct DNs
                member_uids = entry.memberUid.values
                base_user_dn = group_dn.split(',', 1)[1] if ',' in group_dn else group_dn
                member_dns = [f"uid={uid},{base_user_dn}" for uid in member_uids]

            users = []
            # Query each member for user details
            for member_dn in member_dns:
                try:
                    # Use BASE scope to query specific DN
                    # Request all attributes first to see what's available
                    from ldap3 import BASE, ALL_ATTRIBUTES
                    conn.search(
                        search_base=member_dn,
                        search_filter='(objectClass=*)',
                        search_scope=BASE,
                        attributes=ALL_ATTRIBUTES
                    )

                    if conn.entries:
                        entry = conn.entries[0]

                        # Get username - support multiple attributes
                        username = None
                        if hasattr(entry, 'uid'):
                            username = str(entry.uid)
                        elif hasattr(entry, 'sAMAccountName'):
                            username = str(entry.sAMAccountName)
                        elif hasattr(entry, 'cn'):
                            username = str(entry.cn)

                        # Get email - support multiple attributes
                        email = None
                        if hasattr(entry, 'mail'):
                            email = str(entry.mail)

                        # Generate email if not present (for testing)
                        if not email and username:
                            email = f"{username}@example.com"

                        # Get display name - support multiple attributes
                        display_name = None
                        if hasattr(entry, 'displayName'):
                            display_name = str(entry.displayName)
                        elif hasattr(entry, 'cn'):
                            display_name = str(entry.cn)
                        elif hasattr(entry, 'givenName') and hasattr(entry, 'sn'):
                            display_name = f"{entry.givenName} {entry.sn}"

                        if username:
                            users.append(ADUser(
                                username=username,
                                email=email or f"{username}@example.com",
                                display_name=display_name or username,
                                dn=member_dn
                            ))
                except Exception as e:
                    logger.warning(f"Error querying member {member_dn}: {e}")
                    continue

            logger.info(f"Found {len(users)} users in group {group_dn}")
            return users

        except Exception as e:
            logger.error(f"Error getting group members: {e}")
            raise
        finally:
            if conn:
                conn.unbind()

    def add_group_mapping(
        self,
        group_dn: str,
        role_id: str,
        auto_sync: bool = False
    ) -> GroupMapping:
        """
        Create a mapping between an AD group and an RBAC role

        Args:
            group_dn: Distinguished Name of the AD group
            role_id: RBAC role ID
            auto_sync: Whether to automatically sync users from this group

        Returns:
            Created GroupMapping object
        """
        import uuid

        mapping_id = str(uuid.uuid4())
        mapping = GroupMapping(
            mapping_id=mapping_id,
            group_dn=group_dn,
            role_id=role_id,
            auto_sync=auto_sync,
            last_sync=None,
            synced_users=0
        )

        self.mappings[mapping_id] = mapping
        self._save_mappings()

        logger.info(f"Created AD group mapping: {group_dn} -> {role_id}")
        return mapping

    def remove_group_mapping(self, mapping_id: str) -> bool:
        """Remove a group-to-role mapping"""
        if mapping_id in self.mappings:
            del self.mappings[mapping_id]
            database.delete_ad_mapping(mapping_id)
            logger.info(f"Removed AD group mapping: {mapping_id}")
            return True
        return False

    def get_mapping_by_group(self, group_dn: str) -> Optional[GroupMapping]:
        """Get mapping by group DN"""
        for mapping in self.mappings.values():
            if mapping.group_dn == group_dn:
                return mapping
        return None

    def list_mappings(self) -> List[GroupMapping]:
        """List all group-to-role mappings"""
        return list(self.mappings.values())

    def update_mapping_sync_status(
        self,
        mapping_id: str,
        synced_users: int
    ):
        """Update the last sync time and count for a mapping"""
        if mapping_id in self.mappings:
            self.mappings[mapping_id].last_sync = datetime.now()
            self.mappings[mapping_id].synced_users = synced_users
            database.update_ad_mapping_sync(mapping_id, synced_users)


# Global instance
ad_integration = ADIntegration()
