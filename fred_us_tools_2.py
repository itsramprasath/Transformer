#!/usr/bin/env python
# coding: utf-8

import os
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from openai import OpenAI
import anthropic
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import pickle
from datetime import datetime
import streamlit as st
import atexit

# Load environment variables
load_dotenv(override=True)

def get_api_key(key_name: str) -> str:
    """Get API key from environment or Streamlit secrets."""
    # First try Streamlit secrets
    if hasattr(st, 'secrets') and key_name in st.secrets:
        return st.secrets[key_name]
    # Then try environment variables
    return os.getenv(key_name)

# Global variables for API clients
client = None
claude = None

# Initialize API clients with proper error handling
def init_api_clients():
    """Initialize API clients with proper error handling."""
    global client, claude
    
    openai_api_key = get_api_key('OPENAI_API_KEY')
    anthropic_api_key = get_api_key('ANTHROPIC_API_KEY')
    
    if not openai_api_key:
        st.error("OpenAI API key is missing. Please add it to your Streamlit secrets.")
        client = None
    else:
        try:
            client = OpenAI(api_key=openai_api_key)
        except Exception as e:
            st.error(f"Failed to initialize OpenAI client: {e}")
            client = None
    
    if not anthropic_api_key:
        st.error("Anthropic API key is missing. Please add it to your Streamlit secrets.")
        claude = None
    else:
        try:
            # Initialize Anthropic client with proper cleanup
            claude = anthropic.Anthropic(
                api_key=anthropic_api_key,
                max_retries=3  # Add some retries for reliability
            )
            # Register cleanup function
            atexit.register(cleanup_clients)
        except Exception as e:
            st.error(f"Failed to initialize Anthropic client: {e}")
            claude = None

def cleanup_clients():
    """Cleanup function for API clients"""
    global claude
    if claude:
        try:
            # Properly close the Anthropic client
            if hasattr(claude, '_client') and hasattr(claude._client, 'close'):
                claude._client.close()
        except Exception:
            pass  # Ignore cleanup errors
        claude = None

# Initialize clients
init_api_clients()

MODEL = 'gpt-4'

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# System messages
system_message = """You are a helpful assistant. For each user message, provide two different responses labeled as 'Reply 1:' and 'Reply 2:'."""

def get_google_credentials():
    """Get and cache credentials for Google APIs."""
    creds = None
    if os.path.exists('token_sheets.pickle'):
        with open('token_sheets.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                '/etc/secrets/credentials.json',
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open('token_sheets.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def get_sheet_service():
    """Get Google Sheets API service."""
    creds = get_google_credentials()
    return build('sheets', 'v4', credentials=creds)

def get_docs_service():
    """Get Google Docs API service."""
    creds = get_google_credentials()
    return build('docs', 'v1', credentials=creds)

def get_drive_service():
    """Get Google Drive API service."""
    creds = get_google_credentials()
    return build('drive', 'v3', credentials=creds)

def check_sheet_exists(sheet_service, spreadsheet_id: str, sheet_name: str) -> bool:
    """Check if a sheet exists in the spreadsheet."""
    try:
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return any(sheet['properties']['title'] == sheet_name for sheet in spreadsheet.get('sheets', []))
    except Exception as e:
        print(f"Error checking sheet existence: {e}")
        return False

def create_sheet(sheet_service, spreadsheet_id: str, sheet_name: str) -> bool:
    """Create a new sheet with headers."""
    try:
        request = {
            'addSheet': {
                'properties': {
                    'title': sheet_name
                }
            }
        }
        body = {'requests': [request]}
        sheet_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()

        # Add headers
        values = [['Timestamp', 'Client', 'Message', 'Reply 1', 'Reply 2', 'Final Reply', 'Summarized Reply']]
        body = {'values': values}
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

def get_all_sheet_names() -> List[str]:
    """Get all sheet names from the spreadsheet."""
    try:
        sheet_service = get_sheet_service()
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        print(f"Error getting sheet names: {e}")
        return ["Example Client"]

def save_to_sheets(sheet_service, client_name: str, message: str, reply: str, summary: str) -> bool:
    """Save a conversation entry to sheets."""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [[timestamp, client_name, message, "", "", reply, summary]]
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:A"
        ).execute()
        next_row = len(result.get('values', [])) + 1
        sheet_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A{next_row}:G{next_row}",
            valueInputOption='RAW',
            body={'values': values}
        ).execute()
        return True
    except Exception as e:
        print(f"Error saving to sheets: {e}")
        return False

