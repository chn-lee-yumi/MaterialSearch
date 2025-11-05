# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaterialSearch is a local photo and video search engine that enables natural language and image-based search using Chinese CLIP models. It extracts visual features from images and video frames, stores them in a SQLite database, and performs similarity searches using cosine distance.

## Tech Stack

- **Backend**: Python 3.9+, Flask web server
- **Database**: SQLAlchemy ORM with SQLite
- **ML Models**: Transformers (Chinese CLIP or OpenAI CLIP), PyTorch
- **Search**: Faiss for vector similarity search
- **Video Processing**: OpenCV (cv2)
- **Image Processing**: Pillow, pillow-heif
- **Frontend**: Vue.js (served as static files)

## Development Commands

### Setup and Installation
```bash
# Install dependencies (CPU version)
pip install -U -r requirements.txt

# For Windows systems
pip install -U -r requirements_windows.txt
# or double-click: install.bat

# Install ffmpeg (required for video segment download feature)
# Windows: run install_ffmpeg.bat
```

### Running the Application
```bash
# Start the Flask server
python main.py

# Windows: double-click run.bat

# Run with custom configuration (create .env file or set environment variables)
# Example: HOST=0.0.0.0 PORT=8080 python main.py
```

### Testing and Benchmarking
```bash
# Run API tests (requires pytest)
pytest api_test.py
# or
python api_test.py

# Run model performance benchmark
python benchmark.py

# Command-line search
python search.py image "搜索词"
python search.py video "搜索词"
```

### Docker Deployment
```bash
# Start with docker-compose
docker-compose up -d

# Stop
docker-compose down
```

## Architecture

### Core Components

**main.py** - Application entry point
- Initializes temp directories and database
- Starts scanner thread (optional auto-scan)
- Launches Flask web server

**config.py** - Centralized configuration
- All settings configurable via environment variables or `.env` file
- Auto-detects optimal device (CUDA > XPU > MPS > DirectML > CPU)
- Prints full configuration on startup

**scan.py** - Scanner class
- Recursive directory scanning with path filtering
- Batch processing of images (controlled by `SCAN_PROCESS_BATCH_SIZE`)
- Incremental scanning with checkpoint recovery (uses `tmp/assets.pickle`)
- Auto-save every `AUTO_SAVE_INTERVAL` files
- Detects file changes via modification time or SHA1 checksum
- Scheduled auto-scan support

**process_assets.py** - Feature extraction
- Loads CLIP model on import (model cached globally)
- Extracts normalized features from images/videos using CLIP
- Batch processing for efficiency
- Handles various image formats including HEIC

**search.py** - Search operations
- Text-to-image, image-to-image, text-to-video, image-to-video search
- LRU caching for search results (`@lru_cache(maxsize=CACHE_SIZE)`)
- Video search returns time-stamped segments
- Cosine similarity matching with configurable thresholds

**database.py** - Database operations
- CRUD operations for Image and Video tables
- Query builders with path/time filtering
- Batch operations for efficiency
- Handles outdated record detection and deletion

**routes.py** / **routes_encrypted.py** - Flask API endpoints
- RESTful API for search, scan control, file serving
- Optional login authentication
- Image thumbnail generation on-the-fly
- Video segment cropping and download

### Data Flow

**Scanning Workflow:**
1. Scanner walks directories → filters by extension/path/keywords
2. Compares files with database (modification time or checksum)
3. Batches images (size: `SCAN_PROCESS_BATCH_SIZE`)
4. Processes batch → extracts CLIP features
5. Stores features as binary blobs in SQLite
6. Auto-saves progress every N files (checkpoint recovery)

**Search Workflow:**
1. User query (text or image) → processed by CLIP model
2. Feature vector extracted and normalized
3. Database loads relevant features based on filters
4. Computes cosine similarity with all stored features
5. Applies positive/negative thresholds
6. Returns sorted results by similarity score

**Video Search Specifics:**
- Videos stored as individual frames with timestamps
- Each frame has separate database record
- Search finds matching frames → groups into continuous segments
- Segments merged if gap ≤ 2 × `FRAME_INTERVAL`
- Returns video path with time range (`#t=start,end`)

## Configuration

All configuration is in `config.py`, modifiable via:
1. Environment variables
2. `.env` file in project root
3. Default values in `config.py`

**Critical settings:**
- `MODEL_NAME`: CLIP model to use (changing requires database rebuild)
- `DEVICE`: auto/cpu/cuda/mps (auto-detected by default)
- `SCAN_PROCESS_BATCH_SIZE`: Images per batch (higher = faster but more memory)
- `FRAME_INTERVAL`: Seconds between video frames
- `ASSETS_PATH`: Comma-separated scan paths
- `SKIP_PATH`: Comma-separated paths to ignore
- `ENABLE_CHECKSUM`: Use SHA1 instead of mtime (slower but more reliable)

**Performance tuning:**
- 4GB GPU: small model, `SCAN_PROCESS_BATCH_SIZE=6`
- 8GB GPU: small model, `SCAN_PROCESS_BATCH_SIZE=12`
- CPU only: expect slower scanning (~30-50x slower than GPU)

## Database Schema

**Image table:**
- `id`: Primary key
- `path`: File path (indexed)
- `modify_time`: File modification timestamp (indexed)
- `checksum`: SHA1 hash (indexed, optional)
- `features`: Binary blob of normalized CLIP feature vector

**Video table:**
- `id`: Primary key
- `path`: Video file path (indexed)
- `frame_time`: Time in seconds for this frame
- `modify_time`: File modification timestamp (indexed)
- `checksum`: SHA1 hash (indexed, optional)
- `features`: Binary blob of normalized CLIP feature vector
- Note: Each video has multiple rows (one per extracted frame)

**PexelsVideo table:** (optional, for external video source)
- Stores metadata and thumbnail features for Pexels videos

## Important Notes

- **Model changes**: Changing `MODEL_NAME` requires deleting the database and rescanning
- **GPU memory**: If "CUDA out of memory" occurs, reduce `SCAN_PROCESS_BATCH_SIZE` or use smaller model
- **Checkpoint recovery**: If scanning interrupted, restart continues from `tmp/assets.pickle`
- **Cache clearing**: Search cache auto-clears after scan completion
- **Code obfuscation**: Some code (routes_encrypted.py) is intentionally obfuscated for copyright protection
- **Remote paths**: Avoid setting `ASSETS_PATH` to SMB/NFS (performance impact)
- **File extensions**: Add to `IMAGE_EXTENSIONS`/`VIDEO_EXTENSIONS` if formats not recognized

## Common Pitfalls

1. **Not installing ffmpeg**: Required for video segment download feature
2. **Wrong device config**: Check logs for auto-detected device, explicitly set if needed
3. **Small images skipped**: Reduce `IMAGE_MIN_WIDTH`/`IMAGE_MIN_HEIGHT` if needed
4. **Slow scanning**: Enable GPU, increase batch size, or use smaller model
5. **Search returns nothing**: Check thresholds are not too high, verify database has data
6. **Model download fails**: First run auto-downloads models, retry if network issues
