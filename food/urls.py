from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('add/', views.add_grocery, name='add'),
    path('edit/<int:pk>/', views.edit_grocery, name='edit'),
    path('delete/<int:pk>/', views.delete_grocery, name='delete'),
    path('shopping/', views.shopping_list, name='shopping'),
    path('shopping/add/<int:pk>/', views.add_to_shopping_list, name='add_to_shopping_list'),
    path('shopping/remove/<int:pk>/', views.remove_from_shopping_list, name='remove_from_shopping_list'),
    path('signin/', views.signin_view, name='signin'),
    path('signup/', views.signup_view, name='signup'),
    path('signout/', views.signout_view, name='signout'),
    # New recipe AI routes
    path('recipes/suggest/', views.suggest_recipes, name='suggest_recipes'),
    path('recipes/save/', views.save_recipe, name='save_recipe'),
    path('recipes/refine/', views.refine_recipe, name='refine_recipe'),
    # View saved recipes
    path('recipes/', views.view_saved_recipes, name='view_saved_recipes'),
    path('recipes/<int:pk>/', views.view_recipe_detail, name='recipe_detail'),
    path('recipes/<int:pk>/delete/', views.delete_recipe_view, name='delete_recipe'),
    # Food Analysis
    path('analyze-food/', views.analyze_food_view, name='analyze_food'),
    # Bill Upload
    path('upload-bill/', views.upload_bill_view, name='upload_bill'),
    path('save-bill-items/', views.save_bill_items, name='save_bill_items'),
    # AI Chef API
    path('api/generate-recipes/', views.generate_recipes_api, name='generate_recipes_api'),
    path('api/recipe/<int:pk>/candidates/', views.get_recipe_deduction_candidates, name='get_recipe_deduction_candidates'),
    path('api/deduct-ingredients/', views.deduct_ingredients, name='deduct_ingredients'),
]