#!/usr/bin/env python3
"""
BIM_MULTI_DB_EXAMPLE.py — BIM/CAD Multi-Database Workflow Example
==============================================================

Complete example showing how to use the multi-database system for
BIM/CAD applications with PostgreSQL, Qdrant, Neo4j, and Redis.
"""

import secrets
from typing import Dict, List

from backend.multi_db_service import get_multi_db_service


def simulate_bim_element_data(element_id: str) -> Dict:
    """Simulate BIM element data for demonstration."""
    element_types = ["wall", "door", "window", "column", "beam", "floor"]
    categories = ["Architecture", "Structural", "MEP"]

    return {
        "element_id": element_id,
        "type": secrets.choice(element_types),
        "category": secrets.choice(categories),
        "name": f"{secrets.choice(element_types)}_{element_id}",
        "level": f"Level_{1 + secrets.randbelow(4)}",
        "coordinates": [random.uniform(0, 100), random.uniform(0, 100), random.uniform(0, 30)],
        "dimensions": [random.uniform(1, 20), random.uniform(0.1, 5), random.uniform(2, 10)],
        "material": secrets.choice(["Concrete", "Steel", "Wood", "Glass"]),
        "properties": {
            "fire_rating": secrets.choice(["1-hour", "2-hour", "3-hour", "non-rated"]),
            "thermal_resistance": round(random.uniform(0.5, 5.0), 2),
            "cost_per_unit": round(random.uniform(50, 500), 2)
        },
        "created_at": "2024-01-01T00:00:00Z"
    }


def simulate_embeddings(vector_size: int = 1536) -> List[float]:
    """Simulate embeddings for vector search."""
    return [random.random() for _ in range(vector_size)]


def simulate_relationships(element_ids: List[str], count: int) -> List[str]:
    """Simulate relationships between elements."""
    relationships = []
    for _ in range(count):
        if len(element_ids) > 1:
            relationships.append(secrets.choice(element_ids))
    return list(set(relationships))  # Remove duplicates


def example_bim_workflow():
    """Demonstrate a complete BIM workflow using all databases."""
    print("🏢 BIM/CAD Multi-Database Workflow Example")
    print("=" * 50)

    db_service = get_multi_db_service()

    # Step 1: Create sample BIM elements
    print("\n🔍 Step 1: Creating sample BIM elements...")
    element_ids = [f"element_{i:03d}" for i in range(1, 6)]

    for element_id in element_ids:
        element_data = simulate_bim_element_data(element_id)

        # Store in PostgreSQL (primary storage)
        print(f"  📦 Storing {element_id} in PostgreSQL...")
        # In a real application, you would use the database service to store in PostgreSQL

        # Cache in Redis for quick access
        print(f"  ⚡ Caching {element_id} in Redis...")
        success = db_service.cache_bim_element(element_id, element_data)
        if success:
            print(f"    ✓ Cached {element_id}")
        else:
            print(f"    ✗ Failed to cache {element_id}")

    # Step 2: Process embeddings for vector search
    print("\n🧮 Step 2: Processing embeddings for vector search...")
    for element_id in element_ids:
        embeddings = simulate_embeddings()

        # Store embeddings in Qdrant
        print(f"  🔍 Storing embeddings for {element_id} in Qdrant...")
        success = db_service.store_element_embeddings(element_id, embeddings)
        if success:
            print(f"    ✓ Embeddings stored for {element_id}")
        else:
            print(f"    ✗ Failed to store embeddings for {element_id}")

    # Step 3: Create relationships in Neo4j
    print("\n🔗 Step 3: Creating element relationships in Neo4j...")
    for element_id in element_ids:
        related_elements = simulate_relationships([eid for eid in element_ids if eid != element_id], 2)

        if related_elements:
            print(f"  Creating relationships for {element_id} -> {related_elements}")
            success = db_service.create_element_relationships(element_id, related_elements)
            if success:
                print(f"    ✓ Relationships created for {element_id}")
            else:
                print(f"    ✗ Failed to create relationships for {element_id}")

    # Step 4: Demonstrate search capabilities
    print("\n🔍 Step 4: Demonstrating search capabilities...")

    # Redis cache lookup
    print("  🧩 Cache lookup example:")
    sample_element = element_ids[0]
    cached_data = db_service.get_cached_bim_element(sample_element)
    if cached_data:
        print(f"    ✓ Found {sample_element} in cache: {cached_data['type']} in {cached_data['level']}")
    else:
        print(f"    ✗ Element {sample_element} not found in cache")

    # Vector similarity search
    print("  🔍 Vector similarity search example:")
    query_embedding = simulate_embeddings()
    similar_elements = db_service.find_similar_elements(query_embedding, limit=3)
    if similar_elements:
        print(f"    ✓ Found {len(similar_elements)} similar elements:")
        for elem in similar_elements:
            print(f"      - {elem['element_id']} (score: {elem['score']:.3f})")
    else:
        print("    ⚠ No similar elements found (Qdrant may not be configured)")

    # Relationship traversal
    print("  🔗 Relationship traversal example:")
    related_to_sample = db_service.neo4j_find_related_elements(sample_element)
    if related_to_sample:
        print(f"    ✓ Found {len(related_to_sample)} related elements to {sample_element}")
        for item in related_to_sample:
            print(f"      - Related element: {item}")
    else:
        print(f"    ⚠ No related elements found for {sample_element} (Neo4j may not be configured)")

    print("\n✅ BIM/CAD Multi-Database Workflow Complete!")


