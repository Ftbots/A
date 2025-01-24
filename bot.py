import logging
from telethon import TelegramClient, events, functions, types
from mega import Mega

# Import configuration from config.py
from config import API_ID, API_HASH, BOT_TOKEN, MEGA_EMAIL, MEGA_PASSWORD

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Telegram Client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Initialize Mega
mega = Mega()
m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)


# Function to upload file to Mega
async def upload_to_mega(file_path):
    try:
        mega_file = m.upload(file_path)
        return m.get_upload_link(mega_file)
    except Exception as e:
        logging.error(f"Mega upload error: {e}")
        return None


# Bot's main message handler
@bot.on(events.NewMessage)
async def handle_message(event):
    if event.message.document:
        try:
            logging.info(f"Received file from: {event.sender_id}")
            # Download the file
            file_path = f"downloaded_file_{event.id}.{event.message.document.file.ext}"
            logging.info(f"Downloading to {file_path}")
            await bot.download_media(event.message.document, file=file_path)


            # Upload the file to Mega
            logging.info("Uploading to mega")
            mega_link = await upload_to_mega(file_path)

            if mega_link:
                await event.respond(f"File uploaded to Mega: {mega_link}")
            else:
                await event.respond("Failed to upload file to Mega.")
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            await event.respond("Error processing file upload")
        finally:
           import os
           if os.path.exists(file_path):
               os.remove(file_path)
               logging.info(f"Removed downloaded file: {file_path}")


# Run the bot
if __name__ == '__main__':
    logging.info("Bot started. Listening for messages...")
    bot.run_until_disconnected()
