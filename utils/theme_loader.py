import streamlit as st
from pathlib import Path

def load_theme(theme_name):
    """
    Load a theme CSS file and apply it to the Streamlit app
    
    Args:
        theme_name (str): Name of the theme file without .css extension
    """
    theme_path = Path(__file__).parent.parent / 'themes' / f'{theme_name}.css'
    
    try:
        with open(theme_path, 'r') as f:
            st.markdown(f"""
                <style>
                {f.read()}
                </style>
            """, unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Theme '{theme_name}' not found")

def initialize_theme_state():
    """Initialize the theme state and character state in session state if they don't exist"""
    if 'current_theme' not in st.session_state:
        st.session_state.current_theme = 'orange_theme'
    if 'character_emoji' not in st.session_state:
        st.session_state.character_emoji = '👨‍💼'
    if 'character_name' not in st.session_state:
        st.session_state.character_name = 'Fred'

def toggle_theme():
    """Toggle between orange and gradient blue themes"""
    if st.session_state.current_theme == 'orange_theme':
        st.session_state.current_theme = 'gradient_blue_theme'
    else:
        st.session_state.current_theme = 'orange_theme'

def add_theme_toggle():
    """Add a small toggle button for theme switching and character indicator"""
    initialize_theme_state()
    
    # Create a small container for the toggle button and character indicator in the sidebar
    with st.sidebar:
        st.write("")  # Add some spacing
        
        # Create columns for layout
        col1, col2, col3 = st.columns([1, 2, 1])
        
        # Display emoji in first column
        with col1:
            st.markdown(f'<p style="font-size: 1.2em; margin: 0; text-align: center;">{st.session_state.character_emoji}</p>', unsafe_allow_html=True)
        
        # Display name in middle column
        with col2:
            st.markdown(f'<p style="margin: 0; text-align: center;">{st.session_state.character_name}</p>', unsafe_allow_html=True)
        
        # Theme toggle in last column
        with col3:
            current_emoji = "🌅" if st.session_state.current_theme == 'orange_theme' else "🌊"
            if st.button(current_emoji, key="theme_toggle", on_click=toggle_theme, help="Toggle theme"):
                pass
        
        # Add some spacing
        st.write("")
    
    # Load the current theme
    load_theme(st.session_state.current_theme) 