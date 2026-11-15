# Moroccan operator and infrastructure outreach

**Langue:** français (brouillons) + schéma de voyage anonymisé  
**Statut:** aucune donnée reçue à ce jour --- ne pas suggérer un partenariat existant.

---

## Priorité des mesures manquantes

1. **Énergie réelle du groupe froid (TRU)** sur corridor autoroutier marocain (kWh ou équivalent diesel).
2. **SOC / recharge** effective des tracteurs électriques poids lourds (si déploiement pilote) --- puissance, durée, position agrégée.
3. **Géométrie poids lourds** aux aires ADM étudiées (Settat, Benguerir, Amskroud) --- pas seulement présence bornes voitures.
4. **Volumes et saisonnalité** des flux réfrigérés Agadir$\rightarrow$Casablanca (catégories, pas clients).

Voir aussi `reports/moroccan_data_request_specification.md`.

---

## Brouillon 1 --- Opérateur transport frigorifique

**Objet :** Demande d'entretien scientifique --- validation prospective corridor Agadir--Casablanca (données anonymisées)

Madame, Monsieur,

Nous menons une étude universitaire **prospective** sur les besoins éventuels en recharge pour le fret **réfrigéré** sur l'autoroute Agadir--Casablanca, en nous appuyant sur des données ouvertes (OpenStreetMap, COP-DEM) et des hypothèses de véhicules électriques poids lourds **non déployés** à ce jour sur ce corridor.

Nous ne demandons **aucune** donnée commerciale sensible. Si votre organisation est disposée à contribuer, nous recherchons **10 à 30 trajets anonymisés** (ou agrégats sectionnels) selon le schéma ci-dessous.

**Ce que nous ne publierons pas sans accord écrit :** identifiants véhicules, chauffeurs, clients, positions exactes de quais privés.

**Ce qui nous intéresse le plus :** catégorie de fret, masse approximative, consigne et stabilité température cargo, durées de trajet et d'arrêt, et --- si disponible --- une indication d'énergie frigo ou de recharge.

Nous restons à votre disposition pour un protocole d'anonymisation et une convention d'usage des données.

Cordialement,  
[TBD --- coordonnées chercheur]

---

## Brouillon 2 --- ADM / partenaire autoroutier

**Objet :** Clarification technique --- accès poids lourds et capacité électrique prospective aux aires Settat, Benguerir, Amskroud

Madame, Monsieur,

Dans le cadre d'une modélisation académique du corridor Agadir--Casablanca, nous positionnons des **bornes hypothétiques** compatibles camions (150--350~kW) sur la topologie officielle de vos aires de service, **sans** présumer de leur existence opérationnelle aujourd'hui.

Pourriez-vous, lorsque possible, nous indiquer (par sens de circulation) :

- l'identifiant officiel de l'aire et l'accès poids lourds articulés ;
- toute borne de recharge existante (puissance, type de connecteur, usage voiture vs poids lourd) ;
- la disponibilité électrique indicative (kVA/kW), même sous réserve.

Ces éléments permettraient de remplacer des hypothèses par des données **sourcées** dans une publication scientifique.

Respectueusement,  
[TBD]

---

## Brouillon 3 --- ONEE / énergie (optionnel)

**Objet :** Demande d'orientation tarifaire pour scénarios illustratifs (non contractuels)

Nous modélisons des **coûts normalisés illustratifs** pour la recharge en corridor. Avant toute citation publique de tarifs industriels marocains, nous sollicitons une **orientation** sur les catégories tarifaires applicables aux postes haute puissance (sans engagement commercial).

---

## Schéma de voyage anonymisé (CSV suggéré)

En-têtes proposés --- **aucune valeur d'exemple** (ne pas inventer de lignes) :

```csv
trip_id,date,origin_city,destination_city,direction,cargo_category,payload_t_band,trailer_type,setpoint_c,temp_cargo_min,temp_cargo_max,temp_ambient_mean,drive_h,stop_h,departure_local,arrival_local,refrig_energy_kwh_or_band,charge_stop_class,notes_anonymized
```

| Champ | Obligatoire | Commentaire |
| --- | --- | --- |
| `trip_id` | Oui | Hash ou code interne non réversible |
| `direction` | Oui | ex. `agadir_to_casablanca` |
| `cargo_category` | Oui | primeurs / agrumes / mix --- pas de SKU |
| `payload_t_band` | Recommandé | ex. `4-6`, `12-16` |
| `refrig_energy_kwh_or_band` | **Priorité haute** | manquant dans tout le dépôt actuel |
| `charge_stop_class` | Recommandé | `depot` / `autoroute` / `port` / `none` |

Stockage : dossier non public du projet ; statistiques dérivées uniquement pour articles.

---

## Éthique et anonymisation

- Agrégation par tronçon autoroutier si GPS fine impossible.
- Pas de croisement avec contrats ou factures clients.
- Consentement écrit si publication au-delà d'agrégats nationaux.