#!/bin/sh
# Installs a board's firmware and network settings over USB, from the server
# that served this script, then follows the board's log as the install page
# does. The server filled in the values below; SERVER, PORT and ESPTOOL
# override them.

# values
SERVER_HERE=__SERVER__
SETTINGS_PATH=__SETTINGS_PATH__
NETWORK_PATH=__NETWORK_PATH__
WIFI_SSID=__WIFI_SSID__
BOARD_SERVER_URL=__BOARD_SERVER_URL__
MQTT_HOST=__MQTT_HOST__
BOARDS=__BOARDS__
# end of values

SERVER=${SERVER:-$SERVER_HERE}
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/epd
LOG=$CACHE/install-firmware.log

ESPTOOL_VERSION=5.4.0
BAUD_RATE=460800
LOG_BAUD_RATE=115200
STORE_OFFSET=0x9000
# A board logs at once when it starts. Joining Wi-Fi may take a retry 30 s
# after a first try; the server and the broker answer soon after that.
QUIET_LIMIT_S=10
WIFI_LIMIT_S=60
SERVER_LIMIT_S=60
MQTT_LIMIT_S=30

say() { printf '%s\n' "$*"; }
fail() { printf '%s\n' "$*" >&2; exit 1; }

usage() {
    first=$(say "$BOARDS" | head -n 1 | cut -d'|' -f1)
    say "Install firmware on a board connected by USB."
    say "  sh install-firmware.sh $first            (firmware and network settings)"
    say "  sh install-firmware.sh $first-network    (network settings only)"
    say "Boards: $(say "$BOARDS" | cut -d'|' -f1 | paste -sd, - | sed 's/,/, /g')"
    exit 1
}

# The board whose word is $1: sets PRODUCT, CHIP, NAME and VENDOR_IDS.
find_board() {
    line=$(say "$BOARDS" | awk -F'|' -v word="$1" '$1 == word')
    [ -n "$line" ] || return 1
    PRODUCT=$(say "$line" | cut -d'|' -f2)
    CHIP=$(say "$line" | cut -d'|' -f3)
    NAME=$(say "$line" | cut -d'|' -f4)
    VENDOR_IDS=$(say "$line" | cut -d'|' -f5 | tr ',' ' ')
}

sha256() {
    if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
    else sha256sum "$1" | cut -d' ' -f1; fi
}

# The path of an esptool to run: ESPTOOL, or Espressif's standalone build for
# this system, downloaded once and checked against its published checksum.
esptool_path() {
    if [ -n "${ESPTOOL:-}" ]; then say "$ESPTOOL"; return; fi
    exe=esptool
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) asset=macos-arm64 mb=63
            sum=ba332671130939e2e6db90c2784488f7e62a1459b0fe3c5ec66e9a366821de7a ;;
        Darwin-x86_64) asset=macos-amd64 mb=66
            sum=910bb64fe39a84c792752701293c8aa294faeef229fe8705ecd6955b01db3778 ;;
        Linux-x86_64) asset=linux-amd64 mb=86
            sum=61648fbae20735cabb342f2fbe8fc89b3046e1ed6f9c3e09528d837dc9a9b152 ;;
        Linux-aarch64|Linux-arm64) asset=linux-aarch64 mb=78
            sum=2964fff085071c1403f2cf812a7a1d425f987f9992851a60236bbee17b6e7dcc ;;
        Linux-armv7l) asset=linux-armv7 mb=70
            sum=ee542ac6b60aee2604289ee418fccd0ff6eead6f702b51bbe4f0e483477e31d9 ;;
        MINGW*-x86_64|MSYS*-x86_64|CYGWIN*-x86_64) asset=windows-amd64 mb=66 exe=esptool.exe
            sum=b7f6b9dd301a210b31f4829118c909c84aae23107f9ca1fdc14ccf4d7384be2e ;;
        *) fail "No compatible esptool. Install esptool and set ESPTOOL to its path, then try again." ;;
    esac
    dir=$CACHE/esptool-v$ESPTOOL_VERSION
    path=$dir/esptool-$asset/$exe
    if [ -x "$path" ]; then say "$path"; return; fi

    case $asset in windows-*) ext=zip ;; *) ext=tar.gz ;; esac
    file=$dir/esptool-v$ESPTOOL_VERSION-$asset.$ext
    url=https://github.com/espressif/esptool/releases/download/v$ESPTOOL_VERSION/esptool-v$ESPTOOL_VERSION-$asset.$ext
    mkdir -p "$dir"
    say "Downloading esptool ($mb MB). This happens once." >&2
    curl -fsSL --retry 2 -o "$file" "$url" ||
        fail "esptool download failed. Check the internet connection, then try again."
    if [ "$(sha256 "$file")" != "$sum" ]; then
        rm -f "$file"
        fail "esptool download damaged. Try again."
    fi
    case $ext in
        zip) (cd "$dir" && { unzip -qo "$file" || tar -xf "$file"; }) ;;
        *) tar -xzf "$file" -C "$dir" ;;
    esac
    rm -f "$file"
    say "$path"
}

