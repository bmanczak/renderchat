#!/usr/bin/env python3
"""
Render ChatGPT, Claude, or Grok conversations into a single static HTML page with easy XML export.
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from typing import List

import markdown
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


@dataclass
class Message:
    """
    Represents a single message in the conversation.

    Attributes:
        role: The role of the message author ('user' or 'assistant')
        content: The text content of the message
    """

    role: str
    content: str


def ensure_firefox_installed() -> None:
    """
    Ensure Playwright's Firefox browser is installed.
    Auto-installs if not present.

    Raises:
        RuntimeError: If installation fails
    """
    # Check if Firefox is already installed by verifying the executable exists
    executable_path = None
    try:
        with sync_playwright() as p:
            executable_path = getattr(p.firefox, "executable_path", None)
    except Exception:
        # If Playwright driver isn't ready yet, we'll attempt installation below
        executable_path = None

    if executable_path and pathlib.Path(executable_path).exists():
        return

    print("📦 Installing Playwright Firefox browser (first time only)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "firefox"],
            capture_output=True,
            text=True,
            check=True,
        )
        # Verify installation by re-checking the executable existence
        with sync_playwright() as p:
            installed_path = getattr(p.firefox, "executable_path", None)
        assert installed_path and pathlib.Path(installed_path).exists(), "Firefox executable missing after install"
        print("✓ Firefox installed successfully", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to install Firefox: {e.stderr}") from e


def extract_claude_conversation(html_content: str) -> List[Message]:
    """
    Extract conversation messages from Claude shared page HTML.

    Args:
        html_content: Rendered HTML content from the shared conversation page

    Returns:
        List of Message objects representing the conversation

    Raises:
        ValueError: If conversation data cannot be extracted
    """
    soup = BeautifulSoup(html_content, "html.parser")
    messages = []

    # Find all message containers
    # User messages have class !font-user-message
    # Assistant messages have 'standard-markdown' as an exact class name
    # (avoid parent divs which only have it in CSS selectors like [&_.standard-markdown_...])

    # First, check for file/attachment indicators
    file_indicators = soup.find_all(string=lambda t: t and "files hidden" in t.lower() if t else False)
    has_hidden_files = len(file_indicators) > 0

    # Combine and sort by document order
    all_content_divs = []
    for div in soup.find_all("div"):
        classes = div.get("class", [])
        if "!font-user-message" in classes:
            all_content_divs.append((div, "user"))
        # Check if 'standard-markdown' is an exact class, not just in a selector
        # Parent divs have font-claude-response, children have standard-markdown as literal class
        elif "standard-markdown" in classes and "font-claude-response" not in classes:
            all_content_divs.append((div, "assistant"))

    # If files are hidden, add a note to the first user message
    added_file_note = False

    for div, role in all_content_divs:

        # Extract HTML content and convert to markdown
        content_copy = BeautifulSoup(str(div), "html.parser")

        # Remove buttons and UI elements
        for button in content_copy.find_all("button"):
            button.decompose()
        for elem in content_copy.find_all(class_=lambda x: x and "copy" in str(x).lower() if x else False):
            elem.decompose()

        # Convert to markdown
        markdown_text = md(
            str(content_copy),
            heading_style="ATX",
            code_language="",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
        ).strip()

        # Clean up markdown formatting
        markdown_text = clean_markdown_code_blocks(markdown_text)

        # Add attachment note to first user message if files are hidden
        if has_hidden_files and role == "user" and not added_file_note:
            markdown_text = (
                "📎 **[Attachment Hidden]** *(Files/images are not included in shared conversations)*\n\n"
                + markdown_text
            )
            added_file_note = True

        if markdown_text:
            messages.append(Message(role=role, content=markdown_text))

    if not messages:
        raise ValueError("Could not extract conversation data from Claude page")

    return messages


def extract_grok_conversation(html_content: str) -> List[Message]:
    """
    Extract conversation messages from Grok shared page HTML.

    Args:
        html_content: Rendered HTML content from the shared conversation page

    Returns:
        List of Message objects representing the conversation

    Raises:
        ValueError: If conversation data cannot be extracted
    """
    soup = BeautifulSoup(html_content, "html.parser")
    messages = []

    # Check for attachments/images in the conversation
    # Grok uses 'inline-media-container' sections for images/attachments
    # These are empty in shared conversations when media was present
    media_containers = soup.find_all("section", class_=lambda x: x and "inline-media-container" in x if x else False)
    has_hidden_attachments = any(not container.get_text().strip() for container in media_containers)

    # Grok uses 'message-bubble' class for messages
    # User messages have parent with 'items-end' (right-aligned)
    # Assistant messages have parent with 'items-start' (left-aligned)
    message_bubbles = soup.find_all("div", class_=lambda x: x and "message-bubble" in x if x else False)

    added_attachment_note = False

    for bubble in message_bubbles:
        # Determine role based on parent's alignment classes
        role = None
        parent = bubble.parent
        if parent:
            parent_classes = parent.get("class", [])
            if "items-end" in parent_classes:
                role = "user"
            elif "items-start" in parent_classes:
                role = "assistant"

        if not role:
            continue

        # Extract content
        content_copy = BeautifulSoup(str(bubble), "html.parser")

        # Remove UI elements
        for button in content_copy.find_all("button"):
            button.decompose()
        for elem in content_copy.find_all(class_=lambda x: x and "copy" in str(x).lower() if x else False):
            elem.decompose()

        # Convert to markdown
        markdown_text = md(
            str(content_copy),
            heading_style="ATX",
            code_language="",
            escape_asterisks=False,
            escape_underscores=False,
            escape_misc=False,
        ).strip()

        markdown_text = clean_markdown_code_blocks(markdown_text)

        # Add attachment note to first user message if attachments are hidden
        if has_hidden_attachments and role == "user" and not added_attachment_note:
            markdown_text = (
                "📎 **[Attachment Hidden]** *(Files/images are not included in shared conversations)*\n\n"
                + markdown_text
            )
            added_attachment_note = True

        if markdown_text:
            messages.append(Message(role=role, content=markdown_text))

    if not messages:
        raise ValueError("Could not extract conversation data from Grok page")

    return messages


def clean_markdown_code_blocks(markdown_text: str) -> str:
    """
    Clean up markdown code blocks to ensure proper formatting.

    Args:
        markdown_text: Raw markdown text

    Returns:
        Cleaned markdown with properly formatted code blocks
    """
    lines = markdown_text.split("\n")
    cleaned_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # If we find a ``` line
        if line.strip() == "```" or (line.strip().startswith("```") and len(line.strip()) <= 20):
            # Check if the next line is a language identifier
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Common language identifiers
                languages = {
                    "python",
                    "javascript",
                    "typescript",
                    "bash",
                    "sh",
                    "json",
                    "yaml",
                    "yml",
                    "html",
                    "css",
                    "jsx",
                    "tsx",
                    "java",
                    "cpp",
                    "c",
                    "go",
                    "rust",
                    "ruby",
                    "php",
                }
                if next_line.lower() in languages:
                    # Merge the language onto the ``` line
                    cleaned_lines.append(f"```{next_line}")
                    i += 2  # Skip both lines
                    continue
            cleaned_lines.append("```")
        else:
            cleaned_lines.append(line)
        i += 1
    return "\n".join(cleaned_lines).strip()


def extract_conversation_from_html(html_content: str) -> List[Message]:
    """
    Extract conversation messages from ChatGPT shared page HTML.

    Args:
        html_content: Rendered HTML content from the shared conversation page

    Returns:
        List of Message objects representing the conversation

    Raises:
        ValueError: If conversation data cannot be extracted
    """
    soup = BeautifulSoup(html_content, "html.parser")
    messages = []

    # Look for conversation turn elements
    # ChatGPT uses data-message-author-role attribute
    message_divs = soup.find_all(attrs={"data-message-author-role": True})

    if message_divs:
        for div in message_divs:
            role = div.get("data-message-author-role", "")

            if role not in ["user", "assistant"]:
                continue

            # Extract text content from the message
            # Look for the prose content div
            content_div = div.find("div", class_=lambda x: x and "prose" in x if x else False)

            if not content_div:
                # Fallback: get all text from the div
                content_div = div

            # Clean up HTML before conversion
            # Remove "Copy code" buttons and other UI elements
            content_copy = BeautifulSoup(str(content_div), "html.parser")
            for button in content_copy.find_all("button"):
                button.decompose()
            for elem in content_copy.find_all(class_=lambda x: x and "copy" in str(x).lower() if x else False):
                elem.decompose()

            # Convert HTML to markdown to preserve formatting
            markdown_text = md(
                str(content_copy),
                heading_style="ATX",
                code_language="",
                escape_asterisks=False,
                escape_underscores=False,
                escape_misc=False,
            ).strip()

            # Clean up markdown formatting
            markdown_text = clean_markdown_code_blocks(markdown_text)

            if markdown_text:
                messages.append(Message(role=role, content=markdown_text))

    # Fallback: Try to extract from script tags with JSON data
    if not messages:
        script_tags = soup.find_all("script", {"type": "application/json"})

        for script in script_tags:
            if not script.string:
                continue

            try:
                data = json.loads(script.string)

                # Navigate the data structure to find conversation
                if "props" in data and "pageProps" in data["props"]:
                    server_response = data["props"]["pageProps"].get("serverResponse", {})
                    data_obj = server_response.get("data", {})

                    if not data_obj:
                        continue

                    # Extract messages from mapping
                    mapping = data_obj.get("mapping", {})
                    if not mapping:
                        continue

                    for node_data in mapping.values():
                        message_data = node_data.get("message")
                        if not message_data:
                            continue

                        author = message_data.get("author", {})
                        role = author.get("role", "")

                        if role not in ["user", "assistant"]:
                            continue

                        content = message_data.get("content", {})
                        parts = content.get("parts", [])

                        if not parts:
                            continue

                        # Join all parts into a single message
                        text = "\n".join(str(part) for part in parts if part)

                        if text.strip():
                            messages.append(Message(role=role, content=text.strip()))

                    if messages:
                        return messages

            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    if not messages:
        raise ValueError("Could not extract conversation data from the page")

    return messages


def detect_platform(url: str) -> str:
    """
    Detect which platform the URL is from.

    Args:
        url: The conversation URL

    Returns:
        Platform name: 'chatgpt', 'claude', or 'grok'

    Raises:
        ValueError: If URL is not from a supported platform
    """
    if "chatgpt.com/share/" in url:
        return "chatgpt"
    elif "claude.ai/share/" in url:
        return "claude"
    elif "grok.com/share/" in url or "x.ai/share/" in url:
        return "grok"
    else:
        raise ValueError("URL must be from chatgpt.com/share/, claude.ai/share/, or grok.com/share/")


def fetch_conversation(url: str) -> List[Message]:
    """
    Fetch and parse a shared conversation from ChatGPT, Claude, or Grok using Playwright.

    Args:
        url: Shared conversation URL from chatgpt.com/share/, claude.ai/share/, or grok.com/share/

    Returns:
        List of Message objects

    Raises:
        PlaywrightTimeout: If the page load times out
        ValueError: If conversation cannot be parsed or URL is invalid
    """
    # Ensure Firefox is installed before attempting to use it
    ensure_firefox_installed()

    platform = detect_platform(url)

    with sync_playwright() as p:
        # Use Firefox with stealth configuration for all platforms
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
            },
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
            },
        )
        page = context.new_page()

        # Add stealth script to mask automation
        page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

        try:
            page.goto(url, timeout=60000, wait_until="networkidle")

            # Wait for content based on platform
            if platform == "chatgpt":
                page.wait_for_selector('[data-testid*="conversation"]', timeout=10000)
            elif platform == "grok":
                # Wait for Grok content to load
                page.wait_for_timeout(3000)
            else:  # claude
                # Check if we hit a Cloudflare challenge
                try:
                    page.wait_for_selector('text="Just a moment"', timeout=2000)
                    print("⚠️  Cloudflare challenge detected, waiting up to 30s for it to complete...", file=sys.stderr)

                    # Wait for challenge to complete (up to 30 seconds)
                    for i in range(30):
                        page.wait_for_timeout(1000)
                        current_url = page.url
                        content = page.content()

                        # Check if we've passed the challenge
                        if "Just a moment" not in content and "claude.ai" in current_url:
                            print(f"✓ Cloudflare challenge passed after {i+1}s", file=sys.stderr)
                            break

                        if i == 29:
                            raise ValueError(
                                "Cloudflare challenge did not complete. "
                                "Claude.ai is blocking automated access. "
                                "Try accessing the URL in a regular browser first."
                            )
                except PlaywrightTimeout:
                    # No Cloudflare challenge detected, continue normally
                    pass

                # Wait additional time for content to load
                page.wait_for_timeout(3000)

            html_content = page.content()

        finally:
            browser.close()

    # Extract messages based on platform
    if platform == "chatgpt":
        return extract_conversation_from_html(html_content)
    elif platform == "claude":
        return extract_claude_conversation(html_content)
    else:  # grok
        return extract_grok_conversation(html_content)


def render_markdown_with_code(text: str) -> str:
    """
    Render markdown text with syntax-highlighted code blocks.

    Args:
        text: Markdown text to render

    Returns:
        HTML string with rendered markdown and highlighted code
    """
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer

    # First, render markdown with fenced code blocks
    html_content = markdown.markdown(
        text,
        extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
    )

    # Post-process to add syntax highlighting to code blocks
    soup = BeautifulSoup(html_content, "html.parser")

    for code_block in soup.find_all("code"):
        # Skip inline code (code without pre parent)
        if not code_block.parent or code_block.parent.name != "pre":
            continue

        code_text = code_block.get_text()
        # Try to detect language from class attribute
        classes = code_block.get("class", [])
        language = None

        for cls in classes:
            if cls.startswith("language-"):
                language = cls.replace("language-", "")
                break

        # Highlight the code
        try:
            if language:
                lexer = get_lexer_by_name(language, stripall=False)
            else:
                lexer = guess_lexer(code_text)
        except Exception:
            lexer = TextLexer(stripall=False)

        formatter = HtmlFormatter(nowrap=False, cssclass="highlight")
        highlighted = highlight(code_text, lexer, formatter)

        # Replace the pre>code block with highlighted version
        highlighted_soup = BeautifulSoup(highlighted, "html.parser")
        code_block.parent.replace_with(highlighted_soup)

    return str(soup)


def count_turns(messages: List[Message]) -> int:
    """
    Count the number of conversation turns (user-assistant pairs).

    A turn is defined as a user message followed by one or more assistant messages.

    Args:
        messages: List of conversation messages

    Returns:
        Number of complete turns in the conversation
    """
    turns = 0
    i = 0
    while i < len(messages):
        # Look for user message
        if messages[i].role == "user":
            # Count this as a turn
            turns += 1
            i += 1
            # Skip any following assistant messages (they're part of this turn)
            while i < len(messages) and messages[i].role == "assistant":
                i += 1
        else:
            # Skip assistant messages without a preceding user message
            i += 1
    return turns


def filter_last_turns(messages: List[Message], n_turns: int) -> List[Message]:
    """
    Filter messages to keep only the last N conversation turns.

    Args:
        messages: List of all conversation messages
        n_turns: Number of turns to keep from the end

    Returns:
        Filtered list containing last N turns

    Raises:
        ValueError: If n_turns is invalid
    """
    total_turns = count_turns(messages)
    assert n_turns > 0, "Number of turns must be positive"
    assert n_turns <= total_turns, f"Requested {n_turns} turns but conversation only has {total_turns} turns"

    # Find the starting index for the last N turns
    turns_seen = 0
    start_idx = 0

    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            turns_seen += 1
            if turns_seen == n_turns:
                # Found the start of the Nth turn from the end
                start_idx = i
                break

    return messages[start_idx:]


def generate_xml_text(messages: List[Message]) -> str:
    """
    Generate XML format text for LLM consumption.

    Args:
        messages: List of conversation messages

    Returns:
        XML-formatted string representation of the conversation
    """
    lines = ["<conversation>"]

    for idx, msg in enumerate(messages, 1):
        lines.append(f'  <message index="{idx}" role="{msg.role}">')
        lines.append("    <content>")
        # Content will be escaped in the HTML template, not here
        lines.append(f"      {msg.content}")
        lines.append("    </content>")
        lines.append("  </message>")

    lines.append("</conversation>")
    return "\n".join(lines)


def build_html(url: str, messages: List[Message], platform_name: str = "ChatGPT") -> str:
    """
    Build the complete HTML page with conversation content.

    Args:
        url: The source URL of the conversation
        messages: List of conversation messages
        platform_name: Name of the platform ("ChatGPT" or "Claude")

    Returns:
        Complete HTML string ready to be written to file
    """
    from pygments.formatters import HtmlFormatter

    # Generate XML text for LLM view
    xml_text = generate_xml_text(messages)

    # Generate XML for different turn counts for the dropdown
    total_turns = count_turns(messages)
    xml_data_by_turns = {"all": xml_text}
    turn_options = []

    for n in range(1, min(total_turns + 1, 11)):  # Limit to max 10 turn options
        filtered_messages = filter_last_turns(messages, n)
        xml_for_n_turns = generate_xml_text(filtered_messages)
        xml_data_by_turns[str(n)] = xml_for_n_turns
        turn_options.append((n, len(filtered_messages)))

    # Create JavaScript object with escaped XML strings
    xml_data_json = json.dumps(xml_data_by_turns)

    # Check if conversation contains attachment references
    has_attachments = any(
        "attachment hidden" in msg.content.lower() or "files hidden" in msg.content.lower() for msg in messages
    )

    # Build attachment warning if needed
    attachment_warning = ""
    if has_attachments:
        attachment_warning = """
        <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 1rem; margin-bottom: 1rem; border-radius: 4px;">
          <strong>⚠️ Note:</strong> This conversation referenced attachments (images/PDFs) that are not included in shared links for privacy/security reasons.
        </div>
        """

    # Generate Pygments CSS for code highlighting
    formatter = HtmlFormatter(nowrap=False)
    pygments_css = formatter.get_style_defs(".highlight")

    # Build navigation sidebar
    nav_items = []
    for idx, msg in enumerate(messages, 1):
        role_emoji = "👤" if msg.role == "user" else "🤖"
        # Get first line or first 60 chars as preview
        preview = msg.content.split("\n")[0][:60]
        if len(msg.content.split("\n")[0]) > 60 or len(msg.content.split("\n")) > 1:
            preview += "..."

        nav_items.append(
            f'<li><a href="#msg-{idx}">{role_emoji} Message {idx}</a>'
            f'<div class="nav-preview">{html.escape(preview)}</div></li>'
        )

    nav_html = "\n".join(nav_items)

    # Build conversation HTML for human view with markdown rendering
    conversation_html = []
    for idx, msg in enumerate(messages, 1):
        role_class = "user" if msg.role == "user" else "assistant"
        role_label = "👤 User" if msg.role == "user" else "🤖 Assistant"

        # Render markdown content
        content_html = render_markdown_with_code(msg.content)

        conversation_html.append(
            f"""
