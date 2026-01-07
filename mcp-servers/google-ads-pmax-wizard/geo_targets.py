"""
Google Ads Geo Target Constants for Belgium and Netherlands
============================================================
Complete list of targetable locations including countries, provinces/regions, and cities.
Generated from Google Ads API - SuggestGeoTargetConstants
Last Updated: 2025-12-20
"""

# ============================================================================
# COUNTRIES
# ============================================================================

COUNTRIES = {
    "BE": {"id": 2056, "name": "Belgium", "name_nl": "België"},
    "NL": {"id": 2528, "name": "Netherlands", "name_nl": "Nederland"},
    "DE": {"id": 2276, "name": "Germany", "name_nl": "Duitsland"},
    "FR": {"id": 2250, "name": "France", "name_nl": "Frankrijk"},
    "LU": {"id": 2442, "name": "Luxembourg", "name_nl": "Luxemburg"},
    "UK": {"id": 2826, "name": "United Kingdom", "name_nl": "Verenigd Koninkrijk"},
}

# ============================================================================
# LANGUAGES
# ============================================================================

LANGUAGES = {
    "nl": {"id": 1010, "name": "Dutch", "name_nl": "Nederlands"},
    "fr": {"id": 1002, "name": "French", "name_nl": "Frans"},
    "de": {"id": 1001, "name": "German", "name_nl": "Duits"},
    "en": {"id": 1000, "name": "English", "name_nl": "Engels"},
}

# ============================================================================
# BELGIUM - REGIONS & PROVINCES
# ============================================================================

BE_REGIONS = {
    "flanders": {"id": 9069523, "name": "Flanders", "name_nl": "Vlaanderen"},
    "wallonia": {"id": 9069524, "name": "Wallonia", "name_nl": "Wallonië"},
}

BE_PROVINCES = {
    "antwerp": {"id": 20053, "name": "Antwerp", "name_nl": "Antwerpen", "region": "flanders"},
    "brussels": {"id": 20052, "name": "Brussels", "name_nl": "Brussel", "region": None},
    "east_flanders": {"id": 20056, "name": "East Flanders", "name_nl": "Oost-Vlaanderen", "region": "flanders"},
    "flemish_brabant": {"id": 20054, "name": "Flemish Brabant", "name_nl": "Vlaams-Brabant", "region": "flanders"},
    "hainaut": {"id": 20059, "name": "Hainaut", "name_nl": "Henegouwen", "region": "wallonia"},
    "liege": {"id": 20060, "name": "Liege", "name_nl": "Luik", "region": "wallonia"},
    "limburg_be": {"id": 20055, "name": "Limburg", "name_nl": "Limburg", "region": "flanders"},
    "luxembourg_be": {"id": 20061, "name": "Luxembourg", "name_nl": "Luxemburg", "region": "wallonia"},
    "namur": {"id": 20062, "name": "Namur", "name_nl": "Namen", "region": "wallonia"},
    "walloon_brabant": {"id": 20058, "name": "Walloon Brabant", "name_nl": "Waals-Brabant", "region": "wallonia"},
    "west_flanders": {"id": 20057, "name": "West Flanders", "name_nl": "West-Vlaanderen", "region": "flanders"},
}

# ============================================================================
# BELGIUM - CITIES (Most Important)
# ============================================================================

