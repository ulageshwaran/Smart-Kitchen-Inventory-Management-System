from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Grocery, ShoppingList, Receipe, Receipe_Ingredients, Ingredient
from .forms import GroceryForm, ShoppingListForm
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from datetime import date, timedelta
from django.http import JsonResponse
import json
import requests
import os
import base64
import time
import random
from dotenv import load_dotenv

def get_gemini_api_key():
    """Retrieve and validate Gemini API key from environment."""
    load_dotenv()
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    return key if key else None


def get_list_from_json(data):
    """
    Recursively find a list of recipes in a nested JSON response.
    Flexible enough to handle {"recipes": [...]}, {"recipes": {"recipes": [...]}}, or just [...]
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 1. Check direct 'recipes' key first (most common)
        if 'recipes' in data:
            val = data['recipes']
            if isinstance(val, list): return val
            if isinstance(val, dict): return get_list_from_json(val)
            
        # 2. Search other keys
        for key, value in data.items():
            if isinstance(value, list) and 'recipes' in key.lower():
                return value
            if isinstance(value, dict) or isinstance(value, list):
                # Avoid infinite recursion if possible, but JSON is tree-like
                found = get_list_from_json(value)
                if found: return found
    return []




def call_gemini_with_retry(url, payload, headers, max_retries=3):
    """
    Call Gemini API with exponential backoff retry logic for 503/429 errors.
    """
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            if response.status_code == 200:
                return response
                
            # If service unavailable or too many requests, retry
            if response.status_code in [503, 429, 500, 502, 504]:
                if attempt < max_retries - 1:
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    print(f"API Error {response.status_code}. Retrying in {sleep_time:.2f}s...")
                    time.sleep(sleep_time)
                else:
                    return response # Return the failed response after retries
            else:
                return response # Return other 4xx errors immediately
                
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < max_retries - 1:
                sleep_time = (2 ** attempt) + random.uniform(0, 1)
                print(f"Network Error {str(e)}. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
            else:
                raise e # Raise exception after last attempt
                
    return None # Should not reach here

# ============================================
# EXPIRY WARNING SYSTEM
# ============================================

def get_expiry_warnings(user):
    """
    Get expiry status for all user groceries
    Returns: dict with expired and expiring_soon items
    """
    today = date.today()
    
    expired = Grocery.objects.filter(
        user=user,
        ex_date__lt=today
    )
    
    expiring_soon = Grocery.objects.filter(
        user=user,
        ex_date__gte=today,
        ex_date__lte=today + timedelta(days=7)
    )
    
    return {
        'expired': expired,
        'expiring_soon': expiring_soon,
        'expired_count': expired.count(),
        'expiring_soon_count': expiring_soon.count()
    }

# Context processor to add warnings to every page
def add_expiry_warnings(request):
    """Add to context_processors in settings.py"""
    if request.user.is_authenticated:
        warnings = get_expiry_warnings(request.user)
        return {'expiry_warnings': warnings}
    return {}

# ============================================
# HOME / INDEX - WITH EXPIRY WARNINGS
# ============================================

def index(request):
    if not request.user.is_authenticated:
        return render(request, 'food/landing.html')

    search_query = request.GET.get('search', '').strip()
    groceries = Grocery.objects.filter(user=request.user)
    
    if search_query:
        groceries = groceries.filter(
            Q(grocery_name__icontains=search_query) |   
            Q(grocerie_type__icontains=search_query)
        )
    
    groceries = groceries.order_by('ex_date')
    
    # Get expiry warnings
    warnings = get_expiry_warnings(request.user)
    
    # Add warning messages
    if warnings['expired_count'] > 0:
        messages.error(request, f"⚠️ {warnings['expired_count']} item(s) have expired!")
    
    if warnings['expiring_soon_count'] > 0:
        messages.warning(request, f"⏰ {warnings['expiring_soon_count']} item(s) expiring within 7 days!")
    
    return render(request, 'food/index.html', {
        'groceries': groceries,
        'search_query': search_query,
        'warnings': warnings
    })

# ============================================
# GOOGLE GEMINI API RECIPE GENERATION
# ============================================

def get_ai_recipe_suggestion(ingredients_list, preferences=""):
    """
    Free AI recipe generation using Google Gemini API
    
    Get free API key at: https://ai.google.dev/
    
    Gemini Free Tier:
    - 60 requests per minute
    - No credit card required
    - Excellent quality responses
    - Perfect for recipe generation
    """
    
    try:
        # Get API key from environment variable
        api_key = get_gemini_api_key()
        if not api_key:
            return None, "Gemini API key not configured. Please set GEMINI_API_KEY environment variable."
        
        # Gemini API endpoint - use latest model
        # Gemini API endpoint - use latest model
        # Using gemini-3-flash-preview (fastest, free tier)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
        
        ingredients_str = ', '.join(ingredients_list)
        
        prompt = f"""Generate 3 creative, easy-to-make recipes that use as many of these ingredients as possible:

