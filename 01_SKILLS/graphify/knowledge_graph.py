#!/usr/bin/env python3
import json
import psycopg2
from psycopg2 import connect

class GraphifyEngine:
    """
    Cognitive node relation framework. Commits structural dependencies and entities
    straight to the central persistent postgres memory layer.
    """
    def __init__(self):
        # Explicitly targets your active container parameters
        # Target your active, running solocorn_db container parameters
        self.db_params = {
            "dbname": "paperclip_governance",
            "user": "paperclip_admin",
            "password": "***REMOVED***",
            "host": "127.0.0.1",
            "port": "5433"
        }

    def initialize_graph_tables(self):
        """Creates nodes and edges schemas if they don't exist yet."""
        conn = connect(**self.db_params)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id SERIAL PRIMARY KEY,
                source_node VARCHAR(255) REFERENCES graph_nodes(name) ON DELETE CASCADE,
                target_node VARCHAR(255) REFERENCES graph_nodes(name) ON DELETE CASCADE,
                relation_type VARCHAR(100),
                UNIQUE(source_node, target_node)
            );
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("🗄️ [Graphify] Knowledge Graph schemas initialized in Postgres database.")

    def map_extracted_manifest(self, extraction_manifest: dict):
        """Converts an understand-anything manifest into structural rows."""
        conn = connect(**self.db_params)
        cursor = conn.cursor()
        
        # 1. Insert primary nodes
        for entity in extraction_manifest.get("entities", []):
            cursor.execute("""
                INSERT INTO graph_nodes (name, summary)
                VALUES (%s, %s)
                ON CONFLICT (name) DO UPDATE SET summary = EXCLUDED.summary;
            """, (entity, extraction_manifest.get("summary", "")))
            
        # 2. Map explicit dependency directions (Edges)
        title = extraction_manifest.get("title", "Unknown Source")
        for dep in extraction_manifest.get("dependencies", []):
            # Ensure dependency entity exists as a node first
            cursor.execute("INSERT INTO graph_nodes (name) VALUES (%s) ON CONFLICT DO NOTHING;", (dep,))
            cursor.execute("INSERT INTO graph_nodes (name) VALUES (%s) ON CONFLICT DO NOTHING;", (title,))
            
            try:
                cursor.execute("""
                    INSERT INTO graph_edges (source_node, target_node, relation_type)
                    VALUES (%s, %s, %s)
                    ON CONFLICT DO NOTHING;
                """, (title, dep, "DEPENDS_ON"))
            except Exception:
                pass # Prevent edge constraint interrupts
                
        conn.commit()
        cursor.close()
        conn.close()
        print(f"📊 [Graphify] Successfully cross-linked elements for: '{title}' into storage memory.")

if __name__ == "__main__":
    # Diagnostics check run
    engine = GraphifyEngine()
    engine.initialize_graph_tables()