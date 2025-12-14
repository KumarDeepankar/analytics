#!/usr/bin/env python3
"""
Safe Orphaned Entity Cleanup Script

Interactive cleanup of entities with no relationships.
Shows you what will be deleted before doing it.

Usage:
    python cleanup_orphaned_entities.py
    python cleanup_orphaned_entities.py --auto  # Skip confirmation

IMPORTANT: Only run this if you're certain orphaned entities are invalid.
Disjoint graphs are valid - isolated entities might be semantically meaningful!

See ENTITY_CLEANUP_STRATEGY.md for more information.
"""

import json
import argparse
from neo4j import GraphDatabase
from pathlib import Path

def load_config(config_path: str = "config.json") -> dict:
    """Load Neo4j configuration from config file."""
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        config = json.load(f)

    # Validate required fields
    if 'neo4j' not in config:
        raise ValueError("Missing 'neo4j' section in config")

    required_fields = ['uri', 'username', 'password', 'database']
    for field in required_fields:
        if field not in config['neo4j']:
            raise ValueError(f"Missing required field: neo4j.{field}")

    return config['neo4j']

def find_orphaned_entities(session) -> list:
    """Find all entities with no relationships."""
    result = session.run("""
        MATCH (e:__Entity__)
        WHERE NOT (e)-[]-()
        RETURN e.id as entity_id
        ORDER BY entity_id
    """)

    return [record['entity_id'] for record in result]

def get_entity_stats(session) -> dict:
    """Get statistics about entities."""
    # Total entities
    result = session.run("MATCH (e:__Entity__) RETURN count(e) as count")
    total = result.single()['count']

    # Orphaned entities
    result = session.run("""
        MATCH (e:__Entity__)
        WHERE NOT (e)-[]-()
        RETURN count(e) as count
    """)
    orphaned = result.single()['count']

    # Connected entities
    connected = total - orphaned

    # Percentage
    percentage = (orphaned * 100.0 / total) if total > 0 else 0

    return {
        'total': total,
        'connected': connected,
        'orphaned': orphaned,
        'percentage': percentage
    }

def delete_orphaned_entities(session) -> int:
    """Delete all orphaned entities and return count."""
    result = session.run("""
        MATCH (e:__Entity__)
        WHERE NOT (e)-[]-()
        DELETE e
        RETURN count(e) as deleted
    """)

    return result.single()['deleted']

def main():
    parser = argparse.ArgumentParser(
        description='Clean orphaned entities from Neo4j knowledge graph'
    )
    parser.add_argument(
        '--config',
        default='config.json',
        help='Path to config file (default: config.json)'
    )
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Skip confirmation prompt (dangerous!)'
    )
    parser.add_argument(
        '--stats-only',
        action='store_true',
        help='Show statistics only, do not delete'
    )

    args = parser.parse_args()

    # Load config
    try:
        neo4j_config = load_config(args.config)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return 1

    # Connect to Neo4j
    try:
        driver = GraphDatabase.driver(
            neo4j_config['uri'],
            auth=(neo4j_config['username'], neo4j_config['password'])
        )
    except Exception as e:
        print(f"❌ Error connecting to Neo4j: {e}")
        return 1

    try:
        with driver.session(database=neo4j_config['database']) as session:
            # Get statistics
            print("\n=== Entity Statistics ===")
            stats = get_entity_stats(session)
            print(f"Total entities:     {stats['total']:,}")
            print(f"Connected entities: {stats['connected']:,}")
            print(f"Orphaned entities:  {stats['orphaned']:,} ({stats['percentage']:.1f}%)")

            if stats['orphaned'] == 0:
                print("\n✓ No orphaned entities found")
                return 0

            # Stats only mode
            if args.stats_only:
                print("\n(Use without --stats-only to delete)")
                return 0

            # Find orphaned entities
            print("\n=== Finding Orphaned Entities ===")
            orphaned = find_orphaned_entities(session)

            # Show samples
            print(f"\nFound {len(orphaned)} orphaned entities:")
            for i, entity_id in enumerate(orphaned[:20]):
                print(f"  {i+1:3d}. {entity_id}")

            if len(orphaned) > 20:
                print(f"  ... and {len(orphaned) - 20:,} more")

            # Confirmation
            if not args.auto:
                print("\n⚠️  WARNING: This will permanently delete these entities!")
                print("⚠️  Make sure orphaned entities are actually invalid.")
                print("⚠️  Disjoint graphs are valid - isolated entities might be meaningful.")
                print("\nSee ENTITY_CLEANUP_STRATEGY.md for more information.")

                response = input(f"\nDelete all {len(orphaned):,} orphaned entities? (yes/no): ")

                if response.lower() != 'yes':
                    print("❌ Cancelled")
                    return 0

            # Delete
            print("\n=== Deleting Orphaned Entities ===")
            deleted = delete_orphaned_entities(session)
            print(f"✓ Deleted {deleted:,} orphaned entities")

            # Final stats
            print("\n=== Final Statistics ===")
            final_stats = get_entity_stats(session)
            print(f"Total entities:     {final_stats['total']:,}")
            print(f"Connected entities: {final_stats['connected']:,}")
            print(f"Orphaned entities:  {final_stats['orphaned']:,}")

            return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        driver.close()

if __name__ == '__main__':
    exit(main())
