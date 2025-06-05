import os
from typing import List, Dict
from datetime import datetime
import pickle
import google.auth
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '')  # Default to empty string

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
    """Get and cache credentials for Google APIs."""
    creds = None
    
    # First, try to use service account if we're in production
    try:
        from google.oauth2 import service_account
        if os.path.exists('/etc/secrets/credentials.json'):
            creds = service_account.Credentials.from_service_account_file(
                '/etc/secrets/credentials.json',
                scopes=SCOPES
            )
            return creds
    except Exception as e:
        print(f"Service account auth failed, falling back to OAuth: {e}")
    
    # If service account fails or we're in development, try OAuth flow
    try:
        if os.path.exists('token_sheets.pickle'):
            with open('token_sheets.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Try local credentials.json first
                cred_file = 'credentials.json'
                if not os.path.exists(cred_file):
                    cred_file = '/etc/secrets/credentials.json'
                
                flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
                try:
                    creds = flow.run_local_server(port=0)
                except Exception as e:
                    # If browser auth fails, try console auth
                    print(f"Browser auth failed, trying console: {e}")
                    creds = flow.run_console()
                    
            # Save the credentials for the next run
            with open('token_sheets.pickle', 'wb') as token:
                pickle.dump(creds, token)
                
        return creds
    except Exception as e:
        print(f"OAuth authentication failed: {e}")
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

def find_or_create_rag_spreadsheet() -> str:
    """Find existing RAG spreadsheet or create a new one."""
    try:
        drive_service = get_drive_service()
        sheet_service = get_sheet_service()
        
        # Search for existing RAG spreadsheet
        results = drive_service.files().list(
            q="name='RAG' and mimeType='application/vnd.google-apps.spreadsheet'",
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        files = results.get('files', [])
        
        if files:
            # Use the first matching spreadsheet
            spreadsheet_id = files[0]['id']
        else:
            # Create new spreadsheet
            spreadsheet = {
                'properties': {
                    'title': 'RAG'
                }
            }
            spreadsheet = sheet_service.spreadsheets().create(body=spreadsheet).execute()
            spreadsheet_id = spreadsheet['spreadsheetId']
            
            # Add default sheet with headers
            values = [['Timestamp', 'Client', 'Message', 'Reply 1', 'Reply 2', 'Final Reply', 'Summarized Reply']]
            body = {'values': values}
            sheet_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A1:G1',
                valueInputOption='RAW',
                body=body
            ).execute()
        
        return spreadsheet_id
    except Exception as e:
        print(f"Error finding/creating RAG spreadsheet: {e}")
        return None

def get_all_sheet_names() -> List[str]:
    """Get all sheet names from the spreadsheet"""
    try:
        global SPREADSHEET_ID
        sheet_service = get_sheet_service()
        
        # If no spreadsheet ID, try to find or create RAG spreadsheet
        if not SPREADSHEET_ID:
            SPREADSHEET_ID = find_or_create_rag_spreadsheet()
            if not SPREADSHEET_ID:
                return ["Example Client"]
                
        # Get all sheets
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheets = spreadsheet.get('sheets', [])
        
        # Filter out empty or invalid sheet names
        valid_names = [
            sheet['properties']['title'] 
            for sheet in sheets 
            if sheet.get('properties', {}).get('title')
        ]
        
        return valid_names if valid_names else ["Example Client"]
    except Exception as e:
        print(f"Error getting sheet names: {e}")
        return ["Example Client"]

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
        values = [['Timestamp', 'Session ID', 'Message', 'Reply 1', 'Reply 2', 'Final Reply', 'Summarized Reply']]
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

def save_to_docs(docs_service, drive_service, client_name: str, content: str) -> Dict:
    """Save content to a Google Doc"""
    try:
        # Create a new document
        doc_title = f"{client_name}_conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        document = {
            'title': doc_title
        }
        doc = docs_service.documents().create(body=document).execute()
        document_id = doc.get('documentId')
        
        # Insert content
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
            documentId=document_id,
            body={'requests': requests}
        ).execute()
        
        # Get the document URL
        doc_url = f"https://docs.google.com/document/d/{document_id}/edit"
        
        return {
            "status": "success",
            "document_id": document_id,
            "document_url": doc_url
        }
    except Exception as e:
        print(f"Error saving to docs: {e}")
        return {
            "status": "error",
            "message": str(e)
        } 
