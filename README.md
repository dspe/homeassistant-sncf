# SNCF Épernon Paris — intégration Home Assistant

![Icône](custom_components/sncf_epernon/brand/icon.png)

Les prochains trains directs d'Épernon vers Paris-Montparnasse dans Home Assistant,
avec les horaires prévus, les horaires estimés, les retards et les suppressions
annoncées par la SNCF.

**Installation via HACS et configuration depuis l'interface de Home Assistant.**
Compatible avec Home Assistant Core **2026.10.0 ou supérieur**, testé avec
**2026.10.2**. Une clé API SNCF gratuite est nécessaire.

## Installer

1. Dans **HACS → ⋮ → Dépôts personnalisés**, ajouter
   `https://github.com/dspe/homeassistant-sncf`, catégorie **Intégration**.
2. Télécharger **SNCF Épernon Paris**, puis **redémarrer Home Assistant**.
3. Dans **Paramètres → Appareils et services → Ajouter une intégration**,
   rechercher **SNCF Épernon Paris**.
4. Saisir votre [clé API SNCF](https://numerique.sncf.com/startup/api/token-developpeur/).
5. Pour la carte, installer **Flex Table Card** dans HACS, puis coller
   [dashboards/carte.yaml](dashboards/carte.yaml) dans une carte manuelle.

Le capteur créé par défaut est **`sensor.sncf_epernon_paris`**. La liste est dans
son attribut `trains`. En cas de nom déjà utilisé, adapter l'identifiant dans la
carte à celui effectivement créé.

Le [guide détaillé](docs/INSTALLATION.md) couvre l'installation, la migration
 depuis l'ancien package YAML et le dépannage.

## Affichage et réglages

| Statut | Signification |
|---|---|
| 🟢 À l'heure | Horaire confirmé dans les données temps réel reçues |
| 🟠 +N min | Retard par rapport à l'heure prévue |
| 🔴 Supprimé | Suppression explicitement annoncée pour ce départ |
| 🟠 Perturbation | Alerte applicable sans statut plus précis |
| ⚪ Horaire prévu | Confirmation temps réel non fournie |

L'intégration affiche **5 trains** et actualise toutes les **60 secondes** par
défaut. Dans les options de l'intégration, ces valeurs peuvent être réglées de
1 à 20 trains et de 60 à 3 600 secondes. Le menu **Reconfigurer** permet de changer
la clé. Une clé refusée déclenche une demande de réauthentification.

La clé est stockée par Home Assistant dans la configuration de l'intégration ;
aucune modification de `secrets.yaml` n'est nécessaire avec cette version HACS.

## Données et limites

- Deux appels SNCF par actualisation : horaires prévus et temps réel. À 60 secondes,
  environ 2 880 appels par jour, hors configuration, redémarrages et actualisations
  manuelles. Les autres usages de la clé partagent le quota SNCF.
- Les suppressions sont recherchées dans les perturbations explicitement liées
  au départ, avec vérification de leurs périodes et calendriers. L'absence d'un
  train dans le flux temps réel n'est jamais une preuve de suppression.
- Les trains supprimés restent visibles jusqu'à leur heure prévue. Les trains
  retardés restent visibles jusqu'à l'heure estimée reçue.
- Les horaires sont interprétés dans le fuseau Europe/Paris. Les départs du
  lendemain incluent leur date. La liste est triée par heure prévue.
- La recherche couvre les 3 dernières heures et les 24 prochaines heures, avec
  au maximum 80 départs par réponse avant filtrage vers Paris. Un retard de plus
  de 3 heures ou une réponse tronquée peut limiter les résultats.
- La liaison est fixe : Épernon → Paris-Montparnasse, trains directs uniquement,
  sans cars de substitution ni itinéraires avec correspondance.
- Une erreur de récupération rend le capteur indisponible. Le timestamp du capteur
  indique la réception de l'API, pas l'âge de l'information à la source.
- Les tests utilisent des réponses simulées : la disponibilité du temps réel,
  les identifiants et la publication des suppressions restent à confirmer avec
  votre clé et les données réelles d'Épernon.

## Maintenance

Le code installable est dans `custom_components/sncf_epernon/`. HACS gère ses
mises à jour ; après une mise à jour, redémarrer Home Assistant. Les évolutions
du YAML de la carte doivent être reportées dans le tableau de bord.

Les fichiers `packages/` et `dashboards/carte-legacy.yaml` conservent l'ancienne
version YAML comme référence. Ils ne sont pas installés par HACS. Ne pas activer
les deux versions simultanément.

Avec Python **3.14.2 ou supérieur** :

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/verify_templates.py
```

Les tests exercent le traitement des départs et les classes de Home Assistant
2026.10.2, avec simulation de la SNCF. GitHub vérifie aussi la structure HACS et
les manifestes avec hassfest. La validation HACS ignore uniquement les métadonnées
de catalogue (description, topics et licence) ; elle vérifie les fichiers
installables, le manifeste HACS et l'icône.
