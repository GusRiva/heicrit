# HeiCrit - Critical Apparatus Editor

## Project Overview
App for creating critical apparatus for scholarly editions. Works as both web app and desktop app.

## Current Status
✅ Flask backend with basic file operations API
✅ Web frontend with file editor interface
⏳ Electron wrapper (not started)
⏳ XML/TEI processing (planned for later)

## Architecture
- **Backend**: Flask API (runs on localhost:5000)
- **Frontend**: HTML/CSS/JS web interface
- **Desktop**: Electron wrapper (planned)

## How to Run
1. Install dependencies: `pip install -r requirements.txt`
2. Start backend: `cd backend && python app.py`
3. Open frontend: Open `frontend/index.html` in browser

## API Endpoints
- `GET /api/health` - Health check
- `GET /api/files?directory=path` - List files in directory
- `GET /api/file/path` - Get file content
- `POST /api/file` - Save file

## Next Steps
- Add XML/TEI processing capabilities (project-specific)
- Add critical apparatus editing features
- Set up Electron wrapper for desktop app
