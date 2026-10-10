import os
import tempfile
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ["BOT_TOKEN"]
# Set this to the DiskWala API key ONLY if DiskWala's official bot/API documentation
# explicitly says this key is accepted by a supported API endpoint.
DISKWALA_API_KEY = os.getenv("DISKWALA_API_KEY", "").strip()
MAX_DOWNLOAD_MB = int(os.getenv("MAX_DOWNLOAD_MB", "200"))
ALLOWED_HOSTS = {"www.diskwala.com", "diskwala.com"}

HELP = (
    "Send a DiskWala link. This starter can download only a URL that directly returns "
    "a file. A /app/<id> page is usually a webpage, not a direct media URL.\\n\\n"
    "DISKWALA_API_KEY is configurable in Railway Variables, but this bot does not "
    "guess undocumented API endpoints or send the key to arbitrary URLs."
)

def is_diskwala_page(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme == "https" and p.hostname in ALLOWED_HOSTS
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DiskWala bot is running.\\n\\n" + HELP)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)

async def fetch_direct_file(url: str, path: str, status):
    timeout = aiohttp.ClientTimeout(total=900, connect=20, sock_read=60)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} while downloading.")
            ctype = resp.headers.get("Content-Type", "").lower()
            if "text/html" in ctype:
                raise RuntimeError(
                    "This link returned a webpage, not a video file. "
                    "The DiskWala API key alone does not reveal a supported download endpoint. "
                    "Please use DiskWala's documented API or official link-converter bot."
                )
            total = int(resp.headers.get("Content-Length", "0") or 0)
            limit = MAX_DOWNLOAD_MB * 1024 * 1024
            if total > limit:
                raise RuntimeError(f"File exceeds configured {MAX_DOWNLOAD_MB} MB limit.")
            done, shown = 0, -1
            with open(path, "wb") as out:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    done += len(chunk)
                    if done > limit:
                        raise RuntimeError(f"File exceeds configured {MAX_DOWNLOAD_MB} MB limit.")
                    out.write(chunk)
                    if total:
                        pct = int(done * 100 / total)
                        if pct >= shown + 10:
                            shown = pct
                            try:
                                await status.edit_text(f"📥 Downloading: {pct}%")
                            except Exception:
                                pass
            return ctype

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if not is_diskwala_page(url):
        await update.message.reply_text("Send a valid https://diskwala.com/ link.")
        return
    status = await update.message.reply_text("🔎 Checking link…")
    path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="dw_", suffix=".bin", delete=False) as tmp:
            path = tmp.name
        await fetch_direct_file(url, path, status)
        size = os.path.getsize(path)
        if size == 0:
            raise RuntimeError("The response was empty.")
        await status.edit_text("📤 Uploading file to Telegram…")
        with open(path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="diskwala_download.bin",
                caption=f"File size: {size / (1024 * 1024):.1f} MB",
                read_timeout=900, write_timeout=900, connect_timeout=30, pool_timeout=30,
            )
        await status.edit_text("✅ Upload complete.")
    except Exception as exc:
        try:
            await status.edit_text(f"❌ {str(exc)[:850]}")
        except Exception:
            await update.message.reply_text(f"❌ {str(exc)[:850]}")
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
