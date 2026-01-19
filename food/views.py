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

@login_required
def index(request):
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
        # Using gemini-2.5-flash (fastest, free tier)
        url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
        
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
def suggest_recipes(request):
    """Get AI-suggested recipes based on soon-expiring ingredients"""
    user = request.user
    today = date.today()
    
    # Get items expiring within 7 days
    expiring_soon = Grocery.objects.filter(
        user=user,
        ex_date__lte=today + timedelta(days=7),
        ex_date__gte=today
    ).select_related('grocerie_type').order_by('ex_date')
    
    if not expiring_soon.exists():
        messages.info(request, "No ingredients expiring soon! Your fridge is in good shape.")
        return redirect('index')
    
    # Extract ingredient info
    ingredients = [g.grocery_name for g in expiring_soon]
    expiry_info = [(g.grocery_name, g.ex_date) for g in expiring_soon]
    
    # Get preferences from request if provided
    preferences = request.GET.get('preferences', '')
    
    # Generate recipes using Gemini API
    recipes_text, error = get_ai_recipe_suggestion(ingredients, preferences)
    
    if error:
        messages.error(request, f"Could not generate recipes: {error}")
        return redirect('index')
    
    if not recipes_text:
        messages.error(request, "Failed to generate recipes. Please try again.")
        return redirect('index')
    
    return render(request, 'food/recipes_suggestion.html', {
        'recipes': recipes_text,
        'expiring_items': expiring_soon,
        'expiry_info': expiry_info,
        'ingredients_list': ingredients
    })

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
            
            recipe = Receipe.objects.create(
                name=data.get('recipe_name', 'Unnamed Recipe'),
                description=data.get('instructions', '')
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
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
    
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
            url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={api_key}"
            
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