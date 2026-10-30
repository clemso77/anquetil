#!/bin/bash
# Mesure la consommation de plusieurs scénarios, l'un après l'autre.
#
#   sudo ./etude/mesurer.sh                  # tous les scénarios
#   sudo ./etude/mesurer.sh sans_app go      # seulement certains
#   sudo SUFFIXE=_serie2 ./etude/mesurer.sh  # résultats dans sans_app_serie2.csv, etc. (n'écrase rien)
#
# Scénarios : sans_app, go, python_20f914e (ancienne version en service).
# Suffixe _powersave (ex. go_powersave) : CPU bloqué à sa fréquence minimale (S1).
# Le service anquetil et le gouverneur CPU sont toujours rétablis à la fin, même en cas d'erreur.
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "Lancer avec sudo"; exit 1; }
DUREE=${DUREE:-120}     # secondes mesurées par scénario
CHAUFFE=${CHAUFFE:-20}  # secondes d'attente avant de mesurer
SUFFIXE=${SUFFIXE:-}    # ajouté au nom des fichiers de résultats
UTIL=${SUDO_USER:-clement}
REPO=$(cd "$(dirname "$0")/.." && pwd)
RES=$REPO/etude/resultats
TMP=$(mktemp -d)
chown "$UTIL:" "$TMP"   # le build tourne en $UTIL
SCENARIOS=${*:-sans_app go python_20f914e}
APP_PID=""
GOUV=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)

gouverneur() { for f in /sys/devices/system/cpu/cpufreq/policy*/scaling_governor; do echo "$1" > "$f"; done; }

fin() {
    gouverneur "$GOUV"
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
    if [[ $sc == *_powersave ]]; then gouverneur powersave; else gouverneur "$GOUV"; fi
    case ${sc%_powersave} in
        sans_app) ;;
        go)
            systemctl start anquetil
            APP_PID=$(systemctl show -p MainPID --value anquetil) ;;
        python_*)
            base=${sc%_powersave}; commit=${base#python_}
            mkdir -p "$TMP/$sc"
            sudo -u "$UTIL" git -C "$REPO" archive "$commit" | tar -x -C "$TMP/$sc"
            (cd "$TMP/$sc" && exec python3 main.py > "$TMP/$sc.log" 2>&1) &
            APP_PID=$! ;;
        *) echo "Scénario inconnu : $sc"; continue ;;
    esac
    sleep "$CHAUFFE"
    "$TMP/mesure" -pid "${APP_PID:-0}" -duree "$DUREE" -nom "$sc$SUFFIXE" -csv "$RES/$sc$SUFFIXE.csv" | tee "$RES/$sc$SUFFIXE.md"
    if [[ $sc == python_* ]]; then
        kill -INT "$APP_PID"; wait "$APP_PID" || true
        APP_PID=""
    fi
done
