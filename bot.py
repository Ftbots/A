
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
from config import API_ID, API_HASH, BOT_TOKEN, MEGA_EMAIL, MEGA_PASSWORD

# Set up logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Telegram Client
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# Path for the accounts JSON file
ACCOUNTS_FILE = 'mega_accounts.json'

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
          
# Load accounts data on startup
accounts = load_accounts()

# Store currently selected Mega account for each user
user_accounts = {}

# Store queues for each user
user_queues = {}

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


# Modify the default message handler
@bot.on(events.NewMessage)
async def handle_message_default(event):
    if event.is_private and not event.message.text.startswith('/'):
      logging.info(f"Starting handle_message from: {event.sender_id}")
      user_id = str(event.sender_id)

      # Check if the message is a forward
      if event.message.forward:
        logging.info(f"Received a forwarded message from: {event.sender_id}")
        
        # Check if the forwarded message has media
        if event.message.media:
            logging.info(f"Forwarded message contains media")

            # Check if file type is supported
            file_name, file_ext = get_file_name_and_ext(event.message.media)
            if file_name:
              logging.info(f"Supported file type detected {file_name}")
            
              # Add the forwarded message to user's queue
              if user_id not in user_queues:
                user_queues[user_id] = []
              user_queues[user_id].append(event.message)
              
              queue_position = len(user_queues[user_id])
              await event.respond(f"File added to queue. Your position is: {queue_position}")

              # Log the queue
              logging.info(f"Current user queue: {user_queues[user_id]}")

            else:
                logging.info(f"Unsupported file type in forwarded message: {event.sender_id}")
                await event.respond("Unsupported file type. Please forward files with supported formats.")
            
            # Start the upload process if not already in progress
            if not hasattr(handle_message_default, 'is_uploading') or not handle_message_default.is_uploading:
              handle_message_default.is_uploading = True
              asyncio.create_task(process_upload_queue(user_id))
        else:
            logging.info(f"Forwarded message has no media: {event.sender_id}")
            await event.respond("Forwarded message has no media to process.")
      
      else:
        # If not forwarded message, handle as usual
          logging.info(f"Received a direct file from: {event.sender_id}")
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


# New function to process upload queue
async def process_upload_queue(user_id):
    logging.info(f"Starting process_upload_queue for user: {user_id}")
    
    while True:
      if user_id not in user_queues or not user_queues[user_id]:
        handle_message_default.is_uploading = False
        logging.info(f"No files in queue, process_upload_queue finished for user: {user_id}")
        break;
      
      # Get the first 10 elements of the user queue or less
      messages_to_upload = user_queues[user_id][:10]
      
      logging.info(f"Processing a batch of {len(messages_to_upload)} files for user: {user_id}")

      # Check if there's a mega account for the user
      current_mega_account = None
      if user_id in user_accounts and user_accounts[user_id]:
          current_mega_account = user_accounts[user_id]
      elif user_id in accounts and accounts[user_id]:
          current_mega_account = accounts[user_id][0]
      else:
          logging.error(f"No Mega account configured for user: {user_id}")
          
          # Remove the messages from the queue
          del user_queues[user_id][:len(messages_to_upload)]
          
          for message in messages_to_upload:
             await bot.send_message(message.chat_id, "No Mega account configured. Use /addmega <email> <password> to add one.")
          continue
      
      # Upload the batch of files
      await process_batch_uploads(user_id, messages_to_upload, current_mega_account)

      # Remove the processed messages from the queue
      del user_queues[user_id][:len(messages_to_upload)]

      logging.info(f"Batch finished. {len(user_queues[user_id])} files remaining in the queue for user: {user_id}")
      
      # If there is something to process wait for some time before proceeding
      if user_id in user_queues and user_queues[user_id]:
          await asyncio.sleep(5)
      
# New function to process the batch upload logic without concurrency
async def process_batch_uploads(user_id, messages, current_mega_account):
  logging.info(f"Starting process_batch_uploads for user: {user_id}, file count {len(messages)}")
  
  # Loop through messages in the batch
  for message in messages:
      file_path = None
      try:
          logging.info(f"Processing message: {message.id} for user: {user_id}")
          
          media = message.media

          # Extract file name and extension
          file_name, file_ext = get_file_name_and_ext(media)
          
          if file_name is not None:
            file_path = f"downloaded_file_{message.id}.{file_ext}"
          else:
              logging.error(f"File name is None, skipping this message: {message.id}")
              await bot.send_message(message.chat_id, "Error processing file upload")
              continue
              
          # Log file type
          if isinstance(media, types.MessageMediaDocument) and hasattr(media, 'document') and media.document:
              logging.info(f"File MIME type: {media.document.mime_type}")
              # Before Download
              logging.info(f"File size before download: {media.document.size}")

          start_time = time.time()
          progress_message = await bot.send_message(message.chat_id, "Starting download...")

          logging.info(f"Downloading to {file_path}")
          await bot.download_media(message, file=file_path, progress_callback=lambda current, total: download_progress_callback_helper(current, total, progress_message, start_time, True))

          # After Download
          file_size_after_download = os.path.getsize(file_path)
          logging.info(f"File size after download: {file_size_after_download}")
          
          # Upload the file to Mega
          logging.info("Uploading to mega")
          await bot.edit_message(progress_message, "Starting upload...")
          mega_link = await upload_to_mega(file_path, progress_message, current_mega_account)

          if mega_link:
            await bot.edit_message(progress_message, f"File uploaded to Mega: {mega_link}")
          else:
            await bot.edit_message(progress_message, "Failed to upload file to Mega.")

      except Exception as e:
          logging.error(f"Error processing message {message.id}: {e}")
          await bot.send_message(message.chat_id, "Error processing file upload")
      finally:
          if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Removed downloaded file: {file_path}")
  
  logging.info(f"Finished processing a batch of {len(messages)} files for user: {user_id}")

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

# Bot's callback query handler
@bot.on(events.CallbackQuery)
async def callback_query_handler(event):
   if event.data == b'help':
      await event.answer('Send /help command to show all available commands.')


# Run the bot
if __name__ == '__main__':
    logging.info("Bot started. Listening for messages...")
    bot.run_until_disconnected()
