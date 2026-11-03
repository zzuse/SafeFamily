"""Recipes shown on the /recipes page (Sheet section). Edit by hand.

To add a recipe, copy one whole ``{...},`` block below, paste it under the
last one and change the values:

- ``slug``: short unique id used in the page address (/recipes/<slug>), only
  lowercase letters, digits and dashes.
- ``image``: a file in src/safe_family/static/recipes/ (JPG, PNG, WEBP or
  SVG). Leave it as "" for no picture.
- ``ingredients`` and ``steps``: one string per line, in order.
- ``servings``, ``time``, ``tags`` and ``notes`` are optional; use "" or [].

``tests/test_recipes.py`` checks this file (required fields, unique slugs,
pictures that exist), so run ``pytest -q tests/test_recipes.py --no-cov``
after editing. The app reads it at startup: rebuild with
``docker compose up -d --build app``.
"""

RECIPES = [
    {
        "slug": "tomato-egg-stir-fry",
        "title": "Tomato and Egg Stir-Fry",
        "summary": "Soft scrambled eggs in a sweet-sour tomato sauce. Ready in 15 minutes, great over rice.",
        "image": "tomato-egg-stir-fry.svg",
        "servings": "2",
        "time": "15 min",
        "tags": ["dinner", "quick", "vegetarian"],
        "ingredients": [
            "4 eggs",
            "3 ripe tomatoes, cut into wedges",
            "2 green onions, sliced (white and green parts apart)",
            "1 tbsp ketchup",
            "1 tsp sugar",
            "1/2 tsp salt",
            "3 tbsp cooking oil",
            "2 tbsp water",
        ],
        "steps": [
            "Beat the eggs with a pinch of salt until smooth.",
            "Heat 2 tbsp oil in a wok over medium-high heat. Pour in the eggs, stir gently until just set but still soft, then move them to a plate.",
            "Add the remaining oil, fry the white parts of the green onion for 10 seconds, then add the tomatoes.",
            "Cook the tomatoes for 2-3 minutes, pressing them a little, until they turn saucy. Stir in the ketchup, sugar, salt and water.",
            "Return the eggs, fold them through the sauce for 30 seconds, and top with the green onion tops.",
            "Serve right away with steamed rice.",
        ],
        "notes": "Very ripe tomatoes give the best sauce; in winter add 1 extra tbsp ketchup.",
    },
]
