
def convert_quantity(qty, from_unit, to_unit):
    """
    Convert quantity between units. Returns converted quantity or None if impossible.
    """
    if from_unit == to_unit:
        return qty
        
    # strip() is important!
    from_unit = from_unit.strip().lower().rstrip('s')
    to_unit = to_unit.strip().lower().rstrip('s')
    
    print(f"DEBUG: Converting {qty} '{from_unit}' to '{to_unit}'")
    
    # Base units: ml for volume, g for weight
    volume_to_ml = {
        'ml': 1, 'l': 1000, 'liter': 1000, 
        'cup': 240, 
        'tbsp': 15, 'tablespoon': 15,
        'tsp': 5, 'teaspoon': 5,
        'gal': 3785, 'gallon': 3785,
        'oz': 29.57, 'fluid ounce': 29.57 
    }
    
    weight_to_g = {
        'g': 1, 'gram': 1, 
        'kg': 1000, 'kilogram': 1000, 
        'lb': 453.59, 'pound': 453.59, 
        'oz': 28.35, 'ounce': 28.35 
    }
    
    # Try Volume
    if from_unit in volume_to_ml and to_unit in volume_to_ml:
        print("DEBUG: Both Volume")
        ml_qty = qty * volume_to_ml[from_unit]
        return ml_qty / volume_to_ml[to_unit]
        
    # Try Weight
    if from_unit in weight_to_g and to_unit in weight_to_g:
        print("DEBUG: Both Weight")
        g_qty = qty * weight_to_g[from_unit]
        return g_qty / weight_to_g[to_unit]
        
    # Try Weight <-> Volume assumptions (Water density: 1g = 1ml)
    if (from_unit in volume_to_ml and to_unit in weight_to_g) or (from_unit in weight_to_g and to_unit in volume_to_ml):
         print("DEBUG: Mixed Type")
         if from_unit in volume_to_ml:
             base = qty * volume_to_ml[from_unit] # ml
             # assume 1ml = 1g
             res = base / weight_to_g[to_unit]
             print(f"DEBUG: Vol->Weight: {base}ml -> {res} {to_unit}")
             return res
         else:
             base = qty * weight_to_g[from_unit] # g
             # assume 1g = 1ml
             res = base / volume_to_ml[to_unit]
             print(f"DEBUG: Weight->Vol: {base}g -> {res} {to_unit}")
             return res

    print("DEBUG: No match found")
    return None

# Test Cases
print("--- TEST 1: tsp to l ---")
print(convert_quantity(1, "tsp", "l")) # Expected: 0.005

print("\n--- TEST 2: cup to kg ---")
print(convert_quantity(0.5, "cup", "kg")) # Expected: ~0.12

print("\n--- TEST 3: cup to g ---")
print(convert_quantity(0.25, "cup", "g")) # Expected: ~60

print("\n--- TEST 4: tbsp to l ---")
print(convert_quantity(1, "tbsp", "l")) # Expected: 0.015
