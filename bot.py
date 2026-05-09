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

SHARED_FOLDER_ID = "1MryJRIzGVfrGQo2y7OFkFVZysjC_ZxwS"


def admin_only(user_id):
    return user_id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    await update.message.reply_text(
        "Send me a file."
    )


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_only(update.effective_user.id):
        return

    os.makedirs("downloads", exist_ok=True)

    if update.message.document:
        file_obj = update.message.document
        file_name = file_obj.file_name

    elif update.message.photo:
        file_obj = update.message.photo[-1]
        file_name = f"photo_{file_obj.file_unique_id}.jpg"

    elif update.message.video:
        file_obj = update.message.video
        file_name = (
            file_obj.file_name
            or f"video_{file_obj.file_unique_id}.mp4"
        )

    else:
        return

    file_path = f"downloads/{file_name}"

    msg = await update.message.reply_text(
        "Downloading..."
    )

    tg_file = await file_obj.get_file()

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

    metadata = {
        'name': os.path.basename(file_path),
        'parents': [SHARED_FOLDER_ID]
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
            filters.Document.ALL
            | filters.PHOTO
            | filters.VIDEO,
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
