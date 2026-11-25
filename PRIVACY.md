# Data and privacy


Kryo 1.0.0 runs a local loopback server. This describes the source application's behavior, not a promise of anonymity when contacting external services.

## On the device

Settings, playlists, likes, listening/search history, cached audio, logs, imported wallpapers and uploaded avatars may be stored in the application data directory, normally `%LOCALAPPDATA%\Kryo` on Windows. Enabled integrations may also store proxy settings, tokens and cookies there. Local storage is not encryption. Protect your profile and backups; redact secrets before sharing logs.

Custom avatar crops are sent to the local application server, not published to a remote account. The original uploaded file is not overwritten. Processed local copies omit original EXIF/comments/profiles. Avatar-pack exports may include your private pictures. Wallpaper URL imports fetch the supplied public URL and any image/share redirects; the source can see the request and IP address. Processed wallpaper copies are stored locally.

## On the network

Search, playback, lyrics, images, metadata and integrations contact selected providers. Providers may see your IP, query, requested content and any supplied authentication data. Proxy routing does not override provider privacy terms. Scrobbling/presence integrations require configuration; review enabled plugins.

Lyric translation runs locally with Argos in a separate process; lyrics and audio are not sent to an online translation service. Installing the translator, language models and sentence-splitting resources requires downloads. The original lyrics and timing are not overwritten.

Optional karaoke models can download on first use. Native file dialogs and external sites have their own policies. Python plugins execute with your user permissions; use only trusted plugins.

## Removal and backups

Close the app before copying the data folder. Avatar deletion requires confirmation. Uninstall should retain personal data by default; explicit full deletion is irreversible. Deleting local data does not delete records held by external services. Do not publish full data folders or unredacted diagnostic logs.


## TikTok music discovery (v39)

A public TikTok URL is fetched only after explicit consent in the TikTok discovery tab.
TikTok and its public media CDN receive network requests for that video. The video
is downloaded temporarily and decoded locally; up to two short acoustic fingerprints
are sent to Shazam. Original audio/video bytes are not uploaded to Shazam. Recognized
names or unverified sound credits are searched in the selected music catalogues.
Temporary media/sample files are removed after success, errors and cancellation.
No TikTok login, browser cookie import, private-video access or permanent video cache
is added. Related catalogue suggestions are not independent acoustic identifications.

## Imported music profile (v50)

Music-data imports retain allowlisted track/artist names and capped music counts in a separate local SQLite table. Raw account files and account identity fields are not persisted by this importer. Staged previews stay in memory for up to ten minutes, with a bounded cache. Importing does not fabricate local listening history or likes. Reimport replaces the selected service profile; deleting imported taste leaves playlists and genuine local history intact. This does not introduce account login or automatic sync. Imported names/artists can become queries to selected music providers when generating recommendations. Local profile data and backups are not encrypted by this feature.

On first start, if the new folder does not exist, data from `%LOCALAPPDATA%\KryonyxMusic` is copied and checked; the original is retained. Close the old player first. An existing Kryo folder is not merged or overwritten.

The experimental Rust shell still uses `KryonyxMusic\shell` for its own window state and WebView profile.
