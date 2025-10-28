# arxiv-dailyupdate

A small utility that fetches recent arXiv papers for a category (default: `cs.CR`), summarizes them using Google's Generative AI, extracts a main figure where possible, and builds an HTML daily digest which is both saved as `arxiv_daily.html` and emailed via SMTP.

## Features

- Fetch recent arXiv papers (uses `arxiv` Python client)
- Summarize paper content using Google Generative AI (`google-generativeai`)
- Extract main figure from PDFs using PyMuPDF (`fitz`)
- Build an HTML digest and optionally send it via SMTP

## Requirements

- Python 3.10+
- See `requirements.txt` for Python packages.

## Environment variables

Create a `.env` file in the project root (or set these in your environment):

```
ARXIV_CATEGORY=cs.CR # The subject you want to focus
ARXIV_LOOKBACK_HOURS=168
SMTP_USER=your-smtp-user@example.com
SMTP_PASS=your-smtp-password
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
MAIL_TO=recipient1@example.com,recipient2@example.com
GOOGLE_API_KEY=your_google_generative_api_key
```

Notes:

- `GOOGLE_API_KEY` is required for the `summarize_from_pdf` function which uses Google's Generative API.
- If using Gmail, you may need an app password and to enable SMTP access for the account.

## Install

Prefer a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

This will:

- Fetch recent papers and build the digest
- Write `arxiv_daily.html` (preview)
- Attempt to send the email using the SMTP credentials provided

If you only want to preview the generated HTML without sending mail, remove or comment out the `send_email(msg)` call in `main.py`.

## Files

- `main.py` — main script to fetch, summarize and send the digest
- `data_model.py` — pydantic models used by the script
- `arxiv_daily.html` — generated preview output (written by `main.py`)

## Notes & troubleshooting

- The script downloads PDFs and opens them with PyMuPDF — make sure your environment has `PyMuPDF` installed and is able to open binary PDFs.
- Google Generative AI usage may incur costs; ensure your API key and quota are managed appropriately.
- If network libraries (e.g., `httpx`) fail, check your proxy/firewall settings.

## Future Plans

The following features are planned for future releases:

### Multi-language Support

- Add support for summarizing papers in multiple languages
- Allow configurable output language preferences
- Support multilingual email templates

### Custom Date Range

- Add ability to specify custom date ranges for paper fetching
- Support historical paper digests
- Add scheduling options for digest generation

### Multi-subject Support

- Enable fetching papers from multiple arXiv categories simultaneously
- Add subject-based filtering and organization
- Support custom topic grouping and categorization

## License

MIT-style (no license file included). Use as you wish and be mindful of API/key usage and privacy of content.
