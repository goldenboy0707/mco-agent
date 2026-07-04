# ITOps Triage Agent: Automated IT Support Routing with LLM Orchestration

### *A production-ready AI agent bridging Outlook, Make.com, and Jira Cloud to classify, prioritize, and alert on enterprise IT incidents in real-time

---

## 1. The Pitch: Problem, Solution & Value

### Problem Statement & Project Origin
The inspiration for this project stems from real-world operational friction observed during my experience in enterprise environments (such as EDF). Within our production teams, engineers took turns serving as the rotating **"On-Call Engineer"** (or Incident Commander). We experienced firsthand that manually parsing, qualifying, and dispatching dozens of incoming support emails was a massive drain on high-value engineering hours.

Critical business infrastructure failures—such as an entire sales team experiencing a "502 Bad Gateway" on a core CRM—frequently sat unassigned in overloaded shared inboxes while the on-call engineer was drowning in manual Level 1 triage. This operational delay drastically increases Mean Time to Resolution (MTTR), causing avoidable business downtime.

### The Solution
The **ITOps Triage Agent** replaces this manual bottleneck with an autonomous, data-driven automation loop. Instead of acting as a conversational chatbot, this agent functions as a specialized **programmatic decision engine**. 
* It automatically intercepts raw incoming emails from Microsoft 365 Outlook.
* It leverages the `gemini-2.5-flash` model to analyze the technical intent, severity, and context.
* It outputs a strict, validated JSON payload that drives a multi-action response.

### Core Value
* **Zero-Latency Dispatching:** Fully automates the rotating "On-Call Engineer" triage workload, shifting engineers from administrative dispatching to immediate technical resolution.
* **Proactive Crisis Management:** Automatically identifies `Haute` and `Critique` priorities to notify Level 2/3 technicians instantly, reducing critical incident reaction time to seconds.
* **Automated User Reassurance (CX):** Instantly dispatches an acknowledgement email back to the user with an AI-generated summary of their issue, lowering user anxiety and preventing duplicate ticket creation.
* **Operational Accuracy:** Automatically translates chaotic user-written emails into structured enterprise metrics (Category, Urgency, Summary) securely formatted for technical team routing.

---

## 2. Technical Architecture & System Workflow

The system relies on a decentralized, event-driven pipeline optimized for high reliability:

```text
[Outlook Email Ingest] 
          │
          ▼
   [Make Webhook] ───(Sanitizes HTML)───► [FastAPI / Render Cloud]
                                                  │
                                         (Invokes Gemini LLM)
                                                  │
          ▼                                       ▼
    [Make Router] ◄───(JSON parsing)───── [Structured JSON Output]
          │
          ├─► [Action 1: Always] ────────► [Create Jira Cloud Ticket]
          │
          ├─► [Action 2: Always] ────────► [O365 User Reassurance Email]
          │
          └─► [Action 3: If High/Crit] ──► [O365 Emergency Team Alert]
```

1. **Ingestion:** A custom webhook in Make.com monitors the enterprise Outlook inbox, triggering immediately upon new incoming incidents.
2. **Text Sanitization:** The pipeline applies a programmatic `stripHTML()` and `replace()` workflow to purge raw email formatting into clean text, ensuring readable tickets.
3. **Reasoning Layer:** The text is securely forwarded via a POST request to a self-hosted FastAPI service running the Gemini API. The prompt restricts the LLM to output an un-nested JSON schema containing exactly three metadata keys: `urgence`, `categorie`, and `resume`.
4. **Conditional Routing:** Make.com parses this data stream using a Router to execute concurrent actions:
    * **Path A (Logging):** A mapping layer (`toString(switch(...))`) translates the AI's urgency textual analysis into Jira's native priority IDs to generate a perfectly formatted ticket.
    * **Path B (User Acknowledgement):** An automated Microsoft 365 Outlook module immediately sends a reassurance email back to the original sender, confirming ticket creation and providing a transparent summary of the tracked issue.
    * **Path C (Escalation):** If the JSON urgency evaluates to `Haute` or `Critique`, a parallel Outlook module broadcasts an emergency alert directly to the engineering task force's mobile endpoints.

---

## 3. Key Concepts Demonstrated

To fulfill the explicit requirements of the Kaggle/Google competition evaluation matrix, this system implements three core paradigms:

- **Agent Skills:** The LLM is completely isolated from user-facing conversation. It is weaponized strictly as a functional, structural automation utility. By using strict system prompt engineering and string formatting post-processing, the agent reliably behaves as a deterministic router.
- **Security Features:** Adhering to strict production-grade security, zero API keys, tokens, or credentials are exposed in the source code. The project isolates the configuration layer locally using a `.env` file blocked by `.gitignore`. In production, the cloud hosting provider dynamically injects keys at runtime via encrypted environment variables.
- **Deployability:** The agent’s core logic is completely containerized as a public Web Service API built with FastAPI and deployed to Render Cloud. It incorporates automated Swagger UI documentation (`/docs`) for endpoint testing and specialized health-check endpoints allowing constant uptime monitoring.

---

## 4. Detailed Setup & Deployment Instructions

### Prerequisites
- Python 3.10 or higher
- A Google AI Studio account (for the Gemini API Key)
- A Make.com account
- A Jira Cloud instance with administrator rights

### Local Installation & Configuration

1. **Clone the Repository:**
   ```bash
   git clone [https://github.com/votre-nom/votre-repo.git](https://github.com/votre-nom/votre-repo.git)
   cd votre-repo
   ```

2. **Environment Setup:**
   Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Secure Secrets Configuration:**
   Create a `.env` file in the root directory. This file is strictly ignored by Git to prevent credential leaks.
   ```ini
   GEMINI_API_KEY=your_secure_gemini_api_key_here
   ```

4. **Run the Server Locally:**
   ```bash
   python -m uvicorn main:app --reload
   ```
   *The local Swagger UI documentation and testing environment will be accessible at http://127.0.0.1:8000/docs.*

### Cloud Deployment (Render Cloud Platform)

This service is optimized for containerless cloud deployment on Render:
1. Create a new **Web Service** on Render and connect it to your public GitHub repository.
2. Select **Python** as the runtime environment.
3. Set the **Start Command** to: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Go to the **Environment** tab, click **Add Environment Variable**, and inject your keys securely:
   * **Key:** `GEMINI_API_KEY`
   * **Value:** *[Your Secure Google API Key]*
5. Trigger the deployment. Render will compile the API and expose a public HTTPS endpoint.

### Make.com Integration Diagram Mapping
To replicate the automation loop within Make.com:
* **Webhook Module:** Connect directly to your incoming Outlook business inbox.
* **HTTP POST Module:** Route the clean email text to your Render URL (`https://your-service.onrender.com/api/v1/triage`).
* **Router Module:**
  * *Branch 1 (Jira Cloud):* Parse the JSON and map the `urgence` parameter into a native Jira ID using: `toString(switch(agent_decision.urgence; "Critique"; 1; "Haute"; 2; "Moyenne"; 3; "Basse"; 4))`.
  * *Branch 2 (Outlook 365 - User Reassurance):* No filter (Always). Send a reply email to the original sender confirming receipt with the AI-generated `resume`.
  * *Branch 3 (Outlook 365 - Emergency Alert):* Apply a filter: `Condition: agent_decision.urgence IN [Critique, Haute] (case insensitive)`. Map the output to an urgent email alerting the technical team.
