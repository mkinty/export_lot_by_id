# Export LOT — Projet SNA

Réécriture structurée de `export_lot.py` en application modulaire, testable
et maintenable.

## Pourquoi cette structure ?

Le script d'origine mélangeait tout dans un seul fichier : lecture de config,
regex, accès disque, copie de fichiers, et interface graphique. Résultat :
impossible à tester (il fallait lancer Tkinter), et le moindre changement
métier obligeait à toucher au code de l'UI.

La nouvelle architecture applique une séparation stricte en couches :

```
lot_export/
├── config.py                  # Chargement/sauvegarde config.json (I/O, pas de métier)
├── models.py                  # Dataclasses : ExportItem, ExportSummary, ExportStatus
├── services/                  # Logique métier PURE — zéro dépendance UI
│   ├── commune_parser.py      #   extraction des codes commune (regex)
│   ├── error_id_parser.py     #   extraction des ID erreur groupés par code INSEE
│   ├── address_parser.py      #   extraction des adresses <INSEE>_<adresse> groupées par code INSEE
│   ├── excel_filter.py        #   filtrage des lignes de la feuille Audit (openpyxl)
│   ├── excel_merger.py        #   fusion de plusieurs fichiers audit en un seul classeur
│   ├── export_report.py       #   rapport texte des valeurs non exportées
│   ├── file_locator.py        #   recherche des fichiers audit_*.xlsx
│   ├── pending_ids.py         #   liste persistante des ID erreur à rejouer
│   ├── lot_naming.py          #   construction/validation du nom de dossier LOT
│   └── export_service.py      #   orchestration de la copie (injectable/mockable)
├── gui/                       # Présentation uniquement — délègue tout aux services
│   ├── theme.py                #   couleurs, polices & styles ttk centralisés
│   └── main_window.py         #   fenêtre Tkinter (tk.Tk) + ExportWorker (thread)
└── main.py                    # Point d'entrée : câble config + services + UI
```

