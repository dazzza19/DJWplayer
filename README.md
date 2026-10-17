# DJW Player

An Android player for music, films and TV, with device libraries, Samba sources
and Soulseek transfers. Early test builds for Android 8+ on arm64 devices.

## Download

Open [**Releases**](https://github.com/dazzza19/DJWplayer/releases/latest) on this repository, select the latest published release and
download its `.apk` attachment. GitHub's automatic “Source code” ZIP is not an
Android installer. Android asks you to approve installation.

When upgrading, install over the existing app to keep its settings and library.
Only install releases you trust from this repository.

## Updates

Each published latest release has an APK and an `update.json` describing that
exact build. The download page follows the latest published release.

The initial 0.3.5 Android build does not yet contain the GitHub update checker;
it will be added after the repository address is configured in a new build.

## Download page

Optional: enable GitHub Pages from the repository's default branch and root
folder. The included `index.html` is configured for dazzza19/DJWplayer and also works
on Netlify without editing. It only uses GitHub's public release API; no token is needed.

This repository is the download-hosting pack. It does not contain the full
Android application source or signing keys. Application source and notices can
be distributed separately, with private signing material removed.
