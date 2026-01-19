from django import forms
from .models import Grocery, GroceryType, Receipe, Receipe_Ingredients, Ingredient, ShoppingList


# Grocery Form
class GroceryForm(forms.ModelForm):
    class Meta:
        model = Grocery
        fields = ['grocery_name', 'ex_date', 'quantity', 'grocerie_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# Receipe Form
class ReceipeForm(forms.ModelForm):
    class Meta:
        model = Receipe
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

# Receipe_Ingredients Form
class ReceipeIngredientsForm(forms.ModelForm):
    class Meta:
        model = Receipe_Ingredients
        fields = ['ingredient', 'quantity', 'unit']
        widgets = {
            'ingredient': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
        }

# ShoppingList Form
class ShoppingListForm(forms.ModelForm):
    class Meta:
        model = ShoppingList
        fields = ['grocery', 'quantity']
        widgets = {
            'grocery': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }
