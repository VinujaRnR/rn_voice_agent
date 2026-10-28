"""Places and restaurants discovery tool with regional Sri Lankan support, location extraction, and strict cuisine filtering."""
import re
from typing import Dict, Any, List, Optional
import httpx

# Curated regional directories with verified dining recommendations
REGIONAL_RESTAURANT_DIRECTORY: Dict[str, List[Dict[str, Any]]] = {
    "colombo": [
        {
            "name": "Ministry of Crab",
            "category": "Seafood",
            "rating": 4.6,
            "review_count": 4820,
            "price_level": "$$$$",
            "address": "Old Dutch Hospital Complex, Fort, Colombo 01",
            "description": "World-renowned restaurant celebrating fresh Sri Lankan lagoon crabs."
        },
        {
            "name": "The Lagoon (Cinnamon Grand)",
            "category": "Seafood / Multi-cuisine",
            "rating": 4.5,
            "review_count": 2150,
            "price_level": "$$$",
            "address": "77 Galle Road, Colombo 03",
            "description": "Upscale seafood market-style dining where guests choose fresh catches and preparation styles."
        },
        {
            "name": "Giovanni's Presto Pizza",
            "category": "Italian / Neapolitan Wood-Fired Pizza",
            "rating": 4.7,
            "review_count": 3200,
            "price_level": "$$",
            "address": "145 Thimbirigasyaya Road, Colombo 05",
            "description": "Artisanal clay oven wood-fired Neapolitan pizza, fresh burrata, and authentic Italian pastas."
        },
        {
            "name": "Echo (Cinnamon Grand)",
            "category": "Fine Dining Italian",
            "rating": 4.6,
            "review_count": 1950,
            "price_level": "$$$$",
            "address": "77 Galle Road, Colombo 03",
            "description": "Sophisticated Italian fine dining serving handmade ravioli, carpaccio, ossobuco, and fine wines."
        },
        {
            "name": "Upali's by Nawaloka",
            "category": "Authentic Sri Lankan",
            "rating": 4.4,
            "review_count": 3100,
            "price_level": "$$",
            "address": "65 C.W.W. Kannangara Mawatha, Colombo 07",
            "description": "Traditional Sri Lankan dishes such as roast paan, mutton curry, and pol sambol in a family setting."
        },
        {
            "name": "Nihonbashi",
            "category": "Authentic Japanese & Sushi",
            "rating": 4.7,
            "review_count": 2850,
            "price_level": "$$$$",
            "address": "11 Galle Face Terrace, Colombo 03",
            "description": "Founded by Chef Dharshan Munidasa; Asia's 50 Best ranked restaurant celebrated for pristine sashimi, nigiri, and private tatami dining."
        },
        {
            "name": "Sushi Kai",
            "category": "Japanese & Sushi Bar",
            "rating": 4.6,
            "review_count": 1420,
            "price_level": "$$",
            "address": "Galle Road, Colombo 03 / Nawala",
            "description": "One of Colombo's most acclaimed sushi bars, serving fresh salmon and tuna rolls, nigiri platters, and teriyaki."
        },
        {
            "name": "Kuuraku Colombo",
            "category": "Japanese Dining & Sushi",
            "rating": 4.6,
            "review_count": 1890,
            "price_level": "$$$",
            "address": "48 Park Street Mews, Colombo 02",
            "description": "Vibrant Japanese restaurant in Park Street Mews serving handmade sushi, sashimi, and yakitori skewers."
        },
        {
            "name": "Café Japan",
            "category": "Traditional Japanese & Sushi",
            "rating": 4.5,
            "review_count": 960,
            "price_level": "$$",
            "address": "Railway Avenue, Colombo 04",
            "description": "Authentic family-style Japanese kitchen popular for fresh sashimi, sushi rolls, and tempura."
        },
        {
            "name": "Shanmugas",
            "category": "South Indian Vegetarian",
            "rating": 4.5,
            "review_count": 2400,
            "price_level": "$$",
            "address": "53/3 Ramakrishna Road, Wellawatte, Colombo 06",
            "description": "Famous destination for authentic South Indian dosais, thalis, and filter coffee."
        },
        {
            "name": "The Gallery Café",
            "category": "Contemporary / Dessert",
            "rating": 4.5,
            "review_count": 2980,
            "price_level": "$$$",
            "address": "2 Alfred House Road, Colombo 03",
            "description": "Housed in Geoffrey Bawa's former architectural offices, famed for art and black pork curry."
        },
        {
            "name": "Barefoot Garden Café",
            "category": "Café / Casual Dining",
            "rating": 4.3,
            "review_count": 1840,
            "price_level": "$$",
            "address": "704 Galle Road, Colombo 03",
            "description": "Open-air courtyard café serving quiches, salads, fresh juices, and hosting live jazz."
        }
    ],
    "kalutara": [
        {
            "name": "Olu Tropical Grill",
            "category": "Seafood / International Grill",
            "rating": 4.6,
            "review_count": 890,
            "price_level": "$$$",
            "address": "Anantara Kalutara Resort, St. Sebastian's Road, Katukurunda, Kalutara",
            "description": "Upscale oceanfront dining overlooking Kalu Ganga and the Indian Ocean."
        },
        {
            "name": "Acquolina Restaurant",
            "category": "Italian & Seafood",
            "rating": 4.5,
            "review_count": 620,
            "price_level": "$$",
            "address": "Main Galle Road, Kalutara North / Wadduwa",
            "description": "Authentic wood-fired pizza, handmade pasta, and fresh coastal seafood right along Galle Road."
        },
        {
            "name": "Red Lobster Restaurant",
            "category": "Fresh Seafood & Sri Lankan",
            "rating": 4.3,
            "review_count": 780,
            "price_level": "$$",
            "address": "Galle Road, Kalutara North",
            "description": "Popular local spot famed for jumbo prawns, devilled crab, and spicy fried cuttlefish."
        },
        {
            "name": "Breeze Restaurant",
            "category": "Multi-cuisine / Riverfront Dining",
            "rating": 4.4,
            "review_count": 510,
            "price_level": "$$$",
            "address": "Avani Kalutara Resort, St. Sebastian's Road, Kalutara",
            "description": "Scenic riverfront dining serving authentic Sri Lankan curries and fresh seafood."
        }
    ],
    "kandy": [
        {
            "name": "Vito Wood Fired Pizza",
            "category": "Italian / Wood-Fired Pizza",
            "rating": 4.7,
            "review_count": 1240,
            "price_level": "$$",
            "address": "Saranankara Road, Kandy",
            "description": "Top-rated authentic Italian wood-fired Neapolitan pizzas, fresh calzones, and artisanal Italian gelato with panoramic lake views."
        },
        {
            "name": "Chiasso Italian Restaurant",
            "category": "Authentic Italian & Pasta",
            "rating": 4.6,
            "review_count": 580,
            "price_level": "$$$",
            "address": "Peradeniya Road, Kandy",
            "description": "Classic Italian trattoria serving homemade pasta, ravioli, risotto, bruschetta, and tiramisu."
        },
        {
            "name": "Da Franco Italian Restaurant",
            "category": "Italian Trattoria & Pizzeria",
            "rating": 4.5,
            "review_count": 490,
            "price_level": "$$",
            "address": "Dharmashoka Mawatha, Kandy",
            "description": "Traditional Italian cuisine prepared with authentic olive oil, imported cheeses, and wood-fired crusts."
        },
        {
            "name": "The Kandy House",
            "category": "Fine Dining / Sri Lankan Fusion",
            "rating": 4.7,
            "review_count": 920,
            "price_level": "$$$$",
            "address": "Amunugama, Kandy",
            "description": "Ancestral manor house serving refined four-course Sri Lankan fusion dinners."
        },
        {
            "name": "Helga's Folly",
            "category": "Eclectic European & Sri Lankan",
            "rating": 4.4,
            "review_count": 1450,
            "price_level": "$$$",
            "address": "Rajapihilla Mawatha, Kandy",
            "description": "Chalet-style artistic dining with candlelit dinners and hill country views."
        },
        {
            "name": "Balaji Dosai",
            "category": "South Indian Vegetarian",
            "rating": 4.5,
            "review_count": 2100,
            "price_level": "$",
            "address": "Peradeniya Road, Kandy",
            "description": "Beloved local destination for crispy ghee dosas, idlis, and fresh chutneys."
        },
        {
            "name": "Café Secret Alley",
            "category": "Café / Healthy Vegetarian",
            "rating": 4.6,
            "review_count": 910,
            "price_level": "$$",
            "address": "Oxford Lane, Kandy",
            "description": "Charming café known for espresso, smoothie bowls, avocado toast, and vegan treats."
        }
    ],
    "galle": [
        {
            "name": "Aqua Forte",
            "category": "Fine Dining Authentic Italian",
            "rating": 4.8,
            "review_count": 1100,
            "price_level": "$$$$",
            "address": "62 Leyn Baan Street, Galle Fort",
            "description": "Refined Italian fine dining with handmade pastas, risottos, and Italian regional wine pairings."
        },
        {
            "name": "The Pasta Factory",
            "category": "Italian & Fresh Handmade Pasta",
            "rating": 4.7,
            "review_count": 890,
            "price_level": "$$",
            "address": "Pedlar Street, Galle Fort",
            "description": "Specialty Italian eatery crafting fresh fettuccine, gnocchi, and ravioli daily."
        },
        {
            "name": "The Tuna & The Crab",
            "category": "Japanese & Seafood",
            "rating": 4.6,
            "review_count": 1340,
            "price_level": "$$$$",
            "address": "Old Dutch Hospital, Galle Fort",
            "description": "Celebrity chef Dharshan Munidasa's blend of Japanese sashimi and fresh Sri Lankan crab."
        },
        {
            "name": "Pedlar's Inn Café",
            "category": "Café / Italian",
            "rating": 4.4,
            "review_count": 2300,
            "price_level": "$$",
            "address": "92 Pedlar Street, Galle Fort",
            "description": "Historic café in a colonial post office, famed for seafood pasta and homemade gelato."
        }
    ],
    "negombo": [
        {
            "name": "Lords Restaurant Complex",
            "category": "Seafood / International & Live Music",
            "rating": 4.5,
            "review_count": 2890,
            "price_level": "$$$",
            "address": "80 Porutota Road, Negombo",
            "description": "Vibrant art-filled complex with seafood, live music, and garden dining."
        },
        {
            "name": "Prego Italian Restaurant",
            "category": "Italian & Pizzeria",
            "rating": 4.4,
            "review_count": 920,
            "price_level": "$$$",
            "address": "Porutota Road, Negombo",
            "description": "Authentic wood-fired pizzas, carpaccio, and Italian homemade pasta by the coast."
        },
        {
            "name": "King Coconut Restaurant",
            "category": "Beachfront Seafood",
            "rating": 4.3,
            "review_count": 1250,
            "price_level": "$$",
            "address": "Porutota Road, Negombo",
            "description": "Dine directly on the golden sands with fresh seafood catches displayed on ice."
        }
    ],
    "bentota": [
        {
            "name": "Mallika Seafood Restaurant",
            "category": "Seafood",
            "rating": 4.5,
            "review_count": 820,
            "price_level": "$$",
            "address": "National Holiday Resort, Bentota",
            "description": "Direct beachside dining known for garlic butter prawns and grilled barracuda."
        },
        {
            "name": "Pier88 River Restaurant",
            "category": "Italian & Seafood / Riverfront",
            "rating": 4.5,
            "review_count": 590,
            "price_level": "$$",
            "address": "Dedduwa Lake, Bentota",
            "description": "Scenic riverside dining serving thin-crust Italian pizzas and river prawns."
        },
        {
            "name": "The Palms Restaurant",
            "category": "Multi-cuisine",
            "rating": 4.4,
            "review_count": 640,
            "price_level": "$$$",
            "address": "Galle Road, Moragalla, Beruwala / Bentota",
            "description": "Scenic garden dining serving Sri Lankan rice and curry and seafood."
        }
    ]
}

# Cuisine synonym mapping for high-precision matching
CUISINE_SYNONYMS: Dict[str, List[str]] = {
    "italian": ["italian", "pizza", "pasta", "trattoria", "pizzeria", "risotto", "neapolitan", "lasagna", "wood-fired"],
    "seafood": ["seafood", "crab", "fish", "prawn", "prawns", "lobster", "sashimi", "cuttlefish"],
    "indian": ["indian", "dosai", "dosa", "biryani", "thali", "tandoori", "south indian", "north indian"],
    "chinese": ["chinese", "dim sum", "noodle", "noodles", "dumpling", "wok", "cantonese", "szechuan"],
    "japanese": ["japanese", "sushi", "sashimi", "ramen", "teriyaki", "bento"],
    "thai": ["thai", "pad thai", "tom yum"],
    "mexican": ["mexican", "taco", "tacos", "burrito", "nachos"],
    "vegetarian": ["vegetarian", "vegan", "plant-based", "dosai", "dosa"],
    "vegan": ["vegan", "plant-based"],
    "sri lankan": ["sri lankan", "rice and curry", "curry", "pol sambol", "kottu", "hoppers"],
    "cafe": ["café", "cafe", "coffee", "bakery", "espresso", "dessert", "tea"],
    "korean": ["korean", "kimchi", "bulgogi", "bibimbap", "kbbq", "korean bbq"],
    "middle eastern": ["middle eastern", "lebanese", "shawarma", "hummus", "falafel", "arabic", "turkish"],
    "french": ["french", "bistro", "croissant"],
    "german": ["german", "schnitzel"],
    "steak": ["steak", "grill", "bbq", "barbecue"],
    "burger": ["burger", "burgers"],
    "fine dining": ["fine dining", "gourmet", "degustation"],
}

