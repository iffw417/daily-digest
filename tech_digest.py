#!/usr/bin/env python3
"""
Daily Tech News Digest
Fetches RSS feeds, generates TLDRs via OpenAI, and sends a clean HTML email.
"""

import os
import smtplib
import ssl
import feedparser
import requests
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI

# ── Configuration ─────────────────────────────────────────────────────────────
GMAIL_USER = os.environ.get("GMAIL_USER", "shaarikdigest@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TO_EMAIL = os.environ.get("TO_EMAIL", "shaarik@meta.com")

OPENAI_CLIENT = OpenAI()  # uses OPENAI_API_KEY env var

# ── RSS Feed Sources ───────────────────────────────────────────────────────────
FEEDS = [
    {
        "name": "Axios Tech",
        "url": "https://api.axios.com/feed/",
        "category": "Axios",
    },
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "category": "The Verge",
    },
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "category": "TechCrunch",
    },
    {
        "name": "Wired",
        "url": "https://www.wired.com/feed/rss",
        "category": "Wired",
    },
    {
        "name": "Ars Technica",
        "url": "https://feeds.arstechnica.com/arstechnica/index",
        "category": "Ars Technica",
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "category": "MIT Tech Review",
    },
    {
        "name": "Bloomberg Technology",
        "url": "https://feeds.bloomberg.com/technology/news.rss",
        "category": "Bloomberg",
    },
    {
        "name": "NYT Technology",
        "url": "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
        "category": "NYT",
    },
    {
        "name": "Washington Post Tech",
        "url": "http://feeds.washingtonpost.com/rss/business/technology",
        "category": "WashPo",
    },
    {
        "name": "Politico Tech",
        "url": "https://rss.politico.com/technology.xml",
        "category": "Politico",
    },
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TechDigestBot/1.0)"
}

MAX_ARTICLES_PER_SOURCE = 3
MAX_TOTAL_ARTICLES = 20


def fetch_feed(feed_info):
    """Fetch and parse a single RSS feed, return list of article dicts."""
    articles = []
    try:
        resp = requests.get(feed_info["url"], headers=HEADERS, timeout=10)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        entries = parsed.entries[:MAX_ARTICLES_PER_SOURCE]
        for entry in entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            # Strip HTML tags from summary
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = re.sub(r"\s+", " ", summary)[:500]
            if title and link:
                articles.append({
                    "source": feed_info["category"],
                    "title": title,
                    "link": link,
                    "summary": summary,
                })
    except Exception as e:
        print(f"  [WARN] Failed to fetch {feed_info['name']}: {e}")
    return articles


def generate_tldr(title, summary):
    """Use OpenAI to generate a 1-2 sentence TLDR."""
    content = f"Title: {title}\nSummary: {summary}" if summary else f"Title: {title}"
    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a tech news editor. Write a single crisp sentence (max 25 words) "
                        "summarizing the key point of this article. Be direct and informative. "
                        "No fluff, no 'this article', no 'the story'."
                    ),
                },
                {"role": "user", "content": content},
            ],
            max_tokens=60,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [WARN] TLDR generation failed: {e}")
        return summary[:120] + "..." if len(summary) > 120 else summary


def build_html_email(articles_by_source, date_str):
    """Build a clean, professional HTML email."""
    source_colors = {
        "Axios": "#FF6B35",
        "The Verge": "#FA4B2A",
        "TechCrunch": "#0A8A00",
        "Wired": "#000000",
        "Ars Technica": "#FF4E00",
        "MIT Tech Review": "#A31F34",
        "Bloomberg": "#000000",
        "NYT": "#000000",
        "WashPo": "#231F20",
        "Politico": "#003366",
    }

    sections_html = ""
    for source, articles in articles_by_source.items():
        color = source_colors.get(source, "#333333")
        items_html = ""
        for art in articles:
            items_html += f"""
            <tr>
              <td style="padding: 12px 0; border-bottom: 1px solid #f0f0f0;">
                <a href="{art['link']}" style="font-size: 15px; font-weight: 600; color: #1a1a1a;
                   text-decoration: none; line-height: 1.4; display: block; margin-bottom: 4px;">
                  {art['title']}
                </a>
                <span style="font-size: 13px; color: #555; line-height: 1.5;">{art['tldr']}</span>
              </td>
            </tr>"""

        sections_html += f"""
        <tr>
          <td style="padding: 24px 0 8px 0;">
            <span style="display: inline-block; background: {color}; color: white;
              font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;
              padding: 3px 10px; border-radius: 3px;">{source}</span>
          </td>
        </tr>
        {items_html}
        <tr><td style="height: 8px;"></td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Tech Digest — {date_str}</title>
</head>
<body style="margin: 0; padding: 0; background: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont,
  'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background: #f5f5f5;">
    <tr>
      <td align="center" style="padding: 24px 16px;">
        <table width="600" cellpadding="0" cellspacing="0"
          style="max-width: 600px; width: 100%; background: #ffffff;
          border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background: #1a1a1a; padding: 28px 36px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <div style="font-size: 22px; font-weight: 700; color: #ffffff;
                      letter-spacing: -0.3px;">Tech Digest</div>
                    <div style="font-size: 13px; color: #999; margin-top: 4px;">{date_str}</div>
                  </td>
                  <td align="right">
                    <div style="font-size: 11px; color: #666; text-transform: uppercase;
                      letter-spacing: 1px;">Morning Edition</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 8px 36px 32px 36px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                {sections_html}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background: #f9f9f9; border-top: 1px solid #ebebeb;
              padding: 16px 36px; text-align: center;">
              <span style="font-size: 11px; color: #aaa;">
                Delivered daily at 6am ET &nbsp;·&nbsp;
                Sources: Axios, The Verge, TechCrunch, Wired, Ars Technica,
                MIT Tech Review, Bloomberg, NYT, WashPo, Politico
              </span>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return html


def send_email(html_content, date_str):
    """Send the digest email via Gmail SMTP."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Tech Digest — {date_str}"
    msg["From"] = f"Tech Digest <{GMAIL_USER}>"
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"  Email sent to {TO_EMAIL}")


def main():
    date_str = datetime.now().strftime("%A, %B %-d, %Y")
    print(f"\n=== Tech Digest — {date_str} ===\n")

    # 1. Fetch all feeds
    all_articles = []
    for feed in FEEDS:
        print(f"Fetching {feed['name']}...")
        articles = fetch_feed(feed)
        print(f"  Got {len(articles)} articles")
        all_articles.extend(articles)

    if not all_articles:
        print("No articles fetched. Exiting.")
        return

    # 2. Limit total articles
    all_articles = all_articles[:MAX_TOTAL_ARTICLES]

    # 3. Generate TLDRs
    print(f"\nGenerating TLDRs for {len(all_articles)} articles...")
    for art in all_articles:
        art["tldr"] = generate_tldr(art["title"], art["summary"])
        print(f"  [{art['source']}] {art['title'][:60]}...")

    # 4. Group by source
    articles_by_source = {}
    for art in all_articles:
        src = art["source"]
        if src not in articles_by_source:
            articles_by_source[src] = []
        articles_by_source[src].append(art)

    # 5. Build HTML
    print("\nBuilding HTML email...")
    html = build_html_email(articles_by_source, date_str)

    # 6. Send
    print("Sending email...")
    send_email(html, date_str)
    print("\nDone!")


if __name__ == "__main__":
    main()
