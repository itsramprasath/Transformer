import os
from typing import List, Dict
from datetime import datetime
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Google API scopes
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Get spreadsheet ID from Streamlit secrets
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]

def get_google_credentials():
    """Get credentials from Streamlit secrets."""
    try:
        # Create credentials dict from Streamlit secrets
        credentials_dict = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"],
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"]
        }
        
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict,
            scopes=SCOPES
        )
        return credentials
    except Exception as e:
        st.error(f"Error getting Google credentials: {str(e)}")
        return None

def get_sheet_service():
    """Get Google Sheets API service."""
    creds = get_google_credentials()
    if creds:
        return build('sheets', 'v4', credentials=creds)
    return None

def get_docs_service():
    """Get Google Docs API service."""
    creds = get_google_credentials()
    if creds:
        return build('docs', 'v1', credentials=creds)
    return None

def get_drive_service():
    """Get Google Drive API service."""
    creds = get_google_credentials()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None

def get_all_sheet_names() -> List[str]:
    """Get all sheet names from the spreadsheet"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return ["Example Client"]
            
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
        if not sheet_service:
            return False
            
        spreadsheet = sheet_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        return any(sheet['properties']['title'] == sheet_name for sheet in spreadsheet.get('sheets', []))
    except Exception as e:
        print(f"Error checking sheet existence: {e}")
        return False

def create_sheet(sheet_service, spreadsheet_id: str, sheet_name: str) -> bool:
    """Create a new sheet with headers"""
    try:
        if not sheet_service:
            return False
            
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
        if not sheet_service:
            return False
            
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
        if not docs_service or not drive_service:
            return {
                "status": "error",
                "message": "Google services not initialized"
            }
            
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
