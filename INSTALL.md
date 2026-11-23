# Installing LoLo6Fingers (macOS)

The app runs on Macs with an **M1 to M5** chip (Apple Silicon).
Nothing else needs to be installed — ffmpeg and the JavaScript runtime are
bundled inside.

**Not sure which chip you have?** Click the Apple menu  → **About This Mac**.
If it says *Apple M1*, *M2*, *M3*, *M4* or *M5*, you are good to go.
If it says *Intel*, this app will not run on your Mac.

---

## 1. Download

1. Open the **[latest release](https://github.com/Norris87/LoLo6Fingers/releases/latest)**.
2. Scroll down to **Assets**.
3. Click **`LoLo6Fingers-x.y-macOS.zip`** (x.y is the version number).
   Do *not* pick "Source code" — that is for developers.

The zip lands in your **Downloads** folder.

## 2. Unzip

Double-click the downloaded zip. You get a folder with
**LoLo6Fingers.app** and these instructions.

## 3. Move it to Applications

Drag `LoLo6Fingers.app` into your **Applications** folder.
Not required, but tidier — if you keep it elsewhere, just adjust the path
in the next step.

## 4. Unblock the app in Terminal

The app is not signed with an Apple developer certificate, so macOS blocks
it on first launch. The message usually says *"the app is damaged"* or
*"cannot be verified"* — **it is not a virus or a bug**, just Gatekeeper.

Open **Terminal** (Cmd+Space → type `Terminal`) and paste:

```
xattr -cr "/Applications/LoLo6Fingers.app"
```

Press **Enter**. If nothing is printed, it worked.

> **If the app is not in Applications:**
> type `xattr -cr ` (with a space at the end), then drag the `.app` straight
> into the Terminal window — the path fills in by itself. Then press Enter.

## 5. Launch the app

**Right-click** the app → **Open** → confirm **Open** in the dialog.

You only need to do this once. After that it opens with a normal double-click.

---

## Keeping it working

YouTube keeps changing how it serves videos and the `yt-dlp` engine inside
the app has to keep up. If videos that used to download suddenly stop,
an update is almost always the fix — grab the newest zip from the
[Releases](https://github.com/Norris87/LoLo6Fingers/releases/latest) page.

The app checks for new yt-dlp versions itself and tells you in its status line.

---

## When a video will not download

Click **What can be downloaded?** in the app. It lists what YouTube
really offers for the video and tells you whether it is DRM, geo-blocking,
a login requirement or PO Token protection.

If it lists only `sb0`, `sb1`, `sb2`, those are not videos but small
preview images from the timeline — YouTube withheld the real video.

For videos that need a login, see [COOKIES.md](COOKIES.md).
