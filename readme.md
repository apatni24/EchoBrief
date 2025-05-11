# 🎧 EchoBrief — Scalable Podcast Summarization Backend

**EchoBrief** is a fast, event-driven backend system that transcribes and summarizes podcast episodes in real time. Users simply paste a podcast episode URL, choose a summary format (bullet points, narrative, or takeaways), and receive a high-quality summary within a minute for episodes up to 30 minutes.

> ⏱️ **Summarizes a 30-minute podcast in <90 seconds**  
> 🌍 Deployed on low-latency infrastructure (Singapore – Render + Upstash)

---

## 🧠 Why This Project Stands Out

This project demonstrates:

- ⚙️ Real-world **event-driven microservice architecture**
- 🌐 Efficient **streaming workflows** using Redis Streams
- 🧠 Use of **LLMs (LLaMA 3.3 70B Versatile)** for high-quality summarization
- 🔁 **WebSocket-based updates** for live frontend interaction
- 🐳 Clean deployment with **Docker + NGINX reverse proxy**
- 🚀 Built-in **cold start mitigation** for smoother UX
- 📦 Modular design across audio, transcription, and summarization layers

---

## 🧩 Architecture

![EchoBrief Architecture](./assets/architecture.svg)

*Note: Mermaid diagrams may not render correctly on all platforms; hence, a static image is provided.*

---

## 🔁 Cold Start Optimization

Render auto-suspends inactive services, which can cause a ~25–30s delay on the first request. To combat this:

> ⚡ As soon as the frontend loads, it pings the backend's `/health` endpoint to **pre-warm** the server — ensuring fast, seamless user experience even after idle periods.

---

## 📨 Example Payload

Here’s a sample event payload passed to the Redis Stream (`audio_uploaded`) when a podcast is fetched:

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
| Infrastructure     | Docker + NGINX + Render                  |
| Frontend           | Simple React App                         |

---

## 📁 Project Structure

```plaintext
echobrief/
├── podcast_audio_resolver_service/    # RSS parsing, file download & event emit
├── transcription_service/             # Diarization + transcription via AssemblyAI
├── summarization_service/             # LLM-based summarization
├── redis_stream_client.py             # Redis Streams abstraction
├── nginx.conf                         # Reverse proxy config (internal routing)
├── Dockerfile                         # Container for all services
├── start.sh                           # Entrypoint to run everything
└── audio_files/                       # (Optional) Local audio storage
```

---

## 📄 Summary Types Supported

- 🔹 Bullet Points
- 📘 Narrative (Story Format)
- 📌 Key Takeaways

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


## 🚀 Getting Started (Local Dev)

```bash
# Clone the repo
git clone https://github.com/apatni24/EchoBrief.git
cd EchoBrief

# Build and run
docker build -t echobrief .
./start.sh
```

You’ll have:

- All backend microservices up on internal ports
- NGINX reverse proxy managing internal routes
- Redis Streams wiring event flow between services

---

## 🖼️ Frontend Screenshots

![EchoBrief Frontend - Input Screen](./assets/frontend_input.png)  
*User inputs podcast URL and selects summary type.*

![EchoBrief Frontend - Summary Output](./assets/frontend_output.png)  
*Generated summary is displayed live via WebSocket.*

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

---
