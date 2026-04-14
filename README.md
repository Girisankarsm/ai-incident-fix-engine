🚀 Incident Memory Copilot

🔗 Live Demo: https://ai-incident-fix-engine.onrender.com

📝 Technical Deep Dive (Article 1): https://medium.com/p/e8971ecf0730?postPublishedType=initial

📝 Technical Deep Dive (Article 2): https://medium.com/p/94cc7dcde4b3?postPublishedType=initial

📝 Technical Deep Dive (Article 3): https://medium.com/@muhammedafzal1000/i-built-an-ai-that-stops-repeating-debugging-mistakes-075e280c768a

## 🎥 Project Demo  

[![Watch the demo](https://img.youtube.com/vi/CGe5-0ODNL0/maxresdefault.jpg)](https://youtu.be/CGe5-0ODNL0)

## 🧠 Overview

Incident Memory Copilot is a hackathon-ready AI incident response agent for engineering and DevOps teams.

It uses:

* ⚡ **Groq** for fast troubleshooting guidance
* 🧠 **Hindsight (Vectorize)** as a persistent memory layer

This allows the system to:

* Remember past incidents
* Recall similar failures
* Improve recommendations over time

---

## 🎯 Why this stands out

* Solves a real-world DevOps problem: **faster incident resolution**
* Memory is **core to the system**, not just an add-on
* Shows **learning over time** (first vs repeated incidents)
* Demonstrates **persistent AI memory (retain + recall)**

---

## 🖥️ What the demo shows

* Dark, dashboard-style UI (optimized for demos)
* Incident classification & similarity scoring
* Past incident recall with stored fixes
* Real-time incident feed showing learning behavior
* Graceful fallback when AI is not configured

---

## ⚙️ Tech Stack

* **Backend:** FastAPI
* **Frontend:** HTML, CSS, JavaScript
* **LLM:** Groq
* **Memory Layer:** Hindsight (Vectorize)

---

## ⚡ One-command local setup

1. Navigate to project:

   ```bash
   cd ai-incident-fix-engine
   ```

2. Copy environment template:

   ```bash
   cp .env.example .env
   ```

3. Add your API keys:

   ```bash
   GROQ_API_KEY=gsk_your_real_key_here
   HINDSIGHT_API_KEY=your_hindsight_key
   HINDSIGHT_BANK_ID=your_bank_id
   HINDSIGHT_ORG_PATH=your_org_path
   ```

4. Run the app:

   ```bash
   ./run.sh
   ```

5. Open:

   * App → http://127.0.0.1:8000
   * Docs → http://127.0.0.1:8000/docs

---

## 🎬 Demo Flow (for judges)

1. Input:

   ```
   sqlite3.OperationalError: no such table: users
   ```

   → System treats as new incident and stores solution

2. Input similar error:

   ```
   sqlite3.OperationalError: no such table: user_data
   ```

   → System recalls memory + improves solution

3. Try multiple errors
   → Observe **learning behavior in incident feed**

---

## ⚠️ Troubleshooting

If you get:

```bash
401 Invalid organization path
```

Fix:

```bash
HINDSIGHT_ORG_PATH=your_org_path
```

Then restart:

```bash
./run.sh
```

---

## 🌍 Deployment

This project is deployed on Render:
👉 https://ai-incident-fix-engine.onrender.com

---

## ✍️ Author Note

This project explores the intersection of:

* AI reasoning
* Memory systems
* Real-world DevOps workflows

Built for hackathons, but designed with **production thinking**.

