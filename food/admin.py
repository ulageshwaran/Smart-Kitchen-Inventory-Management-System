from django.contrib import admin
from .models import Grocery, GroceryType, Ingredient, Receipe, Receipe_Ingredients, ShoppingList

admin.site.register(Grocery)
admin.site.register(GroceryType)
admin.site.register(Ingredient)
admin.site.register(Receipe)
admin.site.register(Receipe_Ingredients)
admin.site.register(ShoppingList)
