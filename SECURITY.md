# Security


Source version 1.0.0 has not received an independent security audit.

The app binds to loopback and checks local requests, Host and Origin. Do not expose it through public tunnels or disable those checks. Protect local cookies, tokens, proxy settings, user profiles and backups.

Python plugins run with your permissions: install only trusted code. Image validation/limits reduce risk but do not replace keeping Pillow and other dependencies updated. The v33 wallpaper importer rejects private DNS/IP destinations and checks redirects, limits payload sizes and decodes images before saving. These controls are not a whole-application security certification.

Do not disclose credentials, full data folders or private logs in vulnerability reports. Send version, OS, impact and minimal reproduction steps through the verified private channel of your build's distributor. This source package establishes no public repository, support contact or response deadline. Distributors should define a real reporting channel before release.
