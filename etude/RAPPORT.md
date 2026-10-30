# Étude d'optimisation de la consommation énergétique des accès à une API distante

> Document de travail, complété au fur et à mesure de l'étude.
> Dernière mise à jour : 30/10/2026.

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
| Puissance par rail (Wi-Fi, DDR, 0V8, 1V1, 1V8, 3V3), depuis le 30/10 | PMIC | attribuer un écart de puissance hors cœur CPU |

### 3.3 Outils développés (prototype instrumenté)

| Outil | Rôle |
|---|---|
| [`etude/mesure`](mesure/main.go) | échantillonne tous les indicateurs chaque seconde → CSV + tableau de synthèse |
| [`etude/mesurer.sh`](mesurer.sh) | enchaîne les scénarios (sans app, Go, Python `20f914e`, et leurs variantes `_powersave`) sur le vrai matériel ; rétablit le service et le gouverneur CPU à la fin |
| [`etude/reseau`](reseau/main.go) | coût d'une requête API (CPU, octets réels, durée) selon la stratégie : connexion neuve ou réutilisée, gzip, reprise de session TLS, HTTP/2 ; support d'`ETag` (R5) et du filtrage `LineRef` (R6) ; option `-pause` pour voir si la connexion survit à l'inactivité |

```bash
go run ./etude/mesure -pmic                          # lecture brute du PMIC
sudo ./etude/mesurer.sh                              # sans_app, go, python_20f914e (~8 min)
sudo ./etude/mesurer.sh sans_app_powersave go_powersave   # S1 : CPU bloqué à 1,5 GHz
PRIM_API_KEY=... go run ./etude/reseau               # banc réseau
PRIM_API_KEY=... go run ./etude/reseau -pause 80s    # la connexion survit-elle 80 s ?
```

### 3.4 Protocole

- Chaque scénario : 20 s de chauffe puis **120 s de mesure**, à 1 échantillon/s.
- Pendant la mesure, ne pas utiliser le Pi (pas de session interactive active, pas de
  compilation, pas de navigateur).
- Les CSV bruts sont dans [`etude/resultats/`](resultats/).

---

## 4. État initial : résultats

### 4.1 Consommation globale par scénario

Mesures du 29/10/2026 avec [`mesurer.sh`](mesurer.sh), 120 échantillons par scénario,
sans session interactive. Intervalle de confiance à 95 % de la moyenne entre parenthèses.

| Scénario | P PMIC moy. (W) | P PMIC médiane (W) | P cœur CPU (W) | CPU app (% cœur) | CPU système (% cœur) | Réveils app (/s) | Temps à > 1,5 GHz |
|---|---|---|---|---|---|---|---|
| Pi sans application | **2,36** (± 0,03) | 2,25 | 0,81 | — | 0,8 | — | 18 % |
| Go (actuel) | **2,86** (± 0,08) | 2,78 | 1,13 | **10,1** | 9,9 | ~4 300 | 54 % |
| Python `20f914e` (ancienne version) | **3,62** (± 0,21) | 3,00 | 1,93 | **40,0** | 40,3 | ~2 900 | 87 % |

Fichiers : [`sans_app.md`](resultats/sans_app.md), [`go.md`](resultats/go.md),
[`python_20f914e.md`](resultats/python_20f914e.md) et les CSV correspondants.

**Surcoût de l'application** (P moyenne − P sans application) :

| Version | Surcoût (W) | Par jour | Par an |
|---|---|---|---|
| Python `20f914e` | 1,26 W | 30 Wh | 11,1 kWh |
| Go | **0,50 W** | 12 Wh | 4,4 kWh |
| Gain du passage à Go | **−0,76 W (−60 %)** | −18 Wh | −6,7 kWh |

Remarques :

- La mesure préliminaire du 28/10 (Go, 3,21 W) était faussée par la session
  interactive ouverte (CPU système 22 % contre 9,9 % ici).
- Le CPU mesuré de Python (40,0 %) recoupe l'historique `ps` (38,4 % sur 38 jours) :
  le scénario reproduit bien le fonctionnement réel.
