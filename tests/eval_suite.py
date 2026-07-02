#!/usr/bin/env python3
import sys
import json
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from core.harness import McoHarness

def run_eval():
    harness = McoHarness()
    dataset_path = project_root / "tests" / "golden_dataset.json"
    
    if not dataset_path.exists():
        print(f"Error: Golden dataset not found at {dataset_path}")
        sys.exit(1)
        
    with open(dataset_path, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)
        
    print(f"Running evaluation on {len(test_cases)} test cases...")
    passed = 0
    
    for i, case in enumerate(test_cases):
        inp = case["input"]
        exp = case["expected"]
        
        result = harness.triage(inp)
        
        if not result["success"]:
            print(f"❌ Case {i+1} [ID {inp['id']}]: Triage failed with error: {result.get('error')}")
            continue
            
        cat_match = result["category"] == exp["category"]
        priority_match = result["priority"] == exp["priority"]
        
        if cat_match and priority_match:
            print(f"✅ Case {i+1} [ID {inp['id']}]: Matched category '{result['category']}' and priority '{result['priority']}'")
            passed += 1
        else:
            print(f"❌ Case {i+1} [ID {inp['id']}]: Mismatch!")
            print(f"   Input content: '{inp['content']}'")
            print(f"   Expected: Category={exp['category']}, Priority={exp['priority']}")
            print(f"   Got:      Category={result['category']}, Priority={result['priority']}")
            
    print("-" * 40)
    print(f"Evaluation Results: {passed}/{len(test_cases)} passed ({passed/len(test_cases)*100:.1f}%)")
    
    if passed == len(test_cases):
        print("All tests passed successfully!")
        sys.exit(0)
    else:
        print("Some test cases failed.")
        sys.exit(1)

if __name__ == "__main__":
    run_eval()
