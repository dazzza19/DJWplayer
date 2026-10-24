# DJW NAS USB installer

This is a bootable Debian 13 amd64 installer customized for the DJW main unit. Write the ISO to a USB stick, boot the old PC from it, and it installs the operating system and DJW setup as one operation. There is no separate Debian install step.

## What happens

1. The installer identifies the one non-removable, non-USB internal disk and installs Debian onto it. It stops if it finds zero or multiple candidate internal disks.
2. On the first boot, a setup wizard asks for the admin and Samba passwords, Wi-Fi credentials if the PC is offline, and optional ProtonVPN and Soulseek credentials.
3. It installs and starts DJW, Samba, Jellyfin/Jellyseerr, Radarr, Sonarr, Lidarr, Prowlarr, Transmission, slskd and CD/DVD tools. The PC then starts the DJW screen full-screen.

**The selected internal HDD is erased.** Disconnect any internal disk you want to keep. USB storage and other Samba shares can be added after setup. Keep the PC connected to the internet during setup so it can fetch Debian packages and service containers.

The installer includes WPA2-capable NetworkManager and common Wi-Fi firmware. Wi-Fi adapter support depends on the old PC's chipset; if it is unsupported, use Ethernet or a supported USB Wi-Fi adapter during setup.

## Use

- Write the ISO to USB with Rufus, balenaEtcher, or an equivalent image writer. Boot from it and let the automatic install complete.
- TV: in DJW Server Edition, choose **Connect to Windows / Debian server**, enter `https://<PC-IP>:8787`, and enter the PIN shown by `sudo djw-status` on the PC. The supplied server uses a self-signed local certificate, so the TV app may display a certificate warning. The APK pairing handshake has not been tested against physical TV hardware.
- Samba: `\\<PC-IP>\DJW-Media`, username `djwfiles`.
- Jellyfin: `http://<PC-IP>:8096`.
- Transmission and slskd only start after Proton WireGuard is configured; the setup wizard can do that or it can be configured later with `sudo djw-set-vpn`.
- Add a mounted USB library folder using `sudo djw-add-local` or an existing Samba share using `sudo djw-add-smb`.

The local DJW screen is a purpose-built browser player and library view. Jellyfin provides the media server backend. The Android TV APK connection and control compatibility remain unverified because no physical TV receiver was available here.

## Storage and services

- One internal HDD: OS, `/srv/djw/media`, `/srv/djw/downloads`, and `/var/lib/djw/appdata`.
- USB disks: mount with the desktop file manager, then use `djw-add-local` to expose a folder in DJW.
- Remote SMB: `djw-add-smb` saves the credentials root-only and mounts SMB2/SMB3 read-only by default.
- Optical discs: `whipper` supports audio CD ripping; `handbrake-cli` is included for DVD/video conversion. DVD CSS support may require a separately obtained libdvdcss package.
- Download containers are routed through Gluetun/ProtonVPN and remain stopped until the VPN key is configured.