# Downloads $1 from the server into $2, and prints the HTTP status: 000 when
# the server did not answer.
fetch() {
    insecure=
    case $SERVER in https://*) insecure=-k ;; esac
    curl -sS $insecure -o "$2" -w '%{http_code}' "$SERVER/$1" 2>/dev/null || true
}

# Where a person sets the network settings: the project's install page when
# it holds them, else Settings. The link carries the address when there is one.
network_place() {
    if [ -n "$NETWORK_PATH" ]; then printf 'on the install page'
    else printf 'in Settings'; fi
}

network_link() {
    if [ -n "$NETWORK_PATH" ]; then printf 'on the install page: %s/%s' "$SERVER" "$NETWORK_PATH"
    elif [ -n "$SETTINGS_PATH" ]; then printf 'in Settings: %s/%s' "$SERVER" "$SETTINGS_PATH"
    else printf 'in Settings.'; fi
}

# The Settings names of the keys a 409 from the server names.
missing_fields() {
    grep -oE 'client\.[a-z_.]*[a-z_]' "$1" | while read -r key; do
        case $key in
            client.server_url) say "Server address" ;;
            client.wifi.ssid) say "Wi-Fi name" ;;
            client.wifi.password) say "Wi-Fi password" ;;
            client.mqtt_host) say "MQTT broker" ;;
            *) say "$key" ;;
        esac
    done | paste -sd, - | sed 's/,/, /g'
}

download_files() {
    unreachable="Cannot reach the server at $SERVER. Check that it is running, then try again."
    if [ "$WITH_FIRMWARE" = yes ]; then
        code=$(fetch "firmware.merged.bin?product=$PRODUCT" "$CACHE/firmware.bin")
        case $code in
            200) ;;
            404) fail "No firmware to install for the $NAME yet. It appears once the server has built it." ;;
            *) fail "$unreachable" ;;
        esac
    fi
    code=$(fetch "network.bin?product=$PRODUCT" "$CACHE/network.bin")
    case $code in
        200) ;;
        409) fail "Missing: $(missing_fields "$CACHE/network.bin"). Add them $(network_link)" ;;
        *) fail "$unreachable" ;;
    esac
}

run_esptool() {
    if [ -n "${PORT:-}" ]; then
        "$ESPTOOL_BIN" --chip "$CHIP" --port "$PORT" --baud "$BAUD_RATE" "$@" >>"$LOG" 2>&1
    else
        filters=
        for id in $VENDOR_IDS; do filters="$filters --port-filter vid=$id"; done
        # $filters is unquoted on purpose: it holds several words, none with a space.
        "$ESPTOOL_BIN" --chip "$CHIP" $filters --baud "$BAUD_RATE" "$@" >>"$LOG" 2>&1
    fi
}

explain_esptool_failure() {
    if grep -q "Found 0 serial ports" "$LOG"; then
        fail "No board found. Connect it with a USB cable, then try again."
    elif grep -q "This chip is" "$LOG"; then
        fail "Wrong board: this one is not the $NAME. Connect the $NAME, then try again."
    elif grep -q "the port is busy" "$LOG"; then
        fail "Board in use by another app. Close that app, then try again."
    elif grep -qE "No serial data received|Failed to connect" "$LOG"; then
        fail "Board not responding. Hold BOOT while you press RST, then try again."
    fi
    fail "Install failed. Reconnect the board, then try again.
Log: $(say "$LOG" | sed "s|^$HOME|~|")"
}