- Le Pi « à vide » consomme déjà **2,36 W**, soit 82 % de la consommation avec
  l'application Go. Les leviers système (S1) pèsent donc potentiellement plus que
  ceux de l'application.


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
| Nouvelle connexion + gzip (comportement de la version Python) | 9,0 ms | 7 570 | 1 844 | 78 ms |
| Nouvelle connexion, sans gzip | 9,0 ms | 9 277 | 1 820 | 81 ms |
| Connexion réutilisée + gzip | **0,8 ms** | **3 753** | **297** | 80 ms |
| Connexion réutilisée, sans gzip | 0,6 ms | 5 489 | 274 | 124 ms |

Observations :

- La **poignée de main TLS** représente ~90 % du CPU d'une requête et ~55 % des
  octets échangés.
- ~~Entre deux rafraîchissements, aucune connexion vers PRIM ne reste ouverte~~ :
  **corrigé le 30/10**, voir plus bas. C'était le cas de la version Python, pas de la
  version Go, qui garde sa connexion.
- gzip économise ~1,7 ko par réponse pour un surcoût CPU négligeable.
- Les **en-têtes de réponse (~2,8 ko)** pèsent plus que les données utiles (695 o
  compressées) et ne sont pas compressés en HTTP/1.1.

**Stratégies supplémentaires (30/10/2026).** Banc lancé sans clé API : le serveur
répond `401` avec un corps de 41 o. Les chiffres sont donc représentatifs du **coût
de connexion** (TCP, TLS, en-têtes), pas des données ([`reseau_sans_cle.txt`](resultats/reseau_sans_cle.txt)) :

| Stratégie | CPU / requête | Octets reçus | Octets envoyés | Durée |
|---|---|---|---|---|
| Nouvelle connexion + gzip (version Python) | 8,9 ms | 6 393 | 1 812 | 63 ms |
| Nouvelle connexion + **reprise de session TLS** | **3,3 ms** | 4 366 | 2 053 | 44 ms |
| Connexion réutilisée, HTTP/1.1 | 0,6 ms | 2 629 | 265 | 29 ms |
| Connexion réutilisée, **HTTP/2** | 0,6 ms | **1 045** | **97** | 26 ms |

- **Reprise de session TLS** (ticket TLS 1.3) : −63 % de CPU et −2 ko reçus (pas de
  chaîne de certificats ni d'échange de clés asymétrique) **même si la connexion a
  été fermée**. C'est la piste la plus robuste si la connexion ne survit pas à 80 s
  d'inactivité.
- **HTTP/2** est accepté par le serveur (Cloudflare). La compression des en-têtes
  (HPACK) divise par 2,5 les octets reçus et par 2,7 les octets envoyés par
  rapport à HTTP/1.1 sur connexion réutilisée : les ~2,8 ko d'en-têtes sont
  justement le poste le plus lourd.

**Avec la clé API (30/10/2026).** Mêmes stratégies, réponses `200` réelles
([`reseau_avec_cle.txt`](resultats/reseau_avec_cle.txt)) :

| Stratégie | CPU / requête | Octets reçus | Octets envoyés |
|---|---|---|---|
| Nouvelle connexion + gzip (version Python) | 9,0 ms | 7 717 | 1 844 |
| Nouvelle connexion, sans gzip | 9,2 ms | 9 433 | 1 820 |
| Nouvelle connexion + **reprise de session TLS** | **3,4 ms** | 5 684 | 2 084 |
| Connexion réutilisée + gzip, HTTP/1.1 | 0,8 ms | 3 926 | 297 |
| Connexion réutilisée, sans gzip, HTTP/1.1 | 0,7 ms | 5 631 | 274 |
| Connexion réutilisée + gzip, **HTTP/2** (version Go) | 0,9 ms | **2 165** | **103** |

- Les conclusions du banc sans clé se confirment : reprise TLS **−62 % de CPU**,
  HTTP/2 **−45 % d'octets reçus** par rapport à HTTP/1.1 sur connexion réutilisée.
- Par rapport à la version Python (connexion neuve, HTTP/1.1), la version Go
  (connexion réutilisée, HTTP/2, gzip) divise le CPU par requête par **10** et les
  octets reçus par **3,6**. Les 2 165 o mesurés ici sont cohérents avec les 1 253
  à 2 873 o relevés par `ss` sur le service.
- Le corps JSON fait **2 392 o** non compressé ; gzip économise ~1,7 ko par réponse.
- Les durées varient de 58 à 133 ms d'une série à l'autre sans lien clair avec la
  stratégie : elles dépendent surtout du réseau à l'instant de la mesure.

**R5, requêtes conditionnelles : non supportées.** Le serveur n'envoie ni `ETag` ni
`Last-Modified`, et répond `Cache-Control: no-store, no-cache, must-revalidate,
proxy-revalidate, max-age=0`. Pas de réponse `304` possible : piste abandonnée.

**R6, filtrage par ligne : sans gain à cet arrêt.** Le paramètre `LineRef` est
accepté (`200 OK`), mais une seule ligne dessert l'arrêt (`STIF:Line::C01142:`,
2 passages au moment du test) : la réponse filtrée fait exactement la même taille
(2 392 o). Piste abandonnée pour cet arrêt ; elle ne servirait que pour un arrêt
desservi par plusieurs lignes dont une seule intéresse l'afficheur.