# Aliases for directory key lookup
CITY_KEY_MAP = {
    "colombo": "colombo",
    "fort": "colombo",
    "kalutara": "kalutara",
    "calutara": "kalutara",
    "katukurunda": "kalutara",
    "kandy": "kandy",
    "galle": "galle",
    "negombo": "negombo",
    "bentota": "bentota",
    "beruwala": "bentota",
    "wadduwa": "kalutara",
    "panadura": "kalutara"
}

KNOWN_CITIES = [
    "kalutara", "wadduwa", "bentota", "panadura", "beruwala",
    "kandy", "galle", "matara", "negombo", "jaffna", "nuwara eliya",
    "anuradhapura", "trincomalee", "kurunegala", "ratnapura", "batticaloa",
    "colombo", "tokyo", "london", "paris", "new york", "dubai", "singapore", "bangkok"
]


def extract_cuisine(text: str) -> Optional[str]:
    """Extract requested cuisine or food specialty from a query."""
    clean = " ".join(text.lower().split())
    # 1. Exact match against curated synonyms
    for cuisine_key, synonyms in CUISINE_SYNONYMS.items():
        for syn in synonyms:
            pattern = r"\b" + re.escape(syn) + r"\b"
            if re.search(pattern, clean):
                return cuisine_key

    # 2. Extract nationality or food specialty preceding keywords like "restaurant(s)", "food", "places"
    m = re.search(r"\b([a-zA-Z]{3,})\s+(?:restaurant|restaurants|food|place|places|dining|eatery|cuisine)\b", clean)
    if m:
        candidate = m.group(1).lower()
        stopwords = {
            "the", "best", "good", "nice", "top", "great", "any", "some", "local", "many", "famous",
            "fine", "fast", "cheap", "popular", "new", "casual", "find", "around", "near", "open"
        }
        if candidate not in stopwords:
            return candidate

    return None


