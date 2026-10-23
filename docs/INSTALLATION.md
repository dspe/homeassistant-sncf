# Installation de la version ouverte (0.2.1)

Prérequis : Home Assistant Core 2026.10.0 ou supérieur, HACS et un accès Internet.
**Aucun token n'est nécessaire**, ni celui du portail Open Data ni celui de Navitia.

## Si une ancienne version est installée

1. Dans HACS, ouvrir **SNCF Épernon Paris**.
2. Mettre à jour, ou utiliser **⋮ → Télécharger à nouveau** et choisir la branche
   `main` si HACS ne propose pas encore la mise à jour.
3. Redémarrer Home Assistant.
4. Si l'intégration avait été configurée, elle migre automatiquement vers la
   source ouverte en supprimant l'ancienne clé de sa configuration locale.
5. Si l'ajout avait échoué sur « Clé refusée », reprendre l'ajout dans Appareils
   et services : la nouvelle version ne présente plus de champ de clé.

La liste des trains reste dans `sensor.sncf_epernon_paris`. Une carte déjà reliée
à ce capteur reste compatible. Le nouveau YAML ajoute des avertissements utiles
lorsqu'un flux temps réel est temporairement indisponible.

## Nouvelle installation

1. Dans **HACS → ⋮ → Dépôts personnalisés**, ajouter
   `https://github.com/dspe/homeassistant-sncf`, catégorie **Intégration**.
2. Télécharger **SNCF Épernon Paris**, puis redémarrer Home Assistant.
3. Dans **Paramètres → Appareils et services → Ajouter une intégration**,
   rechercher **SNCF Épernon Paris**.
4. Valider le formulaire d'information. Le premier chargement télécharge les
   horaires nationaux et peut prendre quelques secondes.
5. Dans **Outils de développement → États**, rechercher
   `sensor.sncf_epernon_paris` et son attribut `trains`.

## Carte

Installer **Flex Table Card** dans HACS, recharger le navigateur, puis ajouter une
carte manuelle au tableau de bord avec le contenu de
[dashboards/carte.yaml](../dashboards/carte.yaml).

Si le capteur porte un suffixe, adapter ses références dans le YAML de la carte.
Les options de l'intégration règlent le nombre de trains et la fréquence de
récupération. Elles rechargent automatiquement l'intégration.

## Ancien package YAML

Si `packages/sncf_epernon.yaml` avait été copié dans Home Assistant, retirer ce
package, vérifier la configuration et redémarrer avant d'activer l'intégration
HACS. Le capteur de l'ancien package était `sensor.trains_epernon_paris` : remplacer
l'ancienne carte par le nouveau YAML. Le reste de la configuration des packages
peut rester en place. Le [guide historique](LEGACY_YAML.md) est conservé comme référence.

## Dépannage

- **Le formulaire demande encore une clé** : vérifier la version 0.2.1 dans HACS,
  télécharger à nouveau la branche `main`, puis redémarrer Home Assistant.
- **Impossible de charger les horaires publics** : vérifier l'accès réseau et les
  journaux de `custom_components.sncf_epernon`. Aucun token ne résoudra ce message.
- **Capteur indisponible** : le GTFS n'a pas encore pu être chargé ou son cache est
  trop ancien. Home Assistant réessaiera la connexion.
- **Horaires prévus et avertissement sur le temps réel** : les horaires restent
  utilisables, mais l'un des flux n'a pas pu être récupéré ou est trop ancien.
- **Moins de cinq lignes** : dans les options de l'intégration, régler le nombre
  de trains sur 5. Depuis la version 0.2.1, la recherche couvre jusqu'à 7 jours
  pour compléter la liste ; la carte ne limite pas le nombre de lignes.
- **Aucun départ** : il peut ne pas y avoir de trains dans les 7 prochains jours.
  Les adaptations ou travaux peuvent aussi supprimer des circulations du GTFS.
- **Trains supprimés** : la suppression est explicitement fournie par les données.
  L'intégration ne la déduit pas de l'absence d'un train dans le temps réel.
- **Custom element doesn't exist: flex-table-card** : vérifier son installation
  dans HACS et recharger complètement le navigateur.

Les sources et les limites sont décrites dans le [README](../README.md).
