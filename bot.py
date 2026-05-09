import os
import json

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

SCOPES = ['https://www.googleapis.com/auth/drive']

google_creds = json.loads(
    os.getenv("GOOGLE_CREDS")
)

creds = service_account.Credentials.from_service_account_info(
    google_creds,
    scopes=SCOPES
)

drive_service = build('drive', 'v3', credentials=creds)

pending_files = {}

PRESET_FOLDERS = [
    "Movies",
    "Series",
    "Telegram",
    "Backups",
]

def admin_only(user_id):
    return user_id == ADMIN_ID

def get_or_create_folder(folder_name):
    query = (
        f"name='{folder_name}' and "
        "mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )

    results = drive_service.files().list(
        q=query,
        fields="files(id, name)"
    ).execute()

    items = results.get('files', [])

    if items:
        return items[0]['id']

    metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }

    folder = drive_service.files().create(
        body=metadata,
        fields='id'
    ).execute()

    return folder.get('id')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    await update.message.reply_text(
        "Send me a file."
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    doc = update.message.document

    if not doc:
        return

    os.makedirs("downloads", exist_ok=True)

    file_path = f"downloads/{doc.file_name}"

    msg = await update.message.reply_text(
        "Downloading..."
    )

    tg_file = await doc.get_file()

    await tg_file.download_to_drive(file_path)

    pending_files[update.effective_chat.id] = file_path

    keyboard = []

    for folder in PRESET_FOLDERS:
        keyboard.append([
            InlineKeyboardButton(
                folder,
                callback_data=f"folder:{folder}"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "Custom Folder",
            callback_data="custom_folder"
        )
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await msg.edit_text(
        "Choose upload folder:",
        reply_markup=reply_markup
    )

async def folder_callback(update: Update, context):
    query = update.callback_query

    await query.answer()

    chat_id = query.message.chat.id

    if chat_id not in pending_files:
        return

    data = query.data

    if data == "custom_folder":
        context.user_data["awaiting_custom_folder"] = True

        await query.message.reply_text(
            "Send folder name:"
        )
        return

    folder_name = data.split(":")[1]

    await upload_file(
        query.message,
        chat_id,
        folder_name
    )

async def custom_folder(update: Update, context):
    if not context.user_data.get("awaiting_custom_folder"):
        return

    context.user_data["awaiting_custom_folder"] = False

    folder_name = update.message.text

    await upload_file(
        update.message,
        update.effective_chat.id,
        folder_name
    )

async def upload_file(message, chat_id, folder_name):
    file_path = pending_files[chat_id]

    progress = await message.reply_text(
        "Uploading..."
    )

    folder_id = get_or_create_folder(folder_name)

    metadata = {
        'name': os.path.basename(file_path),
        'parents': ['1MryJRIzGVfrGQo2y7OFkFVZysjC_ZxwS']
    }

    media = MediaFileUpload(
        file_path,
        resumable=True
    )

    drive_service.files().create(
        body=metadata,
        media_body=media
    ).execute()

    await progress.edit_text(
        f"Uploaded to {folder_name}"
    )

    os.remove(file_path)

    del pending_files[chat_id]

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_file
        )
    )

    app.add_handler(
        CallbackQueryHandler(folder_callback)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            custom_folder
        )
    )

    print("Bot Running...")

    app.run_polling()

if __name__ == "__main__":
    main()
