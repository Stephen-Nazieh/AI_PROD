#!/usr/bin/env python3
import sys
from pathlib import Path

# Align system boundaries to find relative sister paths cleanly
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT / "01_SKILLS"))

from understand_anything.parser_core import UnderstandAnythingParser
from graphify.knowledge_graph import GraphifyEngine

def execute_ingestion_pipeline(source_file_path: str):
    """
    Stitches Understand-Anything parsing with Graphify knowledge matrix mapping.
    Converts raw files straight into structured database node networks.
    """
    print("\n🚀 [System Pipeline] Initiating multi-layer ingestion stream...")
    
    # 1. Initialize custom modular adapter tools
    parser = UnderstandAnythingParser()
    graph_engine = GraphifyEngine()
    
    try:
        # 2. Extract deep conceptual metadata
        extracted_manifest = parser.ingest_raw_source(source_file_path)
        
        # Inject file naming keys back onto data dicts for indexing targets
        extracted_manifest["title"] = Path(source_file_path).stem
        
        # 3. Synchronize extracted dependencies straight into the Postgres graph nodes
        graph_engine.map_extracted_manifest(extracted_manifest)
        print("🎉 [System Pipeline] Processing stream finished successfully.")
        return True
        
    except Exception as e:
        print(f"❌ [System Pipeline] Processing loop broken: {e}")
        return False

if __name__ == "__main__":
    # Create an instantaneous test file to simulate dropping context into your vault
    sample_vault_doc = PROJECT_ROOT / "01_SKILLS/understand_anything/clt_proof.md"
    sample_vault_doc.write_text(
        "The Law of Large Numbers dictates sample convergence. It directly supports the Central Limit Theorem.", 
        encoding="utf-8"
    )
    
    execute_ingestion_pipeline(str(sample_vault_doc))
    sample_vault_doc.unlink()