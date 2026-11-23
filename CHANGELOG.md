# Changelog — LoLo6Fingers

Versions up to 4.2 were released under the Slovak name
*LoLo šesťprstý downloader*.

---

## 4.3

- **Renamed to LoLo6Fingers** and translated to English: the whole app,
  error messages, scripts and documentation.
- Prepared for a public GitHub repository: `README.md`, MIT `LICENSE`,
  `.gitignore` (blocks `cookies*.txt`, build output and large binaries).
- `spustit.command` → `run.command`, `yt_downloader.py` → `lolo6fingers.py`,
  `NAVOD-INSTALACIA.md` → `INSTALL.md`, `NAVOD-COOKIES.md` → `COOKIES.md`.
- The release zip is now named `LoLo6Fingers-<version>-macOS.zip` and
  includes the license.
- The experimental Windows build moved to `windows/`.
- `setup.command` and `run.command` detect a virtual environment that broke
  because the folder was renamed or moved (a venv stores its absolute path)
  — `setup.command` rebuilds it automatically.
- No changes to how downloading works.

## 4.2

Focus: getting as many YouTube videos to download as possible.

- **Deno bundled into the app.** Without a JavaScript runtime yt-dlp tries
  only one YouTube client (visionos) and many videos fail — and most users
  have neither Node nor Deno. `package.command` now downloads Deno from the
  official Deno Land GitHub, verifies the checksum and bundles it. The zip
  grows by ~37 MB.
- **Rebuilt fallback clients.** The previous fallback clients (android,
  ios, tv_simply, mweb) **all require a PO token** according to yt-dlp's
  own table — without a provider the whole fallback was useless. Now
  clients that need no token (tv, tv_downgraded, web_embedded) are tried
  first, and token clients only when a provider is installed. Clients are
  sent in groups in one request instead of one by one.
- **Half the requests to YouTube.** Each video used to be extracted twice —
  once for the existing-file check and again for the download. Now once,
  and the result is reused. Fewer requests mean less risk of YouTube
  flagging the app as a bot. When the check hits a block, the same failing
  attempt is not repeated.
- **Fix: "Overwrite" did not overwrite.** yt-dlp does not overwrite video
  files by default, so the app said "Done!" but kept the old file. Affected
  every option except re-encoding.
- **JavaScript runtime version check.** yt-dlp needs Node 22+ or Deno 2.3+
  and silently ignores older ones. The app now checks this and diagnostics
  show the version.
- **Updates include the challenge solver.** `update.command` and
  `package.command` install `yt-dlp[default]`. yt-dlp is pinned to an exact
  `yt-dlp-ejs` version and on a mismatch it stops solving YouTube challenges.
- **`setup.command` looks for Python 3.11+.** yt-dlp dropped Python 3.10 and
  older; macOS ships 3.9, on which an ancient yt-dlp would be installed
  silently, unable to download from YouTube.
- `setup-potoken.command` requires Node 22+ (was 20+).

## 4.1

- **JavaScript runtime enabled for YouTube.** YouTube sends signature
  challenges in JavaScript, and without a runtime yt-dlp itself warns that
  "some formats may be missing". yt-dlp looks only for Deno by default, so
  Node.js installed by `setup-potoken.command` went unused. The app now
  finds Node and Deno itself, also inside the bundled `.app`. Diagnostics
  show which runtime is used.
- **Extended fallback chain.** Two new steps:
  - a retry **without cookies** when the error is unrelated to login —
    cookies can push YouTube into the blocking SABR mode or may have been
    rotated meanwhile. For videos that really need a login this step is
    skipped, so it does not replace a useful error message.
  - **HTTP 403** during a download now triggers the fallback through other
    YouTube clients. Before, the download simply stopped.
- **Throttling protection.** YouTube drops the speed to a fraction after a
  while. Below 100 KB/s the app requests fresh URLs and downloads in 10 MB
  chunks, which avoids throttling.
- **Parallel fragments.** Live stream recordings and long videos download
  4 fragments at once instead of one.

## 4.0

