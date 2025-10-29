# AgentHQ Desktop

> Tauri + React desktop application for AgentHQ

## Setup

1. **Install dependencies**:
```bash
npm install
```

2. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your API URL and Google Client ID
```

3. **Run development mode**:
```bash
npm run tauri:dev
```

4. **Build for production**:
```bash
npm run tauri:build
```

## Requirements

- Node.js 18+
- Rust 1.70+
- Backend API running at `http://localhost:8000`

## Features

- 🔐 Google OAuth authentication
- 📝 Create Google Docs, Sheets, Slides
- 🎨 Modern React UI with Tailwind CSS
- 🚀 Fast native performance with Tauri
- 💾 Local state persistence

## Tech Stack

- **Framework**: Tauri 1.5+
- **Frontend**: React 18 + TypeScript
- **Styling**: Tailwind CSS
- **State**: Zustand
- **Data Fetching**: React Query
- **HTTP Client**: Axios

## Project Structure

```
desktop/
├── src/
│   ├── components/     # Reusable components
│   ├── pages/          # Page components
│   ├── services/       # API services
│   ├── store/          # Zustand stores
│   ├── types/          # TypeScript types
│   ├── utils/          # Utility functions
│   ├── App.tsx         # Main app component
│   └── main.tsx        # Entry point
├── src-tauri/          # Tauri Rust backend (to be added)
├── index.html          # HTML entry
├── vite.config.ts      # Vite configuration
└── package.json        # Dependencies
```

## Development

### Running the app

```bash
# Terminal 1: Start backend
cd ../backend
uvicorn app.main:app --reload

# Terminal 2: Start desktop app
cd ../desktop
npm run tauri:dev
```

### Building

```bash
npm run tauri:build
```

Binaries will be in:
- **macOS**: `src-tauri/target/release/bundle/dmg/`
- **Windows**: `src-tauri/target/release/bundle/msi/`
- **Linux**: `src-tauri/target/release/bundle/appimage/`

## OAuth Setup

See [../docs/OAUTH_SETUP.md](../docs/OAUTH_SETUP.md) for detailed Google OAuth configuration.

Quick steps:
1. Create OAuth credentials in Google Cloud Console
2. Set application type to "Desktop app"
3. Download credentials
4. Update `.env` with client ID

## Troubleshooting

### Build fails
- Ensure Rust is installed: `rustc --version`
- Update Rust: `rustup update`
- Clear cache: `rm -rf node_modules && npm install`

### OAuth not working
- Check backend is running
- Verify `.env` configuration
- Check redirect URI matches Google Console

### Hot reload not working
- Restart dev server
- Clear browser cache
- Check file watchers limit (Linux)

## License

MIT
