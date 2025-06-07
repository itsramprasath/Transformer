import streamlit as st
import os
import sys
from pathlib import Path
import uuid
from datetime import datetime
from openai import OpenAI
from anthropic import Anthropic

# Initialize API clients with keys from secrets
openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
anthropic_client = Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# Disable file watcher in production to avoid inotify limits
if not os.environ.get("DEVELOPMENT"):
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

# Disable the dimming effect and configure page
st.set_page_config(
    page_title="Client Conversation Assistant",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': None
    }
)

# Configure Streamlit theme
st.markdown("""
    <style>
        /* Modern Color Scheme - Fresh Green Theme */
        :root {
            --primary-green: #4CAF50;
            --light-green: #8BC34A;
            --pale-green: #F1F8E9;
            --accent-green: #00E676;
            --background-color: #FFFFFF;
            --text-primary: #2E3440;
            --text-secondary: #4C566A;
            --shadow-color: rgba(0, 0, 0, 0.05);
        }

        /* Main App Styling */
        .stApp {
            background: var(--background-color);
        }

        /* Hide default elements */
        .stDeployButton {display:none;}
        .stToolbar {display:none;}
        .stSpinner > div > div {border-top-color: var(--primary-green);}
        .stApp > header {display:none;}

        /* Typography */
        .stMarkdown {
            max-width: 100%;
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Buttons */
        .stButton > button {
            width: 100%;
            background: var(--primary-green) !important;
            color: white !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 12px 24px !important;
            font-weight: 500 !important;
            letter-spacing: 0.3px !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }
        .stButton > button:hover {
            transform: translateY(-1px);
            background: var(--light-green) !important;
            box-shadow: 0 4px 12px var(--shadow-color) !important;
        }

        /* Radio Buttons */
        div.row-widget.stRadio > div {
            flex-direction: row;
            background: var(--pale-green);
            padding: 16px;
            border-radius: 12px;
            gap: 12px;
        }

        /* Chat Messages */
        .stChatMessage {
            background: var(--pale-green) !important;
            border-radius: 16px !important;
            padding: 20px !important;
            margin: 12px 0 !important;
            border: 1px solid rgba(139, 195, 74, 0.2) !important;
            box-shadow: 0 2px 8px var(--shadow-color) !important;
        }

        /* User Message */
        .stChatMessage [data-testid="chatAvatarIcon-user"] {
            background: var(--light-green) !important;
        }

        /* Assistant Message */
        .stChatMessage [data-testid="chatAvatarIcon-assistant"] {
            background: var(--primary-green) !important;
        }

        /* Input Fields */
        .stTextInput > div > div {
            background: white !important;
            border-radius: 12px !important;
            border: 1px solid rgba(139, 195, 74, 0.3) !important;
            padding: 12px !important;
            color: var(--text-primary) !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }
        .stTextInput > div > div:focus-within {
            border-color: var(--primary-green) !important;
            box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2) !important;
        }

        /* Text Area */
        .stTextArea > div > div {
            background: white !important;
            border-radius: 12px !important;
            border: 1px solid rgba(139, 195, 74, 0.3) !important;
            color: var(--text-primary) !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }
        .stTextArea > div > div:focus-within {
            border-color: var(--primary-green) !important;
            box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2) !important;
        }

        /* Expander */
        .streamlit-expanderHeader {
            background: var(--pale-green) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(139, 195, 74, 0.2) !important;
            color: var(--text-primary) !important;
            font-weight: 500 !important;
        }
        .streamlit-expanderContent {
            background: white !important;
            border-radius: 0 0 12px 12px !important;
            border: 1px solid rgba(139, 195, 74, 0.2) !important;
            border-top: none !important;
            color: var(--text-primary) !important;
        }

        /* Sidebar */
        .css-1d391kg {
            background: white;
            border-right: 1px solid rgba(139, 195, 74, 0.2);
        }
        [data-testid="stSidebar"] {
            background: white;
            border-right: 1px solid rgba(139, 195, 74, 0.2);
        }
        [data-testid="stSidebar"] .stMarkdown {
            color: var(--text-primary);
        }

        /* Progress Bar */
        .stProgress > div > div > div {
            background: linear-gradient(to right, var(--light-green), var(--primary-green)) !important;
        }
        .stProgress .st-bo {
            background-color: rgba(139, 195, 74, 0.1);
        }

        /* Success/Error Messages */
        .stSuccess {
            background: var(--pale-green) !important;
            color: var(--primary-green) !important;
            border-radius: 12px !important;
            padding: 16px !important;
            border: 1px solid rgba(139, 195, 74, 0.3) !important;
        }
        .stError {
            background: #FFEBEE !important;
            color: #D32F2F !important;
            border-radius: 12px !important;
            padding: 16px !important;
            border: 1px solid rgba(211, 47, 47, 0.3) !important;
        }

        /* Chat Input */
        .stChatInputContainer {
            background: white !important;
            border-radius: 12px !important;
            border: 1px solid rgba(139, 195, 74, 0.3) !important;
            padding: 8px !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }

        /* Scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: var(--pale-green);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb {
            background: var(--light-green);
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: var(--primary-green);
        }

        /* Additional Modern UI Elements */
        .stSelectbox {
            border-radius: 12px !important;
        }
        .stSelectbox > div > div {
            background: white !important;
            border: 1px solid rgba(139, 195, 74, 0.3) !important;
            box-shadow: 0 2px 6px var(--shadow-color) !important;
        }
        
        /* Animations */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .stChatMessage {
            animation: fadeIn 0.3s ease-out;
        }
    </style>
""", unsafe_allow_html=True)

