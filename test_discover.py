#!/usr/bin/env python
"""Test script for discover_search after fix."""

from app.clients import build_service_clients
from app.settings import load_settings
from app.queries import discover_search
import traceback

s = load_settings()
c = build_service_clients(s)

try:
    print("=== Testing discover_search ===")
    results = discover_search(
        c, s,
        positive_texts=["participacion ciudadana"],
        negative_texts=["violencia"],
        project="default"
    )
    print(f"Discovery results: {len(results)}")
    for r in results[:3]:
        print(f"  - Score: {r.get('score', 0):.3f}")
        print(f"    Text: {r.get('fragmento', '')[:80]}...")
        
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
finally:
    c.close()