BE_CITIES = {
    # Major Cities
    "brussels": {"id": 1001004, "name": "Brussels", "name_nl": "Brussel", "province": "brussels"},
    "antwerp": {"id": 1001021, "name": "Antwerp", "name_nl": "Antwerpen", "province": "antwerp"},
    "ghent": {"id": 1001208, "name": "Ghent", "name_nl": "Gent", "province": "east_flanders"},
    "bruges": {"id": 1001259, "name": "Bruges", "name_nl": "Brugge", "province": "west_flanders"},
    "liege": {"id": 1001394, "name": "Liege", "name_nl": "Luik", "province": "liege"},
    "charleroi": {"id": 1001334, "name": "Charleroi", "name_nl": "Charleroi", "province": "hainaut"},
    "namur": {"id": 1001400, "name": "Namur", "name_nl": "Namen", "province": "namur"},

    # Flanders - Antwerp Province
    "brasschaat": {"id": 1001034, "name": "Brasschaat", "name_nl": "Brasschaat", "province": "antwerp"},
    "mechelen": {"id": 1001059, "name": "Mechelen", "name_nl": "Mechelen", "province": "antwerp"},
    "turnhout": {"id": 1001080, "name": "Turnhout", "name_nl": "Turnhout", "province": "antwerp"},
    "herentals": {"id": 1001047, "name": "Herentals", "name_nl": "Herentals", "province": "antwerp"},
    "mortsel": {"id": 1001063, "name": "Mortsel", "name_nl": "Mortsel", "province": "antwerp"},
    "schoten": {"id": 1001074, "name": "Schoten", "name_nl": "Schoten", "province": "antwerp"},

    # Flanders - Limburg Province
    "hasselt": {"id": 1001165, "name": "Hasselt", "name_nl": "Hasselt", "province": "limburg_be"},
    "genk": {"id": 1001162, "name": "Genk", "name_nl": "Genk", "province": "limburg_be"},
    "beringen": {"id": 1001153, "name": "Beringen", "name_nl": "Beringen", "province": "limburg_be"},
    "lommel": {"id": 1001175, "name": "Lommel", "name_nl": "Lommel", "province": "limburg_be"},
    "sint_truiden": {"id": 1001182, "name": "Sint-Truiden", "name_nl": "Sint-Truiden", "province": "limburg_be"},

    # Flanders - East Flanders
    "aalst": {"id": 1001187, "name": "Aalst", "name_nl": "Aalst", "province": "east_flanders"},
    "sint_niklaas": {"id": 1001242, "name": "Sint-Niklaas", "name_nl": "Sint-Niklaas", "province": "east_flanders"},
    "dendermonde": {"id": 1001198, "name": "Dendermonde", "name_nl": "Dendermonde", "province": "east_flanders"},
    "lokeren": {"id": 1001222, "name": "Lokeren", "name_nl": "Lokeren", "province": "east_flanders"},

    # Flanders - West Flanders
    "kortrijk": {"id": 1001275, "name": "Kortrijk", "name_nl": "Kortrijk", "province": "west_flanders"},
    "ostend": {"id": 1001282, "name": "Ostend", "name_nl": "Oostende", "province": "west_flanders"},
    "roeselare": {"id": 1001287, "name": "Roeselare", "name_nl": "Roeselare", "province": "west_flanders"},
    "waregem": {"id": 1001297, "name": "Waregem", "name_nl": "Waregem", "province": "west_flanders"},
    "knokke_heist": {"id": 1001273, "name": "Knokke-Heist", "name_nl": "Knokke-Heist", "province": "west_flanders"},
    "ypres": {"id": 1001269, "name": "Ypres", "name_nl": "Ieper", "province": "west_flanders"},

    # Flanders - Flemish Brabant
    "leuven": {"id": 1001118, "name": "Leuven", "name_nl": "Leuven", "province": "flemish_brabant"},
    "vilvoorde": {"id": 1001145, "name": "Vilvoorde", "name_nl": "Vilvoorde", "province": "flemish_brabant"},
    "zaventem": {"id": 1001150, "name": "Zaventem", "name_nl": "Zaventem", "province": "flemish_brabant"},
    "tienen": {"id": 1001142, "name": "Tienen", "name_nl": "Tienen", "province": "flemish_brabant"},
    "diest": {"id": 1001310, "name": "Diest", "name_nl": "Diest", "province": "flemish_brabant"},

    # Wallonia - Hainaut
    "mons": {"id": 1001360, "name": "Mons", "name_nl": "Bergen", "province": "hainaut"},
    "tournai": {"id": 1001370, "name": "Tournai", "name_nl": "Doornik", "province": "hainaut"},
    "la_louviere": {"id": 1001355, "name": "La Louviere", "name_nl": "La Louvière", "province": "hainaut"},
    "mouscron": {"id": 1001361, "name": "Mouscron", "name_nl": "Moeskroen", "province": "hainaut"},

    # Wallonia - Liege
    "verviers": {"id": 1001408, "name": "Verviers", "name_nl": "Verviers", "province": "liege"},
    "seraing": {"id": 1001404, "name": "Seraing", "name_nl": "Seraing", "province": "liege"},
    "herstal": {"id": 1001389, "name": "Herstal", "name_nl": "Herstal", "province": "liege"},
    "eupen": {"id": 1001382, "name": "Eupen", "name_nl": "Eupen", "province": "liege"},

    # Wallonia - Other
    "arlon": {"id": 1001418, "name": "Arlon", "name_nl": "Aarlen", "province": "luxembourg_be"},
    "bastogne": {"id": 1001421, "name": "Bastogne", "name_nl": "Bastenaken", "province": "luxembourg_be"},
    "wavre": {"id": 1001329, "name": "Wavre", "name_nl": "Waver", "province": "walloon_brabant"},
    "waterloo": {"id": 1001327, "name": "Waterloo", "name_nl": "Waterloo", "province": "walloon_brabant"},
    "nivelles": {"id": 1001321, "name": "Nivelles", "name_nl": "Nijvel", "province": "walloon_brabant"},
    "dinant": {"id": 1001431, "name": "Dinant", "name_nl": "Dinant", "province": "namur"},

    # Brussels Municipalities
    "schaerbeek": {"id": 1001015, "name": "Schaerbeek", "name_nl": "Schaarbeek", "province": "brussels"},
    "anderlecht": {"id": 1001001, "name": "Anderlecht", "name_nl": "Anderlecht", "province": "brussels"},
    "ixelles": {"id": 1001010, "name": "Ixelles", "name_nl": "Elsene", "province": "brussels"},
    "uccle": {"id": 1001018, "name": "Uccle", "name_nl": "Ukkel", "province": "brussels"},
    "etterbeek": {"id": 1001006, "name": "Etterbeek", "name_nl": "Etterbeek", "province": "brussels"},
}