Ingredients: {ingredients_str}
{f'Preferences: {preferences}' if preferences else ''}

For each recipe, provide:
1. Recipe name
2. Ingredients (with quantities from available items)
3. Step-by-step instructions (5-8 steps)
4. Cooking time
5. Difficulty level (Easy/Medium/Hard)
6. Calories per serving

Keep recipes practical and suitable for home cooking."""

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.5,
                "maxOutputTokens": 4096,
                "topP": 0.9,
            }
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            # Debug: Print response structure
            print(f"API Response: {data}")
            
            # Extract text from Gemini response - with better error handling
            if 'candidates' in data and len(data['candidates']) > 0:
                candidate = data['candidates'][0]
                
                # Check if content exists and has parts
                if 'content' in candidate and 'parts' in candidate['content']:
                    content = candidate['content']
                    if len(content['parts']) > 0:
                        recipe_text = content['parts'][0].get('text', '')
                        
                        if recipe_text:
                            return recipe_text, None
                        else:
                            # Check if API hit token limit
                            finish_reason = candidate.get('finishReason', '')
                            if finish_reason == 'MAX_TOKENS':
                                return None, "API response was cut off. Increase token limit or simplify request."
                            return None, "API returned empty text"
                    else:
                        return None, "No parts in content"
                else:
                    # Handle case where content exists but has no parts (MAX_TOKENS hit)
                    finish_reason = candidate.get('finishReason', '')
                    if finish_reason == 'MAX_TOKENS':
                        return None, "Response cut off (token limit reached). Please try again."
                    return None, "Invalid response structure: no content field"
            else:
                return None, "No candidates in response"
        else:
            # Handle error responses
            try:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', f'HTTP {response.status_code}')
                print(f"API Error Response: {error_data}")
            except:
                error_msg = f'HTTP {response.status_code}: {response.text}'
            
            return None, f"API Error: {error_msg}"
            
    except requests.Timeout:
        return None, "Request timeout. The API took too long to respond. Please try again."
    except requests.ConnectionError:
        return None, "Connection error. Please check your internet connection."
    except json.JSONDecodeError:
        return None, "Invalid API response format."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, f"Error generating recipes: {str(e)}"

# ============================================
# RECIPE SUGGESTION WITH EXPIRY WARNINGS
# ============================================

@login_required
@login_required
def suggest_recipes(request):
    """Landing page for AI Chef - shows ingredients before generation"""
    user = request.user
    today = date.today()
    
    # Get all user groceries
    all_groceries = Grocery.objects.filter(user=user)
    
    expiring_soon = []
    others = []
    
    for g in all_groceries:
        if g.is_expired:
            continue
        if g.is_expiring_soon:
            expiring_soon.append(g)
        else:
            others.append(g)
            
    return render(request, 'food/ai_chef_landing.html', {
        'expiring_items': expiring_soon,
        'other_items': others,
        'total_count': len(all_groceries)
    })

@login_required
def generate_recipes_api(request):
    """API to generate recipes using all ingredients"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        preferences = data.get('preferences', '')
        servings = data.get('servings', '2')
        
        user = request.user
        today = date.today()
        
        # Get ingredients
        groceries = Grocery.objects.filter(user=user)
        
        expiring = []
        others = []
        
        for g in groceries:
            if g.is_expired:
                continue
            if g.is_expiring_soon:
                expiring.append(g.grocery_name)
            else:
                others.append(g.grocery_name)
        
        if not expiring and not others:
            return JsonResponse({
                'status': 'error', 
                'message': 'No ingredients found in your kitchen!'
            }, status=400)
            
        # Call Gemini
        api_key = get_gemini_api_key()
        if not api_key:
            return JsonResponse({'status': 'error', 'message': 'API key not configured'}, status=500)
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
        
        expiring_str = ", ".join(expiring)
        others_str = ", ".join(others)
        
        prompt = f"""As a creative chef, generate 3 detailed recipes based on these available ingredients.
        Create these recipes specifically for {servings} people. Adjust all ingredient quantities accordingly.
        
CRITICAL PRIORITY (Use these if possible as they are expiring):
{expiring_str if expiring else 'None'}

OTHER AVAILABLE INGREDIENTS:
{others_str if others else 'None'}

User Preferences: {preferences if preferences else 'None'}

        Rules:
        1. You don't have to use ALL ingredients, but try to use the PRIORITY ones to reduce waste.
        2. You can assume common pantry staples (oil, salt, pepper, water, basic spices) are available.
        3. STRICT RESOURCE DEDUCTION RULE: 
           - You MUST provide ingredient quantities in standard MASS (g, kg) or VOLUME (ml, l, tbsp, tsp) units.
           - DO NOT use counts like "1 Tomato" or "2 Onions". Instead use "Tomato (150g)" or "Onion (small, 100g)".
           - This is critical for inventory tracking.
           - Exceptions: Eggs (use "unit" or "count"), Bread (use "slices").
        4. Format the output valid JSON (NO markdown backticks) with this structure:
        {{
            "recipes": [
                {{
                    "name": "Recipe Name",
                    "description": "Brief appetizing description",
                    "time": "Cooking Time (e.g. 30 mins)",
                    "difficulty": "Easy/Medium/Hard",
                    "calories": "Total Calories",
                    "macros": {{ "protein": "10g", "carbs": "20g", "fats": "5g" }},
                    "ingredients": {{
                        "Ingredient Name (e.g. Tomato 150g)": "Quantity + Unit only (e.g. 150g) or just 150g", 
                         // IMPORTANT: The key should be the full descriptive name. The value is just for display.
                    }},
                    "instructions": ["Step 1...", "Step 2...", "Step 3..."]
                }}
            ]
        }}
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        headers = {"Content-Type": "application/json"}
        # Use retry logic
        response = call_gemini_with_retry(url, payload, headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and len(data['candidates']) > 0:
                content = data['candidates'][0]['content']
                if 'parts' in content:
                    text_resp = content['parts'][0]['text']
                    # Clean markdown code blocks if present
                    text_resp = text_resp.replace('```json', '').replace('```', '').strip()
                    try:
                        recipes_data = json.loads(text_resp)
                        recipes_list = get_list_from_json(recipes_data)
                        return JsonResponse({'status': 'success', 'recipes': recipes_list})
                    except json.JSONDecodeError:
                        # Fallback if AI fails JSON format
                        return JsonResponse({'status': 'error', 'message': 'AI response format format error'}, status=500)
            return JsonResponse({'status': 'error', 'message': 'AI returned no content'}, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': f'API Error: {response.text}'}, status=500)
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@login_required
def view_saved_recipes(request):
    """View all saved recipes"""
    recipes = Receipe.objects.all().prefetch_related('receipe_ingredients_set__ingredient')
    
    return render(request, 'food/saved_recipes.html', {
        'recipes': recipes
    })

@login_required
def view_recipe_detail(request, pk):
    """View a single recipe in detail"""
    recipe = get_object_or_404(Receipe, pk=pk)
    ingredients = recipe.receipe_ingredients_set.all()
    
    return render(request, 'food/recipe_detail.html', {
        'recipe': recipe,
        'ingredients': ingredients
    })

@login_required
def delete_recipe_view(request, pk):
    """Delete a saved recipe"""
    recipe = get_object_or_404(Receipe, pk=pk)
    
    if request.method == 'POST':
        recipe.delete()
        return JsonResponse({'status': 'success'})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

def parse_ingredient_string(ingredient_str):
    """
    Parse ingredient string into quantity, unit, and name.
    Example: "1/2 cup Milk" -> (0.5, "cup", "Milk")
    Example: "200g Chicken" -> (200.0, "g", "Chicken")
    """
    import re
    
    ingredient_str = ingredient_str.strip()
    qty = 1.0
    unit = 'as needed'
    name = ingredient_str
    
    # 1. Try to find number at start (including fractions)
    # Match: "1 1/2", "1.5", "1/2", "1"
    match = re.match(r'^(\d+\s+\d+/\d+|\d+/\d+|\d+\.\d+|\d+)\s*(.*)', ingredient_str)
    
    if match:
        num_str = match.group(1)
        rest = match.group(2).strip()
        
        # Convert fraction to float
        try:
            if ' ' in num_str and '/' in num_str: # Mixed fraction "1 1/2"
                whole, frac = num_str.split()
                num, den = frac.split('/')
                qty = float(whole) + (float(num) / float(den))
            elif '/' in num_str: # Fraction "1/2"
                num, den = num_str.split('/')
                qty = float(num) / float(den)
            else: # decimal or int
                qty = float(num_str)
        except ValueError:
            qty = 1.0 # Fallback
            
        # 2. Try to find unit in the rest
        # Common units
        units = ['cup', 'cups', 'tbsp', 'tsp', 'g', 'kg', 'ml', 'l', 'oz', 'lb', 'piece', 'pieces', 'slice', 'slices', 'clove', 'cloves', 'pinch', 'bunch', 'packet']
        
        # Check if the next word is a unit
        words = rest.split()
        if words:
            potential_unit = words[0].lower().rstrip('s') # simple singularization
            
            # Check against list or if it looks like a unit
            for u in units:
                if potential_unit == u or potential_unit == u + 's':
                    unit = u
                    # Remove unit from name
                    name = " ".join(words[1:])
                    break
            else:
                 # If not in list, but we extracted a number, keep rest as name
                 # Might handle cases like "2 Apples" -> qty: 2, unit: 'unit' (default), name: Apples
                 name = rest
                 # Optional: treat "Apples" as unit if you want specific behavior, but default 'unit' is safe
                 if not unit or unit == 'as needed':
                     unit = 'unit'
    
    return qty, unit, name
    
def convert_quantity(qty, from_unit, to_unit, item_name=None):
    """
    Convert quantity between units. Returns converted quantity or None if impossible.
    Optional item_name allows specific heuristic conversions (e.g. Bread packet -> slices).
    """
    if from_unit == to_unit:
        return qty
        
    # Simplify and strip
    from_unit = from_unit.strip().lower().rstrip('s')
    to_unit = to_unit.strip().lower().rstrip('s')
    
    # ITEM SPECIFIC CONVERSIONS
    if item_name:
        item_name = item_name.lower()
        
        # Bread: Packet <-> Slice
        if 'bread' in item_name:
            # Assume 1 packet = 15 slices (standard loaf)
            if from_unit == 'packet' and to_unit == 'slice':
                return qty * 15
            if from_unit == 'slice' and to_unit == 'packet':
                return qty / 15
                
        # Leafy Greens/Herbs: Packet <-> Bunch
        if any(x in item_name for x in ['coriander', 'spinach', 'mint', 'methi', 'palak']):
             if from_unit == 'packet' and to_unit == 'bunch':
                 # Assume 1 packet = 1 bunch
                 return qty 
             if from_unit == 'bunch' and to_unit == 'packet':
                 return qty

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
        'oz': 28.35, 'ounce': 28.35, 'ounces': 28.35 # Weight ounce (ambiguous, usually weight in cooking unless specified fl oz)
    }
    
    # Try Volume
    if from_unit in volume_to_ml and to_unit in volume_to_ml:
        ml_qty = qty * volume_to_ml[from_unit]
        return ml_qty / volume_to_ml[to_unit]
        
    # Try Weight
    if from_unit in weight_to_g and to_unit in weight_to_g:
        g_qty = qty * weight_to_g[from_unit]
        return g_qty / weight_to_g[to_unit]
        
    # Try Weight <-> Volume assumptions (Water density: 1g = 1ml)
    # This is a Rough approximation for common liquids/solids if direct type mismatch
    # ml <-> g
    if (from_unit in volume_to_ml and to_unit in weight_to_g) or (from_unit in weight_to_g and to_unit in volume_to_ml):
         # Convert to base (ml or g), assume 1:1, then convert to target
         if from_unit in volume_to_ml:
             base = qty * volume_to_ml[from_unit] # ml
             # assume 1ml = 1g
             return base / weight_to_g[to_unit]
         else:
             base = qty * weight_to_g[from_unit] # g
             # assume 1g = 1ml
             return base / volume_to_ml[to_unit]

    return None

@login_required
def save_recipe(request):
    """Save generated recipe to database"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extract macros if available
            macros = data.get('macros', {})
            
            # specific instructions format for the text field
            desc_text = data.get('description', '')
            inst_text = data.get('instructions', '')
            
            recipe = Receipe.objects.create(
                name=data.get('recipe_name', 'Unnamed Recipe'),
                description=desc_text,
                instructions=inst_text,
                cooking_time=data.get('cooking_time', ''),
                calories=data.get('calories', ''),
                protein=macros.get('protein', ''),
                carbs=macros.get('carbs', ''),
                fats=macros.get('fats', '')
            )
            
            # Save ingredients
            ingredients_dict = data.get('ingredients', {})
            for ingredient_name in ingredients_dict.keys():
                # Parse the key itself assuming it might contain the full text "1 cup milk"
                # OR check if the value has more info. 
                # Usually `ingredients_dict` keys are just names if from UI bubbles, 
                # but if coming from AI directly, check format.
                # Assuming ingredients_dict keys are the full strings like "1 cup Milk" or simplified names.
                # Let's try to parse the name provided.
                
                qty, unit, clean_name = parse_ingredient_string(ingredient_name)
                
                ingredient, _ = Ingredient.objects.get_or_create(
                    name=clean_name
                )
                Receipe_Ingredients.objects.create(
                    receipe=recipe,
                    ingredient=ingredient,
                    quantity=qty,
                    unit=unit
                )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Recipe "{recipe.name}" saved successfully!',
                'recipe_id': recipe.id
            })
        except Exception as e:
            print(f"Error in save_recipe: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def refine_recipe(request):
    """Refine recipe based on user preferences"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            current_recipe = data.get('recipe', '')
            preferences = data.get('preferences', '')
            
            if not preferences:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Please specify preferences'
                }, status=400)
            
            api_key = get_gemini_api_key()
            if not api_key:
                return JsonResponse({
                    'status': 'error',
                    'message': 'API not configured'
                }, status=400)
            
            # Use same API endpoint as recipe generation
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
            
            prompt = f"""Modify this recipe based on the following preferences: {preferences}

Current Recipe:
{current_recipe}

Provide the modified recipe with the same format as before."""
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 4096,
                    "topP": 0.9,
                }
            }
            
            # Headers already defined

            # Use retry logic
            response = call_gemini_with_retry(url, payload, headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'candidates' in data and len(data['candidates']) > 0:
                    candidate = data['candidates'][0]
                    if 'content' in candidate and 'parts' in candidate['content']:
                        refined_recipe = candidate['content']['parts'][0]['text']
                        return JsonResponse({
                            'status': 'success',
                            'recipe': refined_recipe
                        })
                    else:
                        finish_reason = candidate.get('finishReason', '')
                        if finish_reason == 'MAX_TOKENS':
                            return JsonResponse({
                                'status': 'error',
                                'message': 'Response was cut off. Please try again.'
                            }, status=400)
                        return JsonResponse({
                            'status': 'error',
                            'message': 'No response from API'
                        }, status=400)
                else:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'No response from API'
                    }, status=400)
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Failed to refine recipe'
                }, status=400)
                
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

# ============================================
# FOOD IMAGE ANALYSIS
# ============================================

def analyze_food_image(image_data):
    """
    Analyze food image using Gemini Flash Vision
    """
    try:
        api_key = get_gemini_api_key()
        if not api_key:
            return None, "Gemini API key not configured."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
        
        # Determine mime type (assume jpeg if not specified, frontend should handle this)
        # simplistic handling: image_data is base64 string
        
        prompt = """Analyze this food image and provide:
Name of the dish/food
Estimated calories (total or per serving)
Main ingredients visible
Nutritional breakdown:
   - Protein (approx g)
   - Carbs (approx g)
   - Fats (approx g)
Healthiness rating (1-10) and brief explanation

Format the response in clear Markdown."""

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_data
                        }
                    }
                ]
            }]
        }
        
        headers = {"Content-Type": "application/json"}
        # Use retry logic
        response = call_gemini_with_retry(url, payload, headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and len(data['candidates']) > 0:
                content = data['candidates'][0]['content']
                if 'parts' in content:
                    return content['parts'][0]['text'], None
            return None, "No analysis generated."
        else:
            return None, f"API Error: {response.text}"
            
    except Exception as e:
        return None, str(e)

@login_required
def analyze_food_view(request):
    """View to upload and analyze food images"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_b64 = data.get('image')
            
            if not image_b64:
                return JsonResponse({'status': 'error', 'message': 'No image provided'}, status=400)
                
            # Remove header if present (e.g., "data:image/jpeg;base64,")
            if ',' in image_b64:
                image_b64 = image_b64.split(',')[1]
                
            analysis, error = analyze_food_image(image_b64)
            
            if error:
                return JsonResponse({'status': 'error', 'message': error}, status=400)
                
            return JsonResponse({
                'status': 'success',
                'analysis': analysis
            })
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return render(request, 'food/food_analysis.html')


# ============================================
# BILL UPLOAD & ANALYSIS
# ============================================

def analyze_bill_image(image_data):
    """
    Analyze bill image using Gemini Flash Vision
    Returns a list of identified items with estimated expiry
    """
    try:
        api_key = get_gemini_api_key()
        if not api_key:
            return None, "Gemini API key not configured."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
        
        # Create category list string
        categories_str = ", ".join([c[1] for c in Grocery.CATEGORY_CHOICES])
        
        prompt = f"""Analyze this grocery bill/receipt image and extract ONLY the food/grocery items. 
Ignore non-food items (like soap, paper towels) and general receipt text (taxes, store name).

For each food item, provide:
1. Generic Ingredient Name ONLY. Remove all brand names, packaging info, and adjectives. 
   - Example: "Aashirvaad Shudh Chakki Atta" -> "Whole Wheat Flour" or "Atta"
   - Example: "Amul Gold Milk" -> "Milk"
   - Example: "Maggi Noodles" -> "Instant Noodles"
   - Example: "Tata Salt" -> "Salt"
2. Calculate Total Quantity & Unit: 
   - Look for quantity indicators in the item name (e.g., "500ml", "1kg", "200g").
   - Look for multipliers (e.g., "x2", "2 qty", "2 pcs").
   - IF multiplier exists: Calculate total (e.g., "Milk 500ml x 2" -> Total 1000ml -> Quantity: 1, Unit: l).
   - IF no multiplier: Use the size as unit (e.g., "Milk 500ml" -> Quantity: 500, Unit: ml).
   - IF no size in name: Use the bill's Qty column.
3. Quantity (Number): The final calculated quantity.
4. Unit (String):
   - For BREAD: Use "slice" (assume 12-15 slices per packet). If packet, output "slice" and calculate qty * 15.
   - For LEAFY VEG (Coriander, Spinach): Use "bunch".
   - For LIQUIDS: Use "l" or "ml".
   - For SOLIDS: Use "kg" or "g".
   - Avoid "packet" or "unit" if a specific mass/volume/count unit exists.
5. Manufacturing Date (YYYY-MM-DD) - IF found on the bill. Otherwise null.
6. Estimated Expiry Date (YYYY-MM-DD):
   - IF Expiry Date is on bill, use it.
   - IF Manufacturing Date is on bill, calculate based on typical shelf life (e.g. Dairy: +7 days, Bread: +5 days).
   - IF NEITHER, make a reasonable guess based on the type of food from today {date.today()}.
7. Category - Choose the best match from this list: [{categories_str}]

Format the response as a valid JSON list of objects.
Example format:
[
  {{"name": "Milk", "quantity": 1, "unit": "l", "mfd": "2024-01-25", "expiry": "2024-02-01", "category": "Dairy"}},
  {{"name": "Basmati Rice", "quantity": 1, "unit": "kg", "mfd": null, "expiry": "2025-01-01", "category": "Grains"}}
]
Return ONLY the JSON. Do not include markdown formatting or backticks.
"""

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_data
                        }
                    }
                ]
            }]
        }
        
        headers = {"Content-Type": "application/json"}
        # Use retry logic
        response = call_gemini_with_retry(url, payload, headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'candidates' in data and len(data['candidates']) > 0:
                content = data['candidates'][0]['content']
                if 'parts' in content:
                    text_response = content['parts'][0]['text']
                    # Clean up markdown if present
                    text_response = text_response.replace('```json', '').replace('```', '').strip()
                    try:
                        items = json.loads(text_response)
                        return items, None
                    except json.JSONDecodeError:
                        return None, "Failed to parse AI response as JSON."
            return None, "No analysis generated."
        else:
            return None, f"API Error: {response.text}"
            
    except Exception as e:
        return None, str(e)

@login_required
def upload_bill_view(request):
    """View to upload and analyze grocery bills"""
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_b64 = data.get('image')
            
            if not image_b64:
                return JsonResponse({'status': 'error', 'message': 'No image provided'}, status=400)
                
            if ',' in image_b64:
                image_b64 = image_b64.split(',')[1]
                
            items, error = analyze_bill_image(image_b64)
            
            if error:
                return JsonResponse({'status': 'error', 'message': error}, status=400)
                
            return JsonResponse({
                'status': 'success',
                'items': items,
                'categories': [{'id': c[0], 'name': c[1]} for c in Grocery.CATEGORY_CHOICES]
            })
            
        except Exception as e:
            # Log error
            with open('debug_errors.log', 'a') as f:
                import datetime
                f.write(f"{datetime.datetime.now()}: Error in upload_bill_view: {str(e)}\n")
                import traceback
                traceback.print_exc(file=f)
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return render(request, 'food/upload_bill.html')

@login_required
def save_bill_items(request):
    """Save reviewed items from bill to database"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            items = data.get('items', [])
            
            saved_count = 0
            
            for item in items:
                # Find or create category (simple fuzzy match could be better, but exact for now)
                category_name = item.get('category')
                
                bg_name = item.get('name', '').strip()
                ex_date = item.get('expiry')
                manufacturing_date = item.get('mfd') or None # Handle empty string as None
                raw_qty = float(item.get('quantity', 1))
                unit = item.get('unit', 'unit')
                
                # Check for existing item with same name (case-insensitive) for this user
                existing_item = Grocery.objects.filter(
                    user=request.user, 
                    grocery_name__iexact=bg_name
                ).first()
                
                merged = False
                
                if existing_item:
                    # Attempt unit match or conversion
                    if existing_item.unit.lower() == unit.lower():
                        existing_item.quantity += raw_qty
                        merged = True
                    else:
                        # Try to convert NEW item unit -> EXISTING item unit
                        converted_qty = convert_quantity(raw_qty, unit, existing_item.unit, item_name=bg_name)
                        if converted_qty is not None:
                            existing_item.quantity += converted_qty
                            merged = True
                            
                    if merged:
                        # Optional: Update expiry to the newer date if new item expires LATER?
                        # Or Keep Earliest? 
                        # Usually, if you add fresh stock to old stock, you still have old stock.
                        # We will just update quantity and keep the old date warning effective for the old batch.
                        # Or maybe we can't easily track mixed batches. 
                        # Let's just save.
                        existing_item.save()
                
                if not merged:
                    Grocery.objects.create(
                        grocery_name=bg_name,
                        ex_date=ex_date,
                        quantity=raw_qty,
                        unit=unit,
                        grocerie_type=category_name if category_name else 'Others',
                        manufacturing_date=manufacturing_date,
                        user=request.user
                    )
                saved_count += 1
            
            messages.success(request, f'Successfully processed {saved_count} items (merged duplicates where found)!')
            return JsonResponse({'status': 'success', 'count': saved_count})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'error': 'Invalid request'}, status=400)


# ============================================
# EXISTING FUNCTIONS (Keep as is)
# ============================================

@login_required
def add_grocery(request):
    
    if request.method == 'POST':
        grocery_name = request.POST.get('grocery_name')
        ex_date = request.POST.get('ex_date')
        quantity = request.POST.get('quantity')
        unit = request.POST.get('unit')
        grocerie_type = request.POST.get('grocerie_type')
        manufacturing_date = request.POST.get('manufacturing_date')
        
        # Handle empty string for date
        if not manufacturing_date:
            manufacturing_date = None
        
        try:
            Grocery.objects.create(
                grocery_name=grocery_name,
                ex_date=ex_date,
                quantity=quantity,
                unit=unit,
                grocerie_type=grocerie_type,
                manufacturing_date=manufacturing_date,
                user=request.user
            )
            messages.success(request, 'Grocery added successfully!')
            return redirect('index')
        except Exception as e:
            messages.error(request, f'Error adding grocery: {str(e)}')
    
    return render(request, 'food/add.html', {
        'category_choices': Grocery.CATEGORY_CHOICES,
        'is_editing': False
    })

@login_required
def edit_grocery(request, pk):
    grocery = get_object_or_404(Grocery, pk=pk, user=request.user)
    
    if request.method == 'POST':
        grocery_name = request.POST.get('grocery_name')
        ex_date = request.POST.get('ex_date')
        quantity = request.POST.get('quantity')
        unit = request.POST.get('unit')
        grocerie_type = request.POST.get('grocerie_type')
        manufacturing_date = request.POST.get('manufacturing_date')
        
        if not manufacturing_date:
            manufacturing_date = None
        
        try:
            grocery.grocery_name = grocery_name
            grocery.ex_date = ex_date
            grocery.quantity = quantity
            grocery.unit = unit
            grocery.grocerie_type = grocerie_type
            grocery.manufacturing_date = manufacturing_date
            grocery.save()
            messages.success(request, 'Grocery updated successfully!')
            return redirect('index')
        except Exception as e:
            messages.error(request, f'Error updating grocery: {str(e)}')
    
    form_data = {
        'grocery_name': {'value': grocery.grocery_name},
        'ex_date': {'value': grocery.ex_date.strftime('%Y-%m-%d') if grocery.ex_date else ''},
        'quantity': {'value': grocery.quantity},
        'unit': {'value': grocery.unit},
        'grocerie_type': {'value': grocery.grocerie_type},
        'manufacturing_date': {'value': grocery.manufacturing_date.strftime('%Y-%m-%d') if grocery.manufacturing_date else ''}
    }
    
    return render(request, 'food/add.html', {
        'form': type('obj', (object,), form_data),
        'category_choices': Grocery.CATEGORY_CHOICES,
        'is_editing': True
    })

@login_required
def delete_grocery(request, pk):
    grocery = get_object_or_404(Grocery, pk=pk, user=request.user)
    grocery.delete()
    messages.success(request, 'Grocery deleted successfully!')
    return redirect('index')

@login_required
def shopping_list(request):
    search_query = request.GET.get('search', '').strip()
    shop_list = ShoppingList.objects.filter(user=request.user).select_related('grocery')
    groceries = Grocery.objects.filter(user=request.user)
    
    if search_query:
        groceries = groceries.filter(
            Q(grocery_name__icontains=search_query) |
            Q(grocerie_type__icontains=search_query)
        )
    
    groceries = groceries.order_by('grocery_name')
    
    return render(request, 'food/shopping.html', {
        'shop_list': shop_list,
        'groceries': groceries,
        'search_query': search_query
    })

@login_required
def add_to_shopping_list(request, pk):
    grocery = get_object_or_404(Grocery, pk=pk, user=request.user)
    shop_item, created = ShoppingList.objects.get_or_create(
        user=request.user,
        grocery=grocery,
        defaults={'quantity': 1}
    )
    if not created:
        shop_item.quantity += 1
        shop_item.save()
    messages.success(request, f'{grocery.grocery_name} added to your shopping list!')
    return redirect('shopping')

@login_required
def remove_from_shopping_list(request, pk):
    shop_item = get_object_or_404(ShoppingList, pk=pk, user=request.user)
    shop_item.delete()
    messages.success(request, 'Item removed from shopping list!')
    return redirect('shopping')

def signin_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        
        if not email or not password:
            messages.error(request, "Please provide both email and password")
            return render(request, 'food/signin.html')
        
        try:
            user_obj = User.objects.get(email=email)
            username = user_obj.username
        except User.DoesNotExist:
            messages.error(request, "Invalid email or password")
            return render(request, 'food/signin.html')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome {user.username}!")
            next_url = request.GET.get('next', 'index')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid email or password")
    
    return render(request, 'food/signin.html')

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        if not username or not email or not password:
            messages.error(request, "All fields are required")
            return redirect('signup')
        
        if password != confirm_password:
            messages.error(request, "Passwords do not match")
            return redirect('signup')
        
        if len(password) < 8:
            messages.error(request, "Password must be at least 8 characters")
            return redirect('signup')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists!")
            return redirect('signup')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists!")
            return redirect('signup')

        try:
            User.objects.create_user(username=username, email=email, password=password)
            messages.success(request, "Account created successfully! Please sign in.")
            return redirect('signin')
        except Exception as e:
            messages.error(request, f"Error creating account: {str(e)}")
            return redirect('signup')

    return render(request, 'food/signup.html')

@login_required
def signout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully")
    return redirect('signin')

# ============================================
# RECIPE DEDUCTION APIS
# ============================================

@login_required
def get_recipe_deduction_candidates(request, pk):
    """
    Return recipe ingredients and potential inventory matches
    for the user to confirm usage.
    """
    recipe = get_object_or_404(Receipe, pk=pk)
    recipe_ingredients = recipe.receipe_ingredients_set.all()
    user_groceries = Grocery.objects.filter(user=request.user)
    
    candidates = []
    
    for ri in recipe_ingredients:
        # Simple fuzzy match prioritization
        # 1. Exact match
        # 2. Contains match
        
        best_match_id = None
        
        # Try to find best match in inventory
        matches = []
        for g in user_groceries:
            g_name = g.grocery_name.lower()
            ri_name = ri.ingredient.name.lower()
            
            if ri_name == g_name:
                matches.insert(0, g) # Prioritize exact
            elif ri_name in g_name or g_name in ri_name:
                matches.append(g) # Append partials
        
        best_match_id = None
        deduct_qty_suggestion = ri.quantity
        conversion_note = None
        
        if matches:
            best_match = matches[0]
            best_match_id = best_match.id
            
            # Unit conversion check
            # ri.unit vs best_match.unit
            # If units differ, try to convert
            if ri.unit and best_match.unit and ri.unit.lower() != best_match.unit.lower():
                # Pass item name for specific conversions (e.g. Bread)
                converted = convert_quantity(ri.quantity, ri.unit, best_match.unit, item_name=ri.ingredient.name)
                if converted is not None:
                    deduct_qty_suggestion = round(converted, 2)
                    conversion_note = f"Converted from {ri.quantity} {ri.unit}"
        
        candidates.append({
            'ingredient_name': ri.ingredient.name,
            'quantity_needed': ri.quantity,
            'unit': ri.unit,
            'best_match_id': best_match_id,
            'deduct_qty_suggestion': deduct_qty_suggestion,
            'conversion_note': conversion_note
        })
        
    # Serialize user inventory for the dropdown
    inventory_json = [{
        'id': g.id, 
        'name': g.grocery_name, 
        'qty': g.quantity,
        'unit': g.unit # Using the actual unit field
    } for g in user_groceries]
    
    return JsonResponse({
        'status': 'success',
        'candidates': candidates,
        'inventory': inventory_json
    })

@login_required
def deduct_ingredients(request):
    """
    Deduct confirmed ingredient quantities from inventory.
    Expects JSON: { deductions: [{grocery_id: 1, deduct_qty: 0.5}, ...] }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        deductions = data.get('deductions', [])
        
        updated_count = 0
        deleted_count = 0
        
        for item in deductions:
            grocery_id = item.get('grocery_id')
            deduct_qty = float(item.get('deduct_qty', 0))
            
            if not grocery_id or deduct_qty <= 0:
                continue
                
            grocery = Grocery.objects.filter(pk=grocery_id, user=request.user).first()
            if grocery:
                if grocery.quantity <= deduct_qty:
                    grocery.delete()
                    deleted_count += 1
                else:
                    grocery.quantity -= deduct_qty
                    grocery.save()
                    updated_count += 1
                    
        return JsonResponse({
            'status': 'success',
            'message': f'Updated {updated_count} items and consumed {deleted_count} items completely.'
        })
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)