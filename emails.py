from playwright.sync_api import sync_playwright
import yt_dlp
import re
import json
import time
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

# Default values (can be overridden by CLI or environment variables)
DEFAULT_CHANNEL_URL = "https://www.youtube.com/@LeFatShow/videos"
DEFAULT_MAX_VIDEOS = 300
DEFAULT_MAX_THREADS = 10  # More threads possible with yt-dlp (lightweight)
EMAIL_REGEX = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"

def accept_cookies(page):
    """Accept cookies if popup appears"""
    try:
        cookie_selectors = [
            'button[aria-label*="Accept"]',
            'button[aria-label*="Accepter"]',
            'button:has-text("Accept all")',
            'button:has-text("Tout accepter")'
        ]

        for selector in cookie_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.locator(selector).first.click()
                    print("[i] Cookies accepted")
                    page.wait_for_timeout(2000)
                    return True
            except:
                continue
    except:
        pass
    return False

def scroll_and_collect_video_urls(page, channel_url, max_videos):
    print(f"[i] Loading page: {channel_url}")

    page.goto(channel_url, timeout=60000)
    page.wait_for_timeout(5000)

    accept_cookies(page)
    page.wait_for_timeout(3000)

    print("[i] Collecting all videos from page...")

    all_videos = []
    scroll_count = 0
    last_video_count = 0
    no_new_videos = 0

    while len(all_videos) < max_videos and scroll_count < 30:
        # Get all videos at once with JavaScript
        videos_data = page.evaluate(r'''
            () => {
                const videos = [];
                const links = document.querySelectorAll('a[href*="/watch?v="]');

                links.forEach(link => {
                    const href = link.href;
                    if (href.includes('/shorts/')) return;

                    const title = link.title || link.getAttribute('aria-label') || link.textContent || '';
                    const videoId = href.match(/watch\?v=([^&]+)/)?.[1];

                    if (title && videoId) {
                        videos.push({
                            url: href,
                            title: title.trim(),
                            videoId: videoId
                        });
                    }
                });

                // Deduplicate by videoId
                const unique = {};
                videos.forEach(v => {
                    unique[v.videoId] = v;
                });

                return Object.values(unique);
            }
        ''')

        all_videos = videos_data
        print(f"[i] {len(all_videos)} unique videos found...")

        # Check if new videos were found
        if len(all_videos) == last_video_count:
            no_new_videos += 1
            if no_new_videos >= 3:
                print("[i] No more new videos, stopping scroll")
                break
        else:
            no_new_videos = 0
            last_video_count = len(all_videos)

        # If we have enough videos, stop
        if len(all_videos) >= max_videos:
            break

        # Scroll to load more
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(2000)
        scroll_count += 1

    # Return only the requested number
    video_list = [(v['url'], v['title']) for v in all_videos[:max_videos]]
    print(f"[+] {len(video_list)} videos collected")
    return video_list

def extract_email_from_video(video_data):
    """Extract emails from a video with yt-dlp (fast, no browser)"""
    video_url, title = video_data

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            description = info.get('description', '') or ''

            # Search for emails
            emails = list(set(re.findall(EMAIL_REGEX, description)))

            return {
                "title": info.get('title', title),
                "url": video_url,
                "emails": emails,
                "has_description": len(description) > 0
            }
    except Exception as e:
        return {
            "title": title,
            "url": video_url,
            "emails": [],
            "error": str(e)
        }

def parse_delay(delay_str):
    """Parse a delay string (e.g., '3s', '500ms', '1.5s') to seconds"""
    if not delay_str:
        return 0
    delay_str = delay_str.strip().lower()
    if delay_str.endswith('ms'):
        return float(delay_str[:-2]) / 1000
    elif delay_str.endswith('s'):
        return float(delay_str[:-1])
    else:
        return float(delay_str)