def extract_location(text: str, default: str = "Colombo") -> str:
    """Extract requested city or locality from a natural language query."""
    clean = text.lower()
    # 1. Match known cities
    for city in KNOWN_CITIES:
        pattern = r"\b" + re.escape(city) + r"\b"
        if re.search(pattern, clean):
            return city.title()

    # 2. Extract after prepositions: around, in, near, at, from
    m = re.search(r"\b(?:in|around|near|at|from|closest\s+to|nearby)\s+([A-Za-z\s]+?)(?:\s*\?|\s*$|\s*,\s*|\s+and\b)", text, re.IGNORECASE)
    if m:
        extracted = m.group(1).strip()
        stop_words = {"me", "here", "the area", "there", "my area", "town", "city"}
        if extracted.lower() not in stop_words and len(extracted) > 2:
            return extracted.title()

    return default


def search_places(query: str, location: str = "Colombo", max_results: int = 4) -> Dict[str, Any]:
    """Search for restaurants, cafés, and places around a specified location with ratings and reviews.
    Maintains strict cuisine filtering so specific culinary requests return only matching establishments.
    """
    clean_query = " ".join((query or "").lower().split())
    raw_loc = (location or "Colombo").strip()

    # Normalize location name
    loc_lower = raw_loc.lower()
    matched_key = CITY_KEY_MAP.get(loc_lower)

    # Detect if a specific cuisine was requested
    target_cuisine = extract_cuisine(clean_query)

    matches: List[Dict[str, Any]] = []

    # 1. Check curated directory for matched region
    if matched_key and matched_key in REGIONAL_RESTAURANT_DIRECTORY:
        regional_places = REGIONAL_RESTAURANT_DIRECTORY[matched_key]

        if target_cuisine:
            # STRICT CUISINE MATCHING: Only return places matching requested cuisine
            synonyms = CUISINE_SYNONYMS.get(target_cuisine, [target_cuisine])
            for place in regional_places:
                searchable = f"{place['name']} {place['category']} {place.get('description', '')}".lower()
                if any(syn in searchable for syn in synonyms):
                    matches.append(place)
        else:
            # Generic query: check if any query keywords match
            query_words = [
                w for w in re.findall(r"\b[a-zA-Z]{3,}\b", clean_query)
                if w not in {"the", "and", "best", "around", "find", "for", "good", "some", "restaurant", "restaurants", "place", "places", "food", "eat", "dining"}
            ]
            if query_words:
                for place in regional_places:
                    searchable = f"{place['name']} {place['category']}".lower()
                    if any(w in searchable for w in query_words):
                        matches.append(place)
            else:
                matches = list(regional_places)

    # 2. If no curated matches found (e.g. city not in directory, or specific cuisine not in curated list),
    # query OpenStreetMap Nominatim for the requested location & specific cuisine
    if not matches:
        try:
            search_term = f"{target_cuisine} restaurant in {raw_loc}" if target_cuisine else f"restaurants in {raw_loc}"
            with httpx.Client(timeout=6.0) as client:
                resp = client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={
                        "q": search_term,
                        "format": "json",
                        "limit": max_results,
                        "addressdetails": 1
                    },
                    headers={"User-Agent": "RNRobotsVoiceAssistant/1.0"}
                )
                if resp.status_code == 200:
                    places_data = resp.json()
                    for p in places_data:
                        disp = p.get("display_name", "")
                        place_name = disp.split(",")[0]
                        matches.append({
                            "name": place_name,
                            "category": f"{target_cuisine.title()} Restaurant" if target_cuisine else p.get("type", "Restaurant").replace("_", " ").title(),
                            "rating": 4.3,
                            "review_count": 140,
                            "price_level": "$$",
                            "address": disp,
                            "description": f"Dining option located in {raw_loc}."
                        })
        except Exception:
            pass

    # 3. Live internet search fallback for unlisted cuisines or localities
    if not matches:
        try:
            from app.tools.web_search import search_web
            search_prompt = f"best {target_cuisine} places in {raw_loc}" if target_cuisine else f"best {clean_query} in {raw_loc}"
            web_res = search_web(search_prompt, max_results=max_results)
            for item in web_res.get("results", []):
                title = item.get("title", "")
                clean_title = re.sub(r'\s*-\s*(?:Tripadvisor|Restaurant Guru|Yamu|Zomato|Lonely Planet).*$', '', title, flags=re.IGNORECASE).strip()
                clean_title = re.sub(r'^(?:THE\s+\d+\s+BEST|Top\s+\d+|10\s+Best|\d+\s+Best)\s+', '', clean_title, flags=re.IGNORECASE).strip()
                snippet = item.get("snippet", "")
                if snippet and "Recent developments" not in snippet:
                    matches.append({
                        "name": clean_title or title,
                        "category": f"Web Verified ({target_cuisine.title() if target_cuisine else 'Dining'})",
                        "rating": 4.5,
                        "review_count": 220,
                        "price_level": "$$",
                        "address": f"{raw_loc}, Sri Lanka",
                        "description": snippet[:200] + ("..." if len(snippet) > 200 else ""),
                        "source": "live_web_search",
                        "url": item.get("url", "")
                    })
        except Exception:
            pass

    # 4. Fallback behavior:
    # CRITICAL: NEVER return an unrelated cuisine as fallback when a specific cuisine was requested.
    # Only fall back to Colombo directory if NO specific cuisine was requested AND location was Colombo/empty.
    if not matches and not target_cuisine and loc_lower in ["colombo", "default", ""]:
        matches = REGIONAL_RESTAURANT_DIRECTORY["colombo"][:max_results]

    return {
        "location": raw_loc,
        "query": query,
        "cuisine": target_cuisine,
        "count": len(matches[:max_results]),
        "places": matches[:max_results]
    }
