"""Synchronise les cartes et les prix de Dragon Ball Super Card Game (Fusion World et Masters), de
Cyberpunk TCG, de Yu-Gi-Oh! et de Gundam Card Game pour Aura.

TCGCSV recopie chaque jour vers 20 h UTC les données de TCGplayer et demande qu'aucune app ne l'appelle
directement : ce script les télécharge une fois par jour et en garde l'essentiel dans deux fichiers
statiques par jeu, publiés sur GitHub Pages et lus par l'app.

    python3 sync.py <dossier de sortie>

Les noms français des cartes Yu-Gi-Oh! viennent de YGOPRODeck, lu une fois par jour lui aussi. Les images des
cartes Gundam et Dragon Ball Fusion World sont celles des sites officiels de Bandai, celles des cartes Cyberpunk celles
de sa base de cartes officielle (Netdeck), lues chaque jour ; les autres restent celles de TCGplayer. Les cartes
Dragon Ball Masters gardent l'image de TCGplayer, plus grande, avec celle du site officiel en secours.

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
YGOPRODECK_FRENCH = "https://db.ygoprodeck.com/api/v7/cardinfo.php?language=fr"
USER_AGENT = "AuraDataSync/1.0 (+https://github.com/peborde/aura-data)"
# Version des fichiers publiés : une nouvelle version republie tout, même quand TCGCSV n'a pas changé.
FORMAT = 8
# Dossier de chaque jeu et ses séries, chacune une catégorie TCGplayer.
GAMES = {
    "dragonball": {"fw": 80, "masters": 27},
    "cyberpunk": {"cyberpunk": 92},
    "yugioh": {"yugioh": 2},
    "gundam": {"gundam": 86},
}


def get(url, attempts=3, accept="application/json"):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
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


def without_rarity(name, rarity):
    """« Tri-Brigade Revolt (UR) », « Gundam GP01 (R+) » : TCGplayer ajoute la rareté au nom d'une carte Yu-Gi-Oh! ou
    Gundam imprimée dans plusieurs raretés, que l'app montre à part. « (Alternate Art) » ou « (Judge Stamp) »
    restent."""
    if not rarity:
        return name

    def kept(match):
        tag = match.group(1)
        is_rarity = ("Rare" in tag or tag.lower() in rarity.lower()
                     or (re.fullmatch(r"[A-Z]{2,4}", tag) and tag[0] == rarity[0]))
        return "" if is_rarity else match.group(0)

    return " ".join(re.sub(r"\s*\(([^)]*)\)", kept, name).split())


def french_namer():
    """Nom français d'une carte Yu-Gi-Oh!, d'après le code de son édition anglaise (« LOB-EN001 ») ou, à défaut,
    son nom anglais ; les précisions entre parenthèses (« (Alternate Art) ») restent. YGOPRODeck n'a pas encore
    traduit les cartes des extensions les plus récentes. Quand il ne répond pas, les noms de la dernière
    publication servent."""
    try:
        by_code, by_name = {}, {}
        for card in json.loads(get(YGOPRODECK_FRENCH))["data"]:
            by_name[card.get("name_en")] = card["name"]
            for printing in card.get("card_sets") or []:
                by_code[printing["set_code"].upper()] = card["name"]
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
        print(f"YGOPRODeck indisponible ({error}) : noms français de la dernière publication.")
        cards = json.loads(get(f"{PUBLISHED}/yugioh/cards.json", attempts=1))["cards"]
        previous = {card["id"]: card["fr"] for card in cards if "fr" in card}
        return lambda card: previous.get(card["id"])

    def french(card):
        title = re.sub(r"\s*\([^)]*\)", "", card["name"]).strip()
        name = by_code.get(card["number"].upper()) or by_name.get(title)
        tags = re.findall(r"\([^)]*\)", card["name"])
        return " ".join([name] + tags) if name else None

    return french


GUNDAM = "https://www.gundam-gcg.com/en"
FUSION_WORLD = "https://www.dbs-cardgame.com/fw"
MASTERS = "https://www.dbs-cardgame.com"
NETDECK = "https://api.netdeck.gg/api/cards/cyberpunk"


def page(url):
    time.sleep(0.3)
    return get(url, accept="text/html").decode("utf-8", "ignore")


def gundam_images():
    """Image officielle de chaque version d'une carte Gundam : « GD01-001 », puis « GD01-001_p1 »… pour ses
    versions parallèles, d'après la liste de chaque produit sur le site officiel."""
    images = {}
    for package in sorted(set(re.findall(r'data-val="(\d{6})"', page(f"{GUNDAM}/cards/")))):
        for path in re.findall(r'data-src="\.\./images/cards/card/([^"?]+)', page(f"{GUNDAM}/cards/?package={package}")):
            images.setdefault(path.rsplit(".", 1)[0], f"{GUNDAM}/images/cards/card/{path}")
    return images


