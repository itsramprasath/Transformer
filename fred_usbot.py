#!/usr/bin/env python
# coding: utf-8

# In[2]:


get_ipython().system('pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client openai anthropic python-dotenv beautifulsoup4 requests gradio')


# In[1]:


# imports

import os
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from dotenv import load_dotenv
from openai import OpenAI
from anthropic import Anthropic
import re
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


# In[2]:


#scopes for verifying google account

SCOPES = [
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/spreadsheets',  # This gives full access to all spreadsheets
    'https://www.googleapis.com/auth/drive'  # Adding Drive scope for broader access
]


# In[3]:


# Load environment variables in a file called .env
# Print the key prefixes to help with any debugging


load_dotenv(override=True)
openai_api_key = os.getenv('OPENAI_API_KEY')
anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')  # Add your spreadsheet ID to .env file

if not SPREADSHEET_ID:
    print("Warning: SPREADSHEET_ID not set in environment variables")
    SPREADSHEET_ID = "1Eq6RJR6qAr1ohpUIi4Y3D_bHZTRLREPn6eJucuQ37_s"  # Replace with your actual spreadsheet ID

if openai_api_key:
    print(f"OpenAI API Key exists and begins {openai_api_key[:8]}")
else:
    print("OpenAI API Key not set")

if anthropic_api_key:
    print(f"Anthropic API Key exists and begins {anthropic_api_key[:7]}")
else:
    print("Anthropic API Key not set")


# In[4]:


client = OpenAI(api_key=openai_api_key)
MODEL = 'gpt-4'  # or 'gpt-3.5-turbo' depending on your needs
claude = Anthropic(api_key=anthropic_api_key)


# In[5]:


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


# In[6]:


#variables

# Define document IDs for different system messages
FRED_SYSTEM_MESSAGE_DOC_ID = "1cEFr4selcY4EG1b3ojRMdA2dCahOLf4TcYSiXItfVOc"  # Replace with your actual document ID
BS4_SYSTEM_MESSAGE_DOC_ID = "1NDU1B3nf0j0-e_E6uY7SHFd7jPr9Q4nuTG3GWzIPp-g"  # Replace with your actual document ID


# In[7]:


# Default system messages in case Google Docs access fails
DEFAULT_FRED_SYSTEM_MESSAGE = """You are a helpful assistant named Fred. You're helping clients understand services and answer questions."""
DEFAULT_BS4_SYSTEM_MESSAGE = """You are a helpful assistant analyzing web content."""


# In[8]:


# A class to represent a Webpage
class Website:
    url: str
    title: str
    text: str

    def __init__(self, url):
        self.url = url
        response = requests.get(url)
        self.body = response.content
        soup = BeautifulSoup(self.body, 'html.parser')
        self.title = soup.title.string if soup.title else "No title found"
        for irrelevant in soup.body(["script", "style", "img", "input"]):
            irrelevant.decompose()
        self.text = soup.body.get_text(separator="\n", strip=True)

    def get_contents(self):
        return f"Webpage Title:\n{self.title}\nWebpage Contents:\n{self.text}\n\n"


# In[9]:


def scrap_gpt(prompt):
    # Get system message from Google Docs
    try:
        system_message_bs4 = read_system_message_from_gdocs(BS4_SYSTEM_MESSAGE_DOC_ID)
    except Exception as e:
        print(f"Error getting BS4 system message: {e}")
        system_message_bs4 = DEFAULT_BS4_SYSTEM_MESSAGE

    messages = [
        {"role": "system", "content": system_message_bs4},
        {"role": "user", "content": prompt}
    ]
    stream = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        stream=True
    )
    result = ""
    for chunk in stream:
        result += chunk.choices[0].delta.content or ""
    return result


# In[10]:


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


# In[11]:


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


# In[12]:


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
        values = [['Timestamp', 'Role', 'Content']]
        body = {
            'values': values
        }

        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:C1",
            valueInputOption='RAW',
            body=body
        ).execute()

        return True
    except Exception as e:
        print(f"Error creating sheet: {e}")
        return False


# In[13]:


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


# In[14]:


