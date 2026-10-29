# Étude d'optimisation de la consommation énergétique des accès à une API distante

> Document de travail, complété au fur et à mesure de l'étude.
> Dernière mise à jour : 28/10/2026.

**Sujet :** mesurer puis réduire la consommation énergétique d'un Raspberry Pi 5 qui
interroge l'API temps réel d'Île-de-France Mobilités (PRIM, horaires de passage), en
comparant plusieurs stratégies d'accès : fréquence de polling, cache, filtrage des
données, réutilisation des connexions, compression.

**Livrables :** état de l'art, prototype instrumenté, analyse comparative,
recommandations de bonnes pratiques.

## Sommaire

1. [Contexte et système étudié](#1-contexte-et-système-étudié)
2. [État de l'art](#2-état-de-lart)
3. [Méthode et outils de mesure](#3-méthode-et-outils-de-mesure)
4. [État initial : résultats](#4-état-initial--résultats)
5. [Stratégies d'optimisation à tester](#5-stratégies-doptimisation-à-tester)
6. [Recommandations](#6-recommandations)
7. [Journal des mesures](#7-journal-des-mesures)

---

## 1. Contexte et système étudié

### Matériel

| Élément | Détail |
|---|---|
| Carte | Raspberry Pi 5 Model B Rev 1.0, 4 cœurs, 8 Go RAM |
| OS | Ubuntu, noyau Linux 6.17 (raspi) |
| CPU | **overclocké** : `arm_freq=2900`, `over_voltage_delta=50000` (gouverneur `ondemand`, 1,5 à 2,9 GHz) |
| Réseau | Wi-Fi (`wlan0`), mode économie d'énergie **activé** ; Ethernet non branché |
| Écran | ST7789 240×280 en SPI (40 MHz), rétroéclairage en PWM logiciel 1 kHz à 80 % |
| Autres charges | interface graphique GNOME, Docker/containerd, un processus Java |

### Application

L'application affiche les deux prochains passages à l'arrêt *Anquetil*
(`STIF:StopPoint:Q:7800:`) avec un bus animé. Elle interroge l'API
`stop-monitoring` de PRIM **toutes les 80 s** et à chaque appui sur le bouton.

Deux versions existent :

| Version | Description |
|---|---|
| **Python** (jusqu'au 28/10/2026, commit `20f914e`) | Pillow + lgpio + spidev, conversion d'image en Python pur |
| **Go** (actuelle) | même comportement, réécrite en Go (`main.go`, `api.go`, `render.go`, `hardware.go`) |


### L'API PRIM

| Propriété | Valeur observée |
|---|---|
| Point d'accès | `GET https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring?MonitoringRef=…` |
| Authentification | en-tête `apikey` |
| Infrastructure | Cloudflare (`server: cloudflare`), TLS |
| Corps de réponse | **2 392 o** en JSON brut, **695 o** compressé gzip |
| En-têtes de réponse | **~2,8 ko** (cookies Cloudflare, CSP, quotas…) : plus lourds que les données |
| Cache côté serveur | `x-cache-status: Hit`, `age: 10` → les données sont déjà mises en cache par le serveur |
| `Cache-Control` | `no-store, no-cache, max-age=0` → aucun cache HTTP côté client autorisé |
| Quotas | 100 requêtes/s, 1 000 000/jour |

---

## 2. État de l'art

> Synthèse courte, à approfondir.

### 2.1 Facteurs de consommation liés aux accès réseau

- **États de la radio et « énergie de queue »** : après un échange, l'interface radio
  reste un moment dans un état actif coûteux avant de se rendormir. Sur réseau
  cellulaire, cette queue peut dominer le coût des petits transferts
  (Balasubramanian et al., IMC 2009 ; Huang et al., MobiSys 2012). En Wi-Fi, le mode
  économie d'énergie 802.11 (PSM) endort la radio entre les balises du point d'accès ;
  chaque échange la réveille.
  → *Conséquence* : regrouper les requêtes coûte moins cher que les étaler.
- **Établissement de connexion** : résolution DNS, poignée de main TCP (1 aller-retour)
  et TLS (1 aller-retour en TLS 1.3, RFC 8446). La poignée de main TLS implique de la
  cryptographie asymétrique (coûteuse en CPU) et l'envoi des certificats (plusieurs ko).
  → *Conséquence* : réutiliser les connexions (HTTP keep-alive, HTTP/2) ou reprendre
  les sessions TLS.
- **Volume de données** : plus d'octets = radio active plus longtemps. Cela inclut les
  en-têtes HTTP, souvent négligés.
- **Compression** : réduit les octets transférés mais coûte du CPU (décompression).
  Le bilan dépend du rapport entre coût radio et coût CPU.
- **Fréquence de polling** : le coût est proportionnel au nombre de requêtes. Il est
  inutile d'interroger plus vite que la source ne se met à jour.
- **Requêtes conditionnelles et cache** : `ETag` / `If-None-Match` ou
  `If-Modified-Since` (RFC 9110) permettent une réponse `304 Not Modified` sans corps.
  Nécessite que le serveur les supporte.
- **Filtrage côté serveur** : ne demander que les champs ou les lignes utiles.
- **Coûts indirects côté client** : réveils du processeur (timers, threads), qui
  empêchent les états de veille profonde du CPU.

### 2.2 Méthodes et outils de mesure

| Méthode | Exemples | Avantages | Limites                                                        |
|---|---|---|----------------------------------------------------------------|
| Wattmètre USB en série | FNIRSI FNB58, UM25C/UM34C | mesure réelle à la prise, simple | résolution ~10 mA, échantillonnage lent (dont je ne dispose pas)                        |
| Capteur de courant dédié | INA219 / INA226 (I²C) | précis, échantillonnage rapide, scriptable | montage électronique nécessaire (dont je ne dispose pas)       |
| Moniteur de laboratoire | Monsoon Power Monitor | référence scientifique | coûteux                                                        |
| Capteurs internes de la carte | PMIC du Pi 5 (`vcgencmd pmic_read_adc`) | aucun matériel, détail par rail | n'inclut pas les pertes de conversion ni les périphériques USB |
| Estimation logicielle | `/proc` (temps CPU, réveils), `powertop`, `perf`, modèles d'énergie (Eprof, Pathak et al., EuroSys 2012) | attribution par processus | estimation indirecte, à calibrer                               |
| Mesure réseau | `tcpdump`, compteurs `/proc/net/dev`, `curl -w` | octets et durées exacts | ne donne pas des joules                                        |

---

## 3. Méthode et outils de mesure

### 3.1 Puissance électrique : PMIC du Raspberry Pi 5

Le Pi 5 intègre un PMIC qui mesure tension et courant de chaque rail
(cœur CPU, mémoire, 3,3 V, 1,8 V, Wi-Fi…). On le lit via la commande firmware
`pmic_read_adc` (celle de `vcgencmd`), envoyée par la mailbox `/dev/vcio`.

**Puissance retenue** = Σ (tension × courant) de tous les rails.

> ⚠️ Limites : cette valeur exclut les pertes du convertisseur 5 V et les
> périphériques USB. Elle sert à **comparer** des scénarios entre eux, pas à
> donner la consommation à la prise. 
### 3.2 Indicateurs logiciels

| Indicateur | Source | Intérêt |
|---|---|---|
| CPU du processus (% d'un cœur) | `/proc/<pid>/stat` (utime + stime) | part de l'application |
| CPU total (% d'un cœur, 4 cœurs = 400 %) | `/proc/stat` | charge globale |
| Réveils (changements de contexte/s) | `/proc/<pid>/task/*/status` | empêchent la veille du CPU |
| Trafic Wi-Fi (o/s) | `/proc/net/dev` (`wlan0`) | activité radio |
| Fréquence CPU, température | `/sys/devices/system/cpu/…`, `/sys/class/thermal/…` | contexte |

### 3.3 Outils développés (prototype instrumenté)

| Outil | Rôle |
|---|---|
| [`etude/mesure`](mesure/main.go) | échantillonne tous les indicateurs chaque seconde → CSV + tableau de synthèse |
| [`etude/mesurer.sh`](mesurer.sh) | enchaîne les scénarios (sans app, Go, Python) sur le vrai matériel, relance le service à la fin |
| [`etude/reseau`](reseau/main.go) | coût d'une requête API (CPU, octets réels, durée) selon la stratégie de connexion et de compression |

```bash
go run ./etude/mesure -pmic                          # lecture brute du PMIC
sudo ./etude/mesurer.sh                              # tous les scénarios (~10 min)
PRIM_API_KEY=... go run ./etude/reseau               # banc réseau
```

### 3.4 Protocole

- Chaque scénario : 20 s de chauffe puis **120 s de mesure**, à 1 échantillon/s.
- Pendant la mesure, ne pas utiliser le Pi (pas de session interactive active, pas de
  compilation, pas de navigateur).
- Les CSV bruts sont dans [`etude/resultats/`](resultats/).

---

## 4. État initial : résultats

### 4.1 Consommation globale par scénario

| Scénario | P PMIC moy. (W) | P cœur CPU (W) | CPU app (% cœur) | CPU système (% cœur) | Réveils app (/s) |
|---|---|---|---|---|---|
| Pi sans application | *à mesurer* | | — | | — |
| Python `20f914e` (ancienne version en service) | *à mesurer* | | | | |
| Go (actuel) | **3,21** (σ 0,57) | 1,22 | **9,8** | 22,1 | **~4 300** |


**Historique** : avant son remplacement, le processus Python avait consommé
21 055 min de CPU en 38 jours, soit **38,4 % d'un cœur en moyenne**
(environ 4 fois la version Go).

### 4.2 Où passe le CPU de l'application ?

Coût CPU d'**une image** affichée (banc hors matériel, [`python_rendu.txt`](resultats/python_rendu.txt)) :

| Version | Dessin de la page | Conversion RGB565 + envoi | Total / image | À 12 images/s |
|---|---|---|---|---|
| Python `20f914e` | 7,4 ms | 21,6 ms | 29,0 ms | ≈ 35 % d'un cœur |
| Go | 3,5 ms | < 1 ms (+ pilote SPI noyau) | ≈ 4–5 ms | ≈ 10 % mesuré |

La version Python passe les trois quarts de son temps dans la conversion de l'image
en RGB565, écrite en Python pur pixel par pixel.

### 4.3 Coût d'une requête API

Mesuré avec [`etude/reseau`](reseau/main.go), 30 requêtes par stratégie
([`reseau.txt`](resultats/reseau.txt)) :

| Stratégie | CPU / requête | Octets reçus | Octets envoyés | Durée |
|---|---|---|---|---|
| Nouvelle connexion + gzip (**comportement actuel**) | 9,0 ms | 7 570 | 1 844 | 78 ms |
| Nouvelle connexion, sans gzip | 9,0 ms | 9 277 | 1 820 | 81 ms |
| Connexion réutilisée + gzip | **0,8 ms** | **3 753** | **297** | 80 ms |
| Connexion réutilisée, sans gzip | 0,6 ms | 5 489 | 274 | 124 ms |

Observations :

- La **poignée de main TLS** représente ~90 % du CPU d'une requête et ~55 % des
  octets échangés.
- Entre deux rafraîchissements (80 s), **aucune connexion vers PRIM ne reste ouverte**
  (`ss`) : l'application refait donc une poignée de main complète à chaque fois.
- gzip économise ~1,7 ko par réponse pour un surcoût CPU négligeable.
- Les **en-têtes de réponse (~2,8 ko)** pèsent plus que les données utiles (695 o
  compressées) et ne sont pas compressés en HTTP/1.1.

### 4.4 Premières conclusions

1. **L'affichage domine, pas le réseau.** À 1 080 requêtes/jour × 9 ms, l'accès API
   représente ~10 s de CPU par jour, contre ~8 500 s pour l'affichage à 12 images/s :
   **le réseau pèse moins de 0,2 % du CPU de l'application**. Les optimisations
   réseau devront être mesurées **isolément** (sans animation), sinon leur effet
   sera noyé dans le bruit.
2. **Le passage de Python à Go** divise le CPU de l'application par environ 4
   (38 % → 10 % d'un cœur). Le gain en watts reste à mesurer.
3. **Réveils** : ~4 300 changements de contexte/s, surtout dus au PWM logiciel du
   rétroéclairage (2 000 fronts/s) et à la boucle de 10 ms. Ils empêchent les
   cœurs de rester en veille.
   interface graphique et Docker actifs alors que le Pi sert d'afficheur.
5. **Radio Wi-Fi** : le rail `3V7_WL_SW` consomme à lui seul ~0,35 W en continu.

---

## 5. Stratégies d'optimisation à tester

| # | Stratégie | Hypothèse | Mesure prévue | État |
|---|---|---|---|---|
| R1 | Fréquence de polling (30 s, 80 s, 2 min, 5 min, adaptative selon l'heure du prochain bus) | coût ∝ nombre de requêtes | requêtes/jour, P moyenne | à faire |
| R2 | Réutilisation de connexion (keep-alive long, HTTP/2, reprise de session TLS) | −90 % CPU, −50 % octets par requête | banc `reseau` + test 80 s réel | à faire |
| R3 | Compression (gzip, brotli si supporté) | moins d'octets, CPU négligeable | banc `reseau` | en partie fait |
| R4 | Cache local : ne pas interroger si le prochain bus est connu et lointain | moins de requêtes | requêtes/jour | à faire |
| R5 | Requêtes conditionnelles (`ETag`, `If-Modified-Since`) | réponses 304 sans corps | vérifier le support serveur | à faire |
| R6 | Filtrage des données demandées (paramètres de l'API : ligne, direction…) | réponses plus petites | taille de réponse | à faire |
| R7 | Regroupement des requêtes (radio réveillée moins souvent) | moins d'énergie de queue | P du rail Wi-Fi | à faire |
| A1 | Affichage : fréquence d'images réduite, ou n'envoyer que les zones modifiées | gros gain CPU | P moyenne | hors périmètre réseau, mais majoritaire |
| S1 | Système : retirer l'overclock, désactiver l'interface graphique, Ethernet vs Wi-Fi | gain de base | P sans app | à faire |

---

## 6. Recommandations

> À rédiger à partir des résultats des sections 4 et 5.

---

## 7. Journal des mesures

| Date | Mesure | Conditions | Fichier |
|---|---|---|---|
| 28/10/2026 | Go en service, 120 s | session interactive ouverte | — (préliminaire) |
| 28/10/2026 | Coût CPU par image, Python et Go | banc hors matériel | [`python_rendu.txt`](resultats/python_rendu.txt) |
| 28/10/2026 | Coût d'une requête API, 4 stratégies | Wi-Fi, 30 requêtes chacune | [`reseau.txt`](resultats/reseau.txt) |
| *à venir* | Sans app / Go / Python ×2 sur le matériel | `sudo ./etude/mesurer.sh` | `resultats/*.csv`, `resultats/*.md` |