**La connexion survit-elle à 80 s d'inactivité ?** Test `reseau -pause`, 30/10/2026
([`reseau_pause.txt`](resultats/reseau_pause.txt)) : **oui**, en HTTP/1.1 comme en
HTTP/2, après 10 s, 30 s et 80 s de pause. Le serveur ne ferme donc pas la connexion
entre deux rafraîchissements.

**Et dans l'application Go ?** Relevé `ss -tni` sur le service en marche, toutes
les 10 s pendant plus de deux rafraîchissements ([`ss_service_go.txt`](resultats/ss_service_go.txt)) :
c'est **toujours la même connexion** (même port local), et un rafraîchissement n'y
ajoute que **1 253 o reçus**. La version Go réutilise donc déjà sa connexion, très
probablement en HTTP/2 (activé par défaut dans le client HTTP de Go quand le
serveur le propose), avec gzip. **R2 est déjà acquis pour la version Go.** La
version Python, elle, ouvrait une connexion neuve à chaque requête.

Correctif défensif appliqué le 30/10 dans `api.go` : le corps de la réponse est
désormais toujours lu jusqu'au bout avant d'être fermé
(`io.Copy(io.Discard, resp.Body)`). Avant, une réponse en erreur (non-200), dont le
corps n'était pas lu, faisait fermer la connexion. Dans le cas normal,
`json.Decoder` lisait déjà la petite réponse jusqu'à la fin, d'où la connexion
conservée.

Vérifié après correctif (service relancé le 30/10 à 14:45) : une seule connexion
conservée pendant tout le relevé de 3 min. La 1re requête coûte **6 868 o**
(poignée de main TLS comprise), les suivantes **1 253 o et 2 873 o** sans nouvelle
poignée de main. La différence entre ces deux valeurs vient sans doute de la taille
variable de la réponse (nombre de passages listés).

### 4.4 Premières conclusions

1. **L'affichage domine, pas le réseau.** À 1 080 requêtes/jour × 9 ms, l'accès API
   représente ~10 s de CPU par jour, contre ~8 500 s pour l'affichage à 12 images/s :
   **le réseau pèse moins de 0,2 % du CPU de l'application**. Les optimisations
   réseau devront être mesurées **isolément** (sans animation), sinon leur effet
   sera noyé dans le bruit.
