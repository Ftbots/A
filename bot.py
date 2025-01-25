
import logging
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonUrl, KeyboardButtonCallback, ReplyKeyboardMarkup
from mega import Mega
import os
import time
import pkg_resources
import asyncio
import json
import re  # Import the regular expression module

# Import configuration from config.py
from config import API_ID, API_HASH, BOT_TOKEN, MEGA_EMAIL, MEGA_PASSWORD, LOG_CHANNEL_ID

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Telegram Client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Path for the accounts JSON file
ACCOUNTS_FILE = 'mega_accounts.json'

# Path for the logged users JSON file
LOGGED_USERS_FILE = 'logged_users.json'

# Load accounts data
def load_accounts():
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save accounts data
def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=4)

# Load logged users data
def load_logged_users():
    try:
        with open(LOGGED_USERS_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

# Save logged users data
def save_logged_users(logged_users):
    with open(LOGGED_USERS_FILE, 'w') as f:
        json.dump(list(logged_users), f, indent=4)


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
async def upload_to_mega(file_path, message, current_mega_account, max_retries=3):
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            total_size = os.path.getsize(file_path)
            uploaded_size = 0
            
            # Initialize Mega with current user account
            mega = Mega()
            m = mega.login(current_mega_account['email'], current_mega_account['password'])

            # *********** NEW: Initialize progress to 0 ***********
            await upload_progress_callback(0, total_size, message, start_time, True)  
             
            # Use m.upload with file path
            mega_file = m.upload(file_path)
            
            # Manually update the progress
            while uploaded_size < total_size:
                current_size = os.path.getsize(file_path)
                if current_size > uploaded_size:
                    uploaded_size = current_size
                    await upload_progress_callback(uploaded_size, total_size, message, start_time, True)
                else:
                    # Check every second
                    await asyncio.sleep(1)
                    uploaded_size = os.path.getsize(file_path)
                    await upload_progress_callback(uploaded_size, total_size, message, start_time, True)
                    
                
                # To check every 10 second the progress
                if time.time() - start_time > 10 :
                   await upload_progress_callback(uploaded_size, total_size, message, start_time, True)    
                   start_time = time.time()
                    
            return m.get_upload_link(mega_file)
            
        except Exception as e:
            logging.error(f"Mega upload error (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait for 2 seconds before retrying
            else:
              logging.error("Mega upload failed after multiple retries")
              return None
          
# Load accounts data on startup
accounts = load_accounts()

# Load logged users data on startup
logged_users = load_logged_users()


# Store currently selected Mega account for each user
user_accounts = {}

# Function to add a new Mega account
@bot.on(events.NewMessage(pattern=r'/addmega\s+(?P<email>[^\s]+)\s+(?P<password>.+)'))
async def add_mega_account(event):
    logging.info(f"Handling /addmega command from: {event.sender_id}")
    user_id = str(event.sender_id)
    email = event.pattern_match.group('email')
    password = event.pattern_match.group('password')

    try:
        # Attempt to login with the provided credentials
        mega = Mega()
        m = mega.login(email, password)
    
        # If login is successful, add to the accounts
        if user_id not in accounts:
            accounts[user_id] = []
        accounts[user_id].append({'email': email, 'password': password})
        save_accounts(accounts)
        await event.respond("Mega account added successfully!")
        logging.info(f"Mega account added successfully for user: {event.sender_id}")
    except Exception as e:
        logging.error(f"Failed to add Mega account for user: {event.sender_id}, Error: {e}")
        await event.respond(f"Failed to add Mega account. Error: {e}")

# Function to list Mega accounts
@bot.on(events.NewMessage(pattern='/listmega'))
async def list_mega_accounts(event):
    logging.info(f"Handling /listmega command from: {event.sender_id}")
    user_id = str(event.sender_id)
    if user_id in accounts and accounts[user_id]:
        msg = "Your Mega accounts:\n"
        for index, account in enumerate(accounts[user_id]):
            msg += f"{index + 1}. {account['email']}\n"
        await event.respond(msg)
    else:
        await event.respond("No Mega accounts added yet. Use /addmega <email> <password> to add one.")

# Function to switch the active Mega account
@bot.on(events.NewMessage(pattern=r'/switchmega\s+(?P<index>\d+)'))
async def switch_mega_account(event):
    logging.info(f"Handling /switchmega command from: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        account_index = int(event.pattern_match.group('index')) - 1
        if user_id in accounts and 0 <= account_index < len(accounts[user_id]):
            # Setting current mega account for the user
            user_accounts[user_id] = accounts[user_id][account_index]
            await event.respond(f"Switched to Mega account: {accounts[user_id][account_index]['email']}")
        else:
            await event.respond("Invalid account number.")
    except ValueError:
        await event.respond("Invalid input. Please enter a number.")
    except Exception as e:
      logging.error(f"Failed to switch account for user: {event.sender_id}, Error: {e}")
      await event.respond(f"Failed to switch account. Error: {e}")


# Function to remove a Mega account
@bot.on(events.NewMessage(pattern=r'/removemega\s+(?P<index>\d+)'))
async def remove_mega_account(event):
    logging.info(f"Handling /removemega command from: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        account_index = int(event.pattern_match.group('index')) - 1
        if user_id in accounts and 0 <= account_index < len(accounts[user_id]):
            removed_email = accounts[user_id].pop(account_index)['email']
            save_accounts(accounts)
            
            # Remove Current mega account if it was the removed one
            if user_id in user_accounts and user_accounts[user_id]['email'] == removed_email:
                del user_accounts[user_id]

            await event.respond(f"Mega account {removed_email} removed successfully.")
        else:
            await event.respond("Invalid account number.")
    except ValueError:
      await event.respond("Invalid input. Please enter a valid number")
    except Exception as e:
        logging.error(f"Failed to remove account for user: {event.sender_id}, Error: {e}")
        await event.respond(f"Failed to remove account. Error: {e}")

# Default bot's main message handler
@bot.on(events.NewMessage)
async def handle_message_default(event):
    if event.is_private and not event.message.text.startswith('/'):
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

                # Get current mega account of user, use the first if no current mega account found
                user_id = str(event.sender_id)
                current_mega_account = None
                if user_id in user_accounts and user_accounts[user_id]:
                  current_mega_account = user_accounts[user_id]
                elif user_id in accounts and accounts[user_id]:
                  current_mega_account = accounts[user_id][0]
                else:
                   await event.respond("No Mega accounts configured. Use /addmega <email> <password> to add one.")
                   return
                   
                # Upload the file to Mega
                logging.info("Uploading to mega")
                await bot.edit_message(progress_message, "Starting upload...")
                mega_link = await upload_to_mega(file_path, progress_message, current_mega_account)

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


# Define command handler for /start
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    logging.info(f"Handling /start command from: {event.sender_id}")
    user_id = str(event.sender_id)
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
    
    # Send log message to the log channel
    try:
        if user_id not in logged_users:
            user = await bot.get_entity(event.sender_id)
            username = user.username if user.username else "No Username"
            log_message = (
               f"#New_Bot_User\n\n"
               f"» Username - {username}"
            )
            await bot.send_message(LOG_CHANNEL_ID, log_message)
            logging.info(f"Log message sent to channel: {LOG_CHANNEL_ID} for user: {event.sender_id}")
            
            logged_users.add(user_id)
            save_logged_users(logged_users)
        else:
           logging.info(f"User {event.sender_id} already logged")
    except Exception as e:
        logging.error(f"Error sending log message: {e}")

# Initialize last edit times for progress bar
last_edit_time_download = 0
last_edit_time_upload = 0

# Bot's callback query handler
@bot.on(events.CallbackQuery)
async def callback_query_handler(event):
   if event.data == b'help':
      await event.answer('Send /help command to show all available commands.')


# Run the bot
if __name__ == '__main__':
    logging.info("Bot started. Listening for messages...")
    bot.run_until_disconnected()
        
