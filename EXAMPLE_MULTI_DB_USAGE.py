#!/usr/bin/env python3
"""
EXAMPLE_MULTI_DB_USAGE.py — Multi-Database Usage Examples
======================================================

Examples showing how to use the multi-database system with:
- PostgreSQL (primary database)
- Qdrant (vector database)
- Neo4j (graph database)
- Redis (cache/database)
"""

from backend.multi_db_service import get_multi_db_service


def example_redis_usage():
    """Example usage of Redis for caching."""
    print("🔸 Redis Examples:")

    db_service = get_multi_db_service()

    # Set a value with expiration (1 hour)
    success = db_service.redis_set("example_key", "Hello, Redis!", ex=3600)
    if success:
        print("  ✓ Set value in Redis")
    else:
        print("  ✗ Failed to set value in Redis (check connection)")

    # Get the value
    value = db_service.redis_get("example_key")
    if value:
        print(f"  ✓ Retrieved value: {value}")
    else:
        print("  ✗ Failed to get value from Redis")

    # Clean up
    if value:
        db_service.redis_delete("example_key")
        print("  ✓ Deleted key from Redis")


def example_qdrant_usage():
    """Example usage of Qdrant for vector operations."""
    print("\n🔹 Qdrant Examples:")

    db_service = get_multi_db_service()
    qdrant_client = db_service.get_qdrant()

    if qdrant_client:
        try:
            # List collections to verify connection
            collections = qdrant_client.get_collections()
            print(f"  ✓ Connected to Qdrant, found {len(collections.collections)} collections")

            # Example: Create a collection (if needed)
            # Note: This is just an example - in practice you'd want to check if it exists first
            # qdrant_client.recreate_collection(
            #     collection_name="examples",
            #     vectors_config=models.VectorParams(size=4, distance=models.Distance.DOT)
            # )

            print("  ✓ Qdrant connection verified")
        except Exception as e:
            print(f"  ✗ Qdrant connection error: {e}")
    else:
        print("  ✗ Qdrant not available (install with: pip install qdrant-client)")


def example_neo4j_usage():
    """Example usage of Neo4j for graph operations."""
    print("\n🔹 Neo4j Examples:")

    db_service = get_multi_db_service()
    neo4j_driver = db_service.get_neo4j()

    if neo4j_driver:
        try:
            # Test connection with a simple query
            result = db_service.neo4j_execute_query("RETURN 'Hello, Neo4j!' AS greeting")
            if result:
                print(f"  ✓ Connected to Neo4j, greeting: {result[0]['greeting']}")
            else:
                print("  ⚠ Could not execute Neo4j query")
        except Exception as e:
            print(f"  ✗ Neo4j connection error: {e}")
    else:
        print("  ✗ Neo4j not available (install with: pip install neo4j)")


def example_postgres_usage():
    """Example usage of PostgreSQL for relational operations."""
    print("\n🔹 PostgreSQL Examples:")

    db_service = get_multi_db_service()
    postgres_pool = db_service.get_postgres_pool()

    if postgres_pool:
        try:
            # Test with a simple query
            result = db_service.postgres_execute("SELECT version();")
            if result:
                print("  ✓ Connected to PostgreSQL, version info received")
            else:
                print("  ⚠ Could not execute PostgreSQL query")
        except Exception as e:
            print(f"  ✗ PostgreSQL connection error: {e}")
    else:
        print("  ✗ PostgreSQL not available (install with: pip install psycopg2-binary)")


def example_health_check():
    """Example of checking health of all databases."""
    print("\n🏥 Database Health Check:")

    db_service = get_multi_db_service()
    health = db_service.health_check()

    for db_name, is_connected in health.items():
        status = "✓" if is_connected else "✗"
        print(f"  {status} {db_name.capitalize()}: {'Connected' if is_connected else 'Not connected'}")


def main():
    """Main function to run all examples."""
    print("🏗️  Revit Project - Multi-Database Usage Examples")
    print("=" * 50)

    print("\nThis script demonstrates how to use the multi-database system.")
    print("Make sure your environment variables are properly configured.")

    # Run examples
    example_health_check()
    example_redis_usage()
    example_qdrant_usage()
    example_neo4j_usage()
    example_postgres_usage()

    print("\n💡 Remember to install required packages:")
    print("   pip install psycopg2-binary qdrant-client neo4j redis")


if __name__ == "__main__":
    main()
