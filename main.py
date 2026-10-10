import os
import re
import tempfile
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DISKWALA_API_KEY = os.getenv("DISKWALA_API_KEY", "").strip()
# Standard Telegram bot limit 50MB (adhukku mela bot upload allow pannadhu)
MAX_DOWNLOAD_MB = int(os.getenv("MAX_DOWNLOAD_MB", "50"))
ALLOWED_HOSTS = {"www.diskwala.com", "diskwala.com"}

HELP = (
    "DiskWala link anupunga, bot download panni Telegram-la upload pannum.\n\n"
    "Gavanikka: Standard Telegram Bot 50MB varaikkum dhaan upload panna mudiyum."
)

def is_diskwala_page(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme in {"http", "https"} and p.hostname in ALLOWED_HOSTS
    except Exception:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DiskWala Downloader Bot Active-aa irukku! 🚀\n\n" + HELP)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP)

async def resolve_direct_video_url(page_url: str) -> str:
    """DiskWala webpage HTML-la irundhu direct stream/download URL-a thedi edukum."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.diskwala.com/"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(page_url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Link open aagala, HTTP status code: {resp.status}")
            
            content_type = resp.headers.get("Content-Type", "").lower()
            # Oru vela kudutha link-ae direct video file-aa irundha:
            if "video" in content_type or "application/octet-stream" in content_type:
                return page_url

            html_text = await resp.text()

            # Video player tags / direct file links regex thedudhal
            patterns = [
                r'source\s+src=["\']([^"\']+\.(?:mp4|mkv|webm)[^"\']*)["\']',
                r'file:\s*["\']([^"\']+\.(?:mp4|mkv|webm)[^"\']*)["\']',
                r'"(https?://[^"]+\.(?:mp4|mkv|webm)[^"]*)"',
                r'download_url\s*:\s*["\']([^"\']+)["\']',
            ]
            
            for pat in patterns:
                found = re.search(pat, html_text, re.IGNORECASE)
                if found:
                    return found.group(1)

            raise RuntimeError(
                "Direct video URL kedaikala! DiskWala web protection panni vechurukkalaam. "
                "DiskWala dashboard official link converter/API use panni paarunga."
            )

async def download_file(url: str, path: str, status):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.diskwala.com/"
    }
    timeout = aiohttp.ClientTimeout(total=900, connect=30, sock_read=60)
    
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url, allow_redirects=True) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Download panna mudiyala (HTTP {resp.status})")
            
            total = int(resp.headers.get("Content-Length", 0) or 0)
            limit = MAX_DOWNLOAD_MB * 1024 * 1024
            if total > limit:
                raise RuntimeError(f"File size romba perusu. Bot limit: {MAX_DOWNLOAD_MB} MB dhaan.")

            done = 0
            last_pct = -1
            with open(path, "wb") as out:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    done += len(chunk)
                    if done > limit:
                        raise RuntimeError(f"File size limit ({MAX_DOWNLOAD_MB} MB) thaandiruchu.")
                    out.write(chunk)
                    
                    if total > 0:
                        pct = int(done * 100 / total)
                        if pct >= last_pct + 15:
                            last_pct = pct
                            try:
                                await status.edit_text(f"📥 Downloading: {pct}%")
                            except Exception:
                                pass

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if not is_diskwala_page(url):
        await update.message.reply_text("Sariyana https://www.diskwala.com/ link anupunga.")
        return

    status = await update.message.reply_text("🔎 Link check pannudhu...")
    path = None
    
    try:
        # Step 1: Webpage-la irundhu direct video URL edukuradhu
        direct_video_url = await resolve_direct_video_url(url)
        await status.edit_text("📥 Direct link kedachiruchu, downloading...")

        with tempfile.NamedTemporaryFile(prefix="dw_", suffix=".mp4", delete=False) as tmp:
            path = tmp.name

        # Step 2: Download
        await download_file(direct_video_url, path, status)
        size = os.path.getsize(path)
        if size == 0:
            raise RuntimeError("File empty-aa download aayirukku.")

        # Step 3: Telegram upload
        await status.edit_text("📤 Telegram-ku upload pannudhu...")
        with open(path, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption=f"Download mudinjathu! Size: {size / (1024 * 1024):.1f} MB",
                read_timeout=900,
                write_timeout=900,
                connect_timeout=30,
                pool_timeout=30,
            )
        await status.edit_text("✅ Successfully uploaded!")

    except Exception as exc:
        err_msg = str(exc)[:800]
        try:
            await status.edit_text(f"❌ Error: {err_msg}")
        except Exception:
            await update.message.reply_text(f"❌ Error: {err_msg}")
    finally:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable set pannala!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
    
