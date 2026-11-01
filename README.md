# Aura Data

Données publiques lues par [Aura](https://github.com/peborde), une app iOS pour suivre sa collection de cartes à collectionner.

Une tâche GitHub Actions (`.github/workflows/sync.yml`) lance `sync.py` une fois par jour, après la mise à jour de [TCGCSV](https://tcgcsv.com), qui recopie les données de TCGplayer. Elle publie sur GitHub Pages :

- `dragonball/` : Dragon Ball Super Card Game, Fusion World (`fw`) et Masters (`masters`) ;
- `cyberpunk/` : Cyberpunk TCG ;
- `yugioh/` : Yu-Gi-Oh! ;
- `meta.json` : la date des données de TCGCSV, la version des fichiers et la date de la synchronisation.

Chaque dossier contient :

- `sets.json` : les extensions, de la plus récente à la plus ancienne, avec leur série, leur code quand TCGplayer en donne un et leur nombre de cartes ;
- `cards.json` : chaque carte (identifiant TCGplayer, extension, numéro, nom, rareté) avec son prix du marché TCGplayer en dollars, et celui de la version foil (`foil`) ou de la 1re édition d'une carte Yu-Gi-Oh! (`first`) quand elle existe aussi en version courante.

Les images des cartes sont celles de TCGplayer : `https://tcgplayer-cdn.tcgplayer.com/product/<id>_400w.jpg`.

Comme TCGCSV le demande, l'app ne l'appelle jamais : seule cette tâche le fait, une fois par jour, en se présentant, avec une courte pause entre deux requêtes (environ 1 700 requêtes), et ne publie rien quand ses données n'ont pas changé.

Merci à TCGCSV. Dragon Ball Super Card Game est une marque de Bandai, Cyberpunk une marque de CD PROJEKT, Yu-Gi-Oh! une marque de Konami ; ce dépôt n'est affilié ni à eux, ni à TCGplayer, ni à TCGCSV.

```sh
python3 sync.py site   # écrit les fichiers dans site/
```
