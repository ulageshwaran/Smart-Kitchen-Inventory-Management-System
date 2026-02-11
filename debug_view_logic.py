
def convert_quantity(qty, from_unit, to_unit):
    """
    Copy of the function from views.py
    """
    if from_unit == to_unit:
        return qty
        
    # Simplify and strip
    from_unit = from_unit.strip().lower().rstrip('s')
    to_unit = to_unit.strip().lower().rstrip('s')
    
    print(f"DEBUG: Internal Convert {qty} '{from_unit}' -> '{to_unit}'")
    
    # Base units: ml for volume, g for weight
    volume_to_ml = {
        'ml': 1, 'l': 1000, 'liter': 1000, 'liters': 1000,
        'cup': 240, 'cups': 240,
        'tbsp': 15, 'tablespoon': 15,
        'tsp': 5, 'teaspoon': 5,
        'gal': 3785, 'gallon': 3785,
        'oz': 29.57, 'fluid ounce': 29.57 # Fluid ounce
    }
    
    weight_to_g = {
        'g': 1, 'gram': 1, 'grams': 1,
        'kg': 1000, 'kilogram': 1000, 'kilograms': 1000,
        'lb': 453.59, 'pound': 453.59, 'pounds': 453.59,
        'oz': 28.35, 'ounce': 28.35, 'ounces': 28.35 
    }
    
    # Try Volume
    if from_unit in volume_to_ml and to_unit in volume_to_ml:
        ml_qty = qty * volume_to_ml[from_unit]
        res = ml_qty / volume_to_ml[to_unit]
        print(f"DEBUG: Volume Match: {res}")
        return res
        
    # Try Weight
    if from_unit in weight_to_g and to_unit in weight_to_g:
        g_qty = qty * weight_to_g[from_unit]
        res = g_qty / weight_to_g[to_unit]
        print(f"DEBUG: Weight Match: {res}")
        return res
        
    # Try Weight <-> Volume assumptions
    if (from_unit in volume_to_ml and to_unit in weight_to_g) or (from_unit in weight_to_g and to_unit in volume_to_ml):
         if from_unit in volume_to_ml:
             base = qty * volume_to_ml[from_unit] 
             res = base / weight_to_g[to_unit]
             print(f"DEBUG: Vol->Weight Match: {res}")
             return res
         else:
             base = qty * weight_to_g[from_unit]
             res = base / volume_to_ml[to_unit]
             print(f"DEBUG: Weight->Vol Match: {res}")
             return res

    print("DEBUG: FAIL. No map.")
    return None

class MockItem:
    def __init__(self, id, name, qty, unit):
        self.id = id
        self.grocery_name = name
        self.quantity = qty
        self.unit = unit

class MockRI:
    def __init__(self, name, qty, unit):
        self.ingredient_name = name
        self.quantity = qty
        self.unit = unit

def mimic_view_logic():
    # Scenario 1: Milk Cup -> Liters
    ri = MockRI("Milk", 0.5, "cup")
    inv = MockItem(1, "Milk", 1.0, "l")
    
    print(f"\n--- Scenario: {ri.quantity} {ri.unit} {ri.ingredient_name} vs {inv.quantity} {inv.unit} {inv.grocery_name}")
    
    if ri.unit and inv.unit and ri.unit.lower() != inv.unit.lower():
        converted = convert_quantity(ri.quantity, ri.unit, inv.unit)
        if converted is not None:
            print(f"SUCCESS: Suggested Deduct: {round(converted, 2)}")
        else:
            print("FAILURE: Conversion returned None")
    else:
        print("SKIPPED: Units match or missing")

    # Scenario 2: Oil Tbsp -> Liters
    ri2 = MockRI("Cooking Oil", 2.0, "tbsp")
    inv2 = MockItem(2, "Cooking Oil", 1.0, "l")
    
    print(f"\n--- Scenario: {ri2.quantity} {ri2.unit} {ri2.ingredient_name} vs {inv2.quantity} {inv2.unit} {inv2.grocery_name}")
    
    if ri2.unit and inv2.unit and ri2.unit.lower() != inv2.unit.lower():
        converted = convert_quantity(ri2.quantity, ri2.unit, inv2.unit)
        if converted is not None:
             print(f"SUCCESS: Suggested Deduct: {round(converted, 2)}")
        else:
             print("FAILURE: Conversion returned None")

mimic_view_logic()
