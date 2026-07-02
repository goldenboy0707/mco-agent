#!/usr/bin/env python3
import os
import sys
import json
from pathlib import Path

# Add project root to sys.path to allow imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from skills.mco_triage.scripts.validate_payload import validate_payload

class McoHarness:
    def __init__(self):
        self.categories = ["technical_support", "billing", "feedback", "general_inquiry"]

    def triage(self, payload: dict) -> dict:
        """
        Processes a payload, validates it, and returns triage results.
        """
        is_valid, err = validate_payload(payload)
        if not is_valid:
            return {
                "success": False,
                "error": f"Invalid payload: {err}"
            }

        content = payload.get("content", "").lower()
        
        # Simple rule-based triage for demonstration purposes
        category = "general_inquiry"
        priority = "low"
        
        if any(w in content for w in ["error", "bug", "crash", "broken", "fail"]):
            category = "technical_support"
            priority = "high"
        elif any(w in content for w in ["invoice", "billing", "payment", "price", "charge", "refund"]):
            category = "billing"
            priority = "medium"
        elif any(w in content for w in ["suggest", "improvement", "like", "feature"]):
            category = "feedback"
            priority = "low"

        return {
            "success": True,
            "triage_id": f"triage_{payload['id']}",
            "category": category,
            "confidence": 0.85,
            "assigned_skill": f"skill_{category}",
            "priority": priority
        }

def main():
    if len(sys.argv) < 2:
        print("Usage: python harness.py <payload_json_file_or_string>")
        sys.exit(1)
        
    input_arg = sys.argv[1]
    
    if os.path.exists(input_arg):
        with open(input_arg, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    else:
        payload = json.loads(input_arg)
        
    harness = McoHarness()
    result = harness.triage(payload)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
