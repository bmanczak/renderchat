# renderchat

> Just show me the conversation.

Given the URL of a ChatGPT, Claude, or Grok shared conversation, `renderchat` extracts the conversation and renders it into copy-paste text for any LLM. There's also a Human view that is much more readable (but way worse than native interface of chatgpt, claude, or grok tbh).

I built this bc I have conversations in chatgpt, claude, or grok that I want to use in other applications (e.g. Cursor) as context.

[Here's](https://www.loom.com/share/acb40d73daa641c5a4beefd2ba81f678?speed=2.5) a 13 second demo of the tool in action 🤗

## Installation

Install directly from GitHub:

```bash
uv tool install git+https://github.com/bmanczak/renderchat
```

Or manually:

```bash
git clone https://github.com/bmanczak/renderchat
cd renderchat
uv pip install -e .
```

The tool will automatically install Playwright's Firefox browser on first run.

Firefox is used for all platforms (better Cloudflare bypass than Chromium).

## Usage

You get the URL of a conversation by clicking the "Share" button in chatgpt, claude, or grok and then copying the URL.

**ChatGPT:**

```bash
renderchat https://chatgpt.com/share/68f8d065-e1a0-8002-bfad-cd20855d5c8f
```

**Claude:**

```bash
renderchat https://claude.ai/share/a110df84-4c35-4865-8587-e95ed13ae3fb
```

**Grok:**

```bash
renderchat https://grok.com/share/bGVnYWN5_57a569b2-d8d9-43be-b345-b60e756b8c63
```

The tool will:

1. Fetch the shared conversation from ChatGPT, Claude, or Grok
2. Render it into a single static temporary HTML file
3. Automatically open the file in your browser

Once open, you can toggle between two views:

- **👤 Human View**: Clean, readable conversation with markdown rendering and navigation
- **🤖 LLM View**: XML-formatted conversation ready to paste into any LLM

## Features

- **📑 Navigation sidebar** - jump to any message instantly
- **✨ Markdown rendering** - code blocks with syntax highlighting, tables, lists, etc.
- **🌐 Multi-platform** - supports ChatGPT, Claude, and Grok conversations
- **Dual view modes** - toggle between Human and LLM views
  - **👤 Human View**: Pretty interface with conversation flow and markdown
  - **🤖 LLM View**: XML format - perfect for copying to any LLM for analysis
- **Smart parsing** - preserves all formatting and code structure
- **Copy-friendly** - one click to copy the entire conversation
- **Responsive design** - works on mobile
- **Search-friendly** - use Ctrl+F to find anything in the conversation
- **Auto-setup** - Playwright Firefox installs automatically on first run
- **🛡️ Cloudflare bypass** - automatically handles Claude's bot protection

## Supported platforms

- ✅ ChatGPT shared conversations (https://chatgpt.com/share/...)
- ✅ Claude shared conversations (https://claude.ai/share/...)
- ✅ Grok shared conversations (https://grok.com/share/...)

## License

BSD0 go nuts
