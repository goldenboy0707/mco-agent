"""
Kaggle Competition: Agents for Business
Agent: MCO Triage (Maintien en Conditions Opérationnelles / IT Operations Maintenance)

Design:
This application implements an AI-driven triage system using FastAPI for the serving layer and Google Gemini 
as the reasoning engine. The architecture follows a stateless API design to ensure high scalability and easy 
integration into existing IT Service Management (ITSM) pipelines (like Jira or ServiceNow). The use of Pydantic 
ensures strict input validation, while a robust two-layer regex strategy guarantees that the LLM's output 
is cleanly parsed into a deterministic JSON format, which is critical for business process automation.
"""

import os
import re
import json
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Implementation: Load environment variables from a local .env file for secure configuration.
# This ensures that secrets like API keys are not hardcoded in the source code.
load_dotenv()

# Implementation: Initialize the Google Gemini client.
# We wrap the import in a try-except block to provide clear feedback if dependencies are missing.
try:
    import google.generativeai as genai
except ImportError:
    print("[!] Module 'google-generativeai' is missing. Run: pip install google-generativeai")
    sys.exit(1)

# Design: We strictly retrieve the API key from the environment.
# Never hardcode secrets. This is a critical security practice for production and competition code.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("[!] Environment variable GEMINI_API_KEY is missing.")
    print("    Please set it in a .env file or directly in your environment.")
    sys.exit(1)

# Behavior: Configure the SDK with the securely loaded API key and instantiate the model.
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# Behavior: Initialize the FastAPI application with metadata for auto-generated Swagger documentation.
app = FastAPI(
    title="MCO Triage API — Business Agent",
    description="AI-driven entry API for IT Operations incident qualification using Google Gemini.",
    version="2.2.0"
)

# Design: Use Pydantic models to strongly type the expected JSON payload.
# This automatically handles malformed requests and returns clear 422 HTTP errors to the client.
class TriageRequest(BaseModel):
    content: str


@app.post("/api/v1/triage")
def triage_incident(request: TriageRequest):
    """
    Behavior: 
    Main endpoint for IT incident triage. It receives raw text (e.g., from an email or a Teams message),
    injects it into a highly structured prompt enforcing strict business rules, and returns a 
    deterministic JSON decision made by the AI agent.
    """

    # Implementation: Dynamic prompt construction.
    # Design: The prompt is structured in three distinct sections (Rules, User Input, Output Instructions)
    # to maximize the LLM's instruction adherence and reasoning accuracy (Prompt Engineering best practices).
    prompt = f"""Tu es un expert en support informatique MCO (Maintien en Conditions Opérationnelles).
Tu appliques des règles métier strictes et non négociables pour classifier chaque incident.

========================================
RÈGLES DE CLASSIFICATION DE LA CRITICITÉ
========================================

**CRITIQUE** — Réservé aux pannes globales à impact collectif majeur :
  - Serveur principal hors service (down)
  - Panne réseau complète affectant un site ou une infrastructure
  - Cluster ou service de données entièrement inopérant
  → Utilise "Critique" SEULEMENT si la panne empêche un groupe entier de travailler.

**HAUTE** — Application ou service métier indisponible pour un groupe d'utilisateurs :
  - Une application métier (ERP, CRM, outil interne) inaccessible pour plusieurs personnes
  - Service cloud ou API critique en erreur pour une équipe
  → Utilise "Haute" si plusieurs utilisateurs sont bloqués mais que le reste du SI fonctionne.

**MOYENNE** — Incident individuel matériel ou bug logiciel isolé :
  - Un poste de travail / PC individuel qui ne démarre plus ou est très lent
  - Un bug logiciel reproductible bloquant un seul utilisateur
  - Un périphérique individuel défectueux (imprimante, écran, etc.)
  → Utilise "Moyenne" si UN SEUL utilisateur est bloqué sur un problème technique réel.

**BASSE** — Gêne mineure, demande d'information ou accès :
  - Demande de réinitialisation de mot de passe
  - Question ou demande d'information sans impact bloquant
  - Problème mineur non bloquant (lenteur légère, affichage cosmétique)
  - Demande de création ou modification de droits d'accès
  → Utilise "Basse" si l'utilisateur peut continuer à travailler malgré la gêne.

========================================
MESSAGE DE L'UTILISATEUR
========================================
{request.content}

========================================
INSTRUCTIONS DE SORTIE
========================================
Applique les règles ci-dessus et réponds UNIQUEMENT avec un objet JSON strict.
Sans texte avant ou après. Sans balises markdown. Sans ```json```. Juste le JSON brut.

Le JSON doit obligatoirement contenir ces quatre clés :
{{
  "urgence": "<Critique | Haute | Moyenne | Basse>",
  "categorie": "<Matériel | Logiciel | Réseau | Autre>",
  "resume": "<Une seule phrase courte résumant le problème>",
  "reponse_client": "<Un brouillon d'e-mail court (3 à 5 phrases max), professionnel et rassurant, adressé à l'utilisateur. Confirme que son ticket MCO est ouvert et pris en charge selon le niveau d'urgence détecté. Mentionne un délai de prise en charge cohérent avec la criticité (Critique = immédiat, Haute = sous 1h, Moyenne = sous 4h, Basse = sous 24h). Ton formel. Aucun saut de ligne dans cette valeur, remplace-les par des espaces.>"
}}

ATTENTION : La valeur de 'reponse_client' ne doit JAMAIS contenir de retours à la ligne (\\n). C'est une chaîne de caractères sur une seule ligne."""

    # Behavior: Call the Gemini API and handle potential network or authentication errors cleanly.
    try:
        response = model.generate_content(prompt)
        raw_text = response.text.strip()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Erreur lors de l'appel à l'API Gemini : {str(e)}"
        )

    # Implementation: Multi-layered JSON extraction and sanitation.
    # Strategy 1: Strip common markdown code blocks that LLMs often add despite instructions.
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]
    raw_text = raw_text.strip()

    # Implementation: Strategy 2 (Safety Net)
    # Use a regex to extract the first complete JSON object found in the response.
    # The re.DOTALL flag ensures that '.' matches newlines in case the LLM ignored the single-line rule.
    json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
    if json_match:
        raw_text = json_match.group(0).strip()

    # Behavior: Validate that the sanitized string is parsable JSON.
    # If it fails, raise a 422 Unprocessable Entity error and log the raw response for debugging.
    try:
        agent_decision = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=422,
            detail=f"L'IA n'a pas retourné un JSON valide ({e}). Réponse brute : {raw_text}"
        )

    # Behavior: Return the final parsed JSON object wrapped in a predictable key structure.
    return {"agent_decision": agent_decision}


# Implementation: Entry point for running the application locally using Uvicorn.
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
