
import logging
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonUrl, KeyboardButtonCallback, ReplyKeyboardMarkup
from mega import Mega
import os
import time
import pkg_resources
import asyncio

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


# Function to format file size
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"


# Function to display the progress bar
async def display_progress(message, current, total, start_time, text, edit_message,  bars=10):
    if total == 0:
      return "0.00%"
    percentage = current / total * 100
    filled_bars = int(percentage / (100 / bars))
    progress_bar = '▪' * filled_bars + '▫' * (bars - filled_bars)
    
    elapsed_time = time.time() - start_time
    if current > 0 and elapsed_time > 0 :
      speed = current / elapsed_time
    else:
      speed = 0

    if speed > 0:
       remaining = (total - current) / speed
       eta = f"{int(remaining)}s"
    else:
      eta = "N/A"
      
    current_size = format_size(current)
    total_size = format_size(total)
    speed_formatted = format_size(speed)
    
    progress_text = (
        f"{text}: {percentage:.2f}%\n"
        f"[{progress_bar}]\n"
        f"{current_size} of {total_size}\n"
        f"Speed: {speed_formatted}/sec\n"
        f"ETA: {eta}\n\n"
        f"Thanks for using\nPowered by NaughtyX"
    )

    # Define inline button
    buttons = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[
           KeyboardButtonUrl(text='Owner ⚡', url='https://t.me/Nx_KRSHNA')
        ])
    ])


    if edit_message:
      try:
          await bot.edit_message(message, progress_text, buttons=buttons)
      except Exception as e:
          logging.error(f"Error editing message: {e}")
    else:
        return progress_text


# Callback function for download progress
async def download_progress_callback(current, total, message, start_time, edit_message):
    global last_edit_time_download
    current_time = time.time()
    if current_time - last_edit_time_download >= 10:
      await display_progress(message, current, total, start_time, "Downloading", edit_message)
      last_edit_time_download = current_time
    return current


# Callback function for upload progress
async def upload_progress_callback(current, total, message, start_time, edit_message):
    global last_edit_time_upload
    current_time = time.time()
    if current_time - last_edit_time_upload >= 10:
        await display_progress(message, current, total, start_time, "Uploading", edit_message)
        last_edit_time_upload = current_time
    return current

# Helper async function for download progress callback
async def download_progress_callback_helper(current, total, message, start_time, edit_message):
    await download_progress_callback(current, total, message, start_time, edit_message)

# Function to upload file to Mega with retry logic
async def upload_to_mega(file_path, message, max_retries=3):
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            total_size = os.path.getsize(file_path)
            uploaded_size = 0
            
            # Use m.upload with file path
            mega_file = m.upload(file_path)
            
            # Manually update the progress
            while uploaded_size < total_size:
                current_size = os.path.getsize(file_path)
                if current_size > uploaded_size:
                    uploaded_size = current_size
                    await upload_progress_callback(uploaded_size, total_size, message, start_time, True)
            
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
    
    Send me a file, and I'll upload it to your Mega account. 
    
    Use /help for more info.
    
    """

    # Define inline buttons
    buttons = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text='Help', data=b'help')
            ])
        ])
    await bot.send_message(event.chat_id, welcome_message, buttons=buttons)
    logging.info(f"Finished handling /start command from: {event.sender_id}")

# Initialize last edit times for progress bar
last_edit_time_download = 0
last_edit_time_upload = 0

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

                start_time = time.time()
                progress_message = await event.respond("Starting download...")

                logging.info(f"Downloading to {file_path}")
                await bot.download_media(event.message, file=file_path, progress_callback=lambda current, total: download_progress_callback_helper(current, total, progress_message, start_time, True))

                # After Download
                file_size_after_download = os.path.getsize(file_path)
                logging.info(f"File size after download: {file_size_after_download}")

                # Upload the file to Mega
                logging.info("Uploading to mega")
                await bot.edit_message(progress_message, "Starting upload...")
                mega_link = await upload_to_mega(file_path, progress_message)

                if mega_link:
                   await bot.edit_message(progress_message, f"File uploaded to Mega: {mega_link}")
                else:
                   await bot.edit_message(progress_message, "Failed to upload file to Mega.")
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
                