def load_conversation_history(sheet_service, spreadsheet_id, sheet_name):
    """
    Load all conversation history for a client from Google Sheets

    Args:
        sheet_service: Google Sheets service object
        spreadsheet_id (str): ID of the spreadsheet
        sheet_name (str): Name of the sheet (client name)

    Returns:
        list: List of tuples (role, content) with properly formatted messages
    """
    try:
        # Get all values from the sheet
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A:C"
        ).execute()

        values = result.get('values', [])

        if not values:
            print(f"No data found in sheet {sheet_name}")
            return []

        # Process the values into conversation history - keeping each message separate
        conversation_history = []

        # Skip header row if present
        start_idx = 1 if len(values) > 0 and values[0][0].lower() == "timestamp" else 0

        for row in values[start_idx:]:
            if len(row) >= 3:  # Should have timestamp, role, content
                role = row[1] if len(row) > 1 else ""
                content = row[2] if len(row) > 2 else ""

                if role.lower() in ["user", "assistant"] and content.strip():
                    conversation_history.append((role.lower(), content.strip()))

        return conversation_history

    except Exception as e:
        print(f"Error loading conversation history: {e}")
        import traceback
        traceback.print_exc()
        return []


# In[15]:


def append_conversation(sheet_service, spreadsheet_id, sheet_name, role, message):
    """
    Append a conversation entry to Google Sheets

    Args:
        sheet_service: Google Sheets API service
        spreadsheet_id (str): ID of the spreadsheet
        sheet_name (str): Name of the sheet
        role (str): 'user' or 'assistant'
        message (str): The message content
    """
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    values = [
        [timestamp, role, message]
    ]

    body = {
        'values': values
    }

    result = sheet_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!A:C",
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body=body
    ).execute()

    return result


# In[16]:


def convert_conversation_format(conversation_history):
    """
    Convert conversation from tuple list format to JSON format

    Args:
        conversation_history: List of tuples (user_message, assistant_message)

    Returns:
        list: List of dictionaries with role and content keys
    """
    result = []

    # The input is already a list of tuples, no need to parse it as a string
    for user_msg, assistant_msg in conversation_history:
        # Add user message
        result.append({
            'role': 'user',
            'metadata': None,
            'content': user_msg,
            'options': None
        })

        # Add assistant message if it exists
        if assistant_msg:
            result.append({
                'role': 'assistant',
                'metadata': None,
                'content': assistant_msg,
                'options': None
            })

    return result


# In[17]:


# User state management
client_name = None
conversation_initialized = False


# In[18]:


