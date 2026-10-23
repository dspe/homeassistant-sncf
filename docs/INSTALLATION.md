# Carte Épernon → Paris-Montparnasse

Cette configuration prépare une carte affichant les cinq prochains départs directs
en train vers Paris-Montparnasse. Elle associe les horaires prévus, les horaires
temps réel et les perturbations SNCF. Les tests fonctionnent hors ligne sur des exemples. La connexion réelle à la SNCF
reste à valider avec une clé API active.

## Installation

1. Dans **HACS**, chercher et installer **Flex Table Card** (`flex-table-card`).
   [Dépôt de la carte](https://github.com/custom-cards/flex-table-card).
   Recharger ensuite le navigateur de Home Assistant.
2. Demander une clé gratuite sur le
   [formulaire officiel SNCF](https://numerique.sncf.com/startup/api/token-developpeur/).
   Ajouter dans le fichier `secrets.yaml` de Home Assistant :

   ```yaml
   sncf_api_key: "VOTRE_CLE_SNCF"
   ```

3. Créer le dossier `packages` dans le dossier de configuration de Home Assistant,
   puis y copier le fichier `packages/sncf_epernon.yaml` de ce dépôt.
4. Dans `configuration.yaml`, activer les packages :

   ```yaml
   homeassistant:
     packages: !include_dir_named packages
   ```

   Si `homeassistant:` existe déjà, ajouter uniquement la ligne `packages:` à
   l'intérieur. Si les packages sont déjà configurés, conserver leur configuration
   et adapter l'emplacement du fichier. Ne pas créer de deuxième clé identique.
   Le fichier fourni utilise le format `!include_dir_named`, pas
   `!include_dir_merge_named`.
5. Vérifier la configuration dans **Outils de développement → YAML**, puis
   redémarrer Home Assistant. Le fuseau horaire de Home Assistant doit être
   **Europe/Paris**, car les horaires SNCF de cette configuration sont locaux.
6. Dans **Outils de développement → États**, vérifier la présence de :
   - `sensor.sncf_epernon_prevu` ;
   - `sensor.sncf_epernon_temps_reel` ;
   - `sensor.trains_epernon_paris`, dont l'attribut `trains` contient la liste.

   Les noms peuvent recevoir un suffixe si des entités du même nom existent déjà.
   Dans ce cas, adapter leurs références dans les deux fichiers YAML.
7. Modifier le tableau de bord, ajouter une **carte manuelle**, puis y coller
   tout le contenu de `dashboards/carte.yaml`.

## Affichage

Exemple fictif, uniquement pour illustrer le rendu :

| Prévu | Estimé | Train | Statut |
|---|---|---|---|
| 07:05 | 07:05 | 862406 | 🟢 À l'heure |
| 07:22 | 07:34 | 862408 | 🟠 +12 min |
| 07:34 | — | 862410 | 🔴 Supprimé |
| 07:52 | — | 862462 | ⚪ Horaire prévu |

Une perturbation sans statut suffisamment précis est indiquée par
**🟠 Perturbation**. La liste est triée par heure prévue pour conserver les trains
supprimés à leur place. Les départs du lendemain incluent leur date.

## Fonctionnement et limites

- Actualisation toutes les 60 secondes : deux appels par minute, soit environ
  2 880 par jour hors redémarrages et actualisations manuelles. Le quota publié
  par la SNCF est de 5 000 appels par jour pour la formule gratuite ; les autres
  usages de votre clé partagent ce quota.
- Une suppression est affichée lorsqu'une perturbation liée au départ l'indique
  explicitement pendant la période concernée. L'absence d'un train dans le flux
  temps réel n'est jamais considérée comme une preuve de suppression.
- Les périodes, jours de semaine et créneaux horaires des perturbations sont
  vérifiés pour la date et l'heure prévue du train.
- « À l'heure » nécessite un indicateur de données temps réel pour ce départ.
  Sans confirmation, la carte affiche « Horaire prévu ».
- La recherche couvre les trois dernières heures et les 24 prochaines heures,
  avec au maximum 80 départs par réponse avant filtrage vers Paris. Un retard
  supérieur à trois heures peut donc sortir de la recherche ; une réponse tronquée
  peut limiter les départs disponibles.
- Les trains sont rapprochés par numéro et date/heure prévue. Ce rapprochement
  et les champs temps réel devront être vérifiés avec une réponse réelle de
  votre clé API pour Épernon.
- Les données sont masquées si une récupération échoue ou si la dernière
  récupération réussie remonte à plus de trois minutes. L'heure d'actualisation
  indique la réception de l'API, pas l'âge de l'information à la source.
- La configuration filtre les destinations contenant « Paris » et « Montparnasse »
  et les modes contenant « train ». Elle ne propose pas les cars de substitution,
  ni les itinéraires avec correspondance.
- Les suppressions dépendent de leur publication par la SNCF. La carte ne peut
  pas afficher une information absente du flux.

## Dépannage

- `401` / `403` dans les journaux : vérifier la clé et son activation.
- `429` : quota ou limitation de débit de l'API.
- `404` : vérifier l'identifiant d'Épernon avec le service
  `https://api.sncf.com/v1/coverage/sncf/places?q=Epernon` en utilisant votre clé.
  L'identifiant configuré est `stop_area:SNCF:87394114` ; il reste à confirmer
  avec votre accès à l'API.
- « Custom element doesn't exist: flex-table-card » : vérifier l'installation
  HACS et recharger complètement le navigateur.
- Tous les trains sont en « Horaire prévu » : examiner l'attribut `departures`
  du capteur temps réel pour vérifier les indicateurs réellement fournis par l'API.

## Références

- [API SNCF et accès gratuit](https://numerique.sncf.com/startup/api/)
- [FAQ SNCF : authentification et couverture temps réel](https://numerique.sncf.com/faq/api/)
- [Départs de la gare d'Épernon sur TER SNCF](https://www.ter.sncf.com/centre-val-de-loire/se-deplacer/prochains-departs/epernon-87394114)
- [Documentation Navitia : départs et perturbations](https://doc.navitia.io/)
- [Intégration REST Home Assistant](https://www.home-assistant.io/integrations/rest/)
- [Packages Home Assistant](https://www.home-assistant.io/docs/configuration/packages/)
- [Documentation Flex Table Card](https://github.com/custom-cards/flex-table-card)
