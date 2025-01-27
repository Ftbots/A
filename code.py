
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonUrl, KeyboardButtonCallback, ReplyKeyboardMarkup
from mega import Mega
import os
import time
import pkg_resources
import asyncio
import json
import re  # Import the regular expression module
import pymongo # Import PyMongo
import logging # Import logging


# Import configuration from config.py
from config import API_ID, API_HASH, BOT_TOKEN, MEGA_EMAIL, MEGA_PASSWORD, LOG_CHANNEL_ID, ADMIN_USER_IDS, MONGO_URI, DATABASE_NAME, COLLECTION_NAME

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Telegram Client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Path for the accounts JSON file
ACCOUNTS_FILE = 'mega_accounts.json'

# Initialize MongoDB client and collection
try:
  client = pymongo.MongoClient(MONGO_URI)
  db = client[DATABASE_NAME]
  users_collection = db[COLLECTION_NAME]
  logging.info("Connected to MongoDB successfully!")
except Exception as e:
  logging.error(f"Error connecting to MongoDB: {e}")
  exit()
  
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

# Function to add a logged user to the database
def add_logged_user(user_id, username):
    user_data = {
        "_id": user_id,
        "username": username
    }
    users_collection.insert_one(user_data)
    logging.info(f"User {user_id} added to MongoDB")

# Function to get the list of logged users from database
def get_logged_users():
    logged_users = set()
    for user in users_collection.find():
        logged_users.add(str(user["_id"]))
    return logged_users
    

