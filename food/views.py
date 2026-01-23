from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Grocery, GroceryType, ShoppingList, Receipe, Receipe_Ingredients, Ingredient
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
    ).select_related('grocerie_type')
    
    expiring_soon = Grocery.objects.filter(
        user=user,
        ex_date__gte=today,
        ex_date__lte=today + timedelta(days=7)
    ).select_related('grocerie_type')
    
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
    groceries = Grocery.objects.filter(user=request.user).select_related('grocerie_type')
    
    if search_query:
        groceries = groceries.filter(
            Q(grocery_name__icontains=search_query) |   
            Q(grocerie_type__type_name__icontains=search_query)
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
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return None, "Gemini API key not configured. Please set GEMINI_API_KEY environment variable."
        
        # Gemini API endpoint - use latest model
        # Gemini API endpoint - use latest model
        # Using gemini-flash-latest (fastest, free tier)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        
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
    all_groceries = Grocery.objects.filter(user=user).select_related('grocerie_type')
    
    expiring_soon = []
    others = []
    
    for g in all_groceries:
        if g.is_expiring_soon or g.is_expired:
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
        
        user = request.user
        today = date.today()
        
        # Get ingredients
        groceries = Grocery.objects.filter(user=user)
        
        expiring = []
        others = []
        
        for g in groceries:
            if g.is_expiring_soon or g.is_expired:
                expiring.append(g.grocery_name)
            else:
                others.append(g.grocery_name)
        
        if not expiring and not others:
            return JsonResponse({
                'status': 'error', 
                'message': 'No ingredients found in your kitchen!'
            }, status=400)
            
        # Call Gemini
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return JsonResponse({'status': 'error', 'message': 'API key not configured'}, status=500)
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        
        expiring_str = ", ".join(expiring)
        others_str = ", ".join(others)
        
        prompt = f"""As a creative chef, generate 3 detailed recipes based on these available ingredients.
        
CRITICAL PRIORITY (Use these if possible as they are expiring):
{expiring_str if expiring else 'None'}

OTHER AVAILABLE INGREDIENTS:
{others_str if others else 'None'}

User Preferences: {preferences if preferences else 'None'}

Rules:
1. You don't have to use ALL ingredients, but try to use the PRIORITY ones to reduce waste.
2. You can assume basic pantry staples (oil, salt, pepper, water) are available.

Return the response ONLY as a valid JSON list of objects. No markdown formatting.
Example format:
[
    {{
        "name": "Recipe Name",
        "description": "Brief description",
        "ingredients": ["1 cup Rice", "2 Tomatoes"],
        "instructions": ["Step 1...", "Step 2..."],
        "time": "30 mins",
        "difficulty": "Easy",
        "calories": "300 kcal",
        "macros": {{ "protein": "20g", "carbs": "45g", "fats": "15g" }},
        "uses_expiring": true
    }}
]
"""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
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
                        return JsonResponse({'status': 'success', 'recipes': recipes_data})
                    except json.JSONDecodeError:
                        # Fallback if AI fails JSON format
                        return JsonResponse({'status': 'error', 'message': 'AI response format error'}, status=500)
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

@login_required
def save_recipe(request):
    """Save generated recipe to database"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Extract macros if available
            macros = data.get('macros', {})
            
            recipe = Receipe.objects.create(
                name=data.get('recipe_name', 'Unnamed Recipe'),
                description=data.get('instructions', ''),
                calories=data.get('calories', ''),
                protein=macros.get('protein', ''),
                carbs=macros.get('carbs', ''),
                fats=macros.get('fats', '')
            )
            
            # Save ingredients
            ingredients_dict = data.get('ingredients', {})
            for ingredient_name in ingredients_dict.keys():
                ingredient, _ = Ingredient.objects.get_or_create(
                    name=ingredient_name
                )
                Receipe_Ingredients.objects.create(
                    receipe=recipe,
                    ingredient=ingredient,
                    quantity=1,
                    unit='as needed'
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
            
            api_key = os.environ.get('GEMINI_API_KEY')
            if not api_key:
                return JsonResponse({
                    'status': 'error',
                    'message': 'API not configured'
                }, status=400)
            
            # Use same API endpoint as recipe generation
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
            
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
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
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
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return None, "Gemini API key not configured."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        
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
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
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

def analyze_bill_image(image_data, grocery_types):
    """
    Analyze bill image using Gemini Flash Vision
    Returns a list of identified items with estimated expiry
    """
    try:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            return None, "Gemini API key not configured."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
        
        # Create category list string
        categories_str = ", ".join([t.type_name for t in grocery_types])
        
        prompt = f"""Analyze this grocery bill/receipt image and extract ONLY the food/grocery items. 
Ignore non-food items (like soap, paper towels) and general receipt text (taxes, store name).

For each food item, provide:
1. Generic Ingredient Name ONLY. Remove all brand names, packaging info, and adjectives. 
   - Example: "Aashirvaad Shudh Chakki Atta" -> "Whole Wheat Flour" or "Atta"
   - Example: "Amul Gold Milk" -> "Milk"
   - Example: "Maggi Noodles" -> "Instant Noodles"
   - Example: "Tata Salt" -> "Salt"
2. Quantity (default to 1 if not specified)
3. Estimated Expiry Date (YYYY-MM-DD) - Make a reasonable guess based on the type of food (e.g., Milk: 7 days, Rice: 1 year, Vegetables: 5 days). Today is {date.today()}.
4. Category - Choose the best match from this list: [{categories_str}]

Format the response as a valid JSON list of objects.
Example format:
[
  {{"name": "Milk", "quantity": 1, "expiry": "2024-02-01", "category": "Dairy"}},
  {{"name": "Basmati Rice", "quantity": 1, "expiry": "2025-01-01", "category": "Grains"}}
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
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        
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
    grocery_types = GroceryType.objects.all()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            image_b64 = data.get('image')
            
            if not image_b64:
                return JsonResponse({'status': 'error', 'message': 'No image provided'}, status=400)
                
            if ',' in image_b64:
                image_b64 = image_b64.split(',')[1]
                
            items, error = analyze_bill_image(image_b64, grocery_types)
            
            if error:
                return JsonResponse({'status': 'error', 'message': error}, status=400)
                
            return JsonResponse({
                'status': 'success',
                'items': items,
                'categories': [{'id': t.id, 'name': t.type_name} for t in grocery_types]
            })
            
        except Exception as e:
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
                grocery_type = GroceryType.objects.filter(type_name__iexact=category_name).first()
                
                if not grocery_type:
                    # Fallback to first category or a default "Others" if you have it
                    grocery_type = GroceryType.objects.first()
                
                Grocery.objects.create(
                    grocery_name=item.get('name'),
                    ex_date=item.get('expiry'),
                    quantity=float(item.get('quantity', 1)),
                    grocerie_type=grocery_type,
                    user=request.user
                )
                saved_count += 1
            
            messages.success(request, f'Successfully added {saved_count} items to your pantry!')
            return JsonResponse({'status': 'success', 'count': saved_count})
            
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
    return JsonResponse({'error': 'Invalid request'}, status=400)


# ============================================
# EXISTING FUNCTIONS (Keep as is)
# ============================================

@login_required
def add_grocery(request):
    grocery_types = GroceryType.objects.all()
    
    if request.method == 'POST':
        grocery_name = request.POST.get('grocery_name')
        ex_date = request.POST.get('ex_date')
        quantity = request.POST.get('quantity')
        grocerie_type_id = request.POST.get('grocerie_type')
        
        try:
            grocerie_type = GroceryType.objects.get(id=grocerie_type_id)
            Grocery.objects.create(
                grocery_name=grocery_name,
                ex_date=ex_date,
                quantity=quantity,
                grocerie_type=grocerie_type,
                user=request.user
            )
            messages.success(request, 'Grocery added successfully!')
            return redirect('index')
        except Exception as e:
            messages.error(request, f'Error adding grocery: {str(e)}')
    
    return render(request, 'food/add.html', {
        'grocery_types': grocery_types,
        'is_editing': False
    })

@login_required
def edit_grocery(request, pk):
    grocery = get_object_or_404(Grocery, pk=pk, user=request.user)
    grocery_types = GroceryType.objects.all()
    
    if request.method == 'POST':
        grocery_name = request.POST.get('grocery_name')
        ex_date = request.POST.get('ex_date')
        quantity = request.POST.get('quantity')
        grocerie_type_id = request.POST.get('grocerie_type')
        
        try:
            grocerie_type = GroceryType.objects.get(id=grocerie_type_id)
            grocery.grocery_name = grocery_name
            grocery.ex_date = ex_date
            grocery.quantity = quantity
            grocery.grocerie_type = grocerie_type
            grocery.save()
            messages.success(request, 'Grocery updated successfully!')
            return redirect('index')
        except Exception as e:
            messages.error(request, f'Error updating grocery: {str(e)}')
    
    form_data = {
        'grocery_name': {'value': grocery.grocery_name},
        'ex_date': {'value': grocery.ex_date.strftime('%Y-%m-%d')},
        'quantity': {'value': grocery.quantity},
        'grocerie_type': {'value': grocery.grocerie_type.id}
    }
    
    return render(request, 'food/add.html', {
        'form': type('obj', (object,), form_data),
        'grocery_types': grocery_types,
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
    shop_list = ShoppingList.objects.filter(user=request.user).select_related('grocery', 'grocery__grocerie_type')
    groceries = Grocery.objects.filter(user=request.user).select_related('grocerie_type')
    
    if search_query:
        groceries = groceries.filter(
            Q(grocery_name__icontains=search_query) |
            Q(grocerie_type__type_name__icontains=search_query)
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
        
        best_match_id = matches[0].id if matches else None
        
        candidates.append({
            'ingredient_name': ri.ingredient.name,
            'quantity_needed': ri.quantity,
            'unit': ri.unit,
            'best_match_id': best_match_id
        })
        
    # Serialize user inventory for the dropdown
    inventory_json = [{
        'id': g.id, 
        'name': g.grocery_name, 
        'qty': g.quantity,
        'unit': g.grocerie_type.type_name # Using category as proxy for unit context sometimes
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