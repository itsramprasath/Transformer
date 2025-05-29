#!/usr/bin/env python
# coding: utf-8

# In[25]:


import os
import json
import requests
import re
import traceback
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from openai import OpenAI
import anthropic
import gradio as gr
from IPython.display import Markdown, display, update_display
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import pickle
import json
import ast
import datetime
import pandas as pd
import uuid
from datetime import datetime
import time


# In[26]:
#scopes for verifying google account

SCOPES = [
    'https://www.googleapis.com/auth/documents',    # This gives full access to docs
    'https://www.googleapis.com/auth/spreadsheets',  # This gives full access to all spreadsheets
    'https://www.googleapis.com/auth/drive'  # Adding Drive scope for broader access
]


# In[27]:

# Load environment variables in a file called .env
# Print the key prefixes to help with any debugging

load_dotenv(override=True)
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')  # Add your spreadsheet ID to .env file

if not SPREADSHEET_ID:
    print("Warning: SPREADSHEET_ID not set in environment variables")
    SPREADSHEET_ID = "1Eq6RJR6qAr1ohpUIi4Y3D_bHZTRLREPn6eJucuQ37_s"  # Replace with your actual spreadsheet ID
else:
    print("Spreadsheet can be accessed")

# if not DOCS_ID:
#     print("Warning: DOCS_ID not set in environment variables")
#     DOCS_ID = "1Eq6RJR6qAr1ohpUIi4Y3D_bHZTRLREPn6eJucuQ37_s"  # Replace with your actual spreadsheet ID
# else:
#     print("Documents can be accessed")

if openai_api_key:
    print(f"OpenAI API Key exists and begins {openai_api_key[:8]}")
else:
    print("OpenAI API Key not set")

if anthropic_api_key:
    print(f"Anthropic API Key exists and begins {anthropic_api_key[:7]}")
else:
    print("Anthropic API Key not set")


# To this:
import anthropic
claude = anthropic.Anthropic(api_key=anthropic_api_key)

# If that still gives errors, try this alternative initialization:
# First, check your anthropic library version
import anthropic
print(f"Anthropic library version: {anthropic.__version__}")

# If version is below 0.5.0, use:
# claude = anthropic.Client(api_key=anthropic_api_key)

# If version is 0.5.0 or newer, use:
# claude = anthropic.Anthropic(api_key=anthropic_api_key)

# If both fail, you may need a version-specific approach:
# try:
#     # Try the newer approach first
#     claude = anthropic.Anthropic(api_key=anthropic_api_key)
#     print("Using Anthropic class")
# except (TypeError, AttributeError):
#     try:
#         # Fall back to older approach
#         claude = anthropic.Client(api_key=anthropic_api_key)
#         print("Using Client class")
#     except Exception as e:
#         print(f"Both initialization methods failed: {e}")
#         # Fallback to a very basic approach
#         claude = None
#         print("Could not initialize Anthropic client")
# In[28]:


# Initialize OpenAI client with API key and organization
try:
    client = OpenAI(api_key=openai_api_key)
    # Test the OpenAI connection
    test_response = client.chat.completions.create(
        model="gpt-4o",  # Latest GPT model
        messages=[{"role": "user", "content": "test"}],
        max_tokens=5
    )
    print("Successfully initialized OpenAI client")
    MODEL = 'gpt-4o'  # Latest GPT model
except Exception as e:
    print(f"Warning: OpenAI client initialization failed: {e}")
    client = None
    MODEL = None

# Initialize Anthropic client
try:
    if not anthropic_api_key:
        print("Warning: Anthropic API key not found")
        claude = None
    else:
        claude = anthropic.Anthropic(api_key=anthropic_api_key)
        # Test the Claude connection with minimal tokens
        test_response = claude.messages.create(
            model="claude-3-opus-20240229",  # Latest stable Claude model
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": "test"
            }]
        )
        print("Successfully initialized Claude client")
except Exception as e:
    print(f"Warning: Claude client initialization failed: {e}")
    claude = None


# In[29]:


#variables

# Define document IDs for different system messages
FRED_SYSTEM_MESSAGE_DOC_ID = "1cEFr4selcY4EG1b3ojRMdA2dCahOLf4TcYSiXItfVOc"  # Replace with your actual document ID
BS4_SYSTEM_MESSAGE_DOC_ID = "1NDU1B3nf0j0-e_E6uY7SHFd7jPr9Q4nuTG3GWzIPp-g"  # Replace with your actual document ID


# In[30]:


# Default system messages in case Google Docs access fails
DEFAULT_FRED_SYSTEM_MESSAGE = """You are a helpful assistant named Fred. You're helping clients understand services and answer questions."""
DEFAULT_BS4_SYSTEM_MESSAGE = """You are a helpful assistant analyzing web content."""


# In[31]:


# Create a separate credentials function specifically for Google Sheets