# Function to remove all the logged user from database
def clear_logged_users():
    users_collection.delete_many({})
    logging.info(f"All logged users removed from MongoDB")


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
async def display_progress(message, current, total, start_time, text, edit_message,  bars=10, cancel_button=False, download_id = None):
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
           KeyboardButtonUrl(text='Owner ⚡', url='https://t.me/Nx_KRSHNA'),
           
        ]),
          KeyboardButtonRow(buttons=[
             KeyboardButtonCallback(text='Cancel', data=f'cancel_{download_id}'.encode()) if cancel_button else None,
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
async def download_progress_callback(current, total, message, start_time, edit_message, download_id=None):
    global last_edit_time_download
    current_time = time.time()
    if current_time - last_edit_time_download >= 10:
      await display_progress(message, current, total, start_time, "Downloading", edit_message, True, True, download_id)
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
async def download_progress_callback_helper(current, total, message, start_time, edit_message, download_id=None):
    await download_progress_callback(current, total, message, start_time, edit_message, download_id)

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
logged_users = get_logged_users()

# Store currently selected Mega account for each user
user_accounts = {}

# Store currently active downloads
active_downloads = {}

# Store Bot Usage Stats
total_users = 0
total_files_uploaded = 0

# Function to add a new Mega account
async def add_mega_account(event, email, password):
    logging.info(f"Adding mega account from: {event.sender_id}")
    user_id = str(event.sender_id)

    try:
        # Attempt to login with the provided credentials
        mega = Mega()
        m = mega.login(email, password)
    
        # If login is successful, add to the accounts
        if user_id not in accounts:
            accounts[user_id] = []
        accounts[user_id].append({'email': email, 'password': password, 'status': 'valid'})
        save_accounts(accounts)
        await event.respond("Mega account added successfully!")
        logging.info(f"Mega account added successfully for user: {event.sender_id}")
    except Exception as e:
        logging.error(f"Failed to add Mega account for user: {event.sender_id}, Error: {e}")
        if user_id not in accounts:
           accounts[user_id] = []
        accounts[user_id].append({'email': email, 'password': password, 'status': 'invalid', 'error': str(e)})
        save_accounts(accounts)
        await event.respond(f"Failed to add Mega account. Error: {e}")


# Function to list Mega accounts
async def list_mega_accounts(event):
    logging.info(f"Listing mega accounts for: {event.sender_id}")
    user_id = str(event.sender_id)
    if user_id in accounts and accounts[user_id]:
        msg = "Your Mega accounts:\n"
        for index, account in enumerate(accounts[user_id]):
            status = account.get('status','unverified')
            msg += f"{index + 1}. {account['email']} - Status: {status}\n"
        await event.respond(msg)
    else:
        await event.respond("No Mega accounts added yet. Use /settings to add one.")

# Function to switch the active Mega account
async def switch_mega_account(event, account_index):
    logging.info(f"Switching mega account for user: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        if user_id in accounts and 0 <= account_index < len(accounts[user_id]):
            # Setting current mega account for the user
            user_accounts[user_id] = accounts[user_id][account_index]
            await event.respond(f"Switched to Mega account: {accounts[user_id][account_index]['email']}")
        else:
            await event.respond("Invalid account number. Please use /listmega to see the account numbers")
    except ValueError:
        await event.respond("Invalid input. Please enter a valid number.")
    except Exception as e:
        logging.error(f"Failed to switch account for user: {event.sender_id}, Error: {e}")
        await event.respond(f"Failed to switch account. Error: {e}")

# Function to remove a Mega account
async def remove_mega_account(event, account_index):
    logging.info(f"Removing mega account for user: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        if user_id in accounts and 0 <= account_index < len(accounts[user_id]):
            removed_email = accounts[user_id].pop(account_index)['email']
            save_accounts(accounts)
            
            # Remove Current mega account if it was the removed one
            if user_id in user_accounts and user_accounts[user_id]['email'] == removed_email:
                del user_accounts[user_id]

            await event.respond(f"Mega account {removed_email} removed successfully.")
        else:
            await event.respond("Invalid account number. Please use /listmega to see the account numbers.")
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
                
                # Add this download to active_downloads
                download_id = event.id
                active_downloads[download_id] = {
                   "file_path" : file_path,
                    "cancel" : False
                }

                global total_files_uploaded
                total_files_uploaded += 1

                logging.info(f"Downloading to {file_path}")
                await bot.download_media(event.message, file=file_path, progress_callback=lambda current, total: download_progress_callback_helper(current, total, progress_message, start_time, True, download_id))

                # Check if download has been cancelled
                if active_downloads[download_id]['cancel']:
                   await bot.edit_message(progress_message, "Download Cancelled by User")
                   return

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
                   await event.respond("No Mega accounts configured. Use /settings to add one.")
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
                if download_id in active_downloads:
                   del active_downloads[download_id]   
        logging.info(f"Finished handle_message from: {event.sender_id}")

# Define command handler for /admin
@bot.on(events.NewMessage(pattern='/admin'))
async def admin_command(event):
    logging.info(f"Handling /admin command from: {event.sender_id}")
    user_id = str(event.sender_id)
    if int(user_id) not in ADMIN_USER_IDS:
        await event.respond("You are not authorized to use this command.")
        return
    
    logged_users_count = len(get_logged_users())
    
    admin_message = (
         f"**Bot Admin Panel**\n\n"
         f"Total Users: {total_users}\n"
         f"Total Files Uploaded: {total_files_uploaded}\n"
         f"Logged Users: {logged_users_count}\n"
    )
    
    buttons = ReplyInlineMarkup(rows=[
            KeyboardButtonRow(buttons=[
                KeyboardButtonCallback(text='Clear Logged Users', data=b'clear_logged_users')
            ])
        ])
        
    await bot.send_message(event.chat_id, admin_message, buttons=buttons)
    logging.info(f"Finished handling /admin command from: {event.sender_id}")
    
# Function to display the settings menu
async def settings_menu(event):
    buttons = ReplyInlineMarkup(rows=[
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Add Mega Account", data=b"add_mega"),
            KeyboardButtonCallback(text="List Mega Accounts", data=b"list_mega"),
        ]),
        KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Switch Mega Account", data=b"switch_mega"),
            KeyboardButtonCallback(text="Remove Mega Account", data=b"remove_mega"),
        ]),
         KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Check Mega Account", data=b"check_mega_account"),
            KeyboardButtonCallback(text="Show Selected Account", data=b"show_selected_account"),
        ]),
         KeyboardButtonRow(buttons=[
            KeyboardButtonCallback(text="Clear Mega Accounts", data=b"clear_mega"),
        ])
    ])
    await event.respond("Settings Menu:", buttons=buttons)

