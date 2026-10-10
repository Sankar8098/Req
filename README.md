# DiskWala Telegram Bot — API-key-ready configuration

## Railway Variables
- `BOT_TOKEN`: Telegram bot token
- `DISKWALA_API_KEY`: your DiskWala key (optional; only set it if you trust this deployment and DiskWala documents how it is used)
- `MAX_DOWNLOAD_MB`: defaults to `200`

## Important
The screenshot indicates the key is used to verify/link your account in DiskWala's official bots. That does not prove it is a general-purpose download API key. This code intentionally does not send the key to guessed endpoints or arbitrary URLs. A DiskWala `/app/<id>` link may return HTML rather than a direct media file. To add actual API-based resolution, the official API endpoint and required request format are needed.

Keep both tokens private. Since the key was visible in a screenshot, rotate/revoke it in DiskWala if the service supports that.