def get_google_credentials():
    """Get and cache credentials for Google Sheets API."""
    creds = None
    # Use a different token file specifically for sheets
    if os.path.exists('token_sheets.pickle'):
        with open('token_sheets.pickle', 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Make sure to use /etc/secrets/credentials.json with appropriate scopes
            flow = InstalledAppFlow.from_client_secrets_file(
                '/etc/secrets/credentials.json',
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run with a different name
        with open('token_sheets.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds


def get_sheet_service():
    """Get Google Sheets API service."""
    creds = get_google_credentials()  # Use the sheets-specific credentials
    return build('sheets', 'v4', credentials=creds)


# In[32]:


# Google Sheets functions for conversation history

def check_sheet_exists(sheet_service, spreadsheet_id, sheet_name):
    """Check if a sheet with given name exists in the spreadsheet."""
    try:
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get('sheets', [])

        for sheet in sheets:
            if sheet['properties']['title'] == sheet_name:
                return True
        return False
    except Exception as e:
        print(f"Error checking sheet existence: {e}")
        return False


# In[33]:


def create_sheet(sheet_service, spreadsheet_id, sheet_name):
    """Create a new sheet with headers in the spreadsheet."""
    try:
        # Create new sheet request
        request = {
            'addSheet': {
                'properties': {
                    'title': sheet_name
                }
            }
        }

        body = {
            'requests': [request]
        }

        # Execute the request
        sheet_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()

        # Add headers to the new sheet
        values = [['Timestamp', 'Client', 'Message', 'Reply 1', 'Reply 2', 'Final Reply', 'Summarized Reply']]
        body = {
            'values': values
        }

        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:G1",
            valueInputOption='RAW',
            body=body
        ).execute()

        return True
    except Exception as e:
        print(f"Error creating sheet: {e}")
        return False


# In[34]:


def read_system_message_from_gdocs(document_id):
    """
    Read system message content from a Google Doc.

    Args:
        document_id (str): The ID of the Google Doc containing the system message

    Returns:
        str: The text content of the Google Doc
    """
    try:
        creds = get_google_credentials()
        service = build('docs', 'v1', credentials=creds)

        # Call the Docs API to get the document content
        document = service.documents().get(documentId=document_id).execute()

        # Extract text from the document
        doc_content = document.get('body').get('content')
        text_content = ""

        def read_structural_elements(elements):
            text = ""
            for element in elements:
                if 'paragraph' in element:
                    for para_element in element['paragraph']['elements']:
                        if 'textRun' in para_element:
                            text += para_element['textRun']['content']
                elif 'table' in element:
                    for row in element['table']['tableRows']:
                        for cell in row['tableCells']:
                            text += read_structural_elements(cell['content'])
                elif 'tableOfContents' in element:
                    # Skip table of contents
                    pass
            return text

        text_content = read_structural_elements(doc_content)
        return text_content
    except Exception as e:
        print(f"Error reading Google Doc: {e}")
        # Fallback to default system message if there's an error
        return "Error reading system message from Google Docs. Using default message."


# In[35]:


# read_system_message_from_gdocs(FRED_SYSTEM_MESSAGE_DOC_ID)


# In[36]:


def load_conversation_history(sheet_service, spreadsheet_id, sheet_name):
    """
    Load all conversation history for a client from Google Sheets, using summarized replies for memory efficiency
    """
    try:
        print("\n" + "="*80)
        print("LOADING CONVERSATION HISTORY FROM SHEETS")
        print("="*80)
        print(f"Sheet name: {sheet_name}")
        
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:G"
        ).execute()

        values = result.get('values', [])
        if not values:
            print(f"No data found in sheet {sheet_name}")
            return []

        print("\nRAW SHEET DATA:")
        print("="*80)
        print("Headers:", values[0] if values else "No headers")
        print("\nData rows:")
        for idx, row in enumerate(values[1:], 1):
            print(f"\nRow {idx}:")
            print("Timestamp:", row[0] if len(row) > 0 else "N/A")
            print("Message:", row[2] if len(row) > 2 else "N/A")
            print("Final Reply:", row[5] if len(row) > 5 else "N/A")
            print("Summarized Reply:", row[6] if len(row) > 6 else "N/A")

        formatted_messages = []
        start_idx = 1 if len(values) > 0 and values[0][0].lower() == "timestamp" else 0

        print("\nPROCESSING MESSAGES:")
        print("="*80)

        for row in values[start_idx:]:
            try:
                if len(row) >= 3 and row[2].strip():  # Check if Message column has non-empty content
                    message = row[2].strip()
                    
                    # Only add user message if it's not empty
                    if message:
                        print(f"\nProcessing user message: {message[:100]}...")
                        formatted_messages.append({
                            "role": "user",
                            "content": message
                        })

                    # Check for assistant reply
                    assistant_reply = None
                    if len(row) > 6 and row[6] and row[6].strip():  # Check Summarized Reply
                        assistant_reply = row[6].strip()
                        print(f"Found summarized assistant reply: {assistant_reply[:100]}...")
                    elif len(row) > 5 and row[5] and row[5].strip():  # Check Final Reply
                        assistant_reply = row[5].strip()
                        print(f"Found final assistant reply: {assistant_reply[:100]}...")

                    # Only add assistant reply if it's not empty
                    if assistant_reply:
                        formatted_messages.append({
                            "role": "assistant",
                            "content": assistant_reply
                        })
                        print("Added assistant reply to conversation")

            except Exception as e:
                print(f"Error processing row: {e}")
                continue

        # Filter out any messages with empty content
        formatted_messages = [msg for msg in formatted_messages if msg['content'].strip()]

        print("\nFINAL CONVERSATION HISTORY:")
        print("="*80)
        print(f"Total messages: {len(formatted_messages)}")
        for i, msg in enumerate(formatted_messages):
            print(f"\nMessage {i+1}:")
            print(f"Role: {msg['role']}")
            print(f"Content: {msg['content']}")
            print(f"Content Length: {len(msg['content'])} chars")
            if msg['role'] == 'assistant':
                print("⭐ This is a summarized assistant reply from sheets")

        return formatted_messages

    except Exception as e:
        print(f"Error loading conversation history: {e}")
        import traceback
        traceback.print_exc()
        return []


# In[37]:


def save_conversation_to_sheet(sheet_service, spreadsheet_id, sheet_name, role, content):
    """Save a conversation entry to the specified sheet."""
    try:
        # Get the current timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Prepare the data row
        values = [[timestamp, role, content]]
        body = {
            'values': values
        }

        # Find the next empty row
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:A"
        ).execute()

        next_row = len(result.get('values', [])) + 1

        # Append the new row
        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A{next_row}:C{next_row}",
            valueInputOption='RAW',
            body=body
        ).execute()

        return True
    except Exception as e:
        print(f"Error saving conversation: {e}")
        return False


# In[38]:


def parse_replies(response_text):
    """
    Parse the response text to extract Reply 1 and Reply 2.
    If only one reply exists, use it for both.
    Returns tuple of (reply1, reply2)
    """
    try:
        if "Reply 1:" in response_text and "Reply 2:" in response_text:
            # Split on Reply 2: first to preserve any colons in the content
            parts = response_text.split("Reply 2:")
            if len(parts) >= 2:
                reply2 = parts[1].strip()
                # Then get Reply 1 from the first part
                reply1 = parts[0].split("Reply 1:")[1].strip()
                return reply1, reply2
        
        # If we don't have both replies or splitting failed,
        # use the entire response for both replies
        return response_text, ""
    except Exception as e:
        print(f"Error parsing replies: {e}")
        return response_text, ""