# Define command handler for /settings
@bot.on(events.NewMessage(pattern='/settings'))
async def settings_command(event):
    logging.info(f"Handling /settings command from: {event.sender_id}")
    await settings_menu(event)

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
                KeyboardButtonCallback(text='Help', data=b'help'),
                 KeyboardButtonUrl(text='Updates Channel', url='https://t.me/NxLeec')
            ])
        ])
    await bot.send_message(event.chat_id, welcome_message, buttons=buttons)
    logging.info(f"Finished handling /start command from: {event.sender_id}")

    global total_users
    total_users += 1
    
    # Send log message to the log channel
    try:
        if user_id not in get_logged_users():
            user = await bot.get_entity(event.sender_id)
            username = user.username if user.username else "No Username"
            log_message = (
               f"#New_Bot_User\n\n"
               f"» Username - {username}"
            )
            await bot.send_message(LOG_CHANNEL_ID, log_message)
            logging.info(f"Log message sent to channel: {LOG_CHANNEL_ID} for user: {event.sender_id}")
            
            add_logged_user(int(user_id), username)
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
    elif event.data.startswith(b'cancel_'):
        try:
            download_id = int(event.data[7:].decode())
            if download_id in active_downloads:
                active_downloads[download_id]['cancel'] = True
                await event.answer("Download cancelled")
                logging.info(f"Download {download_id} cancelled by user {event.sender_id}")
            else:
                await event.answer("This download session is no longer active.")
        except (ValueError, TypeError):
            await event.answer("Invalid cancel request.")
            logging.error(f"Invalid cancel request from: {event.sender_id}")
        except Exception as e:
            await event.answer("Error cancelling download")
            logging.error(f"Error cancelling download {e} from: {event.sender_id}")
    elif event.data == b'clear_logged_users':
        try:
            clear_logged_users()
            await event.answer("Logged user cache has been cleared.")
            logging.info(f"Logged user cache cleared by admin")
        except Exception as e:
                await event.answer("Failed to clear logged users cache")
                logging.error(f"Error clearing logged user cache: {e}")
    elif event.data == b'add_mega':
        await bot.send_message(event.chat_id,
            "Please send your Mega email and password in the format:\n\n`youremail@example.com yourpassword`\n\nExample:\n`test@example.com 12345678`"
        )
        
        # Register a handler for the next message
        @bot.on(events.NewMessage(from_users=event.sender_id))
        async def add_mega_account_handler(add_event):
            try:
                email, password = add_event.message.text.split()
                await add_mega_account(event, email, password)
            except ValueError:
                await event.respond("Invalid format. Please send in the format:\n\n`youremail@example.com yourpassword`\n\nExample:\n`test@example.com 12345678`")
            except Exception as e:
                logging.error(f"Error adding mega account with callback: {e}")
                await event.respond("Error adding mega account.")
            finally:
                bot.remove_event_handler(add_mega_account_handler)
    elif event.data == b'list_mega':
        await list_mega_accounts(event)
    elif event.data == b'switch_mega':
        await bot.send_message(event.chat_id, "Please send the account number you want to switch to. Example `1` or `2`")
        
        @bot.on(events.NewMessage(from_users=event.sender_id))
        async def switch_mega_account_handler(switch_event):
            try:
                account_index = int(switch_event.message.text) - 1
                await switch_mega_account(event, account_index)
            except ValueError:
                await event.respond("Invalid input. Please send a valid account number\n\nExample: `1` or `2`")
            except Exception as e:
                 logging.error(f"Error switching mega account with callback: {e}")
                 await event.respond("Error switching mega account")
            finally:
               bot.remove_event_handler(switch_mega_account_handler)
    elif event.data == b'remove_mega':
        await bot.send_message(event.chat_id,"Please send the account number you want to remove. Example: `1` or `2`")
        @bot.on(events.NewMessage(from_users=event.sender_id))
        async def remove_mega_account_handler(remove_event):
            try:
                 account_index = int(remove_event.message.text) - 1
                 await remove_mega_account(event, account_index)
            except ValueError:
                 await event.respond("Invalid input. Please send a valid account number.\n\nExample: `1` or `2`")
            except Exception as e:
                 logging.error(f"Error removing mega account with callback: {e}")
                 await event.respond("Error removing mega account")
            finally:
                bot.remove_event_handler(remove_mega_account_handler)
    elif event.data == b'check_mega_account':
        await bot.send_message(event.chat_id,"Please send the account number you want to check. Example: `1` or `2`")
        @bot.on(events.NewMessage(from_users=event.sender_id))
        async def check_mega_account_handler(check_event):
            try:
                account_index = int(check_event.message.text) - 1
                await check_mega_account(event, account_index)
            except ValueError:
                await event.respond("Invalid input. Please send a valid account number.\n\nExample: `1` or `2`")
            except Exception as e:
                logging.error(f"Error checking mega account with callback: {e}")
                await event.respond("Error checking mega account")
            finally:
               bot.remove_event_handler(check_mega_account_handler)
    elif event.data == b'show_selected_account':
        await show_selected_account(event)
    elif event.data == b'clear_mega':
        await clear_mega_accounts(event)