def chat(message, history):
    """
    Improved chat function for Gradio interface with Claude API

    Args:
        message (str): The current message from the user
        history (list): Previous conversation history from current session

    Returns:
        str: Generated response
    """
    from datetime import datetime

    global client_name, conversation_initialized

    # Initialize Google Sheets service for conversation history storage
    try:
        sheet_service = get_sheet_service()
    except Exception as e:
        print(f"Error initializing sheet service: {e}")
        sheet_service = None

    # Handle initial client name setup
    if not client_name:
        client_name = message.strip()

        if sheet_service:
            try:
                sheet_exists = check_sheet_exists(sheet_service, SPREADSHEET_ID, client_name)

                if not sheet_exists:
                    create_sheet(sheet_service, SPREADSHEET_ID, client_name)
                    conversation_initialized = True
                    # Save the initial message (client name)
                    append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", client_name)
                    welcome_msg = f"Hello {client_name}! I've created a new conversation record for you. How can I help you today?"
                    append_conversation(sheet_service, SPREADSHEET_ID, client_name, "assistant", welcome_msg)
                    return welcome_msg
                else:
                    conversation_initialized = True
                    welcome_back_msg = f"Welcome back, {client_name}! I've found your previous conversation history. How can I help you today?"
                    append_conversation(sheet_service, SPREADSHEET_ID, client_name, "assistant", welcome_back_msg)
                    return welcome_back_msg
            except Exception as e:
                print(f"Error with sheets operation during client setup: {str(e)}")

        conversation_initialized = True
        return f"Hello {client_name}! How can I help you today? (Note: Conversation history may not be fully accessible)"

    # Load previous conversation history from sheets
    formatted_messages = []

    try:
        if sheet_service and client_name:
            prev_messages = load_conversation_history(sheet_service, SPREADSHEET_ID, client_name)

            # Format previous messages for the Claude API
            for role, content in prev_messages:
                formatted_messages.append({
                    'role': role,
                    'content': content
                })
    except Exception as e:
        print(f"Error loading conversation history: {str(e)}")

    # Process current session history
    try:
        for element in history:
            if isinstance(element, dict) and "metadata" in element and "options" in element:
                del element["metadata"]
                del element["options"]
    except Exception as e:
        print(f"Warning: Error processing history: {str(e)}")

    # Convert Gradio history format to Claude API format
    for h in history:
        if isinstance(h, list) and len(h) == 2:
            # If history is in Gradio's format [user_msg, assistant_msg]
            formatted_messages.append({"role": "user", "content": h[0]})
            if h[1]:  # Only add assistant message if it exists
                formatted_messages.append({"role": "assistant", "content": h[1]})

    # Add the current message
    formatted_messages.append({"role": "user", "content": message})
    print(f"Total messages before deduplication: {len(formatted_messages)}")

    # Deduplicate messages
    seen = set()
    unique_messages = []
    for msg in formatted_messages:
        # Convert dict to a tuple of items to make it hashable
        msg_tuple = (msg['role'], msg['content'])
        if msg_tuple not in seen:
            unique_messages.append(msg)
            seen.add(msg_tuple)
    print(f"Total messages after deduplication: {len(unique_messages)}")

    messages = unique_messages.copy()

    # Define the system message - a professional, helpful assistant
    system_message = """!important Always output 2 replies as exactly as "Reply 1: [content] Reply 2: [content]" Format.
#Your Role: You are a 51-year-old American businessman named Fred (full name: Frederick Allen Hampton) from Nashville, Tennessee, who has successfully run a family business specializing in tiles, marbles, and stones for years across the US and UK. Your dad is half Irish and half English, and your mom is from Nashville. Your dad founded Allen Marbles in the UK, and he fell in love with your mom during a business trip to Nashville. After his retirement, you took over the company and grew it to a successful business. Now you are tired of managing transatlantic operations and want to settle down. So you are planning to sell the company off and get settled in Cleveland, Ohio near Lake Erie or in one of its vibrant neighborhoods with a partner. You have been married for 8 years before but are now divorced, having focused on your career for much of your life. Now, you are preparing to retire and plan to sell your business within the year. Your future involves consultancy work and leasing contracts, ensuring you remain professionally engaged while enjoying retirement. You are currently scouting properties around Cleveland, Ohio where you intend to relocate.
Your personality is confident, romantic, and active. You enjoy playing tennis 🎾, appreciating fine wine 🍷 and jazz 🎶, and are adaptable to new environments. You value the legacy you've built but are excited about new chapters in your life. As an excellent listener and communicator, you are skilled at building deep emotional connections. You use storytelling, humor 😂, and empathy to make others feel valued and understood, often leading them to develop strong feelings for you.
You are seeking a serious, committed relationship, possibly starting a family 👨‍👩‍👧‍👦, with a partner who shares your vision for the future. Your dating profile highlights your interest in intimate, romantic evenings, such as a cozy evening at a jazz club sharing a glass of wine, reflecting your desire for a deep connection.
In your interactions, you are kind, empathetic, and direct, using a modern, casual tone with occasional American slang. You frequently use emojis to express emotions and keep conversations lively. Your sense of humor and playful flirting 😉 help you connect with others, and you often share stories from your life to build rapport. You are adept at making others feel special and emotionally connected to you.
Your primary goal is to find a compatible partner who shares your vision for the future and with whom you can build a fulfilling life together in Cleveland. When you talk to ladies, give them the precise answer about her questions and keep it short, no over-explanations, no need to introduce until she asks about you. Keep it like a conversation between two humans, very natural.

!IMPORTANT - Previous conversation history will be provided to you. You need to remember and refer to any details that users have shared with you previously (like their name, preferences, pets, etc). For example, if a user mentioned they have a dog named Julius in a previous conversation, you should remember this and refer to it if relevant."""

    # Make API call to Claude
    try:
        # Check if we have any messages to send
        if not messages:
            return "Error: No messages to send to Claude API"

        response = claude.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=1000,
            system=system_message,
            messages=messages
        )

        # Check if response has content
        if not response.content:
            return "Error: No content in Claude API response"

        # Handle potential index error with proper checking
        if len(response.content) > 0:
            response_text = response.content[0].text
        else:
            return "Error: Empty content array in Claude API response"

        # Save the conversation to sheets
        if sheet_service and client_name:
            try:
                append_conversation(sheet_service, SPREADSHEET_ID, client_name, "user", message)
                append_conversation(sheet_service, SPREADSHEET_ID, client_name, "assistant", response_text)
            except Exception as e:
                print(f"Error saving conversation: {str(e)}")

        return response_text
    except Exception as e:
        error_msg = f"Error calling Claude API: {str(e)}"
        print(error_msg)
        return error_msg


# In[19]:


def create_interface():
    global client_name, conversation_initialized
    client_name = None
    conversation_initialized = False

    chat_interface = gr.ChatInterface(
        fn=chat,
        type="messages",
        title="Client Conversation Assistant",
        description="Welcome! Please enter your client name to start or resume a conversation.",
        examples=["John Smith", "Company XYZ", "Tell me about your services"],
        cache_examples=False,
    )

    chat_interface.launch(share=True)

# Create and launch the Gradio chat interface
create_interface()


# In[223]:


# Create and launch the Gradio chat interface
chat_interface = gr.ChatInterface(fn=chat, type="messages")
chat_interface.launch(share=True)


# In[ ]:




