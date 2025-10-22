# renderchat

> Just show me the conversation.

Given the URL of a ChatGPT or Claude shared conversation `renderchat` extracts the conversation and renders it into copy-paste text for any LLM. There's also a Human view that is much more readable (but way worse than native interface of chatgpt or claude tbh).

I built this bc I have conversations in chatgpt or claude that I want to use in other applications (e.g. Cursor) as context.

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

The tool will automatically install Playwright's chromium browser on first run.

## Usage

You get the URL of a conversation by clicking the "Share" button in chatgpt or claude and then copying the URL.

**ChatGPT:**

```bash
renderchat https://chatgpt.com/share/68f8d065-e1a0-8002-bfad-cd20855d5c8f
```

**Claude:**

```bash
renderchat https://claude.ai/share/a110df84-4c35-4865-8587-e95ed13ae3fb
```

The tool will:

1. Fetch the shared conversation from ChatGPT or Claude
2. Render it into a single static temporary HTML file
3. Automatically open the file in your browser

Once open, you can toggle between two views:

- **👤 Human View**: Clean, readable conversation with markdown rendering and navigation
- **🤖 LLM View**: XML-formatted conversation ready to paste into any LLM

## Features

- **📑 Navigation sidebar** - jump to any message instantly
- **✨ Markdown rendering** - code blocks with syntax highlighting, tables, lists, etc.
- **🌐 Multi-platform** - supports both ChatGPT and Claude conversations
- **Dual view modes** - toggle between Human and LLM views
  - **👤 Human View**: Pretty interface with conversation flow and markdown
  - **🤖 LLM View**: XML format - perfect for copying to any LLM for analysis
- **Smart parsing** - preserves all formatting and code structure
- **Copy-friendly** - one click to copy the entire conversation
- **Responsive design** - works on mobile
- **Search-friendly** - use Ctrl+F to find anything in the conversation
- **Auto-setup** - Playwright chromium installs automatically on first run

## Supported platforms

- ✅ ChatGPT shared conversations (https://chatgpt.com/share/...)
- ✅ Claude shared conversations (https://claude.ai/share/...)
- 🚧 More platforms coming soon (Grok)

## License

BSD0 go nuts
