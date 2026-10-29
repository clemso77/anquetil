#!/bin/bash
# Mesure la consommation de plusieurs scénarios, l'un après l'autre.
#
#   sudo ./etude/mesurer.sh                  # tous les scénarios
#   sudo ./etude/mesurer.sh sans_app go      # seulement certains
#
# Scénarios : sans_app, go, python_20f914e (ancienne version en service),
#             python_2097333 (dernière version Python sur GitHub).
# Le service anquetil est toujours relancé à la fin, même en cas d'erreur.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Lancer avec sudo"; exit 1; }
DUREE=${DUREE:-120}     # secondes mesurées par scénario
CHAUFFE=${CHAUFFE:-20}  # secondes d'attente avant de mesurer
UTIL=${SUDO_USER:-clement}
REPO=$(cd "$(dirname "$0")/.." && pwd)
RES=$REPO/etude/resultats
TMP=$(mktemp -d)
chown "$UTIL:" "$TMP"   # le build tourne en $UTIL
SCENARIOS=${*:-sans_app go python_20f914e}
APP_PID=""

fin() {
    [ -n "$APP_PID" ] && kill -INT "$APP_PID" 2>/dev/null && wait "$APP_PID" 2>/dev/null || true
    systemctl start anquetil
    chown -R "$UTIL:" "$RES"
    rm -rf "$TMP"
    echo "Service anquetil relancé. Résultats dans $RES"
}
trap fin EXIT

mkdir -p "$RES"
sudo -u "$UTIL" env PATH="$PATH:/home/$UTIL/.local/go/bin" go build -C "$REPO" -o "$TMP/mesure" ./etude/mesure
export "$(systemctl show anquetil -p Environment --value | tr ' ' '\n' | grep PRIM_API_KEY)"

for sc in $SCENARIOS; do
    echo "=== $sc"
    systemctl stop anquetil
    APP_PID=""
    case $sc in
        sans_app) ;;
        go)
            systemctl start anquetil
            APP_PID=$(systemctl show -p MainPID --value anquetil) ;;
        python_*)
            commit=${sc#python_}
            mkdir -p "$TMP/$sc"
            sudo -u "$UTIL" git -C "$REPO" archive "$commit" | tar -x -C "$TMP/$sc"
            (cd "$TMP/$sc" && exec python3 main.py > "$TMP/$sc.log" 2>&1) &
            APP_PID=$! ;;
        *) echo "Scénario inconnu : $sc"; continue ;;
    esac
    sleep "$CHAUFFE"
    "$TMP/mesure" -pid "${APP_PID:-0}" -duree "$DUREE" -nom "$sc" -csv "$RES/$sc.csv" | tee "$RES/$sc.md"
    if [[ $sc == python_* ]]; then
        kill -INT "$APP_PID"; wait "$APP_PID" || true
        APP_PID=""
    fi
done
