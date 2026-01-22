from django.core.management.base import BaseCommand
from food.models import GroceryType, Ingredient

class Command(BaseCommand):
    help = 'Seeds database with common Indian ingredients'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding Indian ingredients...')

        # 1. Ensure Categories Exist
        categories = {
            'Spices': [
                'Turmeric Powder', 'Red Chilli Powder', 'Coriander Powder', 'Cumin Seeds', 
                'Mustard Seeds', 'Garam Masala', 'Cardamom', 'Cloves', 'Cinnamon', 
                'Fenugreek Seeds', 'Asafoetida (Hing)', 'Fennel Seeds'
            ],
            'Pulses & Legumes': [
                'Toor Dal', 'Moong Dal', 'Chana Dal', 'Urad Dal', 'Masoor Dal', 
                'Chickpeas (Chole)', 'Kidney Beans (Rajma)', 'Black Eyed Peas'
            ],
            'Grains & Flours': [
                'Basmati Rice', 'Sona Masoori Rice', 'Poha', 'Atta (Wheat Flour)', 
                'Besan (Gram Flour)', 'Surologi (Rava)', 'Maida'
            ],
            'Vegetables': [
                'Onion', 'Tomato', 'Potato', 'Ginger', 'Garlic', 'Green Chilli', 
                'Curry Leaves', 'Coriander Leaves', 'Lady Finger (Bhindi)', 
                'Brinjal', 'Cauliflower', 'Spinach (Palak)'
            ],
            'Dairy & Fats': [
                'Ghee', 'Paneer', 'Curd', 'Milk', 'Butter'
            ],
            'Condiments': [
                'Tamarind', 'Jaggery', 'Salt', 'Sugar'
            ]
        }

        created_count = 0
        
        for cat_name, items in categories.items():
            # Create Grocery Type if used for categorization (Optional, depending on usage)
            # We add them to Ingredient model mainly, but also GroceryType if needed for the Add Grocery dropdown
            category, _ = GroceryType.objects.get_or_create(type_name=cat_name)
            
            for item_name in items:
                # Add to Ingredient table (for AI recipes)
                ing, created = Ingredient.objects.get_or_create(
                    name=item_name,
                    defaults={'default_unit': 'grams'}
                )
                if created:
                    created_count += 1
                    
        self.stdout.write(self.style.SUCCESS(f'Successfully added {created_count} new Indian ingredients!'))
