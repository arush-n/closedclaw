# ClosedClaw Memory Graph UI

A beautiful graph visualization interface for viewing and interacting with memories stored in the closedclaw backend (`src/closedclaw/api`). Inspired by [supermemory](https://app.supermemory.ai)'s design system.

## Features

- 🕸️ **Interactive Graph View**: Force-directed graph visualization of all your memories
- 🎨 **Modern Dark UI**: Clean, responsive design with smooth animations
- 💬 **Chat Interface**: Natural language conversations with your memories
- 🔍 **Smart Search**: AI-powered semantic search across your memories
- 📊 **Statistics Legend**: Real-time stats showing memory counts and connections
- 🖱️ **Pan & Zoom**: Navigate the graph with mouse controls
- 📋 **List View**: Alternative list view for memory browsing
- ⚡ **Fast & Responsive**: Built with Next.js 14 and Canvas-based rendering

## Quick Start

### Prerequisites

- Node.js 18+
- pnpm (recommended) or npm
- A running closedclaw API server (default: `http://localhost:8765`)
- OpenAI or Anthropic API key (for chat functionality)

### Installation

```bash
# Navigate to the UI directory
cd src/closedclaw/ui

# Install dependencies
pnpm install

# Copy environment file
cp .env.example .env.local

# Edit .env.local with your configuration
# - Set CLOSEDCLAW_API_URL (or MEM0_API_URL for legacy compatibility)
# - Add OPENAI_API_KEY or ANTHROPIC_API_KEY

# Start the development server
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) to see the chat interface.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLOSEDCLAW_API_URL` | URL to your closedclaw API instance | `http://localhost:8765` |
| `CLOSEDCLAW_API_TOKEN` | API token for closedclaw (if required) | - |
| `MEM0_API_URL` | Legacy alias for API URL (backward compatibility) | - |
| `MEM0_API_KEY` | Legacy alias for API token (backward compatibility) | - |
| `OPENAI_API_KEY` | OpenAI API key for chat responses | - |
| `OPENAI_MODEL` | OpenAI model to use | `gpt-4o-mini` |
| `ANTHROPIC_API_KEY` | Anthropic API key (alternative to OpenAI) | - |
| `ANTHROPIC_MODEL` | Anthropic model to use | `claude-3-haiku-20240307` |

### Setting up closedclaw API

1. Start the backend from this repository:
  ```bash
  cd src/closedclaw
  pip install -e ".[all]"
  closedclaw serve
  ```
2. Set `CLOSEDCLAW_API_URL=http://localhost:8765` in `.env.local`.
3. `MEM0_API_URL` and `MEM0_API_KEY` are still accepted as compatibility aliases.

## Project Structure

```
src/closedclaw/ui/
├── app/
│   ├── api/
│   │   ├── chat/route.ts          # LLM chat endpoint
│   │   └── memories/              # Memory API endpoints
│   │       ├── route.ts           # Get all memories
│   │       └── search/route.ts    # Search memories
│   ├── graph/page.tsx             # Main graph visualization page
│   ├── globals.css                # Dark theme styles
│   ├── layout.tsx
│   └── page.tsx                   # Redirects to /graph
├── components/
│   ├── graph/                     # Graph visualization components
│   │   ├── memory-graph.tsx       # Main graph component
│   │   ├── graph-canvas.tsx       # Canvas-based renderer
│   │   ├── legend.tsx             # Statistics legend
│   │   ├── navigation-controls.tsx # Zoom/pan controls
│   │   ├── node-detail-panel.tsx  # Memory detail panel
│   │   ├── sidebar.tsx            # Left sidebar
│   │   ├── use-force-simulation.ts # D3 force physics
│   │   ├── use-graph-interactions.ts # Pan/zoom/drag
│   │   ├── constants.ts           # Colors, settings
│   │   └── types.ts               # TypeScript types
│   ├── chat/                      # Chat UI components
│   │   ├── chat-sidebar.tsx       # Slide-in chat panel
│   │   ├── chat-input.tsx         # Message input
│   │   ├── agent-message.tsx      # AI responses
│   │   ├── user-message.tsx       # User messages
│   │   └── ...
│   └── ui/                        # Shared components
└── package.json
```

## Components

### ChatSidebar

The main chat interface component.

```tsx
import { ChatSidebar, ChatFloatingButton } from "@/components/chat";

function App() {
  const [isOpen, setIsOpen] = useState(false);
  
  return (
    <>
      <ChatSidebar
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        config={{
          userId: "user-123",
          baseUrl: "/api",
        }}
      />
      <ChatFloatingButton 
        onClick={() => setIsOpen(true)} 
        isOpen={isOpen} 
      />
    </>
  );
}
```

### useChatWithClosedclaw

A React hook for integrating chat with closedclaw.

```tsx
import { useChatWithClosedclaw } from "@/components/chat";

function ChatComponent() {
  const {
    messages,
    input,
    setInput,
    sendMessage,
    isLoading,
    error,
  } = useChatWithClosedclaw({
    config: { userId: "user-123" },
  });

  // Use in your custom UI
}
```

`useChatWithMem0` remains available as a compatibility alias.

## API Routes

### POST /api/chat

Send a message and get an AI response based on memories.

```json
{
  "message": "What do I know about machine learning?",
  "user_id": "user-123",
  "memories": [...],
  "history": [...]
}
```

### POST /api/memories/search

Search for relevant memories.

```json
{
  "query": "machine learning",
  "user_id": "user-123",
  "limit": 10
}
```

## Customization

### Styling

The UI uses Tailwind CSS with CSS variables for theming. Modify `app/globals.css` to customize colors:

```css
:root {
  --primary: 260 94% 59%;  /* Purple accent color */
  --background: 240 10% 3.9%;  /* Dark background */
  /* ... */
}
```

### Suggestions

Customize the default chat suggestions by passing them to `ChatSidebar`:

```tsx
<ChatSidebar
  suggestions={[
    "What meetings do I have?",
    "Summarize my notes from today",
    "What did I learn about X?",
  ]}
  // ...
/>
```

## License

MIT
