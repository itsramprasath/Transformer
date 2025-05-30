# Transformer

A powerful Streamlit-based chat application that integrates with AI models (OpenAI/Claude) and Google Workspace (Docs & Sheets) for managing client conversations and responses.

## Features

- 💬 Interactive chat interface with AI (OpenAI/Claude)
- 📝 Automatic conversation history tracking
- 📊 Google Sheets integration for data storage
- 📄 Google Docs integration for response management
- 🔄 Response retry functionality
- 📋 Multiple response options with editing capability
- 🔍 Session tracking and management
- 📱 Responsive and clean UI

## Prerequisites

1. Python 3.8 or higher
2. Google Cloud Platform account
3. OpenAI API key or Anthropic API key (for Claude)
4. Google Workspace (for Sheets and Docs integration)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/itsramprasath/Transformer.git
cd Transformer
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up Google Cloud Platform:
   - Create a new project in Google Cloud Console
   - Enable Google Sheets API and Google Docs API
   - Create credentials (OAuth 2.0 Client ID)
   - Download the credentials and save as `/etc/secrets/credentials.json`

4. First-time setup:
   - Run the application (it will prompt for Google authentication)
   - Follow the authentication flow in your browser
   - The application will create necessary token files

5. Set up environment variables:
```bash
# For OpenAI
export OPENAI_API_KEY=your_api_key_here

# For Claude (if using)
export ANTHROPIC_API_KEY=your_api_key_here
```

## Usage

1. Start the application:
```bash
# Windows
run_app.bat

# Unix/Linux/Mac
streamlit run fred_streamlit_app.py
```

2. Using the application:
   - Select or enter a new client name in the sidebar
   - Choose the AI model (OpenAI/Claude)
   - Start the conversation
   - Use the retry button (🔄) to regenerate responses
   - Save responses to Google Docs using the Save Reply Tool
   - View conversation history in Google Sheets

## Project Structure

```
├── fred_streamlit_app.py    # Main application file
├── fred_us_tools_2.py       # Core functionality and AI integration
├── google_services.py       # Google API integration
├── requirements.txt         # Python dependencies
├── run_app.bat             # Windows startup script
└── .streamlit/
    └── config.toml         # Streamlit configuration
```

## Security Notes

- Never commit API keys or tokens to the repository
- Keep `/etc/secrets/credentials.json` and token files secure
- Use environment variables for sensitive data
- Regularly rotate API keys and review access permissions

## Troubleshooting

1. Token Expiration:
   - Delete token files
   - Restart the application
   - Re-authenticate

2. API Rate Limits:
   - The application includes built-in retry logic
   - Consider implementing additional rate limiting if needed

3. Google API Issues:
   - Verify API services are enabled in Google Cloud Console
   - Check credential restrictions and quotas
   - Ensure OAuth consent screen is properly configured

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License

## Author

[Ram prasath](https://github.com/itsramprasath)
