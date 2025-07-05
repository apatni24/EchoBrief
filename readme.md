[![CI](https://github.com/apatni24/EchoBrief/actions/workflows/ci.yml/badge.svg)](https://github.com/apatni24/EchoBrief/actions/workflows/ci.yml)

# 🎧 EchoBrief — Scalable Podcast Summarization Backend

**EchoBrief** is an event-driven backend system that transcribes and summarizes podcast episodes in real time. Users simply paste a podcast episode URL, choose a summary format (bullet points, narrative, or takeaways), and receive a high-quality summary within a minute for episodes up to 30 minutes.

> 🔗 **Live App**: [https://echobrief.onrender.com](https://echobrief.onrender.com)  
> ⏱️ **Summarizes a 30-minute podcast in <90 seconds**  
> 🌍 Deployed on low-latency infrastructure (Singapore – Render + Upstash)

---

## 🧠 Why This Project Stands Out

EchoBrief was built to solve real-world backend engineering challenges. It showcases:

- 🔄 Loose coupling across services using Redis Streams
- 📡 Real-time updates with WebSockets for instant feedback
- 🧠 Scalable summarization via LLaMA 3.3 70B LLMs
- 🐳 Unified Dockerized deployment with internal NGINX routing
- 🚦 Thoughtful design to handle cold starts and API rate limits
- 💾 **Multi-layer caching system for optimal performance**
- 🧪 Comprehensive test coverage for reliability

---

### 🐳 Why Only One Dockerfile in a Microservices Setup?

Although EchoBrief follows a microservices architecture, all services are hosted on a single server and exposed on different ports. An NGINX reverse proxy is used to route traffic appropriately.

This design choice avoids multiple Dockerfiles and leverages Render's free-tier constraints efficiently.

---

## 🧩 Architecture

<img src="./assets/architecture.svg" alt="EchoBrief Architecture" width="500"/>

### 🔄 Event Flow

1. **Podcast Audio Resolver Service** (Port 8080)
   - Receives podcast URLs from frontend
   - Extracts audio files from Apple Podcasts/Spotify
   - Emits `audio_uploaded` events to Redis Streams

2. **Transcription Service** (Port 8081)
   - Consumes `audio_uploaded` events
   - Transcribes audio using AssemblyAI with speaker diarization
   - Emits `transcription_complete` events

3. **Summarization Service** (Port 8082)
   - Consumes `transcription_complete` events
   - Generates summaries using LLaMA 3.3 70B
   - Sends real-time updates via WebSockets

---

## 💾 Multi-Layer Caching System

EchoBrief implements a sophisticated multi-layer caching system to optimize performance and reduce processing time:

### Layer 1: Episode-Level Caching (High Impact)
- **Cache Key**: `episode:{platform}:{episode_id}:{summary_type}`
- **What to Cache**: Complete summaries for specific episodes
- **Use Case**: Instant responses for previously processed episodes
- **TTL**: 7 days

### Layer 2: Transcript-Level Caching (Medium Impact)
- **Cache Key**: `transcript:{audio_hash}:{summary_type}`
- **What to Cache**: Summaries for identical transcripts
- **Use Case**: Cross-platform deduplication (same content, different platforms)
- **TTL**: 7 days

### Cache Benefits
- ⚡ **Cache Hits**: 0-1 second response time
- 🔄 **Cache Misses**: Normal processing (50-110 seconds)
- 🌍 **Cross-Platform**: Identical content cached regardless of source
- 📊 **Admin Controls**: Cache statistics and management endpoints

### Cache Management
```bash
# Get cache statistics
GET /cache/stats

# Clear all cache (admin only)
DELETE /cache/clear?admin_key={key}

# Invalidate specific episode
DELETE /cache/invalidate/{platform}/{episode_id}/{summary_type}
```

---

## 🔁 Cold Start Optimization

Render auto-suspends inactive services, which can cause a ~25–30s delay on the first request. To combat this:

> ⚡ As soon as the frontend loads, it pings the backend's `/health` endpoint to **pre-warm** the server — ensuring fast, seamless user experience even after idle periods.

---

## 📨 Example Payload

Here's a sample event payload passed to the Redis Stream (`audio_uploaded`) when a podcast is fetched:

```json
{
  "file_path": "",
  "metadata": {
    "summary": "",
    "show_title": "",
    "show_summary": ""
  },
  "summary_type": "",
  "job_id": ""
}
```
**Fields explained:**

- `file_path`: Local/remote audio path  
- `metadata`: Podcast title, episode summary, and show description  
- `summary_type`: Format (e.g., `ts` = story-style/takeaways)  
- `job_id`: Correlation ID for async WebSocket updates  

---

## 🛠️ Tech Stack

| Layer              | Tool / Service                           |
|--------------------|------------------------------------------|
| Audio Resolution   | Python + feedparser                      |
| Transcription      | AssemblyAI (diarization + speech-to-text)|
| Summarization      | LLaMA 3.3 70B Versatile (via API)        |
| Events             | Redis Streams (Upstash – Singapore)      |
| Real-Time Updates  | WebSockets                               |
| Caching            | Redis (Upstash) with multi-layer strategy|
| Infrastructure     | Docker + NGINX + Render                  |
| Frontend           | React with dark mode support             |
| Testing            | pytest + Jest + comprehensive coverage   |

---

## 📁 Project Structure

```plaintext
echobrief-backend/
├── podcast_audio_resolver_service/    # RSS parsing, file download & event emit
│   ├── main.py                        # FastAPI app with cache endpoints
│   ├── get_audio.py                   # Audio extraction from platforms
│   ├── apple_scraper.py               # Apple Podcasts integration
│   ├── spotify_scraper.py             # Spotify integration
│   └── audio_upload_producer.py       # Redis Stream producer
├── transcription_service/             # Diarization + transcription via AssemblyAI
│   ├── main.py                        # FastAPI app
│   ├── assemblyai_transcriber.py      # Transcription logic
│   ├── audio_upload_consumer.py       # Redis Stream consumer
│   └── transcription_complete_producer.py # Event producer
├── summarization_service/             # LLM-based summarization
│   ├── main.py                        # FastAPI app with WebSocket support
│   ├── summarize.py                   # LLaMA integration with rate limiting
│   ├── transcription_complete_consumer.py # Redis Stream consumer
│   ├── ws_manager.py                  # WebSocket connection management
│   └── summary_types/                 # Different summary formats
│       ├── bullet_points_summary.py
│       ├── narrative_summary.py
│       └── takeaway_summary.py
├── cache_service.py                   # Multi-layer caching implementation
├── redis_stream_client.py             # Redis Streams abstraction
├── nginx.conf                         # Reverse proxy config (internal routing)
├── Dockerfile                         # Container for all services
├── start.sh                           # Entrypoint to run everything
├── tests/                             # Comprehensive test suite
│   ├── test_cache_service.py          # Cache service unit tests
│   ├── test_cache_endpoints.py        # API endpoint tests
│   ├── test_cache_integration.py      # Integration tests
│   └── test_*.py                      # Other service tests
├── run_cache_tests.py                 # Cache test runner
├── CACHE_TESTS_README.md              # Cache testing documentation
└── audio_files/                       # (Optional) Local audio storage
```

---

## 📄 Summary Types Supported

EchoBrief supports the following summary formats:

- **Bullet Points** (`bs`): Structured breakdown of key points
- **Narrative** (`ns`): Story-style narrative summaries
- **Takeaways** (`ts`): Key actionable takeaways and insights

---

## 📉 API Rate Limiting

To comply with **ChatGroq API's per-minute token limit**, EchoBrief enforces:

> ⏳ **A 60-second cooldown between successive LLM summarization requests**

This ensures:

- No unexpected rate-limit errors during high load
- More predictable performance under concurrent usage
- Graceful queuing of summaries without affecting user experience

> The rate-limiting is implemented with an internal wait logic before calling the LLM API, keeping throughput compliant with usage constraints.

---

## 🧪 Testing

EchoBrief includes comprehensive testing across all layers:

### Backend Tests
```bash
# Run all cache tests
python3 run_cache_tests.py

# Run specific test suites
python3 -m pytest tests/test_cache_service.py -v
python3 -m pytest tests/test_cache_endpoints.py -v
python3 -m pytest tests/test_cache_integration.py -v

# Run with coverage
python3 -m pytest tests/test_cache_*.py --cov=cache_service --cov-report=html
```

### Frontend Tests
```bash
cd ../echobrief-frontend
npm test -- --testPathPattern=CacheStats.test.jsx
```

### Test Coverage
- **Cache Service**: Unit tests for all caching operations
- **API Endpoints**: Authentication, error handling, and integration
- **Frontend Components**: Cache statistics display and user interactions
- **Integration**: Complete cache flow from request to storage

---

## 🚀 Getting Started (Local Dev)

### Prerequisites
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies (for frontend)
cd ../echobrief-frontend
npm install
```

### Environment Variables
```bash
# Required for production
ASSEMBLYAI_API_KEY=your_assemblyai_key
CHATGROQ_API_KEY=your_chatgroq_key
CHATGROQ_API_URL=https://api.chatgroq.com/v1
UPSTASH_REDIS_HOST=your_redis_host
UPSTASH_REDIS_PORT=6379
UPSTASH_REDIS_PASSWORD=your_redis_password
ADMIN_CACHE_KEY=your_admin_key

# Optional
ENV=dev  # or 'test' for testing
MODEL_NAME=llama-3.3-70b-versatile
```

### Running the Application
```bash
# Build and run with Docker
docker build -t echobrief .
./start.sh

# Or run services individually
python3 -m uvicorn podcast_audio_resolver_service.main:app --host 0.0.0.0 --port 8080
python3 -m uvicorn transcription_service.main:app --host 0.0.0.0 --port 8081
python3 -m uvicorn summarization_service.main:app --host 0.0.0.0 --port 8082
```

You'll have:
- All backend microservices up on internal ports
- NGINX reverse proxy managing internal routes
- Redis Streams wiring event flow between services
- Multi-layer caching system active

---

## 🔧 Cache Configuration

### Cache TTL Settings
```python
# Episode cache: 7 days
EPISODE_CACHE_TTL = 7 * 24 * 60 * 60

# Transcript cache: 7 days  
TRANSCRIPT_CACHE_TTL = 7 * 24 * 60 * 60
```

### Cache Key Patterns
```python
# Episode cache keys
"episode:{platform}:{episode_id}:{summary_type}"

# Transcript cache keys
"transcript:{sha256_hash}:{summary_type}"
```

### Cache Statistics
The system provides real-time cache statistics:
- Episode cache count
- Transcript cache count
- Total cached items
- Cache hit/miss ratios

---

## 🖼️ Frontend Screenshots

![EchoBrief Frontend - Input Screen](./assets/frontend_input.png)  
*User inputs podcast URL and selects summary type.*

![EchoBrief Frontend - Summary Output](./assets/frontend_output.png)  
*Generated summary is displayed live via WebSocket with cache indicators.*

---

## 👨‍💻 Author

Built by [Atishay Patni](https://www.linkedin.com/in/atishaypatni)  
SDE @ Wells Fargo | Backend Engineer 

---

## 📌 Future Enhancements

- GPU-based transcription (WhisperX + PyAnnote)
- Support for >30 min podcasts (chunking + parallel summary stitching)
- Authentication and saved summary history
- Podcast directory browsing from within the app
- Advanced cache analytics and monitoring
- Cache warming strategies for popular content
- Multi-region cache distribution

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---