<div class="message {role_class}" id="msg-{idx}">
  <div class="message-header">{role_label} <span class="message-number">#{idx}</span></div>
  <div class="message-content">{content_html}</div>
  <div class="back-top"><a href="#top">↑ Back to top</a></div>
</div>
"""
        )

    conversation_section = "".join(conversation_html)

    # Complete HTML document
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{platform_name} Conversation – {html.escape(url)}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, 'Apple Color Emoji','Segoe UI Emoji';
    margin: 0; padding: 0; line-height: 1.6;
    background: #f8f9fa;
  }}

  /* Layout with sidebar */
  .page {{ display: grid; grid-template-columns: 280px minmax(0,1fr); gap: 0; }}

  #sidebar {{
    position: sticky; top: 0; align-self: start;
    height: 100vh; overflow: auto;
    border-right: 1px solid #e1e4e8; background: #ffffff;
    box-shadow: 2px 0 4px rgba(0,0,0,0.05);
  }}
  #sidebar .sidebar-inner {{ padding: 1rem; }}
  #sidebar h2 {{ margin: 0 0 1rem 0; font-size: 1rem; color: #24292e; }}

  .nav-list {{
    list-style: none; padding: 0; margin: 0;
  }}
  .nav-list li {{
    margin-bottom: 0.75rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #f0f0f0;
  }}
  .nav-list li:last-child {{ border-bottom: none; }}
  .nav-list a {{
    text-decoration: none; color: #0366d6;
    font-weight: 500;
    display: block;
  }}
  .nav-list a:hover {{ text-decoration: underline; }}
  .nav-preview {{
    font-size: 0.85rem;
    color: #586069;
    margin-top: 0.25rem;
    line-height: 1.4;
  }}

  main.container {{
    padding: 1rem 2rem;
    max-width: 1000px;
  }}

  @media (max-width: 900px) {{
    .page {{ grid-template-columns: 1fr; }}
    #sidebar {{
      position: relative;
      height: auto;
      border-right: none;
      border-bottom: 1px solid #e1e4e8;
    }}
  }}

  .header {{
    background: white;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  .header h1 {{
    margin: 0 0 0.5rem 0;
    font-size: 1.5rem;
    color: #24292e;
  }}
  .meta {{
    color: #586069;
    font-size: 0.9rem;
  }}
  .meta a {{
    color: #0366d6;
    text-decoration: none;
  }}
  .meta a:hover {{
    text-decoration: underline;
  }}
  .stats {{
    margin-top: 0.5rem;
    color: #586069;
    font-size: 0.85rem;
  }}

  /* View toggle */
  .view-toggle {{
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 1rem;
    padding: 1rem;
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  .toggle-btn {{
    padding: 0.5rem 1rem;
    border: 1px solid #dadce0;
    background: white;
    cursor: pointer;
    border-radius: 6px;
    font-size: 0.9rem;
    transition: all 0.2s;
  }}
  .toggle-btn.active {{
    background: #1a73e8;
    color: white;
    border-color: #1a73e8;
  }}
  .toggle-btn:hover:not(.active) {{
    background: #f8f9fa;
    border-color: #1a73e8;
  }}

  /* Human view */
  #human-view {{
    display: block;
  }}
  .message {{
    background: white;
    margin-bottom: 1.5rem;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    scroll-margin-top: 1rem;
  }}
  .message.user {{
    border-left: 4px solid #0366d6;
  }}
  .message.assistant {{
    border-left: 4px solid #28a745;
  }}
  .message-header {{
    font-weight: 600;
    margin-bottom: 1rem;
    color: #24292e;
    font-size: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .message-number {{
    font-weight: normal;
    color: #6a737d;
    font-size: 0.9rem;
  }}
  .message-content {{
    color: #24292e;
    line-height: 1.6;
  }}
  .message-content p {{
    margin: 0 0 1em 0;
  }}
  .message-content p:last-child {{
    margin-bottom: 0;
  }}
  .message-content pre {{
    background: #f6f8fa;
    padding: 1rem;
    border-radius: 6px;
    overflow-x: auto;
    margin: 1em 0;
  }}
  .message-content code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Courier New', monospace;
    font-size: 0.9em;
  }}
  .message-content pre code {{
    background: none;
    padding: 0;
    border: none;
  }}
  .message-content :not(pre) > code {{
    background: #f6f8fa;
    padding: 0.2em 0.4em;
    border-radius: 3px;
  }}
  .message-content table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }}
  .message-content table th,
  .message-content table td {{
    border: 1px solid #d1d5da;
    padding: 0.5rem;
  }}
  .message-content table th {{
    background: #f6f8fa;
    font-weight: 600;
  }}
  .back-top {{
    margin-top: 1rem;
    font-size: 0.9rem;
  }}
  .back-top a {{
    color: #0366d6;
    text-decoration: none;
  }}
  .back-top a:hover {{
    text-decoration: underline;
  }}

  :target {{
    scroll-margin-top: 1rem;
  }}

  /* LLM view */
  #llm-view {{
    display: none;
    background: white;
    padding: 1.5rem;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  #llm-view h2 {{
    margin: 0 0 1rem 0;
    font-size: 1.25rem;
    color: #202124;
  }}
  #llm-view p {{
    color: #5f6368;
    margin-bottom: 1rem;
  }}
  #llm-text {{
    width: 100%;
    height: 70vh;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.85em;
    border: 1px solid #dadce0;
    border-radius: 6px;
    padding: 1rem;
    resize: vertical;
    background: #f8f9fa;
  }}
  .copy-hint {{
    margin-top: 0.75rem;
    padding: 0.75rem;
    background: #e8f0fe;
    border-radius: 6px;
    color: #174ea6;
    font-size: 0.9em;
  }}

  /* Pygments syntax highlighting */
  {pygments_css}
</style>
</head>
<body>
<a id="top"></a>

<div class="page">
  <nav id="sidebar">
    <div class="sidebar-inner">
      <h2>📑 Messages ({len(messages)})</h2>
      <ul class="nav-list">
        {nav_html}
      </ul>
    </div>
  </nav>

  <main class="container">
    <div class="header">
      <h1>💬 {platform_name} Conversation</h1>
      <div class="meta">
        <strong>Source:</strong> <a href="{html.escape(url)}" target="_blank">{html.escape(url)}</a>
        <div class="stats">
          <strong>Total messages:</strong> {len(messages)}
          · <strong>User:</strong> {sum(1 for m in messages if m.role == 'user')}
          · <strong>Assistant:</strong> {sum(1 for m in messages if m.role == 'assistant')}
          · <strong>Turns:</strong> {count_turns(messages)}
        </div>
      </div>
    </div>

    {attachment_warning}

  <div class="view-toggle">
    <strong>View:</strong>
    <button class="toggle-btn active" onclick="showHumanView(this)">👤 Human</button>
    <button class="toggle-btn" onclick="showLLMView(this)">🤖 LLM</button>
  </div>

  <div id="human-view">
    {conversation_section}
  </div>

    <div id="llm-view">
      <h2>🤖 LLM View - XML Format</h2>
      <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
        <label for="turn-selector" style="font-weight: 500;">Show turns:</label>
        <select id="turn-selector" onchange="updateXMLContent()" style="padding: 0.5rem; border: 1px solid #dadce0; border-radius: 6px; font-size: 0.9rem; cursor: pointer;">
          <option value="all">All ({count_turns(messages)} turns, {len(messages)} messages)</option>
          {"".join(f'<option value="{n}">Last {n} turn{"s" if n > 1 else ""} ({msg_count} messages)</option>' for n, msg_count in reversed(turn_options))}
        </select>
      </div>
      <textarea id="llm-text" readonly>{xml_text.replace('</textarea>', '&lt;/textarea&gt;')}</textarea>
      <div class="copy-hint">
        💡 <strong>Tip:</strong> Click in the text area and press Ctrl+A (Cmd+A on Mac) to select all, then Ctrl+C (Cmd+C) to copy.
      </div>
    </div>
  </main>
</div>

<script>
// Store XML data for different turn counts
const xmlData = {xml_data_json};

function showHumanView(btn) {{
  document.getElementById('human-view').style.display = 'block';
  document.getElementById('llm-view').style.display = 'none';
  document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}

function showLLMView(btn) {{
  document.getElementById('human-view').style.display = 'none';
  document.getElementById('llm-view').style.display = 'block';
  document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  // Auto-select all text when switching to LLM view for easy copying
  setTimeout(() => {{
    const textArea = document.getElementById('llm-text');
    textArea.focus();
    textArea.select();
  }}, 100);
}}

function updateXMLContent() {{
  const selector = document.getElementById('turn-selector');
  const textArea = document.getElementById('llm-text');
  const selectedValue = selector.value;

  if (xmlData[selectedValue]) {{
    textArea.value = xmlData[selectedValue];
  }}
}}
</script>
</body>
</html>
"""