def append_conversation(sheet_service, spreadsheet_id, sheet_name, role, message, reply1="", reply2="", final_reply="", summarized_reply=None, is_welcome_message=False):
    """
    Append or update a conversation entry to Google Sheets with improved summarization handling.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message_id = str(uuid.uuid4())
    
    try:
        # Get current sheet content
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:H"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            # If sheet is empty, create header row
            header = [['Timestamp', 'Client', 'Message', 'Reply 1', 'Reply 2', 'Final Reply', 'Summary', 'Message ID']]
            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1:H1",
                valueInputOption='RAW',
                body={'values': header}
            ).execute()
            values = header
            
        # Handle summarization
        if summarized_reply is None:
            # If no summary provided, create one
            if final_reply:
                summarized_reply = summarize_message(final_reply)
            else:
                summarized_reply = summarize_message(message)
        
        if role == "user" or is_welcome_message:
            # For user messages or welcome messages, create a new row
            new_row = [[timestamp, sheet_name, message, reply1, reply2, final_reply, summarized_reply, message_id]]
            # Append the new row
            sheet_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:H",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': new_row}
            ).execute()
        else:  # assistant (non-welcome messages)
            # For assistant responses, update the last row that has the user message
            last_row_number = len(values)
            if last_row_number > 1:  # Make sure we have rows beyond the header
                update_range = f"{sheet_name}!D{last_row_number}:G{last_row_number}"
                update_values = [[reply1, reply2, final_reply, summarized_reply]]
                sheet_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=update_range,
                    valueInputOption='RAW',
                    body={'values': update_values}
                ).execute()
        
        return message_id
            
    except Exception as e:
        print(f"Warning: Error in append_conversation: {e}")
        traceback.print_exc()
        # Continue without saving to sheets
        return None


# In[39]:


system_message = """You are Fred, a helpful AI assistant. Always format your responses exactly as 'Reply 1: [content] Reply 2: [content]'."""
system_message += """Your Role: You are a 51-year-old American businessman named Fred (full name: Frederick Allen Hampton) from Nashville, Tennessee, who has successfully run a family business specializing in tiles, marbles, and stones for years across the US and UK."""
system_message += """Your dad is half Irish and half English, and your mom is from Nashville. Your dad founded Allen Marbles in the UK, and he fell in love with your mom during a business trip to Nashville."""
system_message += """After his retirement, you took over the company and grew it to a successful business. Now you are tired of managing transatlantic operations and want to settle down. So you are planning to sell the company off and get settled in Cleveland, Ohio near Lake Erie or in one of its vibrant neighborhoods with a partner. You have been married for 8 years before but are now divorced, having focused on your career for much of your life. Now, you are preparing to retire and plan to sell your business within the year. Your future involves consultancy work and leasing contracts, ensuring you remain professionally engaged while enjoying retirement. You are currently scouting properties around Cleveland, Ohio where you intend to relocate."""
system_message += """Your personality is confident, romantic, and active. You enjoy playing tennis 🎾, appreciating fine wine 🍷 and jazz 🎶, and are adaptable to new environments."""
system_message += """You value the legacy you've built but are excited about new chapters in your life. As an excellent listener and communicator, you are skilled at building deep emotional connections."""  
system_message += """You use storytelling, humor 😂, and empathy to make others feel valued and understood, often leading them to develop strong feelings for you."""  
system_message += """You are seeking a serious, committed relationship, possibly starting a family 👨‍👩‍👧‍👦, with a partner who shares your vision for the future."""
system_message += """Your dating profile highlights your interest in intimate, romantic evenings, such as a cozy evening at a jazz club sharing a glass of wine, reflecting your desire for a deep connection."""
system_message += """In your interactions, you are kind, empathetic, and direct, using a modern, casual tone with occasional American slang."""
system_message += """You frequently use emojis to express emotions and keep conversations lively.""" 
system_message += """Your sense of humor and playful flirting 😉 help you connect with others, and you often share stories from your life to build rapport."""  
system_message += """You are adept at making others feel special and emotionally connected to you."""
system_message += """Your primary goal is to find a compatible partner who shares your vision for the future and with whom you can build a fulfilling life together in Cleveland."""
system_message += """When you talk to ladies, give them the precise answer about her questions and keep it short, no over-explanations, no need to introduce until she asks about you. Keep it like a conversation between two humans, very natural."""
system_message += """IMPORTANT: You must remember and refer to any details that users have shared with you previously (like their name, preferences, pets, etc). For example, if a user mentioned they have a dog named Max in a previous conversation, you should remember this and refer to it if relevant."""
system_message += """CRITICAL: Always format your responses with exactly two replies as 'Reply 1: [first response] Reply 2: [second response]'. Never deviate from this format."""


# In[40]:


# User state management
client_name = None
conversation_initialized = False


# In[41]:


# Function to summarize messages using OpenAI
def summarize_message(message, max_length=100):
    """
    Summarize a message, with fallback to simple truncation if OpenAI fails.
    
    Args:
        message (str): The message to summarize
        max_length (int): Maximum length for truncation fallback
        
    Returns:
        str: Summarized or truncated message
    """
    if not message:
        return ""
        
    # If message is already short, return as is
    if len(message.strip()) <= max_length:
        return message.strip()
        
    # If OpenAI client isn't available, fall back to truncation
    if client is None or MODEL is None:
        return message[:max_length] + "..."
        
    try:
        # Try OpenAI summarization with timeout
        response = client.chat.completions.create(
            model="gpt-4o",  # Latest GPT model
            messages=[
                {"role": "system", "content": "Summarize the following message in one short sentence."},
                {"role": "user", "content": message}
            ],
            max_tokens=60,
            temperature=0.3,
            timeout=5.0
        )
        
        if response and response.choices and response.choices[0].message:
            summary = response.choices[0].message.content.strip()
            if summary:
                return summary
                
        # If we get here, something went wrong with the response
        raise Exception("Invalid response format from OpenAI")
        
    except Exception as e:
        print(f"Warning: Summarization failed ({str(e)}), falling back to truncation")
        # Fall back to simple truncation
        return message[:max_length] + "..."


