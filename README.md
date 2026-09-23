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
│   ├── excel_filter.py        #   filtrage des lignes de la feuille Audit (openpyxl)
│   ├── file_locator.py        #   recherche des fichiers audit_*.xlsx
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
