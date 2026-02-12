# Smart Kitchen Inventory Management System - Project Analysis

## 1. Project Overview
This project is a Django-based web application designed to help users manage their kitchen inventory, generate recipes using AI, and automate grocery tracking via bill analysis. It leverages Google's Gemini API for its AI capabilities.

## 2. Directory Structure
```
root/
├── core/                 # Django Project Configuration
│   ├── settings.py       # Global settings (Apps, DB, Auth, API Keys)
│   ├── urls.py           # Root URL routing
│   └── ...
├── food/                 # Main Application Logic
│   ├── models.py         # Database Schemas (Grocery, Receipe, etc.)
│   ├── views.py          # Business Logic (Inventory, AI, Shopping List)
│   ├── urls.py           # App-specific URL routing
│   └── ...
├── templates/            # HTML Templates
│   └── food/             # App-specific templates (index.html, add.html, etc.)
├── static/               # Static Assets (CSS, JS, Images)
├── manage.py             # Django Command Line Utility
└── db.sqlite3            # SQLite Database
```

## 3. Key Modules & Functionality

### A. Core Configuration (`core`)
- **Settings:** Configured for local development with `DEBUG=True`.
- **Database:** Uses SQLite (`db.sqlite3`).
- **Apps:** Standard Django apps + `food`.
- **Authentication:** Custom `EmailBackend` configured alongside default `ModelBackend`.

### B. Food Management App (`food`)
This is the heart of the application, handling all user-facing features.

#### 1. Inventory Management
- **Goal:** Track kitchen ingredients, expiry dates, and quantities.
- **Key Views:**
    - `index`: Dashboard displaying utilizing `expiry_warnings` context processor.
    - `add_grocery`, `edit_grocery`, `delete_grocery`: CRUD operations for inventory items.
- **Data Model:** `Grocery` (stores name, quantity, unit, manufacturing/expiry dates).

#### 2. AI Chef & Recipe Generation
- **Goal:** Suggest recipes based on available ingredients and user preferences.
- **Key Functions:**
    - `get_ai_recipe_suggestion`: interface with Google Gemini API.
    - `generate_recipes_api`: AJAX endpoint generating structured JSON recipes (Name, Ingredients, Instructions, Time, Difficulty, Macros).
    - `suggest_recipes`: Landing page for the AI Chef.
    - `save_recipe`: Persists generated recipes to the database.
- **Data Model:** `Receipe` (stores description, instructions, time, macros).

#### 3. Smart Document Analysis (Bill & Image)
- **Goal:** Automate inventory entry by scanning receipts and food images.
- **Key Functionality:**
    - **Bill Upload:** `upload_bill_view` and `save_bill_items` use Gemini Vision to parse grocery bills into structured items (Name, Qty, MFD, Expiry).
    - **Food Analysis:** `analyze_food_view` identifies food items from photos.

#### 4. Shopping List
- **Goal:** Manage items to buy.
- **Views:** `shopping_list`, `add_to_shopping_list`, `remove_from_shopping_list`.

### C. Frontend Architecture
- **Tech Stack:** Django Templates, HTML5, JavaScript (Vanilla), Bootstrap (inferred from classes).
- **Dynamic Features:**
    - **Recipe Generation:** Asynchronous calls to `generate_recipes_api` with real-time UI updates.
    - **Bill Scanning:** Drag-and-drop file upload with preview and editable result table.

## 4. External Dependencies
- **Django:** Web framework.
- **Google Generative AI (Gemini):** Used for:
    - Recipe generation (Text-to-Text).
    - Bill/Image analysis (Image-to-Text).
- **Pillow:** Image processing.
- **Python-dotenv:** Environment variable management.

## 5. Recent Improvements (Session History)
- **Recipe Accuracy:** Added `cooking_time` and `difficulty` fields to the AI prompt and database model.
- **UI Refinements:** Improved instruction formatting (removing redundant "Step X" prefixes) and added "Per Serving" labels.
- **Robustness:** Fixed error handling for empty Manufacturing Dates during bill upload.
