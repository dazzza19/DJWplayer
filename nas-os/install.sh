#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run by the DJW first-boot service as root.' >&2; exit 1; }
. /etc/os-release
[[ "$ID" == debian && "$VERSION_ID" == 13 ]] || { echo "DJW image requires Debian 13; found $PRETTY_NAME" >&2; exit 1; }
[[ "$(dpkg --print-architecture)" == amd64 ]] || { echo 'This image is for 64-bit Intel/AMD PCs.' >&2; exit 1; }

echo
echo 'DJW NAS first-boot setup'
echo 'The internal drive is already installed. No disks will be formatted now.'
echo
read -r -s -p 'Choose the DJW admin password (12+ characters): ' ADMIN_PASSWORD; echo
if [ "$(printf %s "$ADMIN_PASSWORD" | wc -c)" -lt 12 ]; then echo 'Password must be at least 12 characters.' >&2; exit 1; fi
read -r -s -p 'Choose the Samba password for djwfiles (12+ characters): ' SMB_PASSWORD; echo
if [ "$(printf %s "$SMB_PASSWORD" | wc -c)" -lt 12 ]; then echo 'Password must be at least 12 characters.' >&2; exit 1; fi

systemctl enable --now NetworkManager.service || true

if command -v nmcli >/dev/null && ! nmcli -t -f STATE general 2>/dev/null | grep -q connected; then
  read -r -p 'Wi-Fi network name (SSID): ' WIFI_SSID
  read -r -s -p 'Wi-Fi WPA2 password: ' WIFI_PASSWORD; echo
  nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASSWORD" || { echo 'Wi-Fi connection failed; check the SSID, password, and adapter.' >&2; exit 1; }
  unset WIFI_PASSWORD
fi

echo 'Installing media services. Internet access is needed to download packages and containers.'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends samba cifs-utils docker.io docker-compose openssl python3 ca-certificates avahi-daemon openssh-server sudo curl network-manager network-manager-gnome wpasupplicant wireless-tools rfkill firmware-iwlwifi firmware-realtek firmware-atheros firmware-brcm80211 firmware-misc-nonfree xfce4 lightdm xserver-xorg chromium whipper handbrake-cli eject udisks2

systemctl enable --now docker.service
systemctl enable --now smbd.service
systemctl enable --now avahi-daemon.service || true

if ! getent group djwshare >/dev/null; then groupadd --gid 1000 djwshare 2>/dev/null || groupadd djwshare; fi
if ! id djwserver >/dev/null 2>&1; then useradd --system --home /var/lib/djw --no-create-home --shell /usr/sbin/nologin --gid djwshare djwserver; fi
if ! id djwfiles >/dev/null 2>&1; then useradd --uid 1000 --home /nonexistent --no-create-home --shell /usr/sbin/nologin --gid djwshare djwfiles; fi
install -d -m 0755 /opt/djw-nas/app /opt/djw-nas/compose
install -d -m 0750 -o djwserver -g djwshare /var/lib/djw
install -d -m 2770 -o root -g djwshare /srv/djw/media/music /srv/djw/media/films /srv/djw/media/tv /srv/djw/downloads/incomplete /srv/djw/downloads/complete
install -d -m 0770 -o root -g djwshare /var/lib/djw/appdata
install -d -m 0700 /etc/djw-nas /etc/djw-nas/smb-creds
install -d -m 0755 /mnt/djw/shares /var/cache/djw-jellyfin

install -m 0644 /opt/djw-nas-installer/app/server.py /opt/djw-nas/app/
install -m 0644 /opt/djw-nas-installer/app/kiosk.html /opt/djw-nas/app/
install -m 0644 /opt/djw-nas-installer/compose/media.yml /opt/djw-nas/compose/
install -m 0644 /opt/djw-nas-installer/compose/downloads.yml /opt/djw-nas/compose/
install -m 0755 /opt/djw-nas-installer/tools/djw-status /opt/djw-nas-installer/tools/djw-add-local /opt/djw-nas-installer/tools/djw-add-smb /opt/djw-nas-installer/tools/djw-set-vpn /opt/djw-nas-installer/tools/djw-downloads /opt/djw-nas-installer/tools/djw-compose /usr/local/sbin/
install -m 0644 /opt/djw-nas-installer/systemd/djw-server.service /etc/systemd/system/
install -m 0644 /opt/djw-nas-installer/systemd/djw-media-stack.service /etc/systemd/system/

ADMIN_PASSWORD="$ADMIN_PASSWORD" python3 - <<'PY'
import hashlib,json,os,pathlib,secrets
salt=secrets.token_bytes(16)
digest=hashlib.pbkdf2_hmac('sha256',os.environ['ADMIN_PASSWORD'].encode(),salt,260000).hex()
config={'version':1,'admin_password_hash':salt.hex()+':'+digest,'tv_pin':f'{secrets.randbelow(100000):05}',
        'tokens_file':'/var/lib/djw/tv-tokens.json','tls_cert':'/etc/djw-nas/tls.crt','tls_key':'/etc/djw-nas/tls.key',
        'sources':[{'id':'main-music','name':'DJW Music','kind':'Music','path':'/srv/djw/media/music'},
                   {'id':'main-films','name':'DJW Films','kind':'Film','path':'/srv/djw/media/films'},
                   {'id':'main-tv','name':'DJW TV','kind':'TV','path':'/srv/djw/media/tv'}]}