def fusion_world_images():
    """Image officielle de chaque version d'une carte Dragon Ball Fusion World (« FB01-001 », « FB01-001_p1 »),
    d'après la liste de chaque extension sur le site officiel."""
    images = {}
    categories = sorted(set(re.findall(r"58\d{4}", page(f"{FUSION_WORLD}/en/cardlist/"))))
    for category in categories:
        html = page(f"{FUSION_WORLD}/en/cardlist/?search=true&category%5B0%5D={category}")
        pattern = r'card_no=([^"&]+)(?:&(?:amp;)?p=(_p\d+))?"[^>]*><img[^>]*data-src="\.\./\.\./images/cards/card/en/([^"]+)"'
        for number, version, path in re.findall(pattern, html):
            images.setdefault(number + version, f"{FUSION_WORLD}/images/cards/card/en/{path}")
    return images


def masters_images():
    """Image officielle de chaque carte Dragon Ball Masters, l'ancien jeu, par son numéro (« BT1-001 », « BT1-005_PR »)."""
    images = {}
    for category in sorted(set(re.findall(r"category=(\d+)", page(f"{MASTERS}/us-en/cardlist/?search=true")))):
        html = page(f"{MASTERS}/us-en/cardlist/?search=true&category={category}")
        pattern = r'<dt class="cardNumber">([^<]+)</dt>.*?<img src="\.\./\.\./images/cardlist/cardimg/([^"]+)"'
        for number, path in re.findall(pattern, html, re.S):
            images.setdefault(number.strip().upper(), f"{MASTERS}/images/cardlist/cardimg/{path}")
    return images


def cyberpunk_images():
    """Image officielle de chaque version d'une carte Cyberpunk, par son extension et son numéro, d'après la base de
    cartes officielle (Netdeck). Ses images n'ont que des adresses signées, valables quelques minutes : l'adresse
    gardée est celle de la base, qui y renvoie."""
    images, offset = {}, 0
    while True:
        data = json.loads(get(f"{NETDECK}?limit=60&offset={offset}"))
        for card in data["items"]:
            for printing in card["printings"]:
                key = (cyberpunk_set(printing["set"]["name"]), printing["collector_number"].lower().replace("β", "b"))
                images.setdefault(key, f"{NETDECK}/{card['slug']}/image?printing={printing['id']}")
        offset += data["limit"]
        if offset >= data["total"]:
            return images
        time.sleep(0.3)


def cyberpunk_set(name):
    """« Welcome to Night City — Beta » chez Netdeck, « Welcome to Night City - Beta » chez TCGplayer ; « S 1 » et
    « Season 1 »."""
    name = name.replace("—", "-").replace(" S 1", " Season 1").replace(" S1", " Season 1")
    return " ".join(name.split()).lower()


def is_variant(name):
    """« Vegito (Alternate Art) », « Videl (Gold) » : une version particulière de la carte. « (Mini) » fait partie du
    nom de certains personnages."""
    return any(tag != "Mini" for tag in re.findall(r"\(([^)]*)\)", name))