- Fixed the update check — it compared only against stable versions, so
  on a nightly build a newer nightly went unnoticed. Stable releases can
  be months apart, so the app stayed silent about updates.
- The app now knows whether you run stable or nightly and suggests the
  right option in `update.command`.
- Introduced this file. Every version change adds an entry here.

## 3.9

- Support for a `cookies.txt` file, which takes precedence over reading
  from the browser. YouTube keeps rotating and invalidating cookies on open
  tabs, so reading from a running Chrome fails for non-public videos.
- Added a cookies guide with the private-window method.

## 3.8

- Chrome profile picker. Otherwise yt-dlp always reads the "Default"
  profile and, with several profiles, used cookies from the wrong account.

## 3.7

- Recognises the "Please sign in" message. Before, such a video looked
  like DRM-protected or geo-blocked.

## 3.6

- Diagnostics include the detailed yt-dlp output. Until then the app
  suppressed every message — which is why the wrong cause was chased for
  so long.

## 3.5

- New `setup-potoken.command` — installs the PO Token provider and Node.js.
- Diagnostics show whether the provider is active.

## 3.4

- Added the `missing_pot` switch — an attempt to work around the PO token.
- Fixed the nightly build in `update.command`: a second command installing
  from GitHub reverted it to the stable version, so the nightly was never
  installed.
- Restored the whole project after the folder was deleted. Added
  `setup.command`, which builds the environment, icon and ffmpeg from scratch.

## 3.3

- Fixed diagnostics, which failed on the same error as the download —
  they no longer do format selection.
- Added a DRM column to the listing.

## 3.2

- Added the "What can be downloaded?" button — lists what YouTube really
  offers for a video.
- Support for live streams and premieres (`live_from_start`).
- Fixed a false update warning — it warned by the version's age; now it
  checks whether a newer version actually exists.
- `update.command` offers stable or nightly.

## 3.1

- Hardware decoding and encoding split into separate steps. A decoder
  failure used to bring down the encoding too and it fell back to the CPU.
- The app reports why the GPU failed.

## 3.0

- Automatic codec check after downloading. AV1 or VP9 videos are
  re-encoded to H.264 for Adobe Premiere; H.264 is left alone.
- Re-encoding merged into one method. It existed twice and the second copy
  had an old progress-parsing bug.

## 2.9

- Fixed the MP3 fallback — it switched to a video format.
- Warning about an outdated yt-dlp.

## 2.8

- Fallback YouTube clients (android, ios, tv, mweb) when the standard
  access fails.
- Downloading merged into one method. Each path had its own copy before,
  so the 4K option lacked fixes the others had.

## 2.7

- Progress works for videos of unknown length, e.g. live stream
  recordings. The app used to look frozen.
- The parser handles all three time formats ffmpeg sends.

## 2.6

- Retry added to the 4K path as well.
- `-allow_sw 0` forces real hardware encoding. With 1, VideoToolbox
  silently fell back to software at CPU speed.
- `-hwaccel videotoolbox` for decoding — without it the decoder was the
  bottleneck and the GPU did not help.

## 2.5

- GPU re-encoding (VideoToolbox, NVENC, QuickSync) with automatic CPU fallback.

## 2.4

- Fixed the main cause of failures: "Automatic" used the `best` selector,
  which on YouTube looks for video and audio in a single file. YouTube no
  longer offers those for most videos.
- Automatic retry when format selection fails.
- Version shown in the status line.

## 2.3

- Cascading format fallbacks. Without them videos that do not offer H.264
  at the chosen resolution failed.
- "Open folder" button.

## 2.2

- Removed hardcoded YouTube clients. They caused "The page needs to be
  reloaded" and broke every download.

## 2.1

- "Cancel conversion" button that cleans up unfinished files.
- Existing-file dialog: Overwrite / Keep both / Cancel.
- Percentage and time left during re-encoding.
- Removed Facebook from the labels.
- Window centred on launch.

## 2.0

- Fixed H.264 re-encoding — `FFmpegVideoConvertor` ignored the settings;
  ffmpeg is now called directly.