def parse_batch_delay(batch_str):
    """Parse a batch-delay string (e.g., '3s/50') to (delay_seconds, batch_size)"""
    if not batch_str:
        return (0, 0)
    parts = batch_str.split('/')
    if len(parts) != 2:
        raise ValueError(f"Invalid format for batch-delay: {batch_str}. Use 'DELAY/N' (e.g., '3s/50')")
    delay = parse_delay(parts[0])
    batch_size = int(parts[1])
    return (delay, batch_size)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Extract emails from YouTube video descriptions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python emails.py                                    # Use default values
  python emails.py -c https://www.youtube.com/@bbc   # Specify a channel
  python emails.py -c @france24 -m 50                # Channel + max 50 videos
  python emails.py -t 8                              # 8 parallel threads
  python emails.py -d 0.5s                           # 0.5s between each request
  python emails.py --batch-delay 3s/50              # 3s pause after every 50 requests
  python emails.py -d 100ms --batch-delay 5s/100    # Combined: 100ms between req + 5s/100 req
        """
    )
    parser.add_argument(
        "-c", "--channel",
        default=os.environ.get("YOUTUBE_CHANNEL_URL", DEFAULT_CHANNEL_URL),
        help=f"YouTube channel URL (default: {DEFAULT_CHANNEL_URL})"
    )
    parser.add_argument(
        "-m", "--max-videos",
        type=int,
        default=int(os.environ.get("MAX_VIDEOS", DEFAULT_MAX_VIDEOS)),
        help=f"Maximum number of videos to analyze (default: {DEFAULT_MAX_VIDEOS})"
    )
    parser.add_argument(
        "-t", "--threads",
        type=int,
        default=int(os.environ.get("MAX_THREADS", DEFAULT_MAX_THREADS)),
        help=f"Number of parallel threads (default: {DEFAULT_MAX_THREADS})"
    )
    parser.add_argument(
        "-d", "--delay",
        default=None,
        help="Delay between each request (e.g., '0.5s', '500ms', '1s')"
    )
    parser.add_argument(
        "--batch-delay",
        default=None,
        help="Delay after N requests, format 'DELAY/N' (e.g., '3s/50' = 3s after every 50 req)"
    )
    parser.add_argument(
        "-o", "--output",
        default="emails_youtube",
        help="Output file prefix (default: emails_youtube)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run in headless mode (default: True)"
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Disable headless mode (show browser)"
    )

    args = parser.parse_args()

    # Normalize channel URL
    if not args.channel.startswith("http"):
        args.channel = f"https://www.youtube.com/{args.channel}/videos"
    elif not args.channel.endswith("/videos"):
        args.channel = args.channel.rstrip("/") + "/videos"

    # Handle headless mode
    if args.no_headless:
        args.headless = False

    # Parse delays
    args.delay_seconds = parse_delay(args.delay) if args.delay else 0
    args.batch_delay_seconds, args.batch_size = parse_batch_delay(args.batch_delay) if args.batch_delay else (0, 0)

    return args


def main():
    args = parse_args()

    start = time.time()

    print("[i] Starting YouTube scraper...")
    print(f"[i] Channel: {args.channel}")
    print(f"[i] Max videos: {args.max_videos}")
    print(f"[i] Threads: {args.threads}")

    with sync_playwright() as p:
        # Create browser for URL collection
        browser = p.chromium.launch(
            headless=args.headless,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = context.new_page()

        # Collect URLs
        print("\n[i] Phase 1: Collecting URLs...")
        video_list = scroll_and_collect_video_urls(page, args.channel, args.max_videos)

        browser.close()

        if not video_list:
            print("[!] No videos found")
            return

    # Phase 2: Extract emails with yt-dlp (fast)
    print(f"\n[i] Phase 2: Extracting emails from {len(video_list)} videos (yt-dlp)...")

    # Display delay config
    delay_info = []
    if args.delay_seconds > 0:
        delay_info.append(f"delay: {args.delay_seconds}s/req")
    if args.batch_size > 0:
        delay_info.append(f"batch: {args.batch_delay_seconds}s/{args.batch_size}req")

    # If per-request delay, force 1 thread to respect timing
    effective_threads = 1 if args.delay_seconds > 0 else args.threads
    print(f"[i] Using {effective_threads} thread(s)..." + (f" ({', '.join(delay_info)})" if delay_info else ""))

    all_results = []
    completed_videos = 0
    request_count = 0

    # Parallel processing with yt-dlp (lightweight, allows more threads)
    with ThreadPoolExecutor(max_workers=effective_threads) as executor:
        futures = {}

        for video in video_list:
            # Delay between each request
            if args.delay_seconds > 0 and request_count > 0:
                time.sleep(args.delay_seconds)

            # Delay after N requests (batch delay)
            if args.batch_size > 0 and request_count > 0 and request_count % args.batch_size == 0:
                print(f"[i] Pausing {args.batch_delay_seconds}s after {request_count} requests...")
                time.sleep(args.batch_delay_seconds)

            futures[executor.submit(extract_email_from_video, video)] = video
            request_count += 1

        for future in as_completed(futures):
            completed_videos += 1
            try:
                result = future.result()
                all_results.append(result)

                if result.get('emails'):
                    print(f"[{completed_videos}/{len(video_list)}] + {len(result['emails'])} email(s): {result['title'][:50]}...")
                    for email in result['emails']:
                        print(f"    -> {email}")
                elif completed_videos <= 5 or completed_videos % 20 == 0:
                    if result.get('has_description'):
                        print(f"[{completed_videos}/{len(video_list)}] - No email")
                    else:
                        print(f"[{completed_videos}/{len(video_list)}] - No description")

            except Exception as e:
                print(f"[{completed_videos}/{len(video_list)}] ! Error: {e}")

    # Filter results with emails
    results_with_emails = [r for r in all_results if r.get('emails')]

    # Save results
    json_file = f"{args.output}.json"
    csv_file = f"{args.output}.csv"

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(results_with_emails, f, indent=2, ensure_ascii=False)

    # Create CSV
    if results_with_emails:
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write("Title,URL,Emails\n")
            for r in results_with_emails:
                emails_str = "; ".join(r['emails'])
                title_escaped = r["title"].replace('"', '""')
                f.write(f'"{title_escaped}","{r["url"]}","{emails_str}"\n')

    # Statistics
    total_emails = sum(len(r.get('emails', [])) for r in all_results)
    unique_emails = set()
    for r in all_results:
        unique_emails.update(r.get('emails', []))

    videos_with_description = sum(1 for r in all_results if r.get('has_description'))

    elapsed = round(time.time() - start, 2)

    print(f"\n{'='*60}")
    print(f"Extraction completed in {elapsed} seconds")
    print(f"Speed: {round(len(video_list) / elapsed, 2)} videos/second")
    print(f"{len(video_list)} videos analyzed")
    print(f"{videos_with_description} videos had a description")
    print(f"{len(results_with_emails)} videos contain emails")
    print(f"{total_emails} emails found ({len(unique_emails)} unique)")

    if unique_emails:
        print(f"\nUnique emails found:")
        for email in sorted(unique_emails):
            print(f"   - {email}")
    else:
        print(f"\n[!] No emails found. Possible causes:")
        print(f"    - Videos on this channel don't have emails in descriptions")
        print(f"    - Descriptions are not loading correctly")
        print(f"    - Try with another YouTube channel")

    print(f"\nResults saved to:")
    print(f"   - {json_file}")
    if results_with_emails:
        print(f"   - {csv_file}")

if __name__ == "__main__":
    main()