def official_images(name, sets, cards):
    """Adresse de l'image officielle de chaque carte, quand la correspondance est sûre.

    Gundam : la rareté donne la version (« LR », puis « LR+ » pour « _p1 », « LR++ » pour « _p2 »).
    Cyberpunk : l'extension et le numéro (« β001 » chez Netdeck, « B001 » chez TCGplayer).
    Fusion World : la carte sans précision prend l'image de base ; les versions particulières (« (Alternate Art) »),
    dans l'ordre où TCGplayer les a ajoutées, prennent celles des versions parallèles, seulement quand il y en a
    autant des deux côtés. Les autres cartes gardent l'image de TCGplayer."""
    if name == "gundam":
        images = gundam_images()
        return {card["id"]: images.get(card["number"] + (f"_p{card['rarity'].count('+')}" if "+" in (card["rarity"] or "") else ""))
                for card in cards}
    if name == "cyberpunk":
        images = cyberpunk_images()
        set_names = {s["id"]: cyberpunk_set(s["name"]) for s in sets}
        found = {}
        for card in cards:
            number = card["number"].lower()
            # « V - Streetkid (b) », numéro « 005 » : la version b.
            version = re.search(r"\(([ab])\)\s*$", card["name"])
            if version and not number[-1].isalpha():
                number += version.group(1)
            found[card["id"]] = images.get((set_names.get(card["set"]), number))
        return found
    if name != "dragonball":
        return {}
    found = {}
    images = fusion_world_images()
    fusion_world = {s["id"] for s in sets if s["series"] == "fw"}
    by_code = {}
    for card in cards:
        if card["set"] in fusion_world:
            by_code.setdefault(card["number"].split("_")[0], []).append(card)
    for code, versions in by_code.items():
        parallels = sorted((key for key in images if key.startswith(f"{code}_p")), key=lambda key: int(key.rsplit("_p", 1)[1]))
        variants = sorted((card for card in versions if is_variant(card["name"])), key=lambda card: card["id"])
        for card in versions:
            if not is_variant(card["name"]):
                found[card["id"]] = images.get(code)
        if len(variants) == len(parallels):
            for card, key in zip(variants, parallels):
                found[card["id"]] = images[key]
    return found


def backup_images(name, sets, cards):
    """Image officielle de secours, quand celle de TCGplayer ne se charge pas : celle des cartes Dragon Ball Masters,
    plus petite que celle de TCGplayer (260 × 364 points). Plusieurs cartes du même numéro : seules celles sans
    précision (« (Gold Stamped) ») ont l'image de base."""
    if name != "dragonball":
        return {}
    images = masters_images()
    masters = {s["id"] for s in sets if s["series"] == "masters"}
    by_number = {}
    for card in cards:
        if card["set"] in masters:
            by_number.setdefault(card["number"].strip().upper(), []).append(card)
    return {card["id"]: images.get(number)
            for number, versions in by_number.items()
            for card in versions if len(versions) == 1 or not is_variant(card["name"])}


def attach_official_images(name, sets, cards):
    """Ajoute l'image officielle aux cartes qui en ont une : « img » quand elle remplace celle de TCGplayer,
    « backup » quand elle ne sert qu'en secours. Quand un site officiel ne répond pas, les images de la dernière
    publication servent."""
    previous = None
    for field, finder in (("img", official_images), ("backup", backup_images)):
        try:
            found = finder(name, sets, cards)
        except (urllib.error.URLError, TimeoutError, ValueError) as error:
            print(f"Site officiel indisponible pour {name} ({error}) : images de la dernière publication.")
            if previous is None:
                try:
                    previous = json.loads(get(f"{PUBLISHED}/{name}/cards.json", attempts=1))["cards"]
                except (urllib.error.URLError, ValueError):
                    previous = []
            found = {card["id"]: card.get(field) for card in previous}
        for card in cards:
            if found.get(card["id"]):
                card[field] = found[card["id"]]
    return sum(1 for card in cards if "img" in card), sum(1 for card in cards if "backup" in card)


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
                first = subtypes.get("1st Edition")
                # La version courante : « Unlimited » et « Limited » pour Yu-Gi-Oh!. Une carte qui n'existe qu'en
                # brillante ou qu'en 1re édition a ce prix-là comme prix normal.
                plain = next((kind for kind in ("Normal", "Unlimited", "Limited") if kind in subtypes), None)
                rarity = extended(product, "Rarity")
                title = card_name(product, number)
                card = {"id": product["productId"], "set": set_id, "number": number,
                        "name": without_rarity(title, rarity) if name in ("yugioh", "gundam") else title, "rarity": rarity,
                        "price": subtypes[plain] if plain else foil or first}
                if plain and foil:
                    card["foil"] = foil
                if plain and first:
                    card["first"] = first
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
            if name in ("dragonball", "gundam", "cyberpunk"):
                official, backup = attach_official_images(name, sets, cards)
                print(f"{name} : {official} images officielles, {backup} en secours.")
            if name == "yugioh":
                french = french_namer()
                for card in cards:
                    translated = french(card)
                    if translated and translated != card["name"]:
                        card["fr"] = translated
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