# ============================================================================
# NETHERLANDS - PROVINCES
# ============================================================================

NL_PROVINCES = {
    "drenthe": {"id": 20759, "name": "Drenthe", "name_nl": "Drenthe"},
    "flevoland": {"id": 20760, "name": "Flevoland", "name_nl": "Flevoland"},
    "friesland": {"id": 20761, "name": "Friesland", "name_nl": "Friesland"},
    "gelderland": {"id": 20762, "name": "Gelderland", "name_nl": "Gelderland"},
    "groningen": {"id": 20763, "name": "Groningen", "name_nl": "Groningen"},
    "limburg_nl": {"id": 20764, "name": "Limburg", "name_nl": "Limburg"},
    "north_brabant": {"id": 20765, "name": "North Brabant", "name_nl": "Noord-Brabant"},
    "north_holland": {"id": 20766, "name": "North Holland", "name_nl": "Noord-Holland"},
    "overijssel": {"id": 20767, "name": "Overijssel", "name_nl": "Overijssel"},
    "south_holland": {"id": 20770, "name": "South Holland", "name_nl": "Zuid-Holland"},
    "utrecht": {"id": 20768, "name": "Utrecht", "name_nl": "Utrecht"},
    "zeeland": {"id": 20769, "name": "Zeeland", "name_nl": "Zeeland"},
}

# ============================================================================
# NETHERLANDS - CITIES (Most Important)
# ============================================================================

