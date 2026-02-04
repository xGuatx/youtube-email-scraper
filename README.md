# YouTube Email Scraper

Python tool to scrape email addresses from YouTube channel video descriptions using yt-dlp and Playwright.

## Features

- Extract emails from YouTube video descriptions
- Fast extraction with yt-dlp (no browser needed for descriptions)
- Playwright for channel page scrolling
- Multi-threaded processing (up to 15+ threads)
- Rate limiting options to avoid 403 errors
- Export results to JSON and CSV formats

## Performance

| Videos | Time | Speed | Emails Found |
|--------|------|-------|--------------|
| 100 | ~50s | 2 vid/s | - |
| 525 | ~5min | 1.76 vid/s | 4 |

Example results from @ExampleChannel (525 videos):
```
Emails found:
- example1@email.com
- example2@email.com
- example3@email.com
- example4@email.com
```

## Prerequisites

- Python 3.8+
- Playwright (for channel page scrolling)

## Setup

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:
```bash
playwright install chromium
```

## Usage

Make sure the virtual environment is activated:
```bash
source venv/bin/activate  # Linux/macOS
```

### Basic Usage

```bash
python emails.py
```

### CLI Options

```
Options:
  -c, --channel URL       YouTube channel URL (default: @ExampleChannel)
  -m, --max-videos N      Maximum videos to analyze (default: 300)
  -t, --threads N         Number of parallel threads (default: 10)
  -d, --delay DELAY       Delay between requests (e.g., '0.5s', '500ms')
  --batch-delay DELAY/N   Delay after N requests (e.g., '3s/50')
  -o, --output PREFIX     Output file prefix (default: emails_youtube)
  --no-headless           Show browser window (debug mode)
  -h, --help              Show help message
```

### Examples

```bash
# Scrape default channel
python emails.py

# Scrape a specific channel
python emails.py -c https://www.youtube.com/@bbc

# Short format for channel
python emails.py -c @france24

# Limit to 50 videos with 8 threads
python emails.py -c @euronews -m 50 -t 8

# With rate limiting (delay between each request)
python emails.py -c @ExampleChannel -m 500 -d 0.5s

# With batch delay (pause after N requests)
python emails.py -c @ExampleChannel -m 500 -t 10 --batch-delay 3s/50

# Combined delays
python emails.py -d 100ms --batch-delay 5s/100

# Custom output file name
python emails.py -c @bbc -o bbc_emails
```

### Environment Variables

Configure via environment variables (see `.env.example`):

```bash
export YOUTUBE_CHANNEL_URL=https://www.youtube.com/@bbc/videos
export MAX_VIDEOS=100
export MAX_THREADS=8
python emails.py
```

## Output

Results are saved in two formats:
- `emails_youtube.json` - Structured JSON with video details
- `emails_youtube.csv` - Spreadsheet format

## Rate Limiting

If you get 403 errors, use delay options:

```bash
# Slow but safe: 0.5s between each request
python emails.py -d 0.5s

# Balanced: fast with pauses every 50 requests
python emails.py -t 10 --batch-delay 3s/50
```

## Test Channels

For testing, use public channels:

```bash
python emails.py -c @bbc           # BBC News
python emails.py -c @france24      # France 24
python emails.py -c @euronews      # Euronews
```

## Security & Ethics

**IMPORTANT:**
- Respect privacy and GDPR regulations
- Only use for legitimate purposes
- Do not spam the addresses found
- Educational and research use only

## License

MIT License - See LICENSE file.
