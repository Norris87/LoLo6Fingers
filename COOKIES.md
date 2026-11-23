# Getting a working cookies.txt for YouTube

You only need this for **videos that require a login** — private, unlisted,
age-restricted or members-only. Regular public videos need nothing.

---

## Why it does not simply work from Chrome

The app can read cookies straight from Chrome, but with YouTube that often
fails. The reason is a security mechanism: **YouTube keeps rotating cookies
on open tabs and invalidates the old ones.** By the time the app reads
them, they are no longer valid.

The fix is to create a login session that is never rotated — in a private
window that you close right away. (This is the method recommended by the
[yt-dlp wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).)

---

## Steps

### 1. Install a cookie export extension

Add one of these to Chrome:

- **Get cookies.txt LOCALLY** (recommended)
- **cookies.txt**

You will find them in the Chrome Web Store. What matters is that they
export in the **Netscape / cookies.txt** format.

### 2. Open a private window

`Cmd + Shift + N` opens an Incognito window.

Make sure the extension is allowed to run in Incognito
(Chrome → Extensions → the extension → *Allow in Incognito*).

### 3. Sign in to YouTube

In that Incognito window, sign in with the account that has access to the video.

### 4. Go to robots.txt

**In the same tab**, type into the address bar:

```
https://www.youtube.com/robots.txt
```

This matters. It keeps YouTube from rotating the cookies once more.
No other tab may be open in the Incognito window.

### 5. Export the cookies

Click the extension icon and export the cookies for `youtube.com`.
Save the file, for example to your Desktop as `cookies.txt`.

### 6. Close the private window

Close it **without signing out**. That "freezes" the session and the
cookies stay valid.

> If you sign out, the cookies stop working immediately.

### 7. Load the file in the app

In the app, click *Browse...* next to **cookies.txt file** and pick the
saved file. From now on it is used instead of Chrome.

---

## Important

**Risk to your account.** The yt-dlp developers warn that using your account
for downloading risks a temporary or permanent ban. Consider a secondary
account if you download a lot.

**Cookies expire.** After a few weeks to months they stop working.
Then repeat the steps.

**The file gives access to your account.** Never send it to anyone and
never commit it to Git (the repository's `.gitignore` already blocks
`cookies*.txt`).

---

## If even this does not help

Click **What can be downloaded?** in the app. At the top you will see which
login was used, and the detailed output below. If it still says
`Please sign in`, the account simply has no access to the video — for
example because it is someone else's private video.
