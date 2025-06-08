import streamlit as st
import docx
import io

def initialize_system_prompt_state():
    """Initialize system prompt related session state variables"""
    if 'custom_system_prompt' not in st.session_state:
        st.session_state.custom_system_prompt = None
    if 'using_custom_prompt' not in st.session_state:
        st.session_state.using_custom_prompt = False

def read_docx(file):
    """Read text from a .docx file"""
    doc = docx.Document(file)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return '\n'.join(full_text)

def add_system_prompt_manager():
    """Add system prompt management UI to the sidebar"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("System Prompt Settings")
    
    # Radio button to choose between default and custom prompt
    prompt_choice = st.sidebar.radio(
        "Choose System Prompt:",
        ["Use Default", "Upload Document", "Enter Custom"],
        key="prompt_choice"
    )
    
    if prompt_choice == "Use Default":
        st.session_state.using_custom_prompt = False
        st.session_state.custom_system_prompt = None
        
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
                st.sidebar.success("System prompt updated from document!")
                
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
            
            if st.sidebar.button("Update System Prompt", use_container_width=True):
                st.sidebar.success("System prompt updated!")
        else:
            st.session_state.using_custom_prompt = False
            st.session_state.custom_system_prompt = None

def get_current_system_prompt(default_prompt):
    """Get the current system prompt based on user settings"""
    if st.session_state.using_custom_prompt and st.session_state.custom_system_prompt:
        return st.session_state.custom_system_prompt
    return default_prompt 