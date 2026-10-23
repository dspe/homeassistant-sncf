# Home Assistant — SNCF Épernon → Paris

Configuration Home Assistant pour afficher les cinq prochains trains directs
d'Épernon vers Paris-Montparnasse, avec les horaires prévus, les horaires estimés,
les retards et les suppressions annoncées par la SNCF.

Le dépôt contient un **package YAML Home Assistant** et la configuration d'une
**Flex Table Card**, disponible dans HACS. Le package s'installe dans le dossier
`packages` de Home Assistant ; ce dépôt n'est pas une intégration HACS Python.

## Installation

Suivre le [guide d'installation](docs/INSTALLATION.md).

1. Installer **Flex Table Card** dans HACS.
2. Obtenir une [clé API SNCF gratuite](https://numerique.sncf.com/startup/api/token-developpeur/).
3. Ajouter la clé à votre `secrets.yaml` local, comme dans
   [l'exemple](examples/secrets.yaml.example).
4. Copier [le package](packages/sncf_epernon.yaml) dans le dossier `packages`
   de Home Assistant et activer le chargement des packages.
5. Vérifier la configuration, redémarrer Home Assistant, puis ajouter
   [la carte](dashboards/carte.yaml) au tableau de bord.

## Statuts affichés

| Statut | Signification |
|---|---|
| 🟢 À l'heure | Horaire confirmé dans les données temps réel reçues |
| 🟠 +N min | Retard par rapport à l'heure prévue |
| 🔴 Supprimé | Suppression explicitement annoncée pour ce départ |
| 🟠 Perturbation | Alerte applicable sans statut plus précis |
| ⚪ Horaire prévu | Confirmation temps réel non fournie |

Les appels sont effectués toutes les 60 secondes. Une réponse en erreur ou trop
ancienne rend la carte indisponible. Les trains supprimés sont conservés dans la
liste jusqu'à leur heure de départ prévue. Leur absence du flux temps réel ne
suffit jamais à les déclarer supprimés.

Les identifiants de gare et les champs renvoyés restent à confirmer avec une
réponse authentifiée de l'API SNCF pour Épernon. Les limites et le dépannage sont
décrits dans le [guide](docs/INSTALLATION.md#fonctionnement-et-limites).

## Organisation du dépôt

```text
packages/sncf_epernon.yaml       Données SNCF et préparation de la liste
dashboards/carte.yaml            Carte du tableau de bord
examples/secrets.yaml.example    Exemple sans clé réelle
docs/INSTALLATION.md             Installation et dépannage
tests/verify_templates.py        Régressions hors ligne
.github/workflows/validate.yml   Validation automatique sur GitHub
```

## Maintenance

Modifier le package et la carte dans ce dépôt. Après validation des modifications,
reporter les fichiers concernés dans Home Assistant. Un changement du package
demande une vérification de configuration et un redémarrage ; un changement de
la carte demande de remplacer son YAML dans le tableau de bord.

Le dépôt conserve l'historique et permet de revenir à une version précédente.
La synchronisation vers Home Assistant reste manuelle.

La clé SNCF reste dans le `secrets.yaml` de Home Assistant. Ce fichier et les
données générées par Home Assistant sont exclus du suivi Git. Les tests n'ont
besoin d'aucune clé ni d'aucun accès à votre installation.

## Vérifications locales

Avec Python 3.13 ou supérieur :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tests/verify_templates.py
```

Les vérifications exécutent les modèles Jinja présents dans le package distribué
sur des exemples de réponses SNCF : retards, suppressions liées à un départ,
périodes d'application, jours de semaine, créneaux passant minuit, données
absentes ou périmées, départs du lendemain et trains supplémentaires.

Elles ne remplacent pas la validation de configuration de Home Assistant ni un
essai avec les données SNCF réelles.
