# Smart Kitchen Inventory System - Design & Architecture

## 1. System Architecture

The project follows the standard **Django Model-View-Template (MVT)** architecture, integrated with **Google Gemini AI** for intelligent features.

### Architecture Diagram
```mermaid
graph TD
    User((User))
    
    subgraph "Frontend (Templates)"
        UI[HTML/Bootstrap Interface]
        JS[JavaScript / AJAX]
    end
    
    subgraph "Backend (Django)"
        URL[URL Routing]
        View[Views / Business Logic]
        Model[ORM Models]
    end
    
    subgraph "Database"
        DB[(SQLite3)]
    end
    
    subgraph "External Services"
        Gemini[Google Gemini API]
    end

    User <-->|HTTP Request/Response| UI
    UI <-->|AJAX/Form Data| URL
    URL --> View
    View <-->Model
    Model <--> DB
    View <-->|API Calls| Gemini
```

---

## 2. Module Details

### A. Authentication Module (`core`)
*   **Purpose**: Manages user access and security.
*   **Key Components**:
    *   `EmailBackend`: Custom authentication backend allowing login via email.
    *   `signin_view`, `signup_view`: Handle user sessions.
*   **Data Flow**: User Credentials -> Validation -> Session Creation.

### B. Inventory Module (`food`)
*   **Purpose**: Tracks grocery items, quantities, and expiry dates.
*   **Key Components**:
    *   `Grocery` Model: Stores item details (name, qty, unit, dates).
    *   `add_expiry_warnings`: Context processor that injects expiry alerts globally.
*   **Data Flow**: User Input -> Model Validation -> Database -> Dashboard Query.

### C. AI Chef Module (`food`)
*   **Purpose**: Generates recipes based on inventory.
*   **Key Components**:
    *   `generate_recipes_api`: Main logic engine. 
    *   Prompts: Custom engineered prompts to request JSON output from Gemini.
    *   `Receipe` Model: Caches generated recipes.
*   **Data Flow**: Inventory List -> Prompt Construction -> Gemini API -> JSON Parsing -> Frontend Display.

### D. Smart Scan Module (`food`)
*   **Purpose**: Digitizes physical data (bills, food photos).
*   **Key Components**:
    *   `upload_bill_view`: Handles file uploads.
    *   `save_bill_items`: Processes parsed bill data into inventory.
*   **Data Flow**: Image Upload -> Base64 Encoding -> Gemini Vision API -> Structured Data -> User Review -> Database.

---

## 3. Use Case Diagram

```mermaid
flowchart LR
    User[User]
    AI[Google Gemini]

    subgraph "Smart Kitchen System"
        UC1(Manage Inventory)
        UC2(Upload Bill)
        UC3(Generate Recipes)
        UC4(View Analytics)
        UC5(Manage Shopping List)
    end

    User --> UC1
    User --> UC2
    User --> UC3
    User --> UC4
    User --> UC5

    UC2 -.-> AI
    UC3 -.-> AI
```

---

## 4. Database Schema (ER Diagram)

```mermaid
erDiagram
    User ||--o{ Grocery : owns
    User ||--o{ Receipe : saves
    User ||--o{ ShoppingList : maintains

    Grocery {
        string grocery_name
        float quantity
        string unit
        date manufacturing_date
        date ex_date
    }

    Receipe {
        string name
        text description
        text instructions
        string cooking_time
        string difficulty
        float calories
    }

    ShoppingList {
        string item_name
        float quantity
        boolean is_bought
    }
```

## 5. Sequence Diagram: Recipe Generation
To illustrate the interaction between the user, system, and AI:

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant V as Django View
    participant AI as Gemini API
    
    U->>F: Click "Generate Recipes"
    F->>V: POST /api/generate-recipes/ (Preferences)
    V->>V: Fetch User's Ingredients
    V->>AI: Send Prompt (Ingredients + Constraints)
    AI-->>V: Return JSON Recipe Data
    V->>F: Return JSON Response
    F-->>U: Display Recipe Cards
```
