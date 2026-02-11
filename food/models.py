from django.contrib.auth.models import User
from django.db import models
from datetime import date, timedelta

class Grocery(models.Model):
    CATEGORY_CHOICES = (
        ('Vegetables', 'Vegetables'),
        ('Fruits', 'Fruits'),
        ('Dairy', 'Dairy'),
        ('Meat', 'Meat/Fish'),
        ('Grains', 'Grains/Pasta'),
        ('Spices', 'Spices'),
        ('Condiments & Seasonings', 'Condiments & Seasonings'),
        ('Beverages', 'Beverages'),
        ('Snacks', 'Snacks'),
        ('Others', 'Others'),
    )

    grocery_name = models.CharField(max_length=200)
    ex_date = models.DateField()
    quantity = models.FloatField(default=1.0)
    unit = models.CharField(max_length=20, default='unit')
    grocerie_type = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='Others')
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    class Meta:
        db_table = 'food_groceries'  # matches existing table

    @property
    def is_expired(self):
        return self.ex_date < date.today()

    @property
    def is_expiring_soon(self):
        return date.today() <= self.ex_date <= date.today() + timedelta(days=7)
    def __str__(self):
        return self.grocery_name

# Ingredients
class Ingredient(models.Model):
    name = models.CharField(max_length=200, unique=True)
    default_unit = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.name


# Recipe (you need this model since Receipe_Ingredients references it)
class Receipe(models.Model):
    name = models.CharField(max_length=200, default="Unnamed Recipe")
    description = models.TextField(blank=True, null=True)
    calories = models.CharField(max_length=100, blank=True, null=True)
    protein = models.CharField(max_length=100, blank=True, null=True)
    carbs = models.CharField(max_length=100, blank=True, null=True)
    fats = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name




# Recipe-Ingredients Many-to-Many intermediate table
class Receipe_Ingredients(models.Model):
    receipe = models.ForeignKey(Receipe, on_delete=models.CASCADE)
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    quantity = models.FloatField()
    unit = models.CharField(max_length=50, blank=True, null=True)




class ShoppingList(models.Model):
    grocery = models.ForeignKey(Grocery, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'food_shop_list'
