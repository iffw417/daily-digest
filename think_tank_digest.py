#!/usr/bin/env python3
"""
Daily Think Tank Tech Digest
Fetches RSS feeds from 37 national security/foreign policy orgs, filters for tech,
generates detailed summaries via OpenAI, deduplicates, and sends an HTML email.
"""

import os
import json
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

OPENAI_CLIENT = OpenAI()

HISTORY_FILE = os.environ.get("HISTORY_FILE", "think_tank_history.json")

# Keywords to filter for tech-related content
TECH_KEYWORDS = [
    "ai", "artificial intelligence", "cyber", "cybersecurity", "technology",
    "tech", "algorithm", "machine learning", "semiconductor", "chip",
    "data", "privacy", "digital", "quantum", "space", "satellite",
    "innovation", "social media", "platform", "internet", "telecom",
    "5g", "6g", "drone", "autonomous", "robotics", "crypto", "blockchain"
]

# Load feeds from the research JSON
with open(os.environ.get("RSS_RESEARCH_FILE", "think_tank_rss_research.json"), "r") as f:
    research_data = json.load(f)

FEEDS = []
for item in research_data.get("results", []):
    out = item.get("output", {})
    if out.get("rss_url") and out.get("rss_url").lower() != "none":
        FEEDS.append({
            "name": out.get("org_name"),
            "url": out.get("rss_url")
        })

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ThinkTankDigestBot/1.0)"
}

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return []

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f)

def is_tech_related(title, summary):
    text = (title + " " + summary).lower()
    for kw in TECH_KEYWORDS:
        # simple word boundary check
        if f" {kw} " in f" {text} " or f" {kw}s " in f" {text} " or f" {kw}," in f" {text} " or f" {kw}." in f" {text} ":
            return True
    return False

def fetch_feed(feed_info, history):
    """Fetch and parse a single RSS feed, return list of new tech article dicts."""
    articles = []
    try:
        resp = requests.get(feed_info["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        
        for entry in parsed.entries[:10]:  # check top 10 recent
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()
            summary = re.sub(r"\s+", " ", summary)[:1000]
            
            if not title or not link:
                continue
                
            if link in history:
                continue
                
            if is_tech_related(title, summary):
                articles.append({
                    "source": feed_info["name"],
                    "title": title,
                    "link": link,
                    "summary": summary,
                })
    except Exception as e:
        print(f"  [WARN] Failed to fetch {feed_info['name']}: {e}")
    return articles

def generate_detailed_summary(title, summary):
    """Use OpenAI to generate a detailed summary."""
    content = f"Title: {title}\nOriginal Summary/Excerpt: {summary}"
    try:
        response = OPENAI_CLIENT.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a national security and tech policy analyst. "
                        "Provide a detailed, insightful summary (3-4 sentences) of this piece. "
                        "Focus on the core argument, policy implications, and why it matters. "
                        "Do not use phrases like 'This article discusses'."
                    ),
                },
                {"role": "user", "content": content},
            ],
            max_tokens=150,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  [WARN] Summary generation failed: {e}")
        return summary[:300] + "..." if len(summary) > 300 else summary

def build_html_email(articles_by_source, date_str):
    """Build a clean, professional HTML email."""
    if not articles_by_source:
        return f"""<!DOCTYPE html>
<html>
<body style="font-family: sans-serif; padding: 20px; color: #333;">
  <h2>Think Tank Tech Digest — {date_str}</h2>
  <p>No new tech-related pieces were published by the tracked organizations today.</p>
</body>
</html>"""

    sections_html = ""
    for source, articles in articles_by_source.items():
        items_html = ""
        for art in articles:
            items_html += f"""
            <tr>
              <td style="padding: 16px 0; border-bottom: 1px solid #eaeaea;">
                <a href="{art['link']}" style="font-size: 16px; font-weight: 600; color: #004b87;
                   text-decoration: none; line-height: 1.4; display: block; margin-bottom: 8px;">
                  {art['title']}
                </a>
                <div style="font-size: 14px; color: #444; line-height: 1.6;">{art['detailed_summary']}</div>
              </td>
            </tr>"""

        sections_html += f"""
        <tr>
          <td style="padding: 30px 0 10px 0; border-bottom: 2px solid #004b87;">
            <span style="font-size: 18px; font-weight: 700; color: #111;">{source}</span>
          </td>
        </tr>
        {items_html}
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Think Tank Tech Digest — {date_str}</title>
</head>
<body style="margin: 0; padding: 0; background: #f4f7f6; font-family: Georgia, 'Times New Roman', serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background: #f4f7f6;">
    <tr>
      <td align="center" style="padding: 30px 16px;">
        <table width="650" cellpadding="0" cellspacing="0"
          style="max-width: 650px; width: 100%; background: #ffffff;
          border-radius: 4px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">

          <!-- Header -->
          <tr>
            <td style="background: #002b49; padding: 35px 40px;">
              <div style="font-size: 24px; font-weight: 700; color: #ffffff; font-family: sans-serif;">
                Think Tank Tech Digest
              </div>
              <div style="font-size: 14px; color: #a3c4dc; margin-top: 6px; font-family: sans-serif;">
                {date_str} · National Security & Foreign Policy
              </div>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 10px 40px 40px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0">
                {sections_html}
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background: #f9f9f9; border-top: 1px solid #ebebeb;
              padding: 20px 40px; text-align: center; font-family: sans-serif;">
              <span style="font-size: 12px; color: #888;">
                Tracking 37 national security and foreign policy organizations.<br>
                Delivered daily. Deduplicated automatically.
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
    msg["Subject"] = f"Think Tank Tech Digest — {date_str}"
    msg["From"] = f"Think Tank Digest <{GMAIL_USER}>"
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"  Email sent to {TO_EMAIL}")

def main():
    date_str = datetime.now().strftime("%A, %B %-d, %Y")
    print(f"\n=== Think Tank Tech Digest — {date_str} ===\n")

    history = load_history()
    print(f"Loaded {len(history)} previously sent articles from history.")

    all_new_articles = []
    for feed in FEEDS:
        print(f"Checking {feed['name']}...")
        articles = fetch_feed(feed, history)
        if articles:
            print(f"  Found {len(articles)} new tech-related articles")
            all_new_articles.extend(articles)

    if not all_new_articles:
        print("\nNo new articles found today. Sending 'no new pieces' email.")
        html = build_html_email({}, date_str)
        send_email(html, date_str)
        return

    print(f"\nGenerating detailed summaries for {len(all_new_articles)} articles...")
    for art in all_new_articles:
        art["detailed_summary"] = generate_detailed_summary(art["title"], art["summary"])
        print(f"  [{art['source']}] {art['title'][:60]}...")
        # Add to history
        history.append(art["link"])

    # Group by source
    articles_by_source = {}
    for art in all_new_articles:
        src = art["source"]
        if src not in articles_by_source:
            articles_by_source[src] = []
        articles_by_source[src].append(art)

    print("\nBuilding HTML email...")
    html = build_html_email(articles_by_source, date_str)

    print("Sending email...")
    send_email(html, date_str)
    
    print("Saving history...")
    save_history(history)
    
    print("\nDone!")

if __name__ == "__main__":
    main()
