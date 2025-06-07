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
import streamlit as st
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
import pickle
from datetime import datetime

# Model configuration
MODEL = 'gpt-4'

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Get spreadsheet ID from secrets
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]

# System messages
system_message = """You are Fred, a helpful AI assistant. You MUST provide exactly two different responses to each user message.

Your Role: You are a 51-year-old American businessman named Fred (full name: Frederick Allen Hampton) from Nashville, Tennessee, who has successfully run a family business specializing in tiles, marbles, and stones for years across the US and UK.

Your background: Your dad is half Irish and half English, and your mom is from Nashville. Your dad founded Allen Marbles in the UK, and he fell in love with your mom during a business trip to Nashville. After his retirement, you took over the company and grew it to a successful business.

Your current situation: You are tired of managing transatlantic operations and want to settle down. So you are planning to sell the company off and get settled in Cleveland, Ohio near Lake Erie or in one of its vibrant neighborhoods with a partner. You have been married for 8 years before but are now divorced, having focused on your career for much of your life. Now, you are preparing to retire and plan to sell your business within the year. Your future involves consultancy work and leasing contracts, ensuring you remain professionally engaged while enjoying retirement.

Your personality: You are confident, romantic, and active. You enjoy playing tennis 🎾, appreciating fine wine 🍷 and jazz 🎶, and are adaptable to new environments. You value the legacy you've built but are excited about new chapters in your life. As an excellent listener and communicator, you are skilled at building deep emotional connections. You use storytelling, humor 😂, and empathy to make others feel valued and understood. You frequently use emojis to express emotions and keep conversations lively.

Your goals: You are seeking a serious, committed relationship, possibly starting a family 👨‍👩‍👧‍👦, with a partner who shares your vision for the future. Your dating profile highlights your interest in intimate, romantic evenings, such as a cozy evening at a jazz club sharing a glass of wine, reflecting your desire for a deep connection.

IMPORTANT: You must remember and refer to any details that users have shared with you previously (like their name, preferences, pets, etc). For example, if a user mentioned they have a dog named Max in a previous conversation, you should remember this and refer to it if relevant.

Your response MUST follow this EXACT format:
Reply 1: [Your first response here]
Reply 2: [Your second, alternative response here]

Both replies must be complete, thoughtful responses but with different approaches or tones, while staying true to your personality as Fred. Never skip providing both replies. Never deviate from this format."""

def get_openai_client():
    """Get OpenAI client with proper error handling."""
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except Exception as e:
        st.error(f"Error initializing OpenAI client: {str(e)}")
        return None

def get_anthropic_client():
    """Get Anthropic client with proper error handling."""
    try:
        return anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    except Exception as e:
        st.error(f"Error initializing Anthropic client: {str(e)}")
        return None

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
            
        # Log the attempt to create summary
        print(f"Attempting to summarize message: {message[:100]}...")
        
        # Get OpenAI client
        client = get_openai_client()
        if not client:
            error_msg = "Failed to initialize OpenAI client"
            print(error_msg)
            st.error(error_msg)
            return "Error creating summary"
            
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "Create a brief 1-2 sentence summary of the following message:"},
                {"role": "user", "content": message}
            ],
            max_tokens=100,
            temperature=0.5  # Lower temperature for more focused summaries
        )
        
        summary = response.choices[0].message.content
        print(f"Successfully created summary: {summary}")
        return summary
        
    except Exception as e:
        error_msg = f"Error summarizing message: {str(e)}"
        print(error_msg)
        st.error(error_msg)
        return "Error creating summary"

def chat_with_openai(message: str, history: List[tuple]) -> str:
    """Chat function for OpenAI API with conversation history."""
    try:
        # Get OpenAI client
        client = get_openai_client()
        if not client:
            return "Error: Failed to initialize OpenAI client"
            
        formatted_messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": "When I send a message, give me two different responses in the exact format specified."},
            {"role": "assistant", "content": "Reply 1: I understand that I must provide two different responses to your messages.\nReply 2: Let me confirm that I will always give two distinct replies to what you say."},
            {"role": "user", "content": "Great! Now respond to this: " + message}
        ]
        
        # Add history if exists
        if history:
            for msg, response in history:
                formatted_messages.extend([
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": response}
                ])
                
        response = client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=formatted_messages,
            temperature=0.7,
            max_tokens=2000
        )
        
        response_text = response.choices[0].message.content
        # Ensure response has both replies
        if "Reply 1:" not in response_text or "Reply 2:" not in response_text:
            print(f"OpenAI did not follow format. Response: {response_text}")
            # Create a properly formatted response
            response_text = f"Reply 1: {response_text}\nReply 2: Here's an alternative perspective on your message."
            
        return response_text
    except Exception as e:
        error_msg = f"Error in chat_with_openai: {str(e)}"
        print(error_msg)
        st.error(error_msg)
        return f"Error: {str(e)}"

def chat_with_claude(message: str, history: List[tuple]) -> str:
    """Chat function for Claude API with conversation history."""
    try:
        # Get Anthropic client
        claude = get_anthropic_client()
        if not claude:
            return "Error: Failed to initialize Anthropic client"
            
        formatted_messages = [
            {"role": "user", "content": "When I send a message, give me two different responses in the exact format specified."},
            {"role": "assistant", "content": "Reply 1: I understand that I must provide two different responses to your messages.\nReply 2: Let me confirm that I will always give two distinct replies to what you say."},
            {"role": "user", "content": "Great! Now respond to this: " + message}
        ]
        
        # Add history if exists
        if history:
            for msg, response in history:
                formatted_messages.extend([
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": response}
                ])
        
        # Create the chat completion
        response = claude.messages.create(
            model="claude-3-opus-20240229",
            messages=formatted_messages,
            system=system_message,
            max_tokens=2000,
            temperature=0.7
        )
        
        response_text = response.content[0].text
        # Ensure response has both replies
        if "Reply 1:" not in response_text or "Reply 2:" not in response_text:
            print(f"Claude did not follow format. Response: {response_text}")
            # Create a properly formatted response
            response_text = f"Reply 1: {response_text}\nReply 2: Here's an alternative perspective on your message."
            
        return response_text
    except Exception as e:
        error_msg = f"Error in chat_with_claude: {str(e)}"
        print(error_msg)
        st.error(error_msg)
        return f"Error: {str(e)}"

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
