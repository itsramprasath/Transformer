# Transformer Project

A Streamlit-based conversational AI assistant that uses OpenAI and Anthropic APIs along with Google Workspace integration.

## Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/itsramprasath/Transformer.git
cd Transformer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your environment:
   - Copy `.env.example` to `.env`
   - Add your API keys and credentials
   - Create a `credentials.json` file with your Google service account credentials

4. Configure your secrets:
   - For local development: Update `.streamlit/secrets.toml` with your credentials
   - For Streamlit Cloud: Add your secrets in the Streamlit Cloud dashboard

## Security Notice

⚠️ **IMPORTANT**: Never commit sensitive information such as API keys, tokens, or credentials to the repository. Always use environment variables or secret management systems to handle sensitive data.

## Features

- Dual AI model support (OpenAI GPT-4 and Anthropic Claude)
- Google Sheets integration for conversation tracking
- Google Docs integration for saving responses
- Real-time chat interface
- Response summarization

## Requirements

- Python 3.10.13
- OpenAI API key
- Anthropic API key
- Google Workspace credentials
- Streamlit

## License

MIT License

## Author

[Ram prasath](https://github.com/itsramprasath)
