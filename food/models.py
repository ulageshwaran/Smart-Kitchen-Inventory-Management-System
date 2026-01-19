from django.contrib.auth.models import User
from django.db import models
from datetime import date, timedelta

# Grocery Categories
class GroceryType(models.Model):
    type_name = models.CharField(max_length=100)

    class Meta:
        db_table = 'food_groceries_type'  # matches existing table

    def __str__(self):
        return self.type_name


class Grocery(models.Model):
    grocery_name = models.CharField(max_length=200)
    ex_date = models.DateField()
    quantity = models.PositiveIntegerField(default=1)
    grocerie_type = models.ForeignKey(GroceryType, on_delete=models.CASCADE)
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
