# Installation via HACS

Prérequis : Home Assistant Core 2026.10.0 ou supérieur, HACS et une clé API SNCF.
Cette intégration a été testée avec le Core 2026.10.2 et des réponses simulées.

## Ajouter le dépôt

1. Ouvrir HACS, puis le menu **⋮ → Dépôts personnalisés**.
2. Indiquer `https://github.com/dspe/homeassistant-sncf`.
3. Sélectionner la catégorie **Intégration** et ajouter le dépôt.
4. Télécharger **SNCF Épernon Paris**.
5. Redémarrer Home Assistant.

Le dépôt contient maintenant `custom_components/sncf_epernon/`, la structure
attendue par HACS pour une intégration. Si une ancienne tentative affiche encore
« Repository structure for main is not compliant », fermer et rouvrir HACS,
puis refaire l'ajout avec l'URL ci-dessus. Au besoin, retirer l'entrée échouée
de la liste des dépôts personnalisés avant de l'ajouter à nouveau.

## Configurer la SNCF

1. Demander une clé sur le
   [formulaire officiel SNCF](https://numerique.sncf.com/startup/api/token-developpeur/).
2. Dans **Paramètres → Appareils et services → Ajouter une intégration**,
   rechercher **SNCF Épernon Paris**.
3. Coller la clé API et valider. L'intégration teste l'accès avant d'enregistrer
   la configuration.
4. Vérifier dans **Outils de développement → États** que
   `sensor.sncf_epernon_paris` est présent et possède un attribut `trains`.

La clé est saisie dans un champ masqué et enregistrée localement par Home Assistant.
Elle n'est pas envoyée à GitHub et n'est pas incluse dans les attributs du capteur.
Le menu **Reconfigurer** permet de la remplacer ultérieurement.

Les options de l'intégration permettent de choisir le nombre de trains (1 à 20)
et l'intervalle d'actualisation (60 à 3 600 secondes). Les modifications rechargent
l'intégration automatiquement.

## Ajouter la carte

1. Installer **Flex Table Card** dans HACS et recharger le navigateur.
2. Modifier le tableau de bord et ajouter une **carte manuelle**.
3. Coller tout le contenu de [dashboards/carte.yaml](../dashboards/carte.yaml).

Le capteur utilise par défaut `sensor.sncf_epernon_paris`. Si Home Assistant lui
attribue un suffixe, remplacer ses références dans le YAML de la carte.

## Migration depuis la première version YAML

Si vous aviez déjà installé `packages/sncf_epernon.yaml` :

1. Retirer ce package du dossier de configuration de Home Assistant avant
   d'activer la nouvelle intégration. Vérifier la configuration puis redémarrer.
2. Installer et configurer l'intégration HACS comme ci-dessus.
3. Remplacer l'ancienne carte par le nouveau YAML : le capteur utilisé passe de
   `sensor.trains_epernon_paris` à `sensor.sncf_epernon_paris`.

La clé `sncf_api_key` de `secrets.yaml` n'est plus utilisée par l'intégration HACS.
Les autres packages peuvent continuer d'utiliser votre configuration de packages.
Ne pas activer l'ancienne et la nouvelle versions en même temps : cela doublerait
les appels SNCF. L'[ancien guide YAML](LEGACY_YAML.md) reste disponible comme référence.

## Dépannage

- **L'intégration n'apparaît pas dans Appareils et services** : redémarrer Home
  Assistant après le téléchargement HACS, puis recharger le navigateur.
- **Clé API refusée** : vérifier la clé et son activation auprès de la SNCF.
- **Quota atteint** : attendre la réouverture du quota ou de la limite de débit ;
  l'intégration espace les nouvelles tentatives lorsqu'un code 429 est reçu.
- **Impossible de récupérer les données** : consulter les journaux de
  `custom_components.sncf_epernon`. Un accès réseau, une erreur SNCF ou un
  identifiant de gare non reconnu peuvent empêcher la récupération.
- **Custom element doesn't exist: flex-table-card** : vérifier l'installation
  de la carte dans HACS et recharger complètement le navigateur.
- **Horaire prévu pour tous les trains** : l'API n'a pas confirmé le temps réel
  pour les départs reçus. La carte ne les déclare pas automatiquement à l'heure.

Les limites de couverture et les statuts sont détaillés dans le
[README](../README.md#données-et-limites).

## Références

- [Structure des intégrations HACS](https://www.hacs.xyz/docs/publish/integration/)
- [API SNCF](https://numerique.sncf.com/startup/api/)
- [Documentation Navitia](https://doc.navitia.io/)
- [Flex Table Card](https://github.com/custom-cards/flex-table-card)