p=pathlib.Path('/etc/djw-nas/server.json');p.write_text(json.dumps(config,indent=2)+'\n');os.chmod(p,0o640)
PY
printf 'root:%s\n' "$ADMIN_PASSWORD" | chpasswd
chown root:djwshare /etc/djw-nas/server.json

HOST="$(hostname -s | tr -cd '[:alnum:].-')"
if [ -z "$HOST" ]; then HOST=djw-main; fi
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 -subj "/CN=$HOST.local" -addext "subjectAltName=DNS:$HOST.local,DNS:localhost,IP:127.0.0.1" -keyout /etc/djw-nas/tls.key -out /etc/djw-nas/tls.crt >/dev/null 2>&1
chown root:djwshare /etc/djw-nas/tls.key /etc/djw-nas/tls.crt
chmod 0640 /etc/djw-nas/tls.key
chmod 0644 /etc/djw-nas/tls.crt
install -m 0644 /etc/djw-nas/tls.crt /usr/local/share/ca-certificates/djw-nas.crt
update-ca-certificates >/dev/null

if ! grep -qF '# DJW NAS shares' /etc/samba/smb.conf; then
cat >> /etc/samba/smb.conf <<'EOF'

# DJW NAS shares
[DJW-Media]
  path = /srv/djw/media
  browseable = yes
  guest ok = no
  read only = no
  valid users = djwfiles
  force group = djwshare
  create mask = 0660
  directory mask = 2770
[DJW-Downloads]
  path = /srv/djw/downloads/complete
  browseable = yes
  guest ok = no
  read only = yes
  valid users = djwfiles
  force group = djwshare
  create mask = 0660
  directory mask = 2770
EOF
fi
if ! grep -qE '^[[:space:]]*server min protocol[[:space:]]*=' /etc/samba/smb.conf; then sed -i '/^\[global\]/a\   server min protocol = SMB2_02' /etc/samba/smb.conf; fi
testparm -s >/dev/null
printf '%s\n%s\n' "$SMB_PASSWORD" "$SMB_PASSWORD" | smbpasswd -s -a djwfiles >/dev/null

TRANSMISSION_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
SLSKD_WEB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
read -r -s -p 'ProtonVPN WireGuard private key (blank to configure later): ' PROTON_KEY; echo
read -r -p 'ProtonVPN country [United Kingdom]: ' PROTON_COUNTRY
if [ -z "$PROTON_COUNTRY" ]; then PROTON_COUNTRY='United Kingdom'; fi
read -r -p 'Soulseek username (blank to configure in slskd later): ' SLSK_USER
if [ -n "$SLSK_USER" ]; then read -r -s -p 'Soulseek password: ' SLSK_PASSWORD; echo; else SLSK_PASSWORD=''; fi
cat > /etc/djw-nas/.env <<EOF
PROTON_WIREGUARD_PRIVATE_KEY=$PROTON_KEY
PROTON_COUNTRY='$PROTON_COUNTRY'
TRANSMISSION_USER=djw
TRANSMISSION_PASSWORD=$TRANSMISSION_PASSWORD
SLSKD_WEB_USER=djw
SLSKD_WEB_PASSWORD=$SLSKD_WEB_PASSWORD
SLSKD_SLSK_USERNAME='$SLSK_USER'
SLSKD_SLSK_PASSWORD='$SLSK_PASSWORD'
EOF
chmod 0600 /etc/djw-nas/.env

for g in audio video render; do getent group "$g" >/dev/null || groupadd "$g"; done
if ! id djw-kiosk >/dev/null 2>&1; then useradd --uid 1001 --create-home --shell /bin/bash --groups audio,video,render,djwshare djw-kiosk; fi
mkdir -p /etc/lightdm/lightdm.conf.d /etc/xdg/autostart
cat > /etc/lightdm/lightdm.conf.d/60-djw-kiosk.conf <<'EOF'
[Seat:*]
autologin-user=djw-kiosk
autologin-user-timeout=0
user-session=xfce
EOF
printf '%s\n' '/usr/sbin/lightdm' > /etc/X11/default-display-manager
cat > /etc/xdg/autostart/djw-kiosk.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=DJW Player
Exec=chromium --kiosk --app=https://127.0.0.1:8787/kiosk --no-first-run --disable-session-crashed-bubble
X-GNOME-Autostart-enabled=true
EOF

cat > /root/djw-initial-access.txt <<EOF
DJW admin username: admin
DJW admin password: $ADMIN_PASSWORD
Samba username: djwfiles
Samba password: $SMB_PASSWORD
Transmission username: djw
Transmission password: $TRANSMISSION_PASSWORD
slskd web username: djw
slskd web password: $SLSKD_WEB_PASSWORD
EOF
chmod 0600 /root/djw-initial-access.txt

systemctl daemon-reload
systemctl enable djw-server.service djw-media-stack.service docker.service smbd.service lightdm.service
systemctl enable avahi-daemon.service || true
systemctl start docker.service smbd.service avahi-daemon.service 2>/dev/null || true
systemctl start djw-server.service
systemctl start djw-media-stack.service
if [ -n "$PROTON_KEY" ]; then /usr/local/sbin/djw-downloads start; fi
touch /var/lib/djw/firstboot.done
systemctl disable djw-firstboot.service || true
unset ADMIN_PASSWORD SMB_PASSWORD PROTON_KEY SLSK_PASSWORD
echo
echo 'DJW setup is complete. The PC will open DJW full-screen.'
echo 'TV: enter https://<PC-IP>:8787 and the PIN from sudo djw-status.'
echo 'Initial credentials: sudo cat /root/djw-initial-access.txt'