# New Function to check mega account
async def check_mega_account(event, account_index):
    logging.info(f"Checking mega account for user: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        if user_id in accounts and 0 <= account_index < len(accounts[user_id]):
            selected_account = accounts[user_id][account_index]
            email = selected_account['email']
            password = selected_account['password']
            
            mega = Mega()
            try:
               m = mega.login(email, password)
               accounts[user_id][account_index]['status'] = 'valid'
               if 'error' in accounts[user_id][account_index]:
                    del accounts[user_id][account_index]['error']

               save_accounts(accounts)
               await event.respond(f"Mega account {email} is valid.")
            except Exception as e:
               accounts[user_id][account_index]['status'] = 'invalid'
               accounts[user_id][account_index]['error'] = str(e)
               save_accounts(accounts)
               await event.respond(f"Mega account {email} is invalid, error {e}")
            logging.info(f"Mega account {email} check is complete for user: {event.sender_id}")
        else:
            await event.respond("Invalid account number. Please use /listmega to see the account numbers.")
    except ValueError:
        await event.respond("Invalid input. Please enter a valid number")
    except Exception as e:
        logging.error(f"Failed to check mega account for user: {event.sender_id}, Error: {e}")
        await event.respond(f"Failed to check mega account. Error: {e}")

# Function to show currently selected account
async def show_selected_account(event):
    logging.info(f"Showing selected mega account for user: {event.sender_id}")
    user_id = str(event.sender_id)
    if user_id in user_accounts and user_accounts[user_id]:
        selected_email = user_accounts[user_id]['email']
        await event.respond(f"Currently selected Mega account: {selected_email}")
    else:
        await event.respond("No Mega account is currently selected. Use /settings to select one.")

# Function to clear mega accounts
async def clear_mega_accounts(event):
    logging.info(f"Clearing mega accounts for user: {event.sender_id}")
    user_id = str(event.sender_id)
    try:
        if user_id in accounts:
            del accounts[user_id]
            save_accounts(accounts)
        
        if user_id in user_accounts:
            del user_accounts[user_id]
        await event.respond(f"All Mega accounts removed successfully.")
        logging.info(f"All Mega accounts removed successfully for user: {event.sender_id}")

    except Exception as e:
        logging.error(f"Failed to clear mega accounts for user: {event.sender_id}, Error: {e}")
        await event.respond(f"Failed to clear mega accounts. Error: {e}")
        
# Define command handler for /rename
@bot.on(events.NewMessage(pattern='/rename'))
async def rename_command(event):
    logging.info(f"Handling /rename command from: {event.sender_id}")
    user_id = str(event.sender_id)

    if user_id not in accounts or not accounts[user_id]:
        await event.respond("You have no Mega accounts added. Please use /settings to add one.")
        return

    await bot.send_message(event.chat_id, "Please send the numbers of the accounts you want to rename, separated by space, Example: `1 2 3`")
    
    @bot.on(events.NewMessage(from_users=event.sender_id))
async def rename_account_selection_handler(selection_event):
    try:
        selected_indices = list(map(int, selection_event.message.text.split()))
        
        valid_accounts = []
        invalid_indices = []
        
        # Assuming 'selected' is defined earlier in the code
        for index in selected:
            # Add your logic here, e.g., validate the index
            if index in selected_indices:
                valid_accounts.append(index)  # Example logic
            else:
                invalid_indices.append(index)

        # Example: Send response back
        await bot.send_message(event.sender_id, f"Valid: {valid_accounts}, Invalid: {invalid_indices}")

    except Exception as e:
        # Handle the error appropriately
        await bot.send_message(event.sender_id, f"An error occurred: {str(e)}")
