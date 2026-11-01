"""Synchronise les cartes et les prix de Dragon Ball Super Card Game (Fusion World et Masters) et de
Cyberpunk TCG pour Aura.

TCGCSV recopie chaque jour vers 20 h UTC les données de TCGplayer et demande qu'aucune app ne l'appelle
directement : ce script les télécharge une fois par jour et en garde l'essentiel dans deux fichiers
statiques par jeu, publiés sur GitHub Pages et lus par l'app.

    python3 sync.py <dossier de sortie>

Rien n'est publié quand TCGCSV n'a pas changé depuis la dernière synchronisation ; une extension illisible
arrête tout, pour ne jamais publier un catalogue incomplet.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

TCGCSV = "https://tcgcsv.com"
PUBLISHED = "https://peborde.github.io/aura-data"
USER_AGENT = "AuraDataSync/1.0 (+https://github.com/peborde/aura-data)"
# Version des fichiers publiés : une nouvelle version republie tout, même quand TCGCSV n'a pas changé.
FORMAT = 2
# Dossier de chaque jeu et ses séries, chacune une catégorie TCGplayer.
GAMES = {
    "dragonball": {"fw": 80, "masters": 27},
    "cyberpunk": {"cyberpunk": 92},
}


def get(url, attempts=3):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)


def results(path):
    data = json.loads(get(f"{TCGCSV}{path}"))
    if not data.get("success", True):
        raise RuntimeError(f"{path} : {data.get('errors')}")
    return data["results"]


def published():
    """Date de la version de TCGCSV déjà publiée et version des fichiers, s'il y en a."""
    try:
        meta = json.loads(get(f"{PUBLISHED}/meta.json", attempts=1))
        return meta.get("tcgcsv"), meta.get("format", 1)
    except (urllib.error.URLError, ValueError):
        return None, None


def extended(product, name):
    return next((field["value"] for field in product.get("extendedData", []) if field["name"] == name), None)


def amount(price):
    value = price.get("marketPrice") or price.get("midPrice")
    return round(value, 2) if value else None


def card_name(product, number):
    # « Giblet - FB11-084 » : TCGplayer ajoute parfois le code au nom.
    return re.sub(rf"\s+-\s+{re.escape(number)}\b", "", product["name"]).strip()


def sync_game(name, series_categories):
    """Extensions et cartes d'un jeu, de la plus récente à la plus ancienne."""
    sets, cards = [], []
    for series, category in series_categories.items():
        for group in results(f"/tcgplayer/{category}/groups"):
            # Le code de l'extension quand TCGplayer en donne un, son numéro sinon.
            code = group.get("abbreviation") or None
            set_id = code or str(group["groupId"])
            if any(existing["id"] == set_id for existing in sets):
                set_id = f"{set_id}-{group['groupId']}"
            products = results(f"/tcgplayer/{category}/{group['groupId']}/products")
            time.sleep(0.1)
            prices = {}
            for price in results(f"/tcgplayer/{category}/{group['groupId']}/prices"):
                prices.setdefault(price["productId"], {})[price["subTypeName"]] = amount(price)
            time.sleep(0.1)
            count = 0
            for product in products:
                number = extended(product, "Number")
                # Boîtes, boosters et decks n'ont pas de numéro.
                if not number:
                    continue
                subtypes = prices.get(product["productId"], {})
                foil = subtypes.get("Foil") or subtypes.get("Holofoil")
                # Une carte qui n'existe qu'en brillante a ce prix-là comme prix normal.
                normal = subtypes["Normal"] if "Normal" in subtypes else foil
                card = {"id": product["productId"], "set": set_id, "number": number,
                        "name": card_name(product, number), "rarity": extended(product, "Rarity"),
                        "price": normal}
                if "Normal" in subtypes and foil:
                    card["foil"] = foil
                cards.append(card)
                count += 1
            if count:
                sets.append({"id": set_id, "code": code, "name": group["name"], "series": series,
                             "released": (group.get("publishedOn") or "")[:10] or None, "cards": count})
    sets.sort(key=lambda s: (s["released"] or "", s["id"]), reverse=True)
    return sets, cards


def main(output):
    updated = get(f"{TCGCSV}/last-updated.txt").decode().strip()
    if published() == (updated, FORMAT):
        print(f"TCGCSV n'a pas changé depuis {updated} : rien à publier.")
        changed = False
    else:
        for name, series_categories in GAMES.items():
            sets, cards = sync_game(name, series_categories)
            folder = os.path.join(output, name)
            os.makedirs(folder, exist_ok=True)
            for file_name, content in (("sets.json", {"updated": updated, "sets": sets}),
                                       ("cards.json", {"updated": updated, "cards": cards})):
                with open(os.path.join(folder, file_name), "w", encoding="utf-8") as file:
                    json.dump(content, file, ensure_ascii=False, separators=(",", ":"))
            print(f"{name} : {len(sets)} extensions, {len(cards)} cartes (TCGCSV du {updated}).")
        with open(os.path.join(output, "meta.json"), "w", encoding="utf-8") as file:
            json.dump({"tcgcsv": updated, "format": FORMAT,
                       "synced": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, file)
        changed = True

    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as file:
            file.write(f"changed={'true' if changed else 'false'}\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "site")