**Règle d'or** : `services/` ne connaît jamais `gui/`. On peut donc tester
toute la logique métier (regex, recherche de fichiers, copie, gestion
d'erreurs) sans jamais ouvrir de fenêtre, ni installer Tkinter/CustomTkinter.

## Ce qui a changé par rapport à l'original

- **Séparation des responsabilités** : chaque fichier a un seul rôle
  (extraction de codes, localisation de fichiers, copie, affichage).
- **Injection de dépendances** : `ExportService` reçoit son `AuditFileLocator`
  et sa fonction de copie en paramètre → dans les tests, on remplace la copie
  réelle par un mock qui ne touche pas le disque, ou on simule une erreur
  disque sans avoir besoin de le provoquer réellement.
- **Thread-safety propre** : le thread d'export ne touche plus aux widgets
  directement (source de bugs/plantages aléatoires dans la version d'origine).
  `ExportWorker` est un `threading.Thread` qui communique avec l'UI
  **uniquement** via une `queue.Queue` d'événements (`log`, `progress`,
  `finished`), dépilée par la fenêtre avec `after()` dans le thread de l'UI.
- **Interface Tkinter à thème sombre** : Tkinter est inclus dans la
  bibliothèque standard Python (aucune dépendance GUI lourde, exécutable
  PyInstaller beaucoup plus léger). Palette, polices et styles ttk sont
  centralisés dans `gui/theme.py` — un seul fichier à modifier pour changer
  les couleurs, sans toucher au code des widgets.
- **`ExportStatus` en enum** plutôt que des chaînes libres → moins d'erreurs
  de frappe, autocomplétion, exhaustivité vérifiable.

## Modes d'export

- **Codes commune** : on colle des codes INSEE (`74143`), chaque fichier
  `audit_<INSEE>.xlsx` est copié en entier dans le dossier LOT.
- **ID erreur** : on colle des ID erreur (`74143_1, 74143_2, 38068_207`). Ils
  sont regroupés par code INSEE (`{"74143": ["74143_1", "74143_2"], ...}`),
  puis pour chaque commune le fichier audit est copié en ne gardant, dans la
  feuille `Audit`, que l'en-tête et les lignes dont la colonne `ID erreur`
  fait partie de la liste. Les autres feuilles sont conservées, les formules
  sont recalées sur leur nouvelle ligne. Les ID absents du fichier sont
  signalés dans le journal.
- **Adresse** : on colle une adresse par ligne, préfixée du code INSEE
  (`05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT`). Même principe
  que l'export par ID erreur, mais sur la colonne `adresse` de la feuille
  `Audit`. La comparaison ignore la casse, les accents et les espaces
  multiples ; toutes les lignes ayant une adresse demandée sont conservées.

### Filtres et lignes masquées

Les recherches portent toujours sur la feuille `Audit` et incluent les lignes
masquées par un filtre. Les fichiers filtrés (par ID erreur ou adresse) et le
fichier unique du LOT sont produits sans filtre actif ni ligne/colonne masquée,
sur toutes les feuilles (les flèches de filtre restent disponibles). Les
fichiers source ne sont jamais modifiés. En mode **Codes commune** avec un
fichier par code INSEE, le fichier reste une copie exacte de la source.

### Contrôle de l'export

Une valeur n'est comptée comme exportée qu'après relecture du fichier final.
Avant l'export, la confirmation annonce les communes sans fichier dans le dossier
source et le nombre de valeurs concernées. Après l'export, le message de fin et le
journal donnent le bilan par cause.

S'il y a une valeur non exportée, un doublon ou une saisie non reconnue, le fichier
`LOTxx/non_exportes_LOTxx.txt` donne le bilan, les causes avec la marche à suivre, et
la raison de chaque valeur. Il est supprimé par un nouvel export du même LOT sans
anomalie, pour ne pas laisser un rapport périmé.

Pour une commune, `audit_<commune>.xlsx` est toujours lu en priorité. Une valeur
absente de ce fichier mais présente dans une autre copie du dossier (conflit OneDrive
par exemple) n'est pas exportée : elle est signalée, à vous de dire quelle copie est
à jour.

### ID en attente

Les ID erreur non exportés (fichier verrouillé, OneDrive non synchronisé,
dossier source erroné...) sont conservés d'un lancement à l'autre dans
`ids_en_attente.json`, à côté de `config.json`.

- **Charger les ID en attente** les replace dans la zone de saisie, en mode ID
  erreur, et vide le numéro de LOT. Après l'export, ceux qui ont réussi sont
  retirés de la liste.
- **Vider la liste** efface uniquement la liste, aucun fichier Excel n'est modifié.

Utilisez un nouveau numéro de LOT pour rejouer : dans le même LOT, le fichier
d'une commune (ou le fichier unique) serait remplacé par un fichier ne contenant
que les ID rejoués. Les saisies au format invalide ne sont pas conservées, car
elles ne peuvent pas être rejouées telles quelles.

## Fichier(s) Excel produits

Quel que soit le mode, on choisit la sortie :

- **Un fichier par code INSEE** (par défaut) : un `audit_<INSEE>.xlsx` par commune.
- **Un seul fichier pour tout le LOT** : toutes les communes sont regroupées
  dans `LOTxx/audit_LOTxx.xlsx`. Le premier fichier sert de modèle (mise en
  forme, largeurs de colonnes) ; pour chaque feuille (`Audit`, `DGFIP`, `IPE`,
  `BAN`...), les lignes des communes suivantes sont ajoutées à la suite, sans
  répéter l'en-tête, avec les formules recalées. Les feuilles identiques dans
  tous les fichiers (listes déroulantes) ne sont gardées qu'une fois, et les
  lignes « modèle » ne contenant que des formules sont retirées.

## Configuration des dossiers

Le **dossier source** (racine `DepXX/COMMUNE/audit_*.xlsx`) et le **dossier de
destination** (où le dossier `LOTxx` est créé) se choisissent directement dans
l'interface via les boutons « Parcourir… ». Le choix est appliqué
immédiatement et sauvegardé dans `config.json`, dans le dossier de
configuration utilisateur :

- Windows : `%APPDATA%\LOT Export\config.json`
- macOS : `~/Library/Application Support/LOT Export/config.json`
- Linux : `~/.config/LOT Export/config.json`

## Installation

```bash
pip install -r requirements.txt
```

## Lancer l'application

```bash
python -m lot_export.main
```

## Lancer les tests

```bash
pytest
```

18 tests unitaires couvrent : extraction des codes commune, recherche de
fichiers (trouvé / absent / dossier manquant), export (succès / échec /
fichier introuvable / callback de progression / création de dossier), et
construction du nom de dossier LOT. Aucun test ne dépend de Tkinter.

## Étendre le projet

- Nouvelle règle de nommage/recherche de fichier → modifier uniquement
  `file_locator.py` + son test.
- Nouveau format de code commune → modifier uniquement `commune_parser.py`.
- Nouveau thème de couleurs → modifier uniquement `gui/theme.py` (`Palette`,
  `Fonts` et la fonction `apply_theme()`).
- Export vers un autre support (ex: zip au lieu de simple copie) → ajouter une
  nouvelle implémentation de `copy_fn` injectée dans `ExportService`, sans
  toucher à l'UI.