def example_performance_comparison():
    """Compare performance of different database types for various operations."""
    print("\n⏱️  Performance Comparison Example")
    print("=" * 40)

    get_multi_db_service()

    # Simulate different types of queries
    print("\n  Query Types & Recommended Database:")
    print("  • Element lookup by ID:        Redis (fastest) <- Cache frequently accessed elements")
    print("  • Complex joins/relations:      PostgreSQL <- Relational data with ACID")
    print("  • Similarity search:            Qdrant <- Vector embeddings for ML/AI")
    print("  • Topology/graph traversal:     Neo4j <- Relationships and connections")
    print("  • BIM element properties:       PostgreSQL <- Structured data storage")
    print("  • Element caching:              Redis <- Temporary storage for speed")
    print("  • Semantic search:              Qdrant <- Natural language queries")
    print("  • System relationships:         Neo4j <- Hierarchical structures")


def example_error_handling():
    """Demonstrate error handling when databases are unavailable."""
    print("\n🛡️  Error Handling Example")
    print("=" * 30)

    db_service = get_multi_db_service()
    health = db_service.health_check()

    print("\n  Current database availability:")
    for db_name, is_available in health.items():
        status = "✅" if is_available else "❌"
        print(f"    {status} {db_name.capitalize()}: {'Available' if is_available else 'Unavailable'}")

    print("\n  The system gracefully degrades when databases are unavailable:")
    print("  • If Redis is down: Cache misses, slower repeated queries")
    print("  • If Qdrant is down: No similarity search capability")
    print("  • If Neo4j is down: No relationship/graph queries")
    print("  • If PostgreSQL is down: Fallback to SQLite or error")


def main():
    """Main function to run all examples."""
    print("🏗️  Revit Project - BIM Multi-Database System")
    print("   Advanced BIM/CAD Workflow with Multiple Database Technologies")

    # Run examples
    example_bim_workflow()
    example_performance_comparison()
    example_error_handling()

    print("\n💡 Key Benefits of Multi-Database Approach:")
    print("   • Use the right tool for each job")
    print("   • Scale different components independently")
    print("   • Leverage specialized capabilities of each database")
    print("   • Maintain data consistency across systems")
    print("   • Enable advanced AI/ML capabilities with vector databases")

    print("\n📋 Next Steps:")
    print("   1. Configure your database connections in .env")
    print("   2. Install required packages: pip install -r requirements_multi_db.txt")
    print("   3. Test the setup with: python setup_databases.py")
    print("   4. Explore API endpoints at: /api/v1/multi-db/")


if __name__ == "__main__":
    main()