# Add the current directory to Python path
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# Import from our modules
from fred_us_tools_2 import chat, summarize_message, system_message
from google_services import (
    get_sheet_service, get_docs_service, get_drive_service,
    get_all_sheet_names, save_to_sheets, save_to_docs,
    check_sheet_exists, create_sheet,
    SPREADSHEET_ID
)

def load_chat_history(client_name):
    """Load chat history from Google Sheets and format it for context"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return []
            
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:G"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return []
            
        # Skip header row
        chat_history = []
        for row in values[1:]:
            if len(row) >= 7:  # Ensure row has all required columns
                timestamp = row[0]  # Timestamp
                message = row[2]    # Message column
                reply = row[5]      # Final Reply column
                summary = row[6]    # Summarized Reply column
                
                # Add to context history
                chat_history.append({
                    "timestamp": timestamp,
                    "user_message": message,
                    "bot_reply": reply,
                    "summary": summary
                })
                    
        return chat_history
    except Exception as e:
        st.error(f"Error loading chat history: {e}")
        return []

def get_conversation_context(chat_history, current_question):
    """Create a context for the AI by including all past interactions"""
    # Start with Fred's personality from system_message
    context = system_message + "\n\n"
    
    # Add current client info
    context += f"You are currently chatting with {st.session_state.client_name}.\n"
    
    if chat_history:
        context += "\nPrevious conversation history:\n"
        # Include all previous interactions
        for interaction in chat_history:
            timestamp = interaction.get('timestamp', 'No timestamp')
            context += f"\nTime: {timestamp}\n"
            context += f"{st.session_state.client_name}: {interaction['user_message']}\n"
            context += f"Your response: {interaction['bot_reply']}\n"
            if interaction.get('summary'):
                context += f"Summary: {interaction['summary']}\n"
            context += "---\n"
    
    context += f"\nCurrent message from {st.session_state.client_name}: {current_question}\n"
    context += "\nRespond naturally as Fred, maintaining consistency with your personality and previous interactions."
    
    return context

def save_interaction_to_sheets(sheet_service, client_name, interaction):
    """Helper function to save/update interaction in sheets with proper session tracking"""
    try:
        # Format data for sheets
        row_data = [
            interaction.get('timestamp', ''),
            interaction.get('session_id', ''),
            interaction.get('user_message', ''),
            interaction.get('reply1', ''),
            interaction.get('reply2', ''),
            interaction.get('final_reply', ''),
            interaction.get('summary', '')
        ]
        
        # If this is a retry/edit of an existing message, try to update the existing row
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{client_name}!A:H"
        ).execute()
        
        values = result.get('values', [])
        row_index = None
        
        # Look for matching session_id and message
        for idx, row in enumerate(values):
            if len(row) > 1 and row[1] == interaction['session_id'] and row[2] == interaction['user_message']:
                row_index = idx + 1  # +1 because sheets are 1-indexed
                break
        
        if row_index:
            # Update existing row
            range_name = f"{client_name}!A{row_index}:G{row_index}"
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption='RAW',
                body={'values': [row_data]}
            ).execute()
        else:
            # Append new row
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{client_name}!A:G",
                valueInputOption='RAW',
                body={'values': [row_data]}
            ).execute()
            
        return True
    except Exception as e:
        st.error(f"Error saving to sheets: {e}")
        return False

def handle_chat_input(prompt):
    if not prompt:
        return
        
    st.session_state.current_question = prompt
    
    # Get conversation context from history
    context = get_conversation_context(st.session_state.chat_history, prompt)
    
    with st.spinner("Processing..."):
        # Pass the full context as the prompt
        response = chat(context, [], st.session_state.model_choice)
    
    # Save the interaction to chat history with full details
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = summarize_message(response)
    
    # Parse replies
    reply1, reply2 = parse_replies(response)
    
    new_interaction = {
        "timestamp": current_time,
        "session_id": st.session_state.session_id,
        "user_message": prompt,
        "bot_reply": response,
        "reply1": reply1,
        "reply2": reply2,
        "final_reply": response,  # Initially same as full response
        "summary": summary
    }
    
    st.session_state.chat_history.append(new_interaction)
    st.session_state.current_response = response
    
    # Save to sheets
    try:
        sheet_service = get_sheet_service()
        if sheet_service:
            save_interaction_to_sheets(sheet_service, st.session_state.client_name, new_interaction)
    except Exception as e:
        st.error(f"Error saving to sheets: {e}")

def render_chat_interface():
    if st.session_state.show_history:
        render_chat_history_viewer()
    elif st.session_state.client_initialized:
        st.title(f"Conversation with {st.session_state.client_name}")
        
        # Chat container for better performance
        chat_container = st.container()
        
        # Chat input at the bottom
        prompt = st.chat_input(
            "Type your message here...",
            key=f"chat_input_{st.session_state.session_id}"
        )
        if prompt:
            handle_chat_input(prompt)
        
        # Display chat in the container
        with chat_container:
            # Show current interaction
            if st.session_state.current_question:
                with st.chat_message("user"):
                    st.markdown(st.session_state.current_question)
                
                if st.session_state.current_response:
                    with st.chat_message("assistant"):
                        # First show the response
                        st.markdown(st.session_state.current_response)
                        
                        # Add retry button
                        col1, col2 = st.columns([0.1, 0.9])
                        with col1:
                            retry_key = f"retry_current_{st.session_state.session_id}"
                            if st.button("🔄", key=retry_key):
                                # Regenerate response with full context
                                context = get_conversation_context(
                                    st.session_state.chat_history[:-1], 
                                    st.session_state.current_question
                                )
                                new_response = chat(context, [], st.session_state.model_choice)
                                
                                # Update the last interaction with new response
                                reply1, reply2 = parse_replies(new_response)
                                st.session_state.chat_history[-1].update({
                                    "bot_reply": new_response,
                                    "reply1": reply1,
                                    "reply2": reply2,
                                    "final_reply": new_response,
                                    "summary": summarize_message(new_response)
                                })
                                
                                # Save updated response to sheets
                                try:
                                    sheet_service = get_sheet_service()
                                    if sheet_service:
                                        save_interaction_to_sheets(
                                            sheet_service,
                                            st.session_state.client_name,
                                            st.session_state.chat_history[-1]
                                        )
                                except Exception as e:
                                    st.error(f"Error saving retry to sheets: {e}")
                                    
                                st.session_state.current_response = new_response
                                st.rerun()
            
            # Save reply interface after the chat messages
            if st.session_state.current_response:
                with st.expander("Save Reply Tool", expanded=False):
                    st.subheader("Save Reply")
                    
                    col1, col2 = st.columns([0.3, 0.7])
                    with col1:
                        reply_number = st.number_input(
                            "Reply Number (1 or 2)",
                            min_value=1,
                            max_value=2,
                            value=1,
                            key=f"reply_number_{st.session_state.session_id}"
                        )
                    
                    # Preview and edit
                    reply1, reply2 = parse_replies(st.session_state.current_response)
                    selected_reply = reply1 if reply_number == 1 else reply2
                    
                    edited_reply = st.text_area(
                        "Preview & Edit Reply",
                        value=selected_reply,
                        height=150,
                        key=f"edited_reply_{st.session_state.session_id}"
                    )
                    
                    if st.button(
                        "Save Reply",
                        key=f"save_reply_{st.session_state.session_id}",
                        use_container_width=True
                    ):
                        with st.spinner("Saving reply..."):
                            try:
                                # Update the final reply in sheets
                                st.session_state.chat_history[-1]["final_reply"] = edited_reply
                                sheet_service = get_sheet_service()
                                if sheet_service:
                                    save_interaction_to_sheets(
                                        sheet_service,
                                        st.session_state.client_name,
                                        st.session_state.chat_history[-1]
                                    )
                                st.success("Reply saved successfully!")
                            except Exception as e:
                                st.error(f"Error saving reply: {e}")
    else:
        st.title("Client Conversation Assistant")
        st.info("👈 Please select or enter a client name in the sidebar to start.")

def main():
    initialize_session_state()
    render_sidebar()
    render_chat_interface()

def initialize_session_state():
    """Initialize session state variables"""
    defaults = {
        'session_id': str(uuid.uuid4()),
        'client_name': None,
        'chat_history': [],
        'current_question': None,
        'current_response': None,
        'model_choice': "openai",
        'client_initialized': False,
        'needs_update': False,
        'show_history': False,
        'current_page': 0
    }
    
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

def parse_replies(response_text):
    """Parse the response text to extract Reply 1 and Reply 2"""
    try:
        if "Reply 1:" in response_text and "Reply 2:" in response_text:
            parts = response_text.split("Reply 2:")
            if len(parts) >= 2:
                reply2 = parts[1].strip()
                reply1 = parts[0].split("Reply 1:")[1].strip()
                return reply1, reply2
        return response_text, ""
    except Exception as e:
        st.error(f"Error parsing replies: {e}")
        return response_text, ""

def handle_start_conversation(client_name):
    if not client_name:
        st.error("Please select or enter a client name")
        return
    
    # Initialize sheet for new client
    sheet_service = get_sheet_service()
    if not sheet_service:
        st.error("Could not connect to Google Sheets")
        return
        
    if not check_sheet_exists(sheet_service, SPREADSHEET_ID, client_name):
        if create_sheet(sheet_service, SPREADSHEET_ID, client_name):
            st.success(f"Created new sheet for {client_name}")
        else:
            st.error("Failed to create sheet")
            return
    
    st.session_state.client_name = client_name
    st.session_state.client_initialized = True
    
    # Load chat history from sheets
    st.session_state.chat_history = load_chat_history(client_name)
    st.session_state.needs_update = True

def handle_clear_chat():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None
    st.session_state.needs_update = True

def handle_new_client():
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.client_name = None
    st.session_state.client_initialized = False
    st.session_state.chat_history = []
    st.session_state.current_response = None
    st.session_state.current_question = None
    st.session_state.needs_update = True

def render_sidebar():
    with st.sidebar:
        st.title("Settings")
        
        # Client selection
        st.subheader("Client Selection")
        client_names = get_all_sheet_names()
        
        if not st.session_state.client_initialized:
            selected_client = st.selectbox(
                "Select client:",
                [""] + client_names,
                key="client_selector"
            )
            
            new_client_name = st.text_input(
                "Or enter new client name:",
                key="new_client_name"
            )
            
            if st.button(
                "Start Conversation",
                key="start_conv",
                use_container_width=True
            ):
                handle_start_conversation(new_client_name or selected_client)
        
        # Model selection
        st.subheader("Model Settings")
        model = st.radio(
            "Select AI Model:",
            ["openai", "claude"],
            key="model_choice",
            horizontal=True
        )
        if model != st.session_state.model_choice:
            st.session_state.model_choice = model
        
        # Chat History Viewer
        if st.session_state.client_initialized:
            st.subheader("Chat History")
            view_history = st.button(
                "View Past Conversations",
                key="view_history",
                use_container_width=True
            )
            if view_history:
                st.session_state.show_history = True
                st.session_state.current_page = 0
        
        # Action buttons
        st.button(
            "Clear Chat",
            on_click=handle_clear_chat,
            use_container_width=True
        )
        
        st.button(
            "New Client",
            on_click=handle_new_client,
            use_container_width=True
        )
        
        # Display session info
        st.markdown("---")
        st.caption(f"Session ID: {st.session_state.session_id}")

def render_chat_history_viewer():
    """Render the chat history viewer interface"""
    # Add Back to Chat button at the top
    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        if st.button("← Back to Chat", use_container_width=True):
            st.session_state.show_history = False
            st.rerun()
    
    st.title(f"Chat History - {st.session_state.client_name}")
    
    # Get all chat history
    chat_history = st.session_state.chat_history
    
    # Add date filter
    col1, col2 = st.columns(2)
    with col1:
        # Get unique dates from chat history
        dates = sorted(list(set(
            datetime.strptime(interaction['timestamp'].split()[0], '%Y-%m-%d').date()
            for interaction in chat_history
        )), reverse=True)
        
        selected_date = st.selectbox(
            "Select Date",
            ["All"] + [date.strftime('%Y-%m-%d') for date in dates],
            key="history_date_filter"
        )
    
    with col2:
        search_query = st.text_input(
            "Search Messages",
            key="history_search"
        ).lower()
    
    # Filter chat history
    filtered_history = chat_history
    if selected_date != "All":
        filtered_history = [
            interaction for interaction in filtered_history
            if interaction['timestamp'].startswith(selected_date)
        ]
    
    if search_query:
        filtered_history = [
            interaction for interaction in filtered_history
            if search_query in interaction['user_message'].lower() or
            search_query in (interaction.get('final_reply', '') or interaction['bot_reply']).lower()
        ]
    
    # Display conversations in pages
    ITEMS_PER_PAGE = 5
    total_pages = (len(filtered_history) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    if total_pages > 0:
        page_col1, page_col2, page_col3 = st.columns([1, 3, 1])
        with page_col1:
            if st.button("Previous", disabled=st.session_state.current_page <= 0):
                st.session_state.current_page -= 1
        with page_col2:
            st.write(f"Page {st.session_state.current_page + 1} of {total_pages}")
        with page_col3:
            if st.button("Next", disabled=st.session_state.current_page >= total_pages - 1):
                st.session_state.current_page += 1
        
        start_idx = st.session_state.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(filtered_history))
        
        for idx, interaction in enumerate(filtered_history[start_idx:end_idx]):
            with st.expander(f"Conversation from {interaction['timestamp']}", expanded=True):
                # User Message
                st.markdown("**User Message:**")
                st.write(interaction['user_message'])
                
                # AI Response
                st.markdown("**AI Response:**")
                if interaction.get('final_reply'):
                    # Show the final selected and saved reply
                    st.write(interaction['final_reply'])
                else:
                    # If no final reply exists, show original response
                    st.write(interaction['bot_reply'])
                
                # Show original replies in a container instead of expander
                st.markdown("**Original Replies:**")
                toggle_key = f"show_original_{idx}"
                if toggle_key not in st.session_state:
                    st.session_state[toggle_key] = False
                
                if st.button("Toggle Original Replies", key=f"toggle_{idx}"):
                    st.session_state[toggle_key] = not st.session_state[toggle_key]
                
                if st.session_state[toggle_key]:
                    st.markdown("**Reply 1:**")
                    st.write(interaction.get('reply1', 'Not available'))
                    st.markdown("**Reply 2:**")
                    st.write(interaction.get('reply2', 'Not available'))
                
                if interaction.get('summary'):
                    st.markdown("**Summary:**")
                    st.write(interaction['summary'])
                st.divider()
    else:
        st.info("No conversations found for the selected filters.")
    
    # Add export options
    st.subheader("Export Options")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Export to CSV", use_container_width=True):
            # Convert filtered history to CSV
            csv_data = []
            for interaction in filtered_history:
                csv_data.append({
                    'Timestamp': interaction['timestamp'],
                    'User Message': interaction['user_message'],
                    'AI Response': interaction.get('final_reply', interaction['bot_reply']),
                    'Summary': interaction.get('summary', '')
                })
            
            # Create DataFrame and convert to CSV
            import pandas as pd
            df = pd.DataFrame(csv_data)
            csv = df.to_csv(index=False)
            
            # Create download button
            st.download_button(
                "Download CSV",
                csv,
                f"{st.session_state.client_name}_chat_history.csv",
                "text/csv",
                key='download-csv'
            )
    
    with col2:
        if st.button("Export to Text", use_container_width=True):
            # Convert filtered history to formatted text
            text_content = f"Chat History for {st.session_state.client_name}\n\n"
            for interaction in filtered_history:
                text_content += f"Time: {interaction['timestamp']}\n"
                text_content += f"User: {interaction['user_message']}\n"
                text_content += f"AI: {interaction.get('final_reply', interaction['bot_reply'])}\n"
                if interaction.get('summary'):
                    text_content += f"Summary: {interaction['summary']}\n"
                text_content += "-" * 80 + "\n\n"
            
            # Create download button
            st.download_button(
                "Download Text",
                text_content,
                f"{st.session_state.client_name}_chat_history.txt",
                "text/plain",
                key='download-txt'
            )

if __name__ == "__main__":
    main() 
