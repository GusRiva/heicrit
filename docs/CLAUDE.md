# HeiCrit - Critical Apparatus Editor

## Project Overview
App for creating critical apparatus for scholarly editions. Works as both web app and desktop app.

## Current Status
✅ Flask backend with TEI/XML processing using heipy
✅ Web frontend with file editor and apparatus display
✅ Directory upload for project-based file handling
✅ Classical scholarly apparatus formatting
✅ Synoptic map integration for complete entry lists
✅ Main text (Leithandschrift) display alongside apparatus
✅ Interactive location buttons with details panel
✅ Paginated apparatus entry navigation
✅ Apparatus entry creation with token selection
✅ Smart entry selection and visual token highlighting
⏳ Apparatus processing functions and display (ongoing)
⏳ Electron wrapper (tested)

## Architecture
- **Backend**: Flask API with heipy for TEI parsing (runs on localhost:5000)
- **Frontend**: HTML/CSS/JS web interface with classical apparatus display
- **Desktop**: Electron wrapper 

## How to Run
1. Activate virtual environment: `source venv/bin/activate`
2. Install dependencies: `pip install -r requirements.txt`
3. Start backend: `cd backend && python app.py`
4. Open frontend: Open `frontend/index.html` in browser
5. Use "Open Project Directory" to load TEI apparatus projects

## Development Notes
- Always activate virtual environment first: `source venv/bin/activate`
- Test backend imports: `python -c "import routes; print('Backend loaded')"`

## Key Features
- **Directory Upload**: Upload entire project directories with automatic file detection
- **TEI Processing**: Parse apparatus files with heipy and extract full apparatus data
- **Classical Display**: Format apparatus entries following scholarly conventions
- **Synoptic Integration**: Merge apparatus with synoptic map data for complete entry lists  
- **Main Text Display**: Extract and show Leithandschrift text alongside apparatus
- **Interactive Navigation**: Click location numbers for details, paginate through entries
- **Relative Path Resolution**: Handle TEI file references within project context
- **Apparatus Entry Creation**: Create new critical apparatus entries through token selection
- **Smart Visual Feedback**: Gray background for tokens with apparatus entries, colored highlighting for active selections
- **Intelligent Entry Selection**: Always selects first non-placeholder entry when navigating to new locations

## API Endpoints
- `GET /api/health` - Health check
- `GET /api/files?directory=path` - List files in directory
- `GET /api/file/path` - Get file content
- `POST /api/file` - Save file
- `POST /api/apparatus/process` - Process apparatus file
- `POST /api/apparatus/process-with-project` - Process apparatus with project context
- `POST /api/apparatus/validate` - Validate apparatus file
- `POST /api/synoptic/process` - Process synoptic map file
- `POST /api/apparatus/save` - Save new apparatus entries to XML file
- `POST /api/synoptic/compare` - Get synoptic comparison data for location details

## File Structure
- `backend/routes.py` - Main API routes with apparatus processing
- `frontend/app.js` - Frontend logic with apparatus display and navigation
- `frontend/index.html` - UI layout with main text, apparatus, and details panels
- `frontend/styles.css` - Classical apparatus styling with interactive elements
- `test_data/` - Sample TEI files for testing

## Current Implementation
- **Backend**: Extracts apparatus entries, synoptic map, and main text from TEI files; saves new entries to XML
- **Frontend**: Displays apparatus in classical format with pagination and interactive elements
- **UI Layout**: Three-panel design (main text | apparatus | details)
- **Navigation**: Previous/Next buttons for apparatus entries, clickable location numbers
- **Entry Creation**: Token-based selection system for creating new apparatus entries with visual feedback
- **Smart Navigation**: Automatically selects meaningful (non-placeholder) entries when navigating



