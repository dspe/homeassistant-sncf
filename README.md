# SNCF Épernon Paris — Home Assistant / HACS

![Icône](custom_components/sncf_epernon/brand/icon.png)

Les prochains trains directs d'Épernon vers Paris-Montparnasse : horaires prévus,
prévisions, retards, suppressions explicites et messages de perturbation.

**Depuis la version 0.2.0, l'intégration utilise les flux ouverts SNCF et ne demande
aucun token ni clé API.** Elle fonctionne sans le portail SNCF Numérique.
Compatible avec Home Assistant Core **2026.10.0 ou supérieur**, testé sur **2026.10.2**.

## Installation et mise à jour

1. Dans **HACS → ⋮ → Dépôts personnalisés**, ajouter
   `https://github.com/dspe/homeassistant-sncf`, catégorie **Intégration**.
2. Télécharger **SNCF Épernon Paris**, puis redémarrer Home Assistant.
3. Ouvrir **Paramètres → Appareils et services → Ajouter une intégration**,
   rechercher **SNCF Épernon Paris** et valider le formulaire sans clé.
4. Installer **Flex Table Card** dans HACS et coller
   [dashboards/carte.yaml](dashboards/carte.yaml) dans une carte manuelle.

Pour passer de la version 0.1.x à 0.2.0 : mettre à jour ou télécharger à nouveau
l'intégration dans HACS, puis redémarrer Home Assistant. Une entrée existante est
migrée automatiquement vers la source ouverte et sa clé obsolète est supprimée.
Si l'ajout avait échoué avant la création de l'entrée, reprendre l'étape 3.
Le capteur reste **`sensor.sncf_epernon_paris`**, avec la liste dans l'attribut
`trains`. Vérifier son nom réel si Home Assistant lui a attribué un suffixe.

[Guide complet et dépannage](docs/INSTALLATION.md).

## Affichage

| Statut | Signification |
|---|---|
| 🟢 À l'heure | Le flux fournit explicitement une prévision identique à l'horaire |
| 🟠 +N min | Retard calculé depuis une prévision de départ à Épernon |
| 🔴 Supprimé | Annulation du train ou suppression de l'arrêt de départ explicitement annoncée |
| 🟠 Perturbation | Message applicable ou arrêt à Paris non desservi |
| ⚪ Horaire prévu | Aucune prévision temps réel exploitable pour ce départ |

La carte affiche 5 trains par défaut, avec une actualisation toutes les 2 minutes.
La recherche s'étend jusqu'à 7 jours pour compléter la liste quand les départs
des prochaines 24 heures ne suffisent pas. La date est affichée pour les autres jours.
Les options de l'intégration permettent de choisir 1 à 20 trains et un intervalle
de 120 à 3 600 secondes.

## Sources ouvertes et couverture

L'intégration télécharge le [GTFS SNCF théorique et les flux GTFS-RT](https://transport.data.gouv.fr/datasets/horaires-sncf?locale=fr)
Trip Updates et Service Alerts. La présence d'Épernon, des trains vers Paris et de
suppressions a été vérifiée sur les fichiers réels reçus le **23 octobre 2026**.
Le [rapport de vérification](docs/OPEN_DATA_VALIDATION.md) décrit les observations.

Le GTFS national est téléchargé au premier démarrage, puis toutes les 12 heures.
Seuls les horaires pertinents sont conservés dans un cache local persistant. Le
fichier compressé pesait environ 5,3 Mo lors de la vérification. En cas d'échec de
son actualisation, un cache de moins de 48 heures est réutilisé avec avertissement.
Les prévisions et alertes nationales sont téléchargées à chaque actualisation.

Les flux temps réel sont rejetés si leur date de publication remonte à plus de
10 minutes. Lorsqu'un flux échoue, la carte garde les horaires prévus et affiche
un avertissement ; elle ne transforme jamais l'absence d'information en « À l'heure »
ou en « Supprimé ». Les deux flux peuvent échouer indépendamment.

## Limites

- La SNCF ne garantit pas une couverture temps réel exhaustive des TER. La
  disponibilité constatée à Épernon ne garantit pas tous les trains tous les jours.
- La prévision est essentiellement publiée à proximité de la circulation. Les
  trains plus lointains peuvent rester en horaire prévu ou porter une perturbation.
- Les horaires théoriques peuvent déjà intégrer des adaptations connues et omettre
  certains trains annulés. Un départ absent du GTFS est réintroduit seulement si
  le flux temps réel donne son parcours Épernon → Paris et son horaire de départ.
- Le rapprochement utilise le numéro commercial, la date de service et les arrêts.
  Si plusieurs départs sont ambigus, aucune prévision n'est attribuée automatiquement.
- Seuls les trains directs avec prise en charge autorisée à Épernon et descente
  autorisée à Montparnasse sont retenus. Les cars et correspondances sont exclus.
- La recherche couvre les 7 prochains jours, en conservant aussi les trains
  retardés dont l'heure prévue est passée depuis moins de 3 heures.
- Les heures sont interprétées dans le fuseau Europe/Paris. L'heure du capteur
  indique la réception des données ; `temps_reel_actualise` indique la publication
  du flux de prévisions. Les messages d'incident sont accessibles dans chaque train.

Les données sont fournies par SNCF Voyageurs, via le portail Open Data et le Point
d'Accès National transport.data.gouv.fr. Ce projet est indépendant de la SNCF.

## Développement

Le code installable est dans `custom_components/sncf_epernon/`. HACS gère ses mises
à jour ; le YAML de la carte doit être reporté dans le tableau de bord s'il change.
Les anciens fichiers `packages/` sont conservés comme référence et ne sont pas
installés par HACS. Ne pas activer l'ancien package YAML simultanément.

Avec Python **3.14.2 ou supérieur** :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/verify_templates.py
```

Les tests couvrent le GTFS, les dates de service, les prévisions, les annulations,
les identifiants réellement publiés, le cache, les pannes partielles, la migration
et les classes de Home Assistant 2026.10.2. Un extrait des flux publics réels du
23 octobre 2026 sert aussi de régression. Aucun test ne demande de secret.

GitHub vérifie les tests, la structure HACS et les manifestes avec hassfest.
La validation HACS ignore seulement les métadonnées de catalogue (description,
topics et licence).