write_board() {
    if [ -n "${PORT:-}" ] && [ ! -e "$PORT" ]; then
        fail "No board found. Connect it with a USB cable, then try again."
    fi
    say "Installing on the ${NAME}… Keep the board connected."
    # The merged image fills the settings store's place with blank bytes, so
    # the network settings go after it. esptool refuses files that overlap.
    if [ "$WITH_FIRMWARE" = yes ]; then
        run_esptool write-flash 0x0 "$CACHE/firmware.bin" || explain_esptool_failure
    fi
    run_esptool write-flash "$STORE_OFFSET" "$CACHE/network.bin" || explain_esptool_failure
}

# The port esptool wrote through, as this shell names it.
board_port() {
    if [ -n "${PORT:-}" ]; then say "$PORT"; return; fi
    port=$(sed -n 's/^Serial port \(.*\):$/\1/p' "$LOG" | tail -n 1)
    case $port in
        COM[0-9]*) say "/dev/ttyS$((${port#COM} - 1))" ;;
        *) say "$port" ;;
    esac
}

start_reader() {
    if [ "$(uname -s)" = Darwin ]; then stty -f "$1" "$LOG_BAUD_RATE" raw -echo 2>/dev/null
    else stty -F "$1" "$LOG_BAUD_RATE" raw -echo 2>/dev/null; fi
    cat "$1" >>"$BOARD_LOG" 2>/dev/null &
    READER=$!
}

passed() { grep -q "$1" "$BOARD_LOG" 2>/dev/null; }

# Follows the board's log after its restart, and says how its start went.
check_start() {
    port=$(board_port)
    BOARD_LOG=$CACHE/board.log
    : >"$BOARD_LOG"
    start=$(date +%s)
    heard= wifi= server= mqtt= READER=
    [ -n "$MQTT_HOST" ] || mqtt=-
    while :; do
        now=$(date +%s)
        if [ -z "$READER" ] || ! kill -0 "$READER" 2>/dev/null; then
            [ -e "$port" ] && start_reader "$port"
        fi
        if [ -z "$wifi" ] && passed "wifi connected in"; then wifi=$now; say "✓ Joined Wi-Fi"; fi
        if [ -z "$server" ] && passed "reached the server at"; then server=$now; say "✓ Reached the server"; fi
        if [ -z "$mqtt" ] && passed "connected to MQTT broker"; then mqtt=$now; say "✓ Connected to MQTT"; fi
        [ -z "$heard" ] && [ -s "$BOARD_LOG" ] && heard=$now
        [ -n "$wifi" ] && [ -n "$server" ] && [ -n "$mqtt" ] && break
        if [ -z "$heard" ]; then
            [ $((now - start)) -ge "$QUIET_LIMIT_S" ] && break
        elif [ -z "$wifi" ]; then
            [ $((now - heard)) -ge "$WIFI_LIMIT_S" ] && break
        elif { [ -n "$server" ] || [ $((now - wifi)) -ge "$SERVER_LIMIT_S" ]; } &&
             { [ -n "$mqtt" ] || [ $((now - wifi)) -ge "$MQTT_LIMIT_S" ]; }; then
            break
        fi
        sleep 1
    done
    [ -n "$READER" ] && kill "$READER" 2>/dev/null

    if [ -z "$heard" ]; then
        fail "Installed, but received no data from the board. Reconnect it, then try again."
    elif [ -z "$wifi" ]; then
        fail "Cannot join Wi-Fi \"$WIFI_SSID\". Check the Wi-Fi name and password $(network_place), then try again."
    elif [ -z "$server" ]; then
        fail "Board cannot reach the server at $BOARD_SERVER_URL. Check the server address $(network_place), then try again."
    elif [ -z "$mqtt" ]; then
        fail "Cannot connect to MQTT at $MQTT_HOST. Check the MQTT broker $(network_place)."
    fi
    say "Installed. You can unplug the board."
}

[ $# -eq 1 ] || usage
case $1 in
    *-network) WITH_FIRMWARE=no; find_board "${1%-network}" || usage ;;
    *) WITH_FIRMWARE=yes; find_board "$1" || usage ;;
esac

mkdir -p "$CACHE"
: >"$LOG"
ESPTOOL_BIN=$(esptool_path) || exit 1
download_files
write_board
say "Restarting the board…"
check_start
