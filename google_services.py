import os
import json
from typing import List, Dict
from datetime import datetime
import pickle
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv
import streamlit as st
from google.oauth2 import service_account

# Load environment variables
load_dotenv(override=True)
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

__all__ = [
    'get_sheet_service',
    'get_docs_service',
    'get_drive_service',
    'get_all_sheet_names',
    'save_to_sheets',
    'save_to_docs',
    'check_sheet_exists',
    'create_sheet',
    'SPREADSHEET_ID'
]

def get_credentials():
    """Get Google API credentials from Streamlit secrets"""
    try:
        if not st.secrets.get("gcp_service_account"):
            st.error("Google service account credentials not found in secrets")
            return None
            
        credentials = service_account.Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )
        return credentials
    except Exception as e:
        st.error(f"Error getting Google credentials: {e}")
        return None

def get_sheet_service():
    """Get Google Sheets API service"""
    credentials = get_credentials()
    if not credentials:
        return None
    return build('sheets', 'v4', credentials=credentials)

def get_docs_service():
    """Get Google Docs API service."""
    creds = get_credentials()
    if not creds:
        st.error("Failed to get Google credentials")
        return None
    return build('docs', 'v1', credentials=creds)

def get_drive_service():
    """Get Google Drive API service"""
    credentials = get_credentials()
    if not credentials:
        return None
    return build('drive', 'v3', credentials=credentials)

def check_sheet_exists(sheet_service, spreadsheet_id, sheet_name):
    """Check if a sheet exists in the spreadsheet"""
    try:
        sheets = sheet_service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        return any(sheet['properties']['title'] == sheet_name for sheet in sheets['sheets'])
    except Exception as e:
        st.error(f"Error checking sheet existence: {e}")
        return False

def create_sheet(sheet_service, spreadsheet_id, sheet_name):
    """Create a new sheet in the spreadsheet"""
    try:
        body = {
            'requests': [{
                'addSheet': {
                    'properties': {
                        'title': sheet_name,
                        'gridProperties': {
                            'rowCount': 1000,
                            'columnCount': 7
                        }
                    }
                }
            }]
        }
        
        sheet_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        
        # Add headers
        headers = [
            ['Timestamp', 'Client', 'Message', 'Model', 'Temperature', 'Response', 'Summary']
        ]
        sheet_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1:G1",
            valueInputOption='RAW',
            body={'values': headers}
        ).execute()
        
        return True
    except Exception as e:
        st.error(f"Error creating sheet: {e}")
        return False

def get_all_sheet_names() -> List[str]:
    """Get all sheet names from the spreadsheet"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return ["Example Client"]
            
        spreadsheet = sheet_service.spreadsheets().get(
            spreadsheetId=st.secrets["SPREADSHEET_ID"]
        ).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        st.error(f"Error getting sheet names: {e}")
        return ["Example Client"]

def save_to_sheets(sheet_service, client_name: str, message: str, reply: str, summary: str) -> bool:
    """Save a conversation entry to sheets"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Parse replies
        reply1, reply2 = "", ""
        if "Reply 1:" in reply and "Reply 2:" in reply:
            parts = reply.split("Reply 2:")
            if len(parts) >= 2:
                reply2 = parts[1].strip()
                reply1 = parts[0].split("Reply 1:")[1].strip()
        
        # Create row with separate Reply 1 and Reply 2
        values = [[timestamp, client_name, message, reply1, reply2, reply, summary]]
        
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
    """Save content to Google Doc, appending to existing document if it exists"""
    try:
        # Format document title
        doc_title = f"{client_name}_chats"
        
        # Check if document exists
        query = f"name = '{doc_title}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, createdTime)',
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        
        try:
            if files:  # Document exists
                document_id = files[0]['id']
                
                # Verify we can access the document
                try:
                    document = docs_service.documents().get(documentId=document_id).execute()
                except Exception as e:
                    st.error(f"Cannot access existing document: {e}")
                    return {"status": "error", "message": "Cannot access existing document"}
                
                # Add a separator before new content
                content_to_add = f"\n\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n{content}"
                
                # Append content
                requests = [{
                    'insertText': {
                        'location': {'index': 1},
                        'text': content_to_add
                    }
                }]
                
                # Execute the append
                docs_service.documents().batchUpdate(
                    documentId=document_id,
                    body={'requests': requests}
                ).execute()
                
            else:  # Create new document
                document = {
                    'name': doc_title,
                    'mimeType': 'application/vnd.google-apps.document',
                }
                
                file = drive_service.files().create(
                    body=document,
                    fields='id'
                ).execute()
                
                document_id = file.get('id')
                
                if not document_id:
                    return {"status": "error", "message": "Failed to create document"}
                
                # Add initial content with timestamp
                initial_content = f"Document created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{content}"
                requests = [{
                    'insertText': {
                        'location': {'index': 1},
                        'text': initial_content
                    }
                }]
                
                docs_service.documents().batchUpdate(
                    documentId=document_id,
                    body={'requests': requests}
                ).execute()
            
            # Get the document URL
            doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return {
                "status": "success",
                "document_id": document_id,
                "document_url": doc_url,
                "message": "Successfully saved to document"
            }
            
        except Exception as e:
            st.error(f"Error during document operation: {e}")
            return {
                "status": "error",
                "message": f"Error during document operation: {str(e)}"
            }
            
    except Exception as e:
        st.error(f"Error saving to docs: {e}")
        return {
            "status": "error",
            "message": str(e)
        } 