def save_to_docs(docs_service, drive_service, client_name: str, content: str) -> Dict[str, str]:
    """Save content to a new Google Doc and return its URL."""
    try:
        # Create a new document
        doc_title = f"{client_name}_conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        document = {
            'title': doc_title
        }
        doc = docs_service.documents().create(body=document).execute()
        doc_id = doc.get('documentId')

        # Insert the content
        requests = [
            {
                'insertText': {
                    'location': {
                        'index': 1
                    },
                    'text': content
                }
            }
        ]
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': requests}
        ).execute()

        # Get the document URL
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        return {
            "status": "success",
            "document_id": doc_id,
            "document_url": doc_url,
            "message": "Successfully created document"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def summarize_message(message: str) -> str:
    """Create a brief summary of a message."""
    try:
        if not message:
            return ""
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Create a brief 1-2 sentence summary of the following message:"},
                {"role": "user", "content": message}
            ],
            max_tokens=100
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error summarizing message: {e}")
        return "Error creating summary"

def chat_with_openai(message: str, history: List[tuple]) -> str:
    """Chat function for OpenAI API with conversation history."""
    if not client:
        return "Error: OpenAI client is not properly initialized. Please check your API key."
        
    try:
        formatted_messages = [{"role": "system", "content": system_message}]
        for msg, response in history:
            formatted_messages.extend([
                {"role": "user", "content": msg},
                {"role": "assistant", "content": response}
            ])
        formatted_messages.append({"role": "user", "content": message})
        response = client.chat.completions.create(
            model=MODEL,
            messages=formatted_messages,
            temperature=0.7,
            max_tokens=1000
        )
        response_text = response.choices[0].message.content
        if "Reply 1:" not in response_text:
            response_text = f"Reply 1: {response_text} Reply 2: Alternative response."
        return response_text
    except Exception as e:
        return f"Error with OpenAI API: {str(e)}"

def chat_with_claude(message: str, history: List[tuple]) -> str:
    """Chat function for Claude API with conversation history."""
    if not claude:
        return "Error: Anthropic client is not properly initialized. Please check your API key."
        
    try:
        formatted_messages = []
        # Add conversation history
        for msg, response in history:
            formatted_messages.extend([
                {"role": "user", "content": msg},
                {"role": "assistant", "content": response}
            ])
        # Add current message
        formatted_messages.append({"role": "user", "content": message})
        # Create the chat completion
        response = claude.messages.create(
            model="claude-3-opus-20240229",
            messages=formatted_messages,
            system=system_message,
            max_tokens=1000
        )
        response_text = response.content[0].text
        # Ensure response has both replies
        if "Reply 1:" not in response_text:
            response_text = f"Reply 1: {response_text} Reply 2: Alternative response."
        return response_text
    except Exception as e:
        return f"Error with Anthropic API: {str(e)}"

def chat(message: str, history: List[tuple], model_choice: str = "openai") -> str:
    """Main chat function that routes to the appropriate model."""
    if model_choice == "claude":
        return chat_with_claude(message, history)
    else:
        return chat_with_openai(message, history)

def parse_replies(response_text: str) -> Tuple[str, str]:
    """Parse the response text to extract Reply 1 and Reply 2."""
    try:
        if "Reply 1:" in response_text and "Reply 2:" in response_text:
            parts = response_text.split("Reply 2:")
            if len(parts) >= 2:
                reply2 = parts[1].strip()
                reply1 = parts[0].split("Reply 1:")[1].strip()
                return reply1, reply2
        return response_text, ""
    except Exception as e:
        print(f"Error parsing replies: {e}")
        return response_text, ""