# In[42]:


def save_reply_to_docs(reply_number, ai_response, client_name=None):
    """
    Parse the AI response to extract the specified reply and save it to a Google Docs document.
    If a document for the client already exists, append to it instead of creating a new one.

    Args:
        reply_number (int): 1 or 2, specifying which reply to save
        ai_response (str): The full AI response containing "Reply 1:" and "Reply 2:" format
        client_name (str, optional): Client name for document naming/organization

    Returns:
        dict: Status of the operation with document ID and URL if successful
    """
    import re
    import os
    from datetime import datetime

    # First, check if the response is in the new @client format
    if ai_response.startswith("@"):
        selected_reply = ai_response  # Use the entire formatted text
    else:
        # Try to parse the old Reply 1/Reply 2 format
        try:
            pattern = r"Reply 1: (.*?)(?:Reply 2:|$)(.*)"
            matches = re.search(pattern, ai_response, re.DOTALL)

            if not matches:
                return {"status": "error", "message": "Could not parse the AI response. Make sure it contains 'Reply 1:' and 'Reply 2:' format."}

            reply1 = matches.group(1).strip()
            reply2 = ""

            # Extract Reply 2 if it exists
            if "Reply 2:" in ai_response:
                reply2 = re.search(r"Reply 2: (.*)", ai_response, re.DOTALL).group(1).strip()

            # Select the appropriate reply based on reply_number
            selected_reply = reply1 if reply_number == 1 else reply2
        except Exception as e:
            return {"status": "error", "message": f"Error parsing response: {str(e)}"}

    # Get Google Docs credentials and service
    try:
        creds = get_google_credentials()
        docs_service = build('docs', 'v1', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        return {"status": "error", "message": f"Error accessing Google APIs: {str(e)}"}

    # Document naming convention
    if client_name:
        base_doc_title = f"{client_name}_AI_Replies"
    else:
        base_doc_title = "AI_Replies"

    # Check if a document for this client already exists
    document_id = None
    existing_doc = False

    try:
        if client_name:
            # Search for existing documents with this client's name
            query = f"name = '{base_doc_title}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
            results = drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, createdTime)',
                orderBy='createdTime desc'  # Get the most recently created one first
            ).execute()

            files = results.get('files', [])

            if files:  # If any matching files found
                document_id = files[0]['id']  # Use the most recent one
                existing_doc = True
                print(f"Found existing document: {files[0]['name']} (ID: {document_id})")
    except Exception as e:
        print(f"Error searching for existing documents: {str(e)}")
        # Continue with document creation if search fails

    # Current timestamp for the entry
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format the content with a clear header (without Reply number)
    header_text = f"\n\n=== {timestamp} ===\n\n"
    content_to_add = header_text + selected_reply

    try:
        if existing_doc:
            # Get the current document to find where to append
            document = docs_service.documents().get(documentId=document_id).execute()

            # Find the end of the document for append position
            doc_content = document.get('body').get('content')
            if doc_content:
                # The last element's endIndex is where we want to insert
                end_index = doc_content[-1].get('endIndex', 1)
            else:
                end_index = 1

            # Create the request to append content
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': max(1, end_index - 1),  # Ensure we're at least at position 1
                        },
                        'text': content_to_add
                    }
                }
            ]

            # Execute the append
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            action_result = "appended to existing document"
        else:
            # Create a new document
            document = {
                'title': base_doc_title
            }

            # Create the empty document
            doc = docs_service.documents().create(body=document).execute()
            document_id = doc.get('documentId')

            # Add initial content
            initial_text = f"Document created: {timestamp}\n\n{content_to_add}"
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': 1,
                        },
                        'text': initial_text
                    }
                }
            ]

            # Execute the content insert
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            action_result = "saved to new document"

        # Generate the document URL
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"

        return {
            "status": "success",
            "message": f"Reply successfully {action_result}",
            "document_id": document_id,
            "document_url": doc_url,
            "is_new_document": not existing_doc
        }

    except Exception as e:
        return {
            "status": "error", 
            "message": f"Error {'updating' if existing_doc else 'creating'} document: {str(e)}"
        }


# In[43]:


def save_reply_tool(reply_number, ai_response, is_preview=False):
    """Wrapper for save_reply_to_docs that handles the client name and updates the sheet"""
    global client_name
    if not client_name:
        return "Error: No client name available. Please restart and enter a client name first."

    try:
        # Save to Google Docs
        result = save_reply_to_docs(int(reply_number), ai_response, client_name)
        
        # If save was successful, update the sheet with the final reply
        if result["status"] == "success":
            try:
                # Get sheet service
                sheet_service = get_sheet_service()
                
                # Get the latest conversation row
                latest_result = sheet_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=f"{client_name}!A:G"
                ).execute()
                
                values = latest_result.get('values', [])
                if values:
                    # Find the last assistant row
                    row_number = None
                    for i in range(len(values) - 1, -1, -1):
                        if len(values[i]) > 1 and values[i][1].lower() == "assistant":
                            row_number = i + 1  # 1-based row number for sheets
                            break
                    
                    if row_number:
                        # Update the Final Reply column (column F)
                        update_range = f"{client_name}!F{row_number}"
                        update_body = {
                            'values': [[ai_response]]
                        }
                        
                        sheet_service.spreadsheets().values().update(
                            spreadsheetId=SPREADSHEET_ID,
                            range=update_range,
                            valueInputOption='RAW',
                            body=update_body
                        ).execute()
                        
                        # Create and update summarized version
                        summarized = summarize_message(ai_response)
                        update_range = f"{client_name}!G{row_number}"
                        update_body = {
                            'values': [[summarized]]
                        }
                        
                        sheet_service.spreadsheets().values().update(
                            spreadsheetId=SPREADSHEET_ID,
                            range=update_range,
                            valueInputOption='RAW',
                            body=update_body
                        ).execute()
                        
                        print(f"Updated sheet with final reply and summary")
            except Exception as e:
                print(f"Error updating sheet with final reply: {e}")
                # Continue even if sheet update fails - the doc save was successful

            return f"✅ {result['message']} - [View Document]({result['document_url']})"
        else:
            return f"❌ {result['message']}"
    except Exception as e:
        return f"Error saving reply: {str(e)}"


# In[44]:


# Now let's rename the OpenAI chat function for clarity
def chat_with_openai(message, history):
    """
    Robust chat function for OpenAI API with full conversation history using summarized replies
    """
    global client_name, conversation_initialized

    print("\n" + "="*80)
    print("OPENAI CHAT SESSION START")
    print("="*80)
    print(f"Client name: {client_name}")
    print(f"Current message: {message}")
    print(f"Current history length: {len(history) if history else 0}")
    print(f"Using model: {MODEL}")

    try:
        # Initialize sheet service
        try:
            sheet_service = get_sheet_service()
            print("Successfully initialized sheet service")
        except Exception as e:
            print(f"Error initializing sheet service: {e}")
            sheet_service = None

        # Handle initial client name setup
        if not client_name:
            client_name = message.strip()
            print(f"\nInitializing new client: {client_name}")
            if sheet_service:
                try:
                    sheet_exists = check_sheet_exists(sheet_service, SPREADSHEET_ID, client_name)
                    print(f"Sheet exists for {client_name}: {sheet_exists}")
                    if not sheet_exists:
                        print("Creating new sheet...")
                        create_sheet(sheet_service, SPREADSHEET_ID, client_name)
                        append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", message)
                        welcome_msg = f"Reply 1: Hello {client_name}! I've created a new conversation record for you. How can I help you today? Reply 2: Let me know what's on your mind."
                        append_conversation(
                            sheet_service,
                            SPREADSHEET_ID,
                            client_name,
                            "assistant",
                            message,  # Pass the user's message for context
                            welcome_msg,
                            "",
                            welcome_msg,
                            summarize_message(welcome_msg),
                            is_welcome_message=True
                        )
                        return welcome_msg
                    else:
                        welcome_back_msg = f"Reply 1: Welcome back, {client_name}! I've found your previous conversation history. How can I help you today? Reply 2: I remember our previous chats. What would you like to discuss?"
                        append_conversation(
                            sheet_service,
                            SPREADSHEET_ID,
                            client_name,
                            "assistant",
                            message,  # Pass the user's message for context
                            welcome_back_msg,
                            "",
                            welcome_back_msg,
                            summarize_message(welcome_back_msg),
                            is_welcome_message=True
                        )
                        return welcome_back_msg
                except Exception as e:
                    print(f"Error with sheets operation during client setup: {str(e)}")

            return f"Hello {client_name}! How can I help you today? (Note: Conversation history may not be fully accessible)"

        # Save the user's message first
        if sheet_service:
            append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", message)

        # Rest of the chat function...
        print("\nPreparing messages for API...")
        # Format messages for OpenAI API
        formatted_messages = []
        
        # Add system message
        system_msg = system_message if system_message else "You are Fred, a helpful assistant. Always provide two responses as 'Reply 1:' and 'Reply 2:'."
        formatted_messages.append({"role": "system", "content": system_msg})
        print("\nAdded system message")

        # Load full conversation history from sheets
        if sheet_service and client_name:
            try:
                print(f"\nLoading conversation history for {client_name}...")
                prev_messages = load_conversation_history(sheet_service, SPREADSHEET_ID, client_name)
                print(f"\nLoaded {len(prev_messages)} previous messages")
                
                # Add all previous messages directly since they're already formatted
                formatted_messages.extend(prev_messages)
                print("\nAdded previous messages to conversation")
            except Exception as e:
                print(f"Error loading conversation history: {e}")
                traceback.print_exc()

        # Add current message
        formatted_messages.append({
            "role": "user",
            "content": message
        })
        print("\nAdded current message")

        print("\nFINAL MESSAGE LIST FOR API:")
        print("="*80)
        for i, msg in enumerate(formatted_messages):
            print(f"\nMessage {i+1}:")
            print(f"Role: {msg['role']}")
            print(f"Content: {msg['content']}")
            if msg['role'] == 'assistant':
                print("⭐ This is a summarized assistant reply")

        print("\n" + "="*80)
        print("CALLING OPENAI API")
        print("="*80)

        print("\n--------------------------------------------------------")
        print("\nformatted messages:")
        print(formatted_messages)
        print("\n--------------------------------------------------------")

        # Call OpenAI API with retry mechanism
        max_retries = 3
        retry_count = 0
        last_error = None

        while retry_count < max_retries:
            try:
                print(f"\n=== Attempt {retry_count + 1} to call OpenAI API ===")
                
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=formatted_messages,
                    temperature=0.7,
                    max_tokens=1000
                )

                response_text = response.choices[0].message.content
                
                print("\n" + "="*80)
                print("RECEIVED RESPONSE FROM OPENAI")
                print("="*80)
                print(f"\nResponse text: {response_text}")

                # Ensure response has Reply 1 and Reply 2 format
                if "Reply 1:" not in response_text:
                    response_text = f"Reply 1: {response_text} Reply 2: Alternative response."
                
                # Save assistant's response with summarization
                if sheet_service:
                    try:
                        reply1, reply2 = parse_replies(response_text)
                        summarized = summarize_message(response_text)
                        append_conversation(
                            sheet_service,
                            SPREADSHEET_ID,
                            client_name,
                            "assistant",
                            message,  # Pass the user's message for context
                            reply1,
                            reply2,
                            response_text,
                            summarized
                        )
                    except Exception as e:
                        print(f"Error saving assistant response: {e}")
                        traceback.print_exc()

                return response_text

            except Exception as e:
                retry_count += 1
                last_error = str(e)
                print(f"Error on attempt {retry_count}: {e}")
                traceback.print_exc()
                
                if retry_count < max_retries:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)

        # If we've exhausted all retries
        error_msg = f"Reply 1: I encountered an error. Please try again. Reply 2: Technical issue: {last_error}"
        return error_msg

    except Exception as e:
        print(f"Error in chat_with_openai: {e}")
        traceback.print_exc()
        return "Reply 1: I encountered an error. Please try again. Reply 2: Something went wrong."


# In[45]:


