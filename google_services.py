import os
from typing import List, Dict
from datetime import datetime
import pickle
import google.auth
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv
import streamlit as st
import json

# Load environment variables
load_dotenv(override=True)
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/documents',
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

def get_google_credentials():
    """Get credentials for Google APIs using service account."""
    try:
        # Try to get credentials from Streamlit secrets
        if hasattr(st.secrets, "gcp_service_account"):
            credentials_dict = {
                "type": st.secrets.gcp_service_account.type,
                "project_id": st.secrets.gcp_service_account.project_id,
                "private_key_id": st.secrets.gcp_service_account.private_key_id,
                "private_key": st.secrets.gcp_service_account.private_key,
                "client_email": st.secrets.gcp_service_account.client_email,
                "client_id": st.secrets.gcp_service_account.client_id,
                "auth_uri": st.secrets.gcp_service_account.auth_uri,
                "token_uri": st.secrets.gcp_service_account.token_uri,
                "auth_provider_x509_cert_url": st.secrets.gcp_service_account.auth_provider_x509_cert_url,
                "client_x509_cert_url": st.secrets.gcp_service_account.client_x509_cert_url,
                "universe_domain": st.secrets.gcp_service_account.universe_domain
            }
            return service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=SCOPES
            )
            
        # Fallback to file-based credentials for local development
        cred_paths = [
            'credentials.json',  # Local development
            '/etc/secrets/credentials.json',  # Traditional path
            '/opt/render/project/src/credentials.json'  # Render's typical path
        ]
        
        for cred_path in cred_paths:
            if os.path.exists(cred_path):
                try:
                    return service_account.Credentials.from_service_account_file(
                        cred_path,
                        scopes=SCOPES
                    )
                except Exception as e:
                    print(f"Failed to load credentials from {cred_path}: {e}")
                    continue
        
        raise FileNotFoundError("Could not find valid credentials. Please configure credentials in Streamlit Cloud secrets or provide a credentials file.")
    except Exception as e:
        print(f"Error in get_google_credentials: {e}")
        raise

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
    """Check if a sheet exists in the spreadsheet"""
    try:
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return any(sheet['properties']['title'] == sheet_name for sheet in spreadsheet.get('sheets', []))
    except Exception as e:
        print(f"Error checking sheet existence: {e}")
        return False

def create_sheet(sheet_service, spreadsheet_id: str, sheet_name: str) -> bool:
    """Create a new sheet with headers"""
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
    """Get all sheet names from the spreadsheet"""
    try:
        sheet_service = get_sheet_service()
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        return [sheet['properties']['title'] for sheet in spreadsheet.get('sheets', [])]
    except Exception as e:
        print(f"Error getting sheet names: {e}")
        return ["Example Client"]  # Fallback

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
        # Check if a document for this client already exists
        base_doc_title = f"{client_name}_chats"
        query = f"name = '{base_doc_title}' and mimeType = 'application/vnd.google-apps.document' and trashed = false"
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, createdTime)',
            orderBy='createdTime desc'
        ).execute()

        files = results.get('files', [])
        
        if files:  # If document exists, append to it
            document_id = files[0]['id']
            
            # Get the current document to find where to append
            document = docs_service.documents().get(documentId=document_id).execute()
            doc_content = document.get('body').get('content')
            end_index = doc_content[-1].get('endIndex', 1) if doc_content else 1

            # Add a separator before new content
            content_to_add = f"\n\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n\n{content}"

            # Create the request to append content
            requests = [{
                'insertText': {
                    'location': {'index': max(1, end_index - 1)},
                    'text': content_to_add
                }
            }]

            # Execute the append
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            action_result = "appended to existing document"
        else:  # Create new document
            document = {'title': base_doc_title}
            doc = docs_service.documents().create(body=document).execute()
            document_id = doc.get('documentId')

            # Add initial content with timestamp
            initial_text = f"Document created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n{content}"
            requests = [{
                'insertText': {
                    'location': {'index': 1},
                    'text': initial_text
                }
            }]

            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()

            action_result = "saved to new document"

        # Get the document URL
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
        
        return {
            "status": "success",
            "document_id": document_id,
            "document_url": doc_url,
            "message": f"Successfully {action_result}",
            "is_new_document": action_result == "saved to new document"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        } 