def derive_output_path(url: str) -> pathlib.Path:
    """
    Derive a temporary output path from the conversation URL.

    Args:
        url: The conversation URL

    Returns:
        Path object for the output HTML file in the current directory
    """
    # Detect platform for proper filename prefix
    platform = detect_platform(url)

    # Extract conversation ID from URL
    match = re.search(r"/share/([a-f0-9-]+)", url)
    if match:
        conv_id = match.group(1)[:12]  # Use first 12 chars
        filename = f"{platform}_{conv_id}.html"
    else:
        filename = f"{platform}_conversation.html"

    return pathlib.Path(filename)


def main() -> int:
    """
    Main entry point for the renderchat CLI.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    ap = argparse.ArgumentParser(description="Render ChatGPT, Claude, or Grok conversations to a single HTML page")
    ap.add_argument(
        "url",
        help="Shared conversation URL (https://chatgpt.com/share/..., https://claude.ai/share/..., or https://grok.com/share/...)",
    )
    ap.add_argument("-o", "--out", help="Output HTML file path (default: temporary file derived from conversation ID)")
    ap.add_argument("--no-open", action="store_true", help="Don't open the HTML file in browser after generation")
    ap.add_argument(
        "--save-xml",
        nargs="?",
        const="",
        metavar="PATH",
        help="Save conversation as XML file. If no path specified, saves to {conversation_id}.xml in current directory",
    )
    ap.add_argument(
        "--last-turns",
        type=int,
        metavar="N",
        help="Include only the last N conversation turns (user-assistant pairs) in saved XML. Requires --save-xml.",
    )
    args = ap.parse_args()

    # Validate arguments
    if args.last_turns is not None:
        if args.save_xml is None:
            print("❌ Error: --last-turns requires --save-xml to be specified", file=sys.stderr)
            return 1
        if args.last_turns <= 0:
            print("❌ Error: --last-turns must be a positive integer", file=sys.stderr)
            return 1

    # Validate URL format
    try:
        platform = detect_platform(args.url)
    except ValueError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1

    # Set default output path if not provided
    if args.out is None:
        args.out = str(derive_output_path(args.url))

    try:
        print(f"🌐 Fetching conversation from {args.url}...", file=sys.stderr)
        messages = fetch_conversation(args.url)
        print(
            f"✓ Fetched {len(messages)} messages "
            f"({sum(1 for m in messages if m.role == 'user')} user, "
            f"{sum(1 for m in messages if m.role == 'assistant')} assistant)",
            file=sys.stderr,
        )

        # Save XML if requested
        if args.save_xml is not None:
            # Apply turn filter if specified
            messages_for_xml = messages
            if args.last_turns is not None:
                try:
                    total_turns = count_turns(messages)
                    if args.last_turns > total_turns:
                        print(
                            f"❌ Error: Requested {args.last_turns} turns but conversation only has {total_turns} turns",
                            file=sys.stderr,
                        )
                        return 1
                    messages_for_xml = filter_last_turns(messages, args.last_turns)
                    print(
                        f"📊 Filtered to last {args.last_turns} turn(s) "
                        f"({len(messages_for_xml)} messages out of {len(messages)})",
                        file=sys.stderr,
                    )
                except AssertionError as e:
                    print(f"❌ Error: {e}", file=sys.stderr)
                    return 1

            xml_content = generate_xml_text(messages_for_xml)
            if args.save_xml == "":
                # Default: save to {conversation_id}.xml in current directory
                match = re.search(r"/share/([a-f0-9-]+)", args.url)
                if match:
                    conv_id = match.group(1)[:12]
                    xml_path = pathlib.Path(f"{conv_id}.xml")
                else:
                    xml_path = pathlib.Path("conversation.xml")
            else:
                xml_path = pathlib.Path(args.save_xml)

            print(f"💾 Writing XML file: {xml_path.resolve()}", file=sys.stderr)
            xml_path.write_text(xml_content, encoding="utf-8")
            xml_size = xml_path.stat().st_size
            print(f"✓ Wrote {xml_size:,} bytes to {xml_path}", file=sys.stderr)

        print("🔨 Generating HTML...", file=sys.stderr)
        platform_name = {"chatgpt": "ChatGPT", "claude": "Claude", "grok": "Grok"}[platform]
        html_out = build_html(args.url, messages, platform_name)

        out_path = pathlib.Path(args.out)
        print(f"💾 Writing HTML file: {out_path.resolve()}", file=sys.stderr)
        out_path.write_text(html_out, encoding="utf-8")
        file_size = out_path.stat().st_size
        print(f"✓ Wrote {file_size:,} bytes to {out_path}", file=sys.stderr)

        if not args.no_open:
            print(f"🌐 Opening {out_path} in browser...", file=sys.stderr)
            webbrowser.open(str(out_path.resolve().as_uri()))

            # Wait for browser to load the file before deleting
            time.sleep(10)

            # Remove the HTML file after browser has loaded it
            try:
                out_path.unlink()
                print("🧹 Removed temporary file", file=sys.stderr)
            except Exception:
                pass  # Silently ignore if removal fails

        return 0

    except PlaywrightTimeout as e:
        print(f"❌ Error: Page load timeout - {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"❌ Error parsing conversation: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
