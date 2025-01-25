
import logging
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonCallback, ReplyKeyboardMarkup
from mega import Mega
import os
import time
import pkg_resources

# Import configuration from config.py
from config import API_ID, API_HASH, BOT_TOKEN, MEGA_EMAIL, MEGA_PASSWORD

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Telegram Client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Initialize Mega
mega = Mega()
m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)

# Get mega.py version
mega_version = pkg_resources.get_distribution("mega.py").version
logging.info(f"Mega.py version: {mega_version}")

# Function to safely extract file name and extension
def get_file_name_and_ext(media):
    file_name = None
    file_ext = ""
    try:
        if isinstance(media, types.MessageMediaDocument) and hasattr(media, 'document') and media.document:
            if hasattr(media.document, 'name') and media.document.name:
                file_name = media.document.name
                file_ext = media.document.name.split('.')[-1]
            elif hasattr(media.document, 'attributes') and media.document.attributes:
                for attribute in media.document.attributes:
                    if isinstance(attribute, types.DocumentAttributeFilename):
                        file_name = attribute.file_name
                        file_ext = attribute.file_name.split('.')[-1]
                        break
                    elif isinstance(attribute, types.DocumentAttributeVideo):
                        if hasattr(attribute,'file_name') and attribute.file_name:
                            file_name = attribute.file_name
                            file_ext = attribute.file_name.split('.')[-1]
                        else:
                           file_name = str(media.document.id)
                           file_ext = ".mp4"
                        break
        
    except Exception as e:
        logging.error(f"Error getting file info: {e}")
    if file_name is None and hasattr(media, 'id'):
        file_name = str(media.id)
    
    if not file_ext:
        if isinstance(media, types.MessageMediaDocument):
            for attribute in media.document.attributes:
                if isinstance(attribute, types.DocumentAttributeVideo):
                    file_ext = ".mp4"
                    break
        else:
             file_ext = ""
    return file_name, file_ext

# Function to upload file to Mega with retry logic
async def upload_to_mega(file_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            mega_file = m.upload(file_path)
            return m.get_upload_link(mega_file)
        except Exception as e:
            logging.error(f"Mega upload error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait for 2 seconds before retrying
            else:
              logging.error("Mega upload failed after multiple retries")
              return None


# Define command handler for /start
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    logging.info(f"Handling /start command from: {event.sender_id}")
    welcome_message = """
    Hello! I'm your Mega Uploader Bot.
    
    I can help you upload files directly to your Mega account. Here's how to use me:
    
    1. Simply send me a file, and I'll upload it to your Mega account and provide you with the shareable link.
    
    Here are the available commands:
    
    - `/start`: Shows this welcome message and instructions.
    - `/help`:  Shows all available command.

    If you have any questions please reach out to support.

    Bot version: 1.0.0
    
    """

    # Define inline buttons
    buttons = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text='Help', data=b'help')
            ])
        ])
    await bot.send_message(event.chat_id, welcome_message, buttons=buttons)
    logging.info(f"Finished handling /start command from: {event.sender_id}")

# Bot's main message handler
@bot.on(events.NewMessage)
async def handle_message(event):
    if event.is_private and not event.message.text == "/start":
        logging.info(f"Starting handle_message from: {event.sender_id}")
        file_path = None
        if event.message.media:
            try:
                logging.info(f"Received media from: {event.sender_id}")
                
                media = event.message.media
                print(f"media type: {type(media)}")

                # Extract file name and extension
                file_name, file_ext = get_file_name_and_ext(media)
                
                if file_name is not None:
                    file_path = f"downloaded_file_{event.id}.{file_ext}"
                else:
                    logging.error("File name is None")
                    await event.respond("Error processing file upload")
                    return
                    
                # Log file type
                if isinstance(media, types.MessageMediaDocument) and hasattr(media, 'document') and media.document:
                    logging.info(f"File MIME type: {media.document.mime_type}")
                    # Before Download
                    logging.info(f"File size before download: {media.document.size}")

                logging.info(f"Downloading to {file_path}")
                await bot.download_media(event.message, file=file_path)

                # After Download
                file_size_after_download = os.path.getsize(file_path)
                logging.info(f"File size after download: {file_size_after_download}")

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
                if file_path and os.path.exists(file_path):
                  os.remove(file_path)
                  logging.info(f"Removed downloaded file: {file_path}")
        logging.info(f"Finished handle_message from: {event.sender_id}")

# Bot's callback query handler
@bot.on(events.CallbackQuery)
async def callback_query_handler(event):
   if event.data == b'help':
      await event.answer('Send /help command to show all available commands.')


# Run the bot
if __name__ == '__main__':
    logging.info("Bot started. Listening for messages...")
    bot.run_until_disconnected()
    
