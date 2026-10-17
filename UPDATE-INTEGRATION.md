# Contract for the next Android updater build

Hosting is prepared here. The installed 0.3.5 app has no GitHub updater yet.
The user supplied https://github.com/dazzza19/DJWplayer. Configure that public
repository in the next Android updater build. No token or account login belongs in the distributed APK.

1. Fetch https://api.github.com/repos/dazzza19/DJWplayer/releases/latest over HTTPS.
   Handle absent releases, rate limits and offline state. This route excludes
   drafts and prereleases. The upload guide uses normal, clearly labelled test
   releases so the simple latest route can find them.
2. Find the release asset named exactly update.json, download it using the
   asset's browser_download_url and validate the schema below.
3. Compare versionCode to the installed Android package's versionCode. Do not
   decide upgrade order using version-name strings or release dates.
4. Select the APK asset by manifest.apkFilename in the SAME release. Treat
   missing/ambiguous assets, invalid metadata and size mismatches as errors.
5. Show the offered version and notes and let the user choose to download it.
   Keep showing progress; support leaving this screen during download.
6. Download into app-private staging, with a bounded size. Verify byte count
   and SHA-256. Check the downloaded APK's actual package ID and versionCode
   against the manifest and verify that its signing certificate matches the
   installed app's certificate. A certificate stated by remote JSON is not a
   trust anchor. The installed signing certificate is authoritative.
7. Invoke Android's installer using a FileProvider content URI and temporary
   read grant. Handle Android's install-from-this-source permission and return
   to installation after the user grants it. Installation requires user action;
   do not promise silent installation or bypass Play Protect.
8. Future APKs retain applicationId com.harbor.media and the same signing key.
   Increment versionCode on every offered upgrade.

## update.json schema 1

- schemaVersion: integer 1
- packageName: "com.harbor.media"
- versionCode: positive integer, actual Android package versionCode
- versionName: actual Android versionName
- apkFilename: exact APK release asset filename, no path
- sizeBytes: exact positive file size
- sha256: 64 lowercase hex characters
- minSdk: actual minimum Android API level
- notes: plain text for the update screen

The supplied manifest describes ONLY the previously verified DJW Player 0.3.5
APK. Expected file size: 85984112 bytes. Expected SHA-256:
915d5e8f060d2d255e810c63c6b5f86737ee92392371861c631894fdf8e4fbaa

The page does not fetch update.json: it displays the latest release API's APK
asset. Browsers can follow the APK link; Android will fetch and validate the
manifest natively when its updater is implemented.

Official references:
- https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
- https://docs.github.com/en/rest/releases/releases#get-the-latest-release
- https://docs.github.com/en/pages/quickstart