2. **Le passage de Python à Go** divise le CPU de l'application par environ 4
   (38 % → 10 % d'un cœur), soit −0,76 W (§ 4.1).
3. **Réveils** : ~4 300 changements de contexte/s, surtout dus au PWM logiciel du
   rétroéclairage (2 000 fronts/s) et à la boucle de 10 ms. Ils empêchent les
   cœurs de rester en veille.
4. **Charge de fond** : interface graphique et Docker actifs alors que le Pi sert
   d'afficheur.
5. **Radio Wi-Fi** : le rail `3V7_WL_SW` monte à ~0,38 W lorsque la radio est
   active, mais sa moyenne mesurée le 30/10 n'est que de **0,09 W** (§ 4.7) : le
   mode économie d'énergie du Wi-Fi coupe la radio la plupart du temps.

### 4.5 Analyse : la fréquence CPU explique l'essentiel de l'écart

Avec le gouverneur `ondemand` et l'overclock à 2,9 GHz, la moindre charge fait monter
la fréquence, et la tension avec elle. Puissance moyenne selon la fréquence relevée
au même instant :

| Scénario | P à 1,5 GHz (W) | P au-dessus de 1,5 GHz (W) | Temps au-dessus |
|---|---|---|---|
| Sans application | 2,31 | 2,59 | 18 % |
| Go | 2,59 | 3,08 | 54 % |
| Python `20f914e` | 2,62 | 3,77 | 87 % |

- À fréquence minimale, Go et Python coûtent presque pareil (+0,3 W par rapport au
  Pi à vide). **Ce qui sépare les deux versions, c'est surtout le temps passé en
  fréquence haute**, pas le travail lui-même.
- Les rails hors cœur CPU (mémoire, 3,3 V, Wi-Fi…) varient peu : 1,55 W à vide,
  1,72 W avec Go, 1,69 W avec Python. Le surcoût est concentré sur `VDD_CORE`.
- Les écarts-types élevés (σ 0,44 W pour Go, 1,16 W pour Python) viennent de ces
  montées en fréquence, pas d'un défaut de mesure.

**Conséquence pour la suite** : une application à 10 % d'un cœur déclenche encore
des montées à 2,9 GHz la moitié du temps. Deux pistes à mesurer en priorité :

1. **S1 – gouverneur / overclock** : tester `powersave` (fréquence fixe 1,5 GHz) ou
   retirer l'overclock. Gain attendu pour Go : jusqu'à ~0,27 W (2,86 → 2,59 W) si
   l'affichage reste fluide.
2. **A1 – lisser la charge de l'affichage** : moins d'images/s ou des envois partiels,
   pour que le gouverneur ne monte plus.

Les stratégies réseau (R1–R7) restent à mesurer **en isolant l'effet réseau**
(animation coupée, fréquence fixée), sinon leur effet (< 0,2 % du CPU) sera noyé
dans les variations de fréquence.

### 4.6 R1 : poids de la fréquence de polling (estimation)

Hypothèse : on convertit le CPU en énergie avec le rapport mesuré sur l'application
Go, soit 0,50 W pour 10 % d'un cœur, donc **~5 mJ par ms de CPU**. C'est une borne
haute, car ce rapport inclut les montées en fréquence dues à l'affichage. Le coût de
réveil de la radio n'est pas compté (rail Wi-Fi à mesurer, R7).

| Intervalle | Requêtes / jour | Nouvelle connexion (9 ms, 9,4 ko) | Connexion réutilisée (0,8 ms, 4,0 ko) |
|---|---|---|---|
| 30 s | 2 880 | 130 J/j · 27 Mo/j | 12 J/j · 11,7 Mo/j |
| **80 s (actuel)** | **1 080** | 49 J/j (0,014 Wh) · 10 Mo/j (cas de la version Python) | **4 J/j · 4,4 Mo/j (cas de la version Go)** |
| 2 min | 720 | 32 J/j · 6,8 Mo/j | 3 J/j · 2,9 Mo/j |
| 5 min | 288 | 13 J/j · 2,7 Mo/j | 1 J/j · 1,2 Mo/j |

À comparer aux **12 Wh/j (43 000 J)** de surcoût de l'application Go : même à 30 s,
le CPU des requêtes représente **0,3 %** du total. Changer la fréquence de polling
ne se verra donc pas au wattmètre tant que l'affichage tourne. L'intérêt reste réel
pour le volume de données et pour le serveur.

En pratique, la version Go ne reçoit que **1 253 o par rafraîchissement** sur sa
connexion HTTP/2 conservée (§ 4.3), soit **~1,4 Mo/j** à 80 s, encore moins que la
colonne « connexion réutilisée » (mesurée en HTTP/1.1).

### 4.7 S1 : CPU bloqué à 1,5 GHz (gouverneur `powersave`)

Mesures du 30/10/2026 vers 15 h (`sudo ./etude/mesurer.sh sans_app_powersave go_powersave`),
120 échantillons par scénario, **sans session interactive**, comparées à celles du
29/10 en gouverneur `ondemand`. Intervalle de confiance à 95 % de la moyenne entre
parenthèses.

| Scénario | P PMIC moy. (W) | σ (W) | P cœur CPU (W) | P hors cœur (W) | CPU app (% cœur) | CPU système (% cœur) | Trafic Wi-Fi (o/s) |
|---|---|---|---|---|---|---|---|
| Sans app, `ondemand` (29/10) | 2,36 (± 0,03) | 0,19 | 0,81 | 1,55 | — | 0,8 | 218 |
| Sans app, `powersave` (30/10) | **2,34** (± 0,03) | 0,19 | 0,76 | 1,57 | — | 0,8 | 60 |
| Go, `ondemand` (29/10) | 2,86 (± 0,08) | 0,44 | 1,13 | 1,72 | 10,1 | 9,9 | 56 |
| Go, `powersave` (30/10) | **2,49** (± 0,04) | 0,22 | **0,79** | 1,70 | 11,0 | 10,6 | 57 |

Fichiers : [`sans_app_powersave.md`](resultats/sans_app_powersave.md),
[`go_powersave.md`](resultats/go_powersave.md) et les CSV.

Une première série, lancée le même jour avec une session Claude Code ouverte, donnait
2,59 W et 2,78 W : tous les rails hors cœur y étaient plus hauts de ~0,25 W, y compris
sans application. Elle a été écartée et remplacée par celle-ci.

**Comparabilité.** Les deux gouverneurs ont été mesurés à des jours différents, mais
le Pi sans application consomme la même chose (2,36 et 2,34 W, écart inférieur à
l'intervalle de confiance) et les rails hors cœur sont identiques à 0,02 W près.
La comparaison est donc fiable.

**Résultats :**

- **Total avec Go : 2,86 → 2,49 W (−0,37 W, −13 %)**, au-delà de la prévision du
  § 4.5 (−0,27 W).
- **Surcoût de l'application Go : 0,50 → 0,15 W (−69 %)**, soit 3,7 Wh/j et
  1,3 kWh/an au lieu de 12 Wh/j et 4,4 kWh/an.
- Tout le gain est sur le cœur CPU (1,13 → 0,79 W, −0,35 W). Le surcoût de Go sur ce
  rail passe de 0,33 W à **0,03 W** : à fréquence fixe, l'application ne coûte
  presque plus rien au processeur.
- Sans application, `powersave` ne change presque rien (−0,02 W) : le Pi à vide
  passait déjà 82 % du temps à 1,5 GHz.
- Le CPU de l'application monte un peu (10,1 → 11,0 % d'un cœur) car chaque image
  prend plus de temps à 1,5 GHz. Il reste une large marge.
- Les variations de puissance sont divisées par deux (σ 0,22 W au lieu de 0,44 W).

**Où passe le surcoût restant ?** Grâce à l'enregistrement par rail (même série) :

| Rail | Sans app (W) | Go (W) | Écart (W) |
|---|---|---|---|
| `VDD_CORE` (cœur CPU) | 0,762 | 0,788 | +0,026 |
| `3V3_SYS` | 0,250 | 0,369 | **+0,119** |
| `DDR_VDD2` | 0,045 | 0,051 | +0,006 |
| Autres (`0V8_SW`, `1V1_SYS`, `1V8_SYS`, `3V7_WL_SW`) | 1,190 | 1,191 | ≈ 0 |

**Près de 80 % du surcoût restant est sur le rail 3,3 V**, qui alimente l'écran
et son rétroéclairage (l'écran est branché sur la broche 3,3 V du connecteur GPIO).
Le prochain levier n'est donc plus le CPU, mais l'**afficheur** : luminosité du
rétroéclairage, mise en veille de l'écran quand aucun bus n'est proche (A1). Ces
pistes sortent du périmètre de l'étude (accès réseau) et ne sont pas mesurées ici.

Point à vérifier à l'œil : l'animation reste-t-elle fluide à 1,5 GHz ?

---

## 5. Stratégies d'optimisation à tester

| # | Stratégie | Hypothèse | Mesure prévue | État |
|---|---|---|---|---|
| R1 | Fréquence de polling (30 s, 80 s, 2 min, 5 min, adaptative selon l'heure du prochain bus) | coût ∝ nombre de requêtes | requêtes/jour, P moyenne | estimé (§ 4.6) : < 0,3 % du surcoût de l'app |
| R2 | Réutilisation de connexion (keep-alive long, HTTP/2, reprise de session TLS) | −90 % CPU, −50 % octets par requête | banc `reseau` + test `-pause 80s` | **fait** : la version Go réutilise déjà une seule connexion (`ss`, 1 253 o par rafraîchissement) ; correctif défensif dans `api.go` pour les réponses en erreur (§ 4.3) |
| R3 | Compression (gzip, brotli si supporté) | moins d'octets, CPU négligeable | banc `reseau` | en partie fait |
| R4 | Cache local : ne pas interroger si le prochain bus est connu et lointain | moins de requêtes | requêtes/jour | à faire |
| R5 | Requêtes conditionnelles (`ETag`, `If-Modified-Since`) | réponses 304 sans corps | vérifier le support serveur | **abandonné** : ni `ETag` ni `Last-Modified`, `Cache-Control: no-store` (§ 4.3) |
| R6 | Filtrage des données demandées (paramètres de l'API : ligne, direction…) | réponses plus petites | taille de réponse | **abandonné** : `LineRef` accepté, mais une seule ligne dessert l'arrêt, réponse identique (2 392 o, § 4.3) |
| R7 | Regroupement des requêtes (radio réveillée moins souvent) | moins d'énergie de queue | P du rail Wi-Fi | à faire |
| A1 | Affichage : fréquence d'images réduite, zones modifiées seules, rétroéclairage moins fort ou éteint quand aucun bus n'est proche | gros gain CPU ; en `powersave`, ~80 % du surcoût restant est sur le rail 3,3 V (§ 4.7) | P moyenne, P `3V3_SYS` | **hors périmètre**, non mesuré : poste majoritaire, l'écran est alimenté par le rail 3,3 V (§ 4.7) |
| S1 | Système : gouverneur `powersave`, retirer l'overclock, désactiver l'interface graphique, Ethernet vs Wi-Fi | gain de base ; jusqu'à −0,27 W sur Go par la seule fréquence (§ 4.5) | P sans app et P Go | **`powersave` fait** : −0,37 W sur le total avec Go, surcoût de l'app 0,50 → 0,15 W (§ 4.7). Reste : fluidité à vérifier, réglage à rendre permanent ; overclock, interface graphique, Ethernet non testés |

---

## 6. Recommandations

> S1, R2, R5 et R6 sont mesurés. R5 et R6 sont abandonnés (non supporté par le serveur, sans gain à cet arrêt).

Par ordre de gain attendu :

1. **Optimiser le code qui tourne en continu avant le réseau.** Le passage de
   Python à Go a fait gagner 0,76 W (−60 % du surcoût). Toutes les stratégies réseau
   réunies portent sur moins de 0,3 % du surcoût restant.
2. **Ne pas laisser le gouverneur monter en fréquence pour une charge légère**
   (S1) : sur ce Pi overclocké, la fréquence explique l'essentiel de l'écart entre
   versions (§ 4.5). Bloquer le CPU à 1,5 GHz (gouverneur `powersave`) retire
   **0,37 W** avec l'application Go et ramène son surcoût de 0,50 à **0,15 W**
   (−69 %, § 4.7), sans rien changer au code.
3. **Ensuite, s'attaquer à l'afficheur** (A1, hors périmètre, non mesuré) : une
   fois le CPU stabilisé, ~80 % du surcoût restant est sur le rail 3,3 V, qui
   alimente l'écran et son rétroéclairage.
4. **Côté API, réduire le coût par requête plutôt que leur nombre :**
   - **garder une seule connexion ouverte** (un seul client HTTP réutilisé) et
     **lire entièrement le corps des réponses**, y compris en cas d'erreur : le
     serveur la garde ouverte au moins 80 s. C'est déjà le cas de la version Go ;
   - garder un seul client HTTP et activer la **reprise de session TLS**
     (`tls.Config{ClientSessionCache: …}` en Go) : −62 % de CPU même quand la
     connexion a été fermée ;
   - activer **HTTP/2** quand le serveur le propose : en-têtes compressés, −45 %
     d'octets reçus avec les vraies réponses (déjà le cas de la version Go) ;
   - garder **gzip** (déjà le cas par défaut en Go).
5. **Adapter la fréquence de polling** à la fraîcheur réelle des données (le serveur
   les met en cache ~10 s, `age: 10`) et à l'heure du prochain bus : gain faible en
   énergie, mais net en volume de données.

---

## 7. Journal des mesures

| Date | Mesure | Conditions | Fichier |
|---|---|---|---|
| 28/10/2026 | Go en service, 120 s | session interactive ouverte | — (préliminaire) |
| 28/10/2026 | Coût CPU par image, Python et Go | banc hors matériel | [`python_rendu.txt`](resultats/python_rendu.txt) |
| 28/10/2026 | Coût d'une requête API, 4 stratégies | Wi-Fi, 30 requêtes chacune | [`reseau.txt`](resultats/reseau.txt) |
| 29/10/2026 | Sans app / Go / Python `20f914e` sur le matériel, 120 s chacun | `sudo ./etude/mesurer.sh`, sans session interactive | [`sans_app`](resultats/sans_app.md), [`go`](resultats/go.md), [`python_20f914e`](resultats/python_20f914e.md) |
| 30/10/2026 | Analyse puissance / fréquence | à partir des CSV du 29/10 | § 4.5 |
| 30/10/2026 | Banc réseau : reprise TLS, HTTP/2 | sans clé API (réponses 401), Wi-Fi, 30 requêtes | [`reseau_sans_cle.txt`](resultats/reseau_sans_cle.txt) |
| 30/10/2026 | Estimation R1 (fréquence de polling) | calcul à partir du § 4.3 et du § 4.1 | § 4.6 |
| 30/10/2026 | Survie de la connexion à 10 s, 30 s, 80 s d'inactivité | sans clé API, HTTP/1.1 et HTTP/2 | [`reseau_pause.txt`](resultats/reseau_pause.txt) |
| 30/10/2026 | Connexion du service Go vers PRIM, avant et après correctif `api.go` | `ss -tni` toutes les 10 s, ~3 min chacun | [`ss_service_go.txt`](resultats/ss_service_go.txt) |
| 30/10/2026 | S1 : `sans_app_powersave`, `go_powersave`, 120 s chacun (1re série) | session Claude Code ouverte ; écartée (rails hors cœur +0,25 W), fichiers écrasés par la 2e série | — |
| 30/10/2026 | S1 : `sans_app_powersave`, `go_powersave`, 120 s chacun (2e série, ~15 h) | `sudo ./etude/mesurer.sh sans_app_powersave go_powersave`, sans session interactive | [`sans_app_powersave`](resultats/sans_app_powersave.md), [`go_powersave`](resultats/go_powersave.md) |
| 30/10/2026 | Outil `mesure` : ajout de la puissance par rail dans le CSV et la synthèse | — | [`mesure/main.go`](mesure/main.go) |
| *facultatif* | S1 : les quatre scénarios dans une seule série (contrôle) | `sudo SUFFIXE=_serie2 ./etude/mesurer.sh sans_app sans_app_powersave go go_powersave` | `resultats/*_serie2.*` |
| 30/10/2026 | Banc réseau complet avec clé (R5, R6) | `PRIM_API_KEY=… go run ./etude/reseau`, Wi-Fi, 30 requêtes | [`reseau_avec_cle.txt`](resultats/reseau_avec_cle.txt) |
