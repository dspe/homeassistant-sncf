# Vérification des flux ouverts — 23 octobre 2026

Les liens publiés dans [HORAIRES SNCF](https://ressources.data.sncf.com/explore/dataset/horaires-sncf/)
et sur le [Point d'Accès National](https://transport.data.gouv.fr/datasets/horaires-sncf?locale=fr)
ont été téléchargés sans authentification.

## Observations

- Archive GTFS : environ 5,3 Mo compressés, fichiers valides et calendrier courant.
- Épernon : `StopArea:OCE87394114`, avec un arrêt de train TER associé.
- Destination : `StopArea:OCE87391003`, Paris Montparnasse Hall 1 - 2.
- 189 variantes de courses directes trouvées sur l'ensemble du calendrier publié.
  Ce nombre ne représente pas les départs d'une journée : chaque variante possède
  son calendrier de circulation.
- Trip Updates : 1 293 entités, publication à 14:42:06 heure de Paris.
- Service Alerts : 541 entités, publication à 14:42:28 heure de Paris.
- SIRI ET Lite : présence d'Épernon également confirmée ; ce flux n'est pas utilisé
  par l'intégration, qui privilégie le GTFS-RT, plus compact.

Le rapprochement a confirmé que le GTFS emploie des identifiants longs et des
arrêts `StopPoint`, tandis que le GTFS-RT utilise notamment des identifiants courts
comme `OCESN862430F` et des arrêts `StopArea`. Le numéro commercial, la date de
service et les références UIC permettent le rapprochement sans confondre les jours.

À l'heure de cet échantillon, les trains 862520 (15:11), 862430 (16:07) et 862524
(17:12), vers Paris, portaient explicitement le statut GTFS-RT `CANCELED`. Leur
suppression a été reproduite dans la liste calculée par l'intégration. Ceci est
une observation datée, pas un bulletin de circulation à utiliser ultérieurement.

Un extrait de ces fichiers publics est conservé dans
`tests/fixtures/open_data_20261023/`, afin de vérifier les identifiants et la
récupération de trains annulés déjà absents des horaires théoriques actifs.
Les données proviennent de SNCF Voyageurs ; leur licence et leurs conditions
sont indiquées sur le portail source.

## Conclusion technique

L'accès sans token, les horaires, les arrêts, les prévisions et les statuts de
suppression sont exploitables pour cette liaison. La présence d'un flux valide
ne garantit pas la couverture de chaque TER. Un train sans prévision explicite
reste en « Horaire prévu » ; un flux manquant ou périmé produit un avertissement.
