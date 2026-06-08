#!/usr/bin/env python3
import os
import sys
import psycopg2
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass  # dotenv optional; falls back to the already-exported environment

class PaperclipEnterpriseGovernor:
    """
    The macroeconomic and corporate governance core of the operating system.
    Spins up corporate ledger entries, manages cap tables, and monitors runways.
    """
    def __init__(self):
        # Credentials sourced from environment (.env at repo root); see AGENTS.md.
        self.db_params = {
            "dbname": os.environ.get("PAPERCLIP_DB_NAME", "paperclip_governance"),
            "user": os.environ.get("PAPERCLIP_DB_USER", "paperclip_admin"),
            "password": os.environ.get("PAPERCLIP_DB_PASSWORD", ""),
            "host": os.environ.get("PAPERCLIP_DB_HOST", "127.0.0.1"),
            "port": os.environ.get("PAPERCLIP_DB_PORT", "5433"),  # paperclip_db container
        }

    def initialize_governance_ledger(self):
        """Initializes relational schemas for managing corporate entities and equity pools."""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        
        # 1. Enterprise Registry Layout
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS corporate_entities (
                company_id SERIAL PRIMARY KEY,
                legal_name VARCHAR(255) UNIQUE NOT NULL,
                incorporation_type VARCHAR(50) DEFAULT 'C-Corp',
                authorized_shares BIGINT DEFAULT 10000000,
                option_pool_percentage NUMERIC(5,2) DEFAULT 10.00,
                current_valuation_usd NUMERIC(15,2) DEFAULT 0.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. Capitalization Table Schema Tracker
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cap_tables (
                shareholder_id SERIAL PRIMARY KEY,
                company_name VARCHAR(255) REFERENCES corporate_entities(legal_name) ON DELETE CASCADE,
                stakeholder_name VARCHAR(255) NOT NULL,
                shares_owned BIGINT NOT NULL,
                equity_type VARCHAR(100) DEFAULT 'Common Stock',
                UNIQUE(company_name, stakeholder_name)
            );
        """)
        
        conn.commit()
        cursor.close()
        conn.close()
        print("🏛️ [Paperclip] Corporate Governance and Enterprise schemas established in port 5433.")

    def materialize_new_company(self, name: str, inc_type: str = "C-Corp", total_shares: int = 10000000, founder: str = "Stephen"):
        """Programmatically registers a brand new corporation inside the tracking systems memory."""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        
        try:
            # 1. Inject primary company metadata row
            cursor.execute("""
                INSERT INTO corporate_entities (legal_name, incorporation_type, authorized_shares)
                VALUES (%s, %s, %s)
                ON CONFLICT (legal_name) DO NOTHING;
            """, (name, inc_type, total_shares))
            
            # 2. Allocate initial founder equity parameters (80% allocation)
            founder_shares = int(total_shares * 0.80)
            cursor.execute("""
                INSERT INTO cap_tables (company_name, stakeholder_name, shares_owned, equity_type)
                VALUES (%s, %s, %s, 'Founder Common Stock')
                ON CONFLICT (company_name, stakeholder_name) DO NOTHING;
            """, (name, founder, founder_shares))
            
            conn.commit()
            print(f"🏢 [Paperclip] Enterprise '{name}' incorporated successfully.")
            print(f"📊 [Cap Table] Issued {founder_shares:,} Founder Common Shares to {founder}.")
            
        except Exception as e:
            conn.rollback()
            print(f"❌ [Paperclip] Failed to manifest corporate entity structure: {e}")
        finally:
            cursor.close()
            conn.close()

    def record_operational_expense(self, company_name: str, resource_type: str, units_consumed: float, unit_cost_usd: float):
        """
        Logs an active hardware, token, or platform compute resource transaction.
        Enforces macro runway checks to safeguard corporate solvency parameters.
        """
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        
        total_cost = units_consumed * unit_cost_usd
        
        # Initialize a ledger table for system operational costs if not present
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operational_ledger (
                expense_id SERIAL PRIMARY KEY,
                company_name VARCHAR(255) REFERENCES corporate_entities(legal_name) ON DELETE CASCADE,
                resource_type VARCHAR(100),
                cost_usd NUMERIC(10,4),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        try:
            cursor.execute("""
                INSERT INTO operational_ledger (company_name, resource_type, cost_usd)
                VALUES (%s, %s, %s);
            """, (company_name, resource_type, total_cost))
            
            conn.commit()
            print(f"📉 [Paperclip Expense] Allocated ${total_cost:.4f} to '{company_name}' under [{resource_type.upper()}].")
            
            # Run automatic threshold guardrail audit checks
            self._audit_runway_solvency(company_name)
            
        except Exception as e:
            conn.rollback()
            print(f"⚠️ [Paperclip] Ledger logging faulted: {e}")
        finally:
            cursor.close()
            conn.close()

    def _audit_runway_solvency(self, company_name: str):
        """Internal governor check. Flags alerts if operational spending accelerates unsustainably."""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(cost_usd) FROM operational_ledger WHERE company_name = %s;
        """, (company_name,))
        
        total_spent = cursor.fetchone()[0] or 0.0000
        
        # Threshold parameters against a standard pre-seed operating pool baseline
        allocated_runway_pool = 15000.00
        remaining_balance = allocated_runway_pool - float(total_spent)
        
        if remaining_balance < 1000.00:
            print(f"🚨 [PAPERCLIP GOVERNOR BREAK] CRITICAL WARNING: '{company_name}' runway balance is critically depleted (${remaining_balance:.2f} remaining)!")
        else:
            print(f"🛡️ [Paperclip Governance] Audit clear. '{company_name}' capital index safe. Remaining: ${remaining_balance:.2f}")
            
        cursor.close()
        conn.close()

if __name__ == "__main__":
    governor = PaperclipEnterpriseGovernor()
    governor.initialize_governance_ledger()
    
    # 1. Seed corporate identity mapping parameters
    governor.materialize_new_company("DeParadigm Media LLC", inc_type="LLC")
    
    # 2. Simulate multi-pass computational resource logging checks
    governor.record_operational_expense("DeParadigm Media LLC", resource_type="local_inference_tokens", units_consumed=8500, unit_cost_usd=0.00002)
    governor.record_operational_expense("DeParadigm Media LLC", resource_type="manim_gpu_compute_hours", units_consumed=2.5, unit_cost_usd=0.12)