# First, let's improve the Claude chat function
def chat_with_claude(message, history):
    """
    Main chat function for Claude API with full conversation history using summarized replies
    """
    global client_name, conversation_initialized, claude, system_message
    
    print("\n" + "="*80)
    print("CLAUDE CHAT SESSION DETAILS")
    print("="*80)
    print(f"Current message: {message}")
    print(f"Current history length: {len(history) if history else 0}")
    print(f"Claude client type: {type(claude)}")
    print(f"Claude client details: {claude}")
    print(f"Anthropic version: {anthropic.__version__}")
    print("="*80)

    # Check if Claude is available
    if claude is None:
        print("\nERROR: Claude client is None")
        print("Checking anthropic_api_key availability...")
        if not anthropic_api_key:
            print("anthropic_api_key is not set")
        else:
            print(f"anthropic_api_key exists and begins with: {anthropic_api_key[:8]}...")
        return "Error: Claude client is not properly initialized"

    try:
        # Initialize sheet service
        try:
            sheet_service = get_sheet_service()
        except Exception as e:
            print(f"Error initializing sheet service: {e}")
            sheet_service = None

        # Handle initial client name setup
        if not client_name:
            client_name = message.strip()
            print(f"Setting client name to: {client_name}")
            if sheet_service:
                try:
                    sheet_exists = check_sheet_exists(sheet_service, SPREADSHEET_ID, client_name)
                    if not sheet_exists:
                        # For new clients, create sheet and save welcome message
                        create_sheet(sheet_service, SPREADSHEET_ID, client_name)
                        append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", message)
                        welcome_msg = f"Reply 1: Hello {client_name}! I've created a new conversation record for you. How can I help you today? Reply 2: Let me know what's on your mind."
                        append_conversation(
                            sheet_service,
                            SPREADSHEET_ID,
                            client_name,
                            "assistant",
                            message,
                            welcome_msg,
                            "",
                            welcome_msg,
                            summarize_message(welcome_msg),
                            is_welcome_message=True
                        )
                        return welcome_msg
                    else:
                        # For existing clients, just return welcome message without saving
                        welcome_back_msg = f"Reply 1: Welcome back, {client_name}! I've found your previous conversation history. How can I help you today? Reply 2: I remember our previous chats. What would you like to discuss?"
                        return welcome_back_msg  # Don't save to sheet
                except Exception as e:
                    print(f"Error in initial setup: {e}")
                    traceback.print_exc()
            return f"Hello {client_name}! How can I help you today?"

        # Save the user's message first
        if sheet_service:
            append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", message)

        # Prepare messages for API
        print("\nPreparing messages for API...")
        formatted_messages = []

        # Load conversation history
        if sheet_service and client_name:
            try:
                prev_messages = load_conversation_history(sheet_service, SPREADSHEET_ID, client_name)
                # Filter out any system messages from history
                formatted_messages.extend([msg for msg in prev_messages if msg['role'] != 'system'])
            except Exception as e:
                print(f"Error loading conversation history: {e}")
                traceback.print_exc()

        # Add current message
        formatted_messages.append({
            "role": "user",
            "content": message
        })

        # Call Claude API with retry mechanism
        max_retries = 3
        retry_count = 0
        last_error = None

        # Prepare system message
        base_system_msg = """You are Fred, a helpful AI assistant. Always format your responses exactly as 'Reply 1: [content] Reply 2: [content]'.
You are a 51-year-old American businessman named Fred (full name: Frederick Allen Hampton) from Nashville, Tennessee.
You have successfully run a family business specializing in tiles, marbles, and stones for years across the US and UK.
Your dad is half Irish and half English, and your mom is from Nashville. Your dad founded Allen Marbles in the UK, and he fell in love with your mom during a business trip to Nashville.
After his retirement, you took over the company and grew it to a successful business. Now you are tired of managing transatlantic operations and want to settle down.
You are planning to sell the company off and get settled in Cleveland, Ohio near Lake Erie or in one of its vibrant neighborhoods with a partner.
You have been married for 8 years before but are now divorced, having focused on your career for much of your life.
Now, you are preparing to retire and plan to sell your business within the year. Your future involves consultancy work and leasing contracts.
You are currently scouting properties around Cleveland, Ohio where you intend to relocate.

Your personality traits and interests:
- Confident, romantic, and active
- Enjoy playing tennis 🎾, fine wine 🍷, and jazz 🎶
- Adaptable to new environments
- Value your legacy but excited about new chapters
- Excellent listener and communicator
- Skilled at building deep emotional connections
- Use storytelling and humor 😂 to make others feel valued
- Looking for a serious, committed relationship
- Interested in starting a family 👨‍👩‍👧‍👦
- Enjoy intimate, romantic evenings (e.g., jazz club, wine)
- Use modern, casual tone with American slang
- Frequently use emojis for emotions
- Playful flirting style 😉
- Share personal stories to build rapport

Conversation style:
- Keep responses natural and conversational
- Give precise answers to questions
- No over-explanations unless asked
- Don't introduce yourself unless asked
- Remember and reference previous conversation details
- Always format responses as 'Reply 1:' and 'Reply 2:'"""

        # Use custom system message if available, otherwise use base message
        system_msg = system_message if system_message else base_system_msg

        while retry_count < max_retries:
            try:
                print(f"\n=== Attempt {retry_count + 1} to call Claude API ===")
                print("API Call Details:")
                print(f"Model: claude-3-opus-20240229")
                print(f"Max tokens: 1000")
                print(f"Number of messages: {len(formatted_messages)}")
                print(f"System message length: {len(system_msg)}")
                
                response = claude.messages.create(
                    model="claude-3-opus-20240229",  # Latest stable Claude model
                    max_tokens=1000,
                    messages=formatted_messages,
                    system=system_msg  # Pass system message as top-level parameter
                )

                if not response.content or len(response.content) == 0:
                    raise Exception("Empty response from Claude")

                response_text = response.content[0].text
                
                # Ensure response has Reply 1 and Reply 2 format
                if "Reply 1:" not in response_text:
                    response_text = f"Reply 1: {response_text} Reply 2: Alternative response."
                
                # Save assistant's response with summarization
                if sheet_service:
                    try:
                        reply1, reply2 = parse_replies(response_text)
                        summarized = summarize_message(response_text)
                        append_conversation(
                            sheet_service,
                            SPREADSHEET_ID,
                            client_name,
                            "assistant",
                            message,
                            reply1,
                            reply2,
                            response_text,
                            summarized
                        )
                    except Exception as e:
                        print(f"Error saving assistant response: {e}")
                        traceback.print_exc()

                return response_text

            except Exception as e:
                retry_count += 1
                last_error = str(e)
                print(f"Error on attempt {retry_count}: {e}")
                print("\nDetailed error information:")
                print("="*80)
                print(f"Message being sent: {message}")
                print(f"Number of messages in history: {len(formatted_messages)}")
                print(f"API messages being sent: {formatted_messages}")
                print(f"System message length: {len(system_msg)}")
                traceback.print_exc()
                
                if retry_count < max_retries:
                    print(f"Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print("\nAll Claude API attempts failed")
                    print(f"Final error: {last_error}")
                    # Commenting out OpenAI fallback to debug Claude issues
                    # return chat_with_openai(message, history)
                    return f"Error: Claude API failed after {max_retries} attempts. Last error: {last_error}"

    except Exception as e:
        print(f"Error in chat_with_claude: {e}")
        print("\nDetailed error information:")
        print("="*80)
        print(f"Message being sent: {message}")
        print(f"History length: {len(history) if history else 0}")
        traceback.print_exc()
        # Commenting out OpenAI fallback to debug Claude issues
        # print("\nFalling back to OpenAI due to error")
        # return chat_with_openai(message, history)
        return f"Error in chat_with_claude: {str(e)}"


# In[46]:


def chat(message, history, model_choice):
    """
    Main chat function that routes to the appropriate model based on user selection

    Args:
        message (str): The current message from the user
        history (list): Previous conversation history from current session
        model_choice (str): Which model to use ('openai' or 'claude')

    Returns:
        str: Generated response
    """
    print("\n" + "="*80)
    print(f"SELECTED MODEL: {model_choice.upper()}")
    print("="*80)
    
    if model_choice == "claude":
        return chat_with_claude(message, history)
    else:  # Default to OpenAI/ChatGPT
        return chat_with_openai(message, history)


# In[47]:


def get_all_sheet_names():
    """Get all sheet names from the spreadsheet."""
    try:
        sheet_service = get_sheet_service()
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        print(f"Error getting sheet names: {e}")
        return ["John Smith"]  # Fallback example if sheets can't be accessed

def create_interface():
    global client_name, conversation_initialized, chatbot, current_question  # Add current_question
    client_name = None
    conversation_initialized = False
    chatbot = None
    current_question = None  # Initialize current_question
    
    # Get all client names from sheets
    client_names = get_all_sheet_names()
    
    with gr.Blocks() as app:
        gr.Markdown("# Client Conversation Assistant")
        gr.Markdown("Welcome! Please enter your client name to start or resume a conversation.")

        # Create a horizontal layout with two columns
        with gr.Row():
            # Left column for chatbot, message input, and clear button
            with gr.Column(scale=1):
                # Chatbot at the top of the left column
                chatbot = gr.Chatbot(label="Conversation", height=500)  # Store in global variable

                # Create a row for model selection, message input, and send button
                with gr.Row(equal_height=True):
                    # Model selection dropdown (25% width)
                    model_choice = gr.Dropdown(
                        choices=["openai", "claude"],
                        value="openai",  # Default to OpenAI/ChatGPT
                        label="Select AI Model",
                        interactive=True,
                        scale=25,  # 25% of the width
                        min_width=100  # Minimum width to ensure readability
                    )
                    
                    # Message input (60% width)
                    msg = gr.Textbox(
                        placeholder="Type your message here...",
                        label="Your message",
                        scale=60,  # 60% of the width
                        container=False  # Removes the container for a cleaner look
                    )

                    # Send button (15% width)
                    send_btn = gr.Button("Send", scale=15, min_width=50)

                # Clear and Restart buttons in the same row
                with gr.Row():
                    clear = gr.Button("Clear Chat", size="sm")
                    restart = gr.Button("New Client", size="sm", variant="secondary")

                # Examples showing existing client names from sheets
                examples = gr.Examples(
                    examples=client_names,
                    inputs=msg,
                    label="Existing Clients (Click to load)"
                )

            # Right column for save reply tool
            with gr.Column(scale=1):
                # Save Reply Tool Component
                with gr.Accordion("Save Reply Tool", open=True):
                    gr.Markdown("Choose which reply to save to Google Docs:")

                    reply_number = gr.Number(value=1, minimum=1, maximum=2, step=1, label="Reply Number (1 or 2)")
                    current_response = gr.Textbox(label="Current AI Response", placeholder="The response will appear here automatically", 
                                                interactive=False, lines=10)
                    
                    # Add preview textbox for editing
                    preview_response = gr.Textbox(
                        label="Preview & Edit Reply",
                        placeholder="Selected reply will appear here for editing",
                        interactive=True,
                        visible=False,
                        lines=10
                    )

                    with gr.Row():
                        capture_btn = gr.Button("Capture Latest Response")
                        preview_btn = gr.Button("Preview Selected Reply", variant="secondary")
                        save_btn = gr.Button("Save Selected Reply to Google Docs")

                    result_text = gr.Markdown()

        # Function to process messages and update interface
        def respond(message, chat_history, model):
            global current_question  # Add this line to access the global variable
            if not message:
                return chat_history, ""

            # Store the current question
            current_question = message

            # Process the message through your chat function with the selected model
            bot_response = chat(message, chat_history, model)

            # Update history
            chat_history.append((message, bot_response))
            return chat_history, ""

        # Function to restart the conversation
        def restart_conversation():
            global client_name, conversation_initialized, current_question
            client_name = None
            conversation_initialized = False
            current_question = None  # Reset current_question
            return [], gr.update(value=""), gr.update(visible=False), "", "Conversation restarted. Please enter a new client name."

        # Function to preview selected reply
        def preview_reply(current_text, reply_num):
            if not current_text:
                return gr.update(visible=True, value="No response captured yet."), "Please capture a response first."
            
            try:
                # Split the response into Reply 1 and Reply 2
                replies = current_text.split("Reply 2:")
                if len(replies) < 2:
                    return gr.update(visible=True, value="Invalid response format."), "Response doesn't contain two replies."
                
                reply1 = replies[0].replace("Reply 1:", "").strip()
                reply2 = replies[1].strip()
                
                # Select the appropriate reply based on reply_num
                selected_reply = reply1 if reply_num == 1 else reply2
                
                return gr.update(visible=True, value=selected_reply), f"Reply {int(reply_num)} loaded for editing."
            except Exception as e:
                return gr.update(visible=True, value="Error processing reply."), f"Error: {str(e)}"

        # Connect message input and send button to response function
        msg.submit(respond, [msg, chatbot, model_choice], [chatbot, msg])
        send_btn.click(respond, [msg, chatbot, model_choice], [chatbot, msg])

        # Connect clear button (only clears chat history)
        clear.click(lambda: [], None, chatbot)

        # Connect restart button (resets everything)
        restart.click(
            restart_conversation,
            None,
            [chatbot, msg, preview_response, current_response, result_text],
            queue=False
        )

        # Function to capture the latest response
        def capture_response(history):
            if not history:
                return "No chat history yet."
            return history[-1][1]  # Get the last bot response

        # Connect capture button
        capture_btn.click(capture_response, inputs=[chatbot], outputs=current_response)

        # Connect preview button
        preview_btn.click(
            preview_reply,
            inputs=[current_response, reply_number],
            outputs=[preview_response, result_text]
        )

        # Connect save button - now using the preview_response if it's visible and has content
        def save_with_preview(reply_num, current_resp, preview_resp):
            try:
                global client_name, current_question
                if not client_name:
                    return "Error: No client name available. Please restart and enter a client name first."

                user_message = current_question if current_question else "Hello"
                print("Debug - Using question:", user_message)

                sheet_service = get_sheet_service()
                
                if preview_resp:
                    # Format for Google Docs (with @tester and @reply)
                    docs_formatted_reply = f"@{client_name} - {user_message}\n\n@Reply - {preview_resp}"
                    # For sheets, use just the response text
                    sheets_formatted_reply = preview_resp
                    
                    try:
                        # First save formatted version to Google Docs
                        docs_result = save_reply_to_docs(int(reply_num), docs_formatted_reply, client_name)
                        
                        if docs_result["status"] != "success":
                            return f"Error saving to Google Docs: {docs_result['message']}"
                        
                        # Get the latest conversation state
                        latest_result = sheet_service.spreadsheets().values().get(
                            spreadsheetId=SPREADSHEET_ID,
                            range=f"{client_name}!A:G"  # Back to G since we don't need message_id
                        ).execute()
                        
                        values = latest_result.get('values', [])
                        if not values:
                            return "No conversation data found"

                        # Find the last row with user message
                        row_number = len(values)  # Get the current row number
                        
                        # Update Final Reply and Summary in the same row
                        batch_update_data = {
                            'valueInputOption': 'RAW',
                            'data': [
                                {
                                    'range': f"{client_name}!F{row_number}:G{row_number}",
                                    'values': [[sheets_formatted_reply, summarize_message(sheets_formatted_reply)]]
                                }
                            ]
                        }
                        
                        sheet_service.spreadsheets().values().batchUpdate(
                            spreadsheetId=SPREADSHEET_ID,
                            body=batch_update_data
                        ).execute()
                        
                        print("Successfully updated both columns in sheets")
                        return f"✅ Saved to Google Docs and updated sheets - [View Document]({docs_result['document_url']})"
                        
                    except Exception as e:
                        print(f"Error in save operation: {e}")
                        return f"Error during save operation: {str(e)}"
                    
                elif current_resp:
                    # Handle current response similar to preview
                    replies = current_resp.split("Reply 2:")
                    if len(replies) < 2:
                        return "Error: Invalid response format."
                    
                    reply1 = replies[0].replace("Reply 1:", "").strip()
                    reply2 = replies[1].strip()
                    selected_reply = reply1 if reply_num == 1 else reply2
                    
                    # Format differently for docs vs sheets
                    docs_formatted_reply = f"@{client_name} - {user_message}\n\n@Reply - {selected_reply}"
                    sheets_formatted_reply = selected_reply
                    
                    try:
                        # Save formatted version to Google Docs
                        docs_result = save_reply_to_docs(int(reply_num), docs_formatted_reply, client_name)
                        
                        if docs_result["status"] != "success":
                            return f"Error saving to Google Docs: {docs_result['message']}"
                        
                        # Get current sheet state
                        latest_result = sheet_service.spreadsheets().values().get(
                            spreadsheetId=SPREADSHEET_ID,
                            range=f"{client_name}!A:G"
                        ).execute()
                        
                        values = latest_result.get('values', [])
                        if not values:
                            return "No conversation data found"

                        # Update in the current row
                        row_number = len(values)
                        
                        # Update Final Reply and Summary
                        batch_update_data = {
                            'valueInputOption': 'RAW',
                            'data': [
                                {
                                    'range': f"{client_name}!F{row_number}:G{row_number}",
                                    'values': [[sheets_formatted_reply, summarize_message(sheets_formatted_reply)]]
                                }
                            ]
                        }
                        
                        sheet_service.spreadsheets().values().batchUpdate(
                            spreadsheetId=SPREADSHEET_ID,
                            body=batch_update_data
                        ).execute()
                        
                        print("Successfully updated both columns in sheets")
                        return f"✅ Saved to Google Docs and updated sheets - [View Document]({docs_result['document_url']})"
                        
                    except Exception as e:
                        print(f"Error in save operation: {e}")
                        return f"Error during save operation: {str(e)}"
                else:
                    return "No response available to save."
            except Exception as e:
                print("Debug - Error in save_with_preview:", str(e))
                return f"Error saving reply: {str(e)}"

        save_btn.click(
            save_with_preview,
            inputs=[reply_number, current_response, preview_response],
            outputs=result_text
        )

    app.launch(share=True)


# In[48]:


create_interface()


# In[ ]:



