#!/usr/bin/env python3
import sys
import json
from psycopg2 import connect, OperationalError

# Local container staging parameters with explicit authentication overrides
DB_PARAMS = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "postgres",  # Matches your container password exactly
    "host": "127.0.0.1",
    "port": "5432",
    "connect_timeout": 5,
    #"options": "-c gssencmode=disable"  # Force-disables the macOS GSSAPI security warning
}

def initialize_solocorn_ledger():
    print("⏳ Connecting to local PostgreSQL storage plane...")
    
    try:
        conn = connect(**DB_PARAMS)
        cursor = conn.cursor()
        print("⚡ DBMS Handshake established. Building ledger schemas...")
        
        # 1. TRACKS TABLE: Maps target business channels
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS production_tracks (
                track_id SERIAL PRIMARY KEY,
                track_name VARCHAR(50) UNIQUE NOT NULL,
                vault_path TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("  -> Table 'production_tracks' verified/created.")
        
        # 2. MEDIA ASSETS LEDGER: Tracks execution assets across render planes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_assets (
                asset_id SERIAL PRIMARY KEY,
                track_id INT REFERENCES production_tracks(track_id),
                asset_name VARCHAR(255) NOT NULL,
                asset_type VARCHAR(50) NOT NULL, 
                file_path TEXT UNIQUE NOT NULL,
                generation_metadata JSONB,      
                qa_status VARCHAR(20) DEFAULT 'PENDING', 
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("  -> Table 'media_assets' verified/created.")

        # 3. SEED SECTIONS: Ensure data hooks are cataloged
        tracks = [
            ("edtech", "02_CURRICULUM/01_SOLOCORN_EDTECH"),
            ("ap_stats_movie", "02_CURRICULUM/02_AP_STATS_MOVIE"),
            ("devops_control", "02_CURRICULUM/03_DEVOPS_CONTROL"),
            ("vertical_farming", "02_CURRICULUM/04_VERTICAL_FARMING")
        ]
        
        for track_name, path in tracks:
            cursor.execute("""
                INSERT INTO production_tracks (track_name, vault_path)
                VALUES (%s, %s)
                ON CONFLICT (track_name) DO NOTHING;
            """, (track_name, path))

        conn.commit()
        print("📊 Relational schema definitions written to disk.")
        
        cursor.execute("SELECT track_name, vault_path FROM production_tracks;")
        rows = cursor.fetchall()
        print("\n🔒 Active Production Ledger Checkpoints:")
        for row in rows:
            print(f"   [Track]: {row[0]:<20} -> [Vault Path]: {row[1]}")
            
        cursor.close()
        conn.close()
        print("\n🏁 Database ledger configuration complete.")

    except OperationalError as e:
        print("\n❌ CONNECTION ERROR: Authentication or port mapping failed.")
        print("👉 Diagnostics:")
        print("   1. Verify your user/password credentials match the script.")
        print(f"   Error Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED SYSTEM FAULT: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    initialize_solocorn_ledger()