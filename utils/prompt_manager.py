import streamlit as st
import docx
import io
import random
from google_services import (
    get_sheet_service,
    check_sheet_exists,
    create_sheet,
    SPREADSHEET_ID
)

# List of fun random character names
RANDOM_NAMES = [
    "Ziggy", "Nova", "Echo", "Atlas", "Phoenix", "Sage", "Luna", "Orion",
    "Aurora", "Kai", "Zephyr", "Iris", "Thorne", "Raven", "Storm", "Ash"
]

def initialize_system_prompt_state():
    """Initialize system prompt related session state variables"""
    if 'custom_system_prompt' not in st.session_state:
        st.session_state.custom_system_prompt = None
    if 'using_custom_prompt' not in st.session_state:
        st.session_state.using_custom_prompt = False
    if 'character_name' not in st.session_state:
        st.session_state.character_name = "Fred"
    if 'character_emoji' not in st.session_state:
        st.session_state.character_emoji = "👨‍💼"

def read_docx(file):
    """Read text from a .docx file"""
    doc = docx.Document(file)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return '\n'.join(full_text)

def save_character_to_sheet(name, prompt):
    """Save character data to the characters sheet"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return False
            
        # Check if characters sheet exists, create if not
        if not check_sheet_exists(sheet_service, SPREADSHEET_ID, "characters"):
            if not create_sheet(sheet_service, SPREADSHEET_ID, "characters"):
                st.error("Failed to create characters sheet")
                return False
            
            # Add headers
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range="characters!A1:B1",
                valueInputOption="RAW",
                body={"values": [["Character Name", "System Prompt"]]}
            ).execute()
        
        # Check if character already exists
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="characters!A:B"
        ).execute()
        
        values = result.get('values', [])
        row_index = None
        
        # Look for existing character
        for idx, row in enumerate(values):
            if row[0] == name:
                row_index = idx + 1  # +1 because sheets are 1-indexed
                break
        
        if row_index:
            # Update existing character
            range_name = f"characters!A{row_index}:B{row_index}"
            sheet_service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=range_name,
                valueInputOption="RAW",
                body={"values": [[name, prompt]]}
            ).execute()
        else:
            # Add new character
            sheet_service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range="characters!A:B",
                valueInputOption="RAW",
                body={"values": [[name, prompt]]}
            ).execute()
        
        return True
    except Exception as e:
        st.error(f"Error saving character: {e}")
        return False

def load_characters():
    """Load all characters from the sheet"""
    try:
        sheet_service = get_sheet_service()
        if not sheet_service:
            return []
            
        if not check_sheet_exists(sheet_service, SPREADSHEET_ID, "characters"):
            return []
            
        result = sheet_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range="characters!A:B"
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return []
            
        # Skip header row and convert to list of tuples
        return [(row[0], row[1]) for row in values[1:] if len(row) >= 2]
    except Exception as e:
        st.error(f"Error loading characters: {e}")
        return []

def get_random_name_and_emoji():
    """Generate a random character name and emoji"""
    name = random.choice(RANDOM_NAMES)
    emojis = ["🤖", "🎭", "🦸", "🧙", "🦊", "🐉", "🎪", "🎯", "🎨", "🎮"]
    emoji = random.choice(emojis)
    return name, emoji

def add_system_prompt_manager():
    """Add system prompt management UI to the sidebar"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("System Prompt Settings")
    
    # Radio button to choose between default and custom prompt
    prompt_choice = st.sidebar.radio(
        "Choose System Prompt:",
        ["Use Default", "Upload Document", "Enter Custom", "Load Saved Character"],
        key="prompt_choice"
    )
    
    if prompt_choice == "Use Default":
        st.session_state.using_custom_prompt = False
        st.session_state.custom_system_prompt = None
        st.session_state.character_name = "Fred"
        st.session_state.character_emoji = "👨‍💼"
        
    elif prompt_choice == "Upload Document":
        uploaded_file = st.sidebar.file_uploader(
            "Upload .docx file",
            type=['docx'],
            key="system_prompt_file"
        )
        
        if uploaded_file:
            try:
                content = read_docx(uploaded_file)
                st.session_state.custom_system_prompt = content
                st.session_state.using_custom_prompt = True
                
                # Character name input
                char_name = st.sidebar.text_input(
                    "Character Name (optional)",
                    key="char_name_upload"
                )
                
                if not char_name:
                    char_name, emoji = get_random_name_and_emoji()
                    st.sidebar.info(f"Using random name: {char_name} {emoji}")
                else:
                    emoji = "🎭"
                
                st.session_state.character_name = char_name
                st.session_state.character_emoji = emoji
                
                if st.sidebar.button("Save Character", use_container_width=True):
                    if save_character_to_sheet(char_name, content):
                        st.sidebar.success(f"Character {char_name} saved!")
                
                # Show preview in an expander
                with st.sidebar.expander("Preview Prompt"):
                    st.write(content)
                    
            except Exception as e:
                st.sidebar.error(f"Error reading file: {str(e)}")
                st.session_state.using_custom_prompt = False
                st.session_state.custom_system_prompt = None
                
    elif prompt_choice == "Enter Custom":
        custom_prompt = st.sidebar.text_area(
            "Enter custom system prompt",
            height=150,
            key="custom_prompt_input"
        )
        
        if custom_prompt:
            st.session_state.custom_system_prompt = custom_prompt
            st.session_state.using_custom_prompt = True
            
            # Character name input
            char_name = st.sidebar.text_input(
                "Character Name (optional)",
                key="char_name_custom"
            )
            
            if not char_name:
                char_name, emoji = get_random_name_and_emoji()
                st.sidebar.info(f"Using random name: {char_name} {emoji}")
            else:
                emoji = "🎭"
            
            st.session_state.character_name = char_name
            st.session_state.character_emoji = emoji
            
            if st.sidebar.button("Save Character", use_container_width=True):
                if save_character_to_sheet(char_name, custom_prompt):
                    st.sidebar.success(f"Character {char_name} saved!")
        else:
            st.session_state.using_custom_prompt = False
            st.session_state.custom_system_prompt = None
            
    elif prompt_choice == "Load Saved Character":
        characters = load_characters()
        if characters:
            char_names = [char[0] for char in characters]
            selected_char = st.sidebar.selectbox(
                "Select Character",
                char_names,
                key="saved_char_select"
            )
            
            # Find the selected character's prompt
            for name, prompt in characters:
                if name == selected_char:
                    st.session_state.custom_system_prompt = prompt
                    st.session_state.using_custom_prompt = True
                    st.session_state.character_name = name
                    st.session_state.character_emoji = "🎭"
                    
                    with st.sidebar.expander("Preview Prompt"):
                        st.write(prompt)
                    break
        else:
            st.sidebar.info("No saved characters found")

def get_current_system_prompt(default_prompt):
    """Get the current system prompt based on user settings"""
    if st.session_state.using_custom_prompt and st.session_state.custom_system_prompt:
        return st.session_state.custom_system_prompt
    return default_prompt 