NL_CITIES = {
    # Major Cities (Randstad)
    "amsterdam": {"id": 1010543, "name": "Amsterdam", "name_nl": "Amsterdam", "province": "north_holland"},
    "rotterdam": {"id": 1010729, "name": "Rotterdam", "name_nl": "Rotterdam", "province": "south_holland"},
    "the_hague": {"id": 1010714, "name": "The Hague", "name_nl": "Den Haag", "province": "south_holland"},
    "utrecht": {"id": 1010638, "name": "Utrecht", "name_nl": "Utrecht", "province": "utrecht"},

    # North Holland
    "haarlem": {"id": 1010561, "name": "Haarlem", "name_nl": "Haarlem", "province": "north_holland"},
    "alkmaar": {"id": 1010541, "name": "Alkmaar", "name_nl": "Alkmaar", "province": "north_holland"},
    "amstelveen": {"id": 1010542, "name": "Amstelveen", "name_nl": "Amstelveen", "province": "north_holland"},
    "zaandam": {"id": 1010596, "name": "Zaandam", "name_nl": "Zaandam", "province": "north_holland"},
    "hilversum": {"id": 1010567, "name": "Hilversum", "name_nl": "Hilversum", "province": "north_holland"},

    # South Holland
    "leiden": {"id": 1010722, "name": "Leiden", "name_nl": "Leiden", "province": "south_holland"},
    "dordrecht": {"id": 1010706, "name": "Dordrecht", "name_nl": "Dordrecht", "province": "south_holland"},
    "zoetermeer": {"id": 1010747, "name": "Zoetermeer", "name_nl": "Zoetermeer", "province": "south_holland"},
    "delft": {"id": 1010704, "name": "Delft", "name_nl": "Delft", "province": "south_holland"},
    "gouda": {"id": 1010712, "name": "Gouda", "name_nl": "Gouda", "province": "south_holland"},

    # North Brabant
    "eindhoven": {"id": 1010481, "name": "Eindhoven", "name_nl": "Eindhoven", "province": "north_brabant"},
    "tilburg": {"id": 1010512, "name": "Tilburg", "name_nl": "Tilburg", "province": "north_brabant"},
    "breda": {"id": 1010474, "name": "Breda", "name_nl": "Breda", "province": "north_brabant"},
    "s_hertogenbosch": {"id": 1010517, "name": "'s-Hertogenbosch", "name_nl": "Den Bosch", "province": "north_brabant"},
    "helmond": {"id": 1010487, "name": "Helmond", "name_nl": "Helmond", "province": "north_brabant"},

    # Gelderland
    "arnhem": {"id": 1010351, "name": "Arnhem", "name_nl": "Arnhem", "province": "gelderland"},
    "nijmegen": {"id": 1010398, "name": "Nijmegen", "name_nl": "Nijmegen", "province": "gelderland"},
    "apeldoorn": {"id": 1010350, "name": "Apeldoorn", "name_nl": "Apeldoorn", "province": "gelderland"},
    "ede": {"id": 1010373, "name": "Ede", "name_nl": "Ede", "province": "gelderland"},

    # Overijssel
    "enschede": {"id": 1010605, "name": "Enschede", "name_nl": "Enschede", "province": "overijssel"},
    "zwolle": {"id": 1010624, "name": "Zwolle", "name_nl": "Zwolle", "province": "overijssel"},
    "deventer": {"id": 1010604, "name": "Deventer", "name_nl": "Deventer", "province": "overijssel"},
    "almelo": {"id": 1010600, "name": "Almelo", "name_nl": "Almelo", "province": "overijssel"},
    "hengelo": {"id": 1010607, "name": "Hengelo", "name_nl": "Hengelo", "province": "overijssel"},

    # Limburg
    "maastricht": {"id": 1010448, "name": "Maastricht", "name_nl": "Maastricht", "province": "limburg_nl"},
    "venlo": {"id": 1010466, "name": "Venlo", "name_nl": "Venlo", "province": "limburg_nl"},
    "heerlen": {"id": 1010443, "name": "Heerlen", "name_nl": "Heerlen", "province": "limburg_nl"},
    "sittard": {"id": 1010458, "name": "Sittard", "name_nl": "Sittard", "province": "limburg_nl"},
    "roermond": {"id": 1010455, "name": "Roermond", "name_nl": "Roermond", "province": "limburg_nl"},

    # Utrecht Province
    "amersfoort": {"id": 1010625, "name": "Amersfoort", "name_nl": "Amersfoort", "province": "utrecht"},
    "nieuwegein": {"id": 1010633, "name": "Nieuwegein", "name_nl": "Nieuwegein", "province": "utrecht"},
    "zeist": {"id": 1010644, "name": "Zeist", "name_nl": "Zeist", "province": "utrecht"},

    # Flevoland
    "almere": {"id": 1010318, "name": "Almere", "name_nl": "Almere", "province": "flevoland"},
    "lelystad": {"id": 1010321, "name": "Lelystad", "name_nl": "Lelystad", "province": "flevoland"},

    # Groningen
    "groningen": {"id": 1010419, "name": "Groningen", "name_nl": "Groningen", "province": "groningen"},

    # Friesland
    "leeuwarden": {"id": 1010337, "name": "Leeuwarden", "name_nl": "Leeuwarden", "province": "friesland"},

    # Drenthe
    "assen": {"id": 1010304, "name": "Assen", "name_nl": "Assen", "province": "drenthe"},
    "emmen": {"id": 1010311, "name": "Emmen", "name_nl": "Emmen", "province": "drenthe"},

    # Zeeland
    "middelburg": {"id": 1010671, "name": "Middelburg", "name_nl": "Middelburg", "province": "zeeland"},
    "vlissingen": {"id": 1010675, "name": "Vlissingen", "name_nl": "Vlissingen", "province": "zeeland"},
    "goes": {"id": 1010670, "name": "Goes", "name_nl": "Goes", "province": "zeeland"},
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_geo_target_id(location_type: str, key: str) -> int:
    """Get geo target ID by type and key"""
    if location_type == "country":
        return COUNTRIES.get(key, {}).get("id")
    elif location_type == "be_province":
        return BE_PROVINCES.get(key, {}).get("id")
    elif location_type == "be_region":
        return BE_REGIONS.get(key, {}).get("id")
    elif location_type == "be_city":
        return BE_CITIES.get(key, {}).get("id")
    elif location_type == "nl_province":
        return NL_PROVINCES.get(key, {}).get("id")
    elif location_type == "nl_city":
        return NL_CITIES.get(key, {}).get("id")
    elif location_type == "language":
        return LANGUAGES.get(key, {}).get("id")
    return None


def get_all_flanders_ids() -> list:
    """Get all geo target IDs for Flanders region"""
    ids = [BE_REGIONS["flanders"]["id"]]
    for key, prov in BE_PROVINCES.items():
        if prov.get("region") == "flanders":
            ids.append(prov["id"])
    return ids


def get_all_wallonia_ids() -> list:
    """Get all geo target IDs for Wallonia region"""
    ids = [BE_REGIONS["wallonia"]["id"]]
    for key, prov in BE_PROVINCES.items():
        if prov.get("region") == "wallonia":
            ids.append(prov["id"])
    return ids


def get_pomandi_default_targeting() -> dict:
    """Get default targeting for Pomandi (Brasschaat + Genk focused)"""
    return {
        "countries": [COUNTRIES["BE"]["id"], COUNTRIES["NL"]["id"]],
        "primary_cities": [
            BE_CITIES["brasschaat"]["id"],  # Store location
            BE_CITIES["genk"]["id"],         # Store location
            BE_CITIES["antwerp"]["id"],
            BE_CITIES["hasselt"]["id"],
        ],
        "languages": [LANGUAGES["nl"]["id"]],
    }


def list_all_be_cities() -> list:
    """List all Belgian cities with IDs"""
    return [{"key": k, **v} for k, v in BE_CITIES.items()]


def list_all_nl_cities() -> list:
    """List all Dutch cities with IDs"""
    return [{"key": k, **v} for k, v in NL_CITIES.items()]


def search_locations(query: str) -> list:
    """Search for locations by name"""
    query = query.lower()
    results = []

    # Search countries
    for key, data in COUNTRIES.items():
        if query in data["name"].lower() or query in data.get("name_nl", "").lower():
            results.append({"type": "country", "key": key, **data})

    # Search BE provinces
    for key, data in BE_PROVINCES.items():
        if query in data["name"].lower() or query in data.get("name_nl", "").lower():
            results.append({"type": "be_province", "key": key, **data})

    # Search BE cities
    for key, data in BE_CITIES.items():
        if query in data["name"].lower() or query in data.get("name_nl", "").lower():
            results.append({"type": "be_city", "key": key, **data})

    # Search NL provinces
    for key, data in NL_PROVINCES.items():
        if query in data["name"].lower() or query in data.get("name_nl", "").lower():
            results.append({"type": "nl_province", "key": key, **data})

    # Search NL cities
    for key, data in NL_CITIES.items():
        if query in data["name"].lower() or query in data.get("name_nl", "").lower():
            results.append({"type": "nl_city", "key": key, **data})

    return results
