
import json

def get_list_from_json(data):
    """
    Recursively find a list of recipes in a nested JSON response.
    Flexible enough to handle {"recipes": [...]}, {"recipes": {"recipes": [...]}}, or just [...]
    """
    print(f"Checking data type: {type(data)}")
    if isinstance(data, list):
        print("Found list!")
        return data
    if isinstance(data, dict):
        # 1. Check direct 'recipes' key first (most common)
        if 'recipes' in data:
            print("Found 'recipes' key")
            val = data['recipes']
            if isinstance(val, list): 
                print("Value is list, returning")
                return val
            if isinstance(val, dict): 
                print("Value is dict, recurring")
                return get_list_from_json(val)
            
        # 2. Search other keys
        print("Searching other keys...")
        for key, value in data.items():
            if isinstance(value, list) and 'recipes' in key.lower():
                print(f"Found list in key '{key}'")
                return value
            if isinstance(value, dict) or isinstance(value, list):
                # Avoid infinite recursion if possible, but JSON is tree-like
                print(f"Recurring into key '{key}'")
                found = get_list_from_json(value)
                if found: return found
    return []

# Test Case 1: Standard
json1 = '{"recipes": [{"name": "Standard"}]}'
print("\n--- Test 1 ---")
res1 = get_list_from_json(json.loads(json1))
print(f"Result 1: {res1}")

# Test Case 2: Double Nested (Simulating the error)
# {"recipes": {"recipes": [...]}}
json2 = '{"recipes": {"recipes": [{"name": "Nested"}]}}'
print("\n--- Test 2 ---")
res2 = get_list_from_json(json.loads(json2))
print(f"Result 2: {res2}")

# Test Case 3: Just List
json3 = '[{"name": "ListOnly"}]'
print("\n--- Test 3 ---")
res3 = get_list_from_json(json.loads(json3))
print(f"Result 3: {res3}")

# Test Case 4: Deeply Nested
json4 = '{"status": "success", "data": {"recipes": [{"name": "Deep"}]}}'
print("\n--- Test 4 ---")
res4 = get_list_from_json(json.loads(json4))
print(f"Result 4: {res4}")
