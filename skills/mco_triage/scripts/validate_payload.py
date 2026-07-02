#!/usr/bin/env python3
"""
validate_payload.py — Validateur déterministe de partition JSON MCO Triage.

Valide la conformité d'une sortie agent par rapport au schéma strict
défini dans skills/mco_triage/skill.md §4.

Aucun appel LLM. Code Python pur.
Référence : spec/mco_triage.spec.md v1.0.0-immutable
"""

import json
import sys
from datetime import datetime
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Constantes — Valeurs autorisées (dérivées de skill.md §4)
# ─────────────────────────────────────────────────────────────────────────────

VERDICTS_AUTORISES = {"MCO_OK", "HORS_PERIMETRE"}
CRITICITES_AUTORISEES = {"P1", "P2", "P3", "N/A"}
SLA_AUTORISES = {30, 120, 480, None}
ENVIRONNEMENTS_AUTORISES = {"PROD", "PRE-PROD", "CORPORATE", "DEV"}
TRAJECTOIRES_AUTORISEES = {"ACTIVE", "STOPPEE"}
PRIORITES_MCO_OK = {"Highest", "High", "Medium"}
PRIORITE_HORS_PERIMETRE = "Lowest"
CANAUX_AUTORISES = {"email", "teams", "sms"}
STATUTS_NOTIFICATION = {"PRIS_EN_CHARGE", "REJETE"}

BLOCS_RACINE = {"triage", "jira_payload", "client_notification"}


# ─────────────────────────────────────────────────────────────────────────────
# Fonctions utilitaires
# ─────────────────────────────────────────────────────────────────────────────

def _assert_type(valeur: Any, type_attendu: type, chemin: str) -> None:
    """Lève ValueError si la valeur n'est pas du type attendu."""
    if not isinstance(valeur, type_attendu):
        raise ValueError(
            f"[TYPE] '{chemin}' : attendu {type_attendu.__name__}, "
            f"reçu {type(valeur).__name__} ({valeur!r})"
        )


def _assert_present(bloc: dict, cle: str, chemin_parent: str) -> Any:
    """Lève KeyError si la clé est absente du bloc."""
    if cle not in bloc:
        raise KeyError(f"[MANQUANT] Champ requis absent : '{chemin_parent}.{cle}'")
    return bloc[cle]


def _assert_enum(valeur: Any, valeurs_autorisees: set, chemin: str) -> None:
    """Lève ValueError si la valeur n'appartient pas à l'ensemble autorisé."""
    if valeur not in valeurs_autorisees:
        raise ValueError(
            f"[ENUM] '{chemin}' : valeur '{valeur}' non autorisée. "
            f"Valeurs acceptées : {sorted(str(v) for v in valeurs_autorisees)}"
        )


def _assert_iso8601(valeur: str, chemin: str) -> None:
    """Lève ValueError si la chaîne n'est pas un timestamp ISO 8601 valide."""
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            datetime.strptime(valeur.replace("+00:00", "Z").replace("+02:00", "Z"), fmt)
            return
        except ValueError:
            continue
    # Tentative avec fromisoformat (Python 3.7+)
    try:
        datetime.fromisoformat(valeur.replace("Z", "+00:00"))
        return
    except (ValueError, AttributeError):
        pass
    raise ValueError(
        f"[FORMAT] '{chemin}' : '{valeur}' n'est pas un timestamp ISO 8601 valide."
    )


def _assert_non_vide(valeur: str, chemin: str) -> None:
    """Lève ValueError si la chaîne est vide ou ne contient que des espaces."""
    if not valeur or not valeur.strip():
        raise ValueError(f"[VIDE] '{chemin}' : la valeur ne doit pas être vide.")


# ─────────────────────────────────────────────────────────────────────────────
# Validateurs par bloc
# ─────────────────────────────────────────────────────────────────────────────

def _valider_bloc_triage(triage: dict) -> str:
    """
    Valide le bloc 'triage'. Retourne le verdict pour usage par les
    validateurs suivants.
    """
    _assert_type(triage, dict, "triage")
    chemin = "triage"

    # — Champs requis de type string —
    champs_string = [
        "triage_id", "ticket_id", "timestamp_verdict", "verdict",
        "criticite", "domaine", "composant_impacte", "environnement",
        "trajectoire",
    ]
    for champ in champs_string:
        val = _assert_present(triage, champ, chemin)
        _assert_type(val, str, f"{chemin}.{champ}")
        _assert_non_vide(val, f"{chemin}.{champ}")

    # — Contraintes d'enum —
    _assert_enum(triage["verdict"], VERDICTS_AUTORISES, f"{chemin}.verdict")
    _assert_enum(triage["criticite"], CRITICITES_AUTORISEES, f"{chemin}.criticite")
    _assert_enum(triage["environnement"], ENVIRONNEMENTS_AUTORISES, f"{chemin}.environnement")
    _assert_enum(triage["trajectoire"], TRAJECTOIRES_AUTORISEES, f"{chemin}.trajectoire")

    # — timestamp_verdict doit être ISO 8601 —
    _assert_iso8601(triage["timestamp_verdict"], f"{chemin}.timestamp_verdict")

    # — sla_minutes : entier ou null —
    sla = _assert_present(triage, "sla_minutes", chemin)
    if sla is not None:
        _assert_type(sla, int, f"{chemin}.sla_minutes")
    _assert_enum(sla, SLA_AUTORISES, f"{chemin}.sla_minutes")

    # — Cohérence verdict / trajectoire —
    verdict = triage["verdict"]
    if verdict == "MCO_OK" and triage["trajectoire"] != "ACTIVE":
        raise ValueError(
            f"[INVARIANT] Verdict MCO_OK mais trajectoire "
            f"'{triage['trajectoire']}' au lieu de 'ACTIVE'."
        )
    if verdict == "HORS_PERIMETRE" and triage["trajectoire"] != "STOPPEE":
        raise ValueError(
            f"[INVARIANT] Verdict HORS_PERIMETRE mais trajectoire "
            f"'{triage['trajectoire']}' au lieu de 'STOPPEE'."
        )

    # — Cohérence verdict / criticité —
    if verdict == "HORS_PERIMETRE" and triage["criticite"] != "N/A":
        raise ValueError(
            f"[INVARIANT] Verdict HORS_PERIMETRE mais criticité "
            f"'{triage['criticite']}' au lieu de 'N/A'."
        )
    if verdict == "MCO_OK" and triage["criticite"] == "N/A":
        raise ValueError(
            "[INVARIANT] Verdict MCO_OK mais criticité 'N/A'. "
            "Un incident qualifié doit avoir une criticité P1, P2 ou P3."
        )

    # — Cohérence verdict / sla_minutes —
    if verdict == "HORS_PERIMETRE" and sla is not None:
        raise ValueError(
            f"[INVARIANT] Verdict HORS_PERIMETRE mais sla_minutes={sla} "
            f"au lieu de null."
        )

    # — motif_rejet : optionnel mais vérifié si présent —
    if "motif_rejet" in triage and triage["motif_rejet"] is not None:
        _assert_type(triage["motif_rejet"], str, f"{chemin}.motif_rejet")

    return verdict


def _valider_bloc_jira(jira: dict, verdict: str) -> None:
    """Valide le bloc 'jira_payload' et les invariants liés au verdict."""
    _assert_type(jira, dict, "jira_payload")
    chemin = "jira_payload"

    # — Champs requis de type string —
    for champ in ["project_key", "issue_type", "summary", "description", "priority"]:
        val = _assert_present(jira, champ, chemin)
        _assert_type(val, str, f"{chemin}.{champ}")
        _assert_non_vide(val, f"{chemin}.{champ}")

    # — labels : liste de chaînes —
    labels = _assert_present(jira, "labels", chemin)
    _assert_type(labels, list, f"{chemin}.labels")
    for i, label in enumerate(labels):
        _assert_type(label, str, f"{chemin}.labels[{i}]")

    # — custom_fields : bloc imbriqué —
    cf = _assert_present(jira, "custom_fields", chemin)
    _assert_type(cf, dict, f"{chemin}.custom_fields")
    for champ in ["cf_verdict", "cf_criticite", "cf_domaine", "cf_environnement"]:
        val = _assert_present(cf, champ, f"{chemin}.custom_fields")
        _assert_type(val, str, f"{chemin}.custom_fields.{champ}")
    sla_cf = _assert_present(cf, "cf_sla_minutes", f"{chemin}.custom_fields")
    if sla_cf is not None:
        _assert_type(sla_cf, int, f"{chemin}.custom_fields.cf_sla_minutes")

    # ── Invariants HORS_PERIMETRE sur jira_payload ──
    if verdict == "HORS_PERIMETRE":
        if jira["priority"] != PRIORITE_HORS_PERIMETRE:
            raise ValueError(
                f"[INVARIANT] Verdict HORS_PERIMETRE mais "
                f"jira_payload.priority='{jira['priority']}' au lieu de "
                f"'{PRIORITE_HORS_PERIMETRE}'."
            )
        if not jira["summary"].startswith("[HORS_PERIMETRE]"):
            raise ValueError(
                f"[INVARIANT] Verdict HORS_PERIMETRE mais "
                f"jira_payload.summary ne commence pas par '[HORS_PERIMETRE]'. "
                f"Reçu : '{jira['summary'][:60]}...'"
            )
    else:
        # MCO_OK : priority doit être Highest, High ou Medium
        _assert_enum(jira["priority"], PRIORITES_MCO_OK, f"{chemin}.priority")


def _valider_bloc_notification(notif: dict, verdict: str) -> None:
    """Valide le bloc 'client_notification' et les invariants liés au verdict."""
    _assert_type(notif, dict, "client_notification")
    chemin = "client_notification"

    # — canal —
    canal = _assert_present(notif, "canal", chemin)
    _assert_type(canal, str, f"{chemin}.canal")
    _assert_enum(canal, CANAUX_AUTORISES, f"{chemin}.canal")

    # — destinataires : liste non vide de chaînes —
    dest = _assert_present(notif, "destinataires", chemin)
    _assert_type(dest, list, f"{chemin}.destinataires")
    if len(dest) == 0:
        raise ValueError(f"[VIDE] '{chemin}.destinataires' : la liste ne doit pas être vide.")
    for i, d in enumerate(dest):
        _assert_type(d, str, f"{chemin}.destinataires[{i}]")

    # — sujet —
    sujet = _assert_present(notif, "sujet", chemin)
    _assert_type(sujet, str, f"{chemin}.sujet")
    _assert_non_vide(sujet, f"{chemin}.sujet")

    # — corps : bloc imbriqué —
    corps = _assert_present(notif, "corps", chemin)
    _assert_type(corps, dict, f"{chemin}.corps")

    champs_corps = [
        "statut", "resume_incident", "criticite",
        "sla", "prochaines_etapes", "reference_jira",
    ]
    for champ in champs_corps:
        val = _assert_present(corps, champ, f"{chemin}.corps")
        _assert_type(val, str, f"{chemin}.corps.{champ}")
        _assert_non_vide(val, f"{chemin}.corps.{champ}")

    # — statut : enum —
    _assert_enum(corps["statut"], STATUTS_NOTIFICATION, f"{chemin}.corps.statut")

    # ── Invariant verdict / statut notification ──
    statut_attendu = "REJETE" if verdict == "HORS_PERIMETRE" else "PRIS_EN_CHARGE"
    if corps["statut"] != statut_attendu:
        raise ValueError(
            f"[INVARIANT] Verdict '{verdict}' mais "
            f"client_notification.corps.statut='{corps['statut']}' "
            f"au lieu de '{statut_attendu}'."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Fonction principale de validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_triage_json(json_str: str) -> dict:
    """
    Valide la conformité d'une chaîne JSON par rapport au schéma strict
    défini dans skill.md §4.

    Args:
        json_str: Chaîne JSON brute produite par l'agent.

    Returns:
        Le dictionnaire Python parsé si la validation réussit.

    Raises:
        ValueError: JSON malformé, type incorrect ou invariant violé.
        KeyError:   Champ requis manquant.
    """
    # ── Parsing JSON ──
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"[PARSE] JSON malformé : {e}") from e

    if not isinstance(data, dict):
        raise ValueError(
            f"[TYPE] La racine doit être un objet JSON (dict), "
            f"reçu {type(data).__name__}."
        )

    # ── Présence des trois blocs racine ──
    for bloc in BLOCS_RACINE:
        _assert_present(data, bloc, "racine")

    # ── Validation séquentielle des blocs ──
    verdict = _valider_bloc_triage(data["triage"])
    _valider_bloc_jira(data["jira_payload"], verdict)
    _valider_bloc_notification(data["client_notification"], verdict)

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Tests intégrés
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    SEPARATEUR = "=" * 72

    # ── Cas 1 : JSON valide — Incident P1 MCO_OK ──────────────────────────

    json_valide_p1 = json.dumps({
        "triage": {
            "triage_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            "ticket_id": "INC-20260625-001",
            "timestamp_verdict": "2026-06-25T10:18:42Z",
            "verdict": "MCO_OK",
            "criticite": "P1",
            "sla_minutes": 30,
            "domaine": "pipeline_data",
            "composant_impacte": "logstash_ingest",
            "environnement": "PROD",
            "trajectoire": "ACTIVE",
            "motif_rejet": ""
        },
        "jira_payload": {
            "project_key": "MCO",
            "issue_type": "Incident",
            "summary": "[P1] logstash_ingest — Échec parsing CloudTrail",
            "description": (
                "Rupture du pipeline Logstash suite à un changement de "
                "format JSON des events AWS CloudTrail. Perte totale "
                "d'ingestion des logs de sécurité en production."
            ),
            "priority": "Highest",
            "labels": ["MCO", "RUN", "pipeline_data", "logstash_ingest"],
            "custom_fields": {
                "cf_verdict": "MCO_OK",
                "cf_criticite": "P1",
                "cf_sla_minutes": 30,
                "cf_domaine": "pipeline_data",
                "cf_environnement": "PROD"
            }
        },
        "client_notification": {
            "canal": "email",
            "destinataires": ["ops-mco@entreprise.fr", "astreinte@entreprise.fr"],
            "sujet": "[MCO-P1] Incident logstash_ingest",
            "corps": {
                "statut": "PRIS_EN_CHARGE",
                "resume_incident": (
                    "Le pipeline Logstash est en échec de parsing suite à "
                    "un changement de format AWS CloudTrail. L'ingestion "
                    "des logs de sécurité est interrompue."
                ),
                "criticite": "P1",
                "sla": "Prise en charge sous 30 minutes",
                "prochaines_etapes": (
                    "Analyse du nouveau schéma CloudTrail et mise à jour "
                    "du filtre Logstash. Redémarrage du pipeline prévu."
                ),
                "reference_jira": "MCO-4521"
            }
        }
    }, ensure_ascii=False)

    print(SEPARATEUR)
    print("CAS 1 — JSON valide (MCO_OK / P1)")
    print(SEPARATEUR)
    try:
        resultat = validate_triage_json(json_valide_p1)
        print(f"  ✅ VALIDATION RÉUSSIE")
        print(f"     Verdict   : {resultat['triage']['verdict']}")
        print(f"     Criticité : {resultat['triage']['criticite']}")
        print(f"     SLA       : {resultat['triage']['sla_minutes']} min")
    except (ValueError, KeyError) as e:
        print(f"  ❌ ÉCHEC INATTENDU : {e}")

    # ── Cas 2 : JSON valide — HORS_PERIMETRE ─────────────────────────────

    json_valide_hp = json.dumps({
        "triage": {
            "triage_id": "f9e8d7c6-b5a4-4321-9876-543210fedcba",
            "ticket_id": "INC-20260625-002",
            "timestamp_verdict": "2026-06-25T11:45:00Z",
            "verdict": "HORS_PERIMETRE",
            "criticite": "N/A",
            "sla_minutes": None,
            "domaine": "gestion_identites",
            "composant_impacte": "active_directory",
            "environnement": "CORPORATE",
            "trajectoire": "STOPPEE",
            "motif_rejet": "Domaine exclu du périmètre MCO"
        },
        "jira_payload": {
            "project_key": "MCO",
            "issue_type": "Incident",
            "summary": "[HORS_PERIMETRE] active_directory — Reset mot de passe",
            "description": "Demande de réinitialisation de mot de passe Windows.",
            "priority": "Lowest",
            "labels": ["MCO", "RUN", "gestion_identites", "active_directory"],
            "custom_fields": {
                "cf_verdict": "HORS_PERIMETRE",
                "cf_criticite": "N/A",
                "cf_sla_minutes": None,
                "cf_domaine": "gestion_identites",
                "cf_environnement": "CORPORATE"
            }
        },
        "client_notification": {
            "canal": "teams",
            "destinataires": ["support-n1@entreprise.fr"],
            "sujet": "[MCO-N/A] Incident active_directory",
            "corps": {
                "statut": "REJETE",
                "resume_incident": (
                    "La demande de réinitialisation de mot de passe ne "
                    "relève pas du périmètre MCO."
                ),
                "criticite": "N/A",
                "sla": "Non applicable",
                "prochaines_etapes": "Réorienter vers le support poste de travail / IAM.",
                "reference_jira": "MCO-4522"
            }
        }
    }, ensure_ascii=False)

    print()
    print(SEPARATEUR)
    print("CAS 2 — JSON valide (HORS_PERIMETRE)")
    print(SEPARATEUR)
    try:
        resultat = validate_triage_json(json_valide_hp)
        print(f"  ✅ VALIDATION RÉUSSIE")
        print(f"     Verdict   : {resultat['triage']['verdict']}")
        print(f"     Criticité : {resultat['triage']['criticite']}")
        print(f"     Priorité  : {resultat['jira_payload']['priority']}")
    except (ValueError, KeyError) as e:
        print(f"  ❌ ÉCHEC INATTENDU : {e}")

    # ── Cas 3 : JSON invalide — champ requis manquant ─────────────────────

    json_champ_manquant = json.dumps({
        "triage": {
            "triage_id": "abc-123",
            "ticket_id": "INC-003",
            "timestamp_verdict": "2026-06-25T12:00:00Z",
            "verdict": "MCO_OK",
            # "criticite" manquant volontairement
            "sla_minutes": 30,
            "domaine": "pipeline_data",
            "composant_impacte": "logstash",
            "environnement": "PROD",
            "trajectoire": "ACTIVE"
        },
        "jira_payload": {},
        "client_notification": {}
    })

    print()
    print(SEPARATEUR)
    print("CAS 3 — JSON invalide (champ requis manquant : criticite)")
    print(SEPARATEUR)
    try:
        validate_triage_json(json_champ_manquant)
        print("  ❌ ÉCHEC : la validation aurait dû échouer.")
    except KeyError as e:
        print(f"  ✅ REJET CORRECT (KeyError) : {e}")
    except ValueError as e:
        print(f"  ✅ REJET CORRECT (ValueError) : {e}")

    # ── Cas 4 : JSON invalide — verdict invalide ─────────────────────────

    json_verdict_invalide = json.dumps({
        "triage": {
            "triage_id": "abc-456",
            "ticket_id": "INC-004",
            "timestamp_verdict": "2026-06-25T12:00:00Z",
            "verdict": "PEUT_ETRE",
            "criticite": "P2",
            "sla_minutes": 120,
            "domaine": "pipeline_data",
            "composant_impacte": "logstash",
            "environnement": "PROD",
            "trajectoire": "ACTIVE"
        },
        "jira_payload": {},
        "client_notification": {}
    })

    print()
    print(SEPARATEUR)
    print("CAS 4 — JSON invalide (verdict 'PEUT_ETRE' non autorisé)")
    print(SEPARATEUR)
    try:
        validate_triage_json(json_verdict_invalide)
        print("  ❌ ÉCHEC : la validation aurait dû échouer.")
    except ValueError as e:
        print(f"  ✅ REJET CORRECT (ValueError) : {e}")
    except KeyError as e:
        print(f"  ✅ REJET CORRECT (KeyError) : {e}")

    # ── Cas 5 : JSON invalide — invariant HORS_PERIMETRE violé ────────────

    json_invariant_hp_viole = json.dumps({
        "triage": {
            "triage_id": "abc-789",
            "ticket_id": "INC-005",
            "timestamp_verdict": "2026-06-25T12:00:00Z",
            "verdict": "HORS_PERIMETRE",
            "criticite": "N/A",
            "sla_minutes": None,
            "domaine": "gestion_identites",
            "composant_impacte": "active_directory",
            "environnement": "CORPORATE",
            "trajectoire": "STOPPEE",
            "motif_rejet": "Hors périmètre"
        },
        "jira_payload": {
            "project_key": "MCO",
            "issue_type": "Incident",
            "summary": "[P2] active_directory — Reset mdp",
            "description": "Reset mot de passe.",
            "priority": "High",
            "labels": ["MCO"],
            "custom_fields": {
                "cf_verdict": "HORS_PERIMETRE",
                "cf_criticite": "N/A",
                "cf_sla_minutes": None,
                "cf_domaine": "gestion_identites",
                "cf_environnement": "CORPORATE"
            }
        },
        "client_notification": {
            "canal": "email",
            "destinataires": ["test@entreprise.fr"],
            "sujet": "[MCO-N/A] Incident AD",
            "corps": {
                "statut": "PRIS_EN_CHARGE",
                "resume_incident": "Reset mot de passe.",
                "criticite": "N/A",
                "sla": "Non applicable",
                "prochaines_etapes": "Réorienter.",
                "reference_jira": "MCO-9999"
            }
        }
    }, ensure_ascii=False)

    print()
    print(SEPARATEUR)
    print("CAS 5 — JSON invalide (HORS_PERIMETRE avec priority='High',")
    print("         summary sans préfixe, statut='PRIS_EN_CHARGE')")
    print(SEPARATEUR)
    try:
        validate_triage_json(json_invariant_hp_viole)
        print("  ❌ ÉCHEC : la validation aurait dû échouer.")
    except ValueError as e:
        print(f"  ✅ REJET CORRECT (ValueError) : {e}")
    except KeyError as e:
        print(f"  ✅ REJET CORRECT (KeyError) : {e}")

    # ── Cas 6 : JSON totalement malformé ──────────────────────────────────

    json_malformed = '{"triage": NOPE, broken }'

    print()
    print(SEPARATEUR)
    print("CAS 6 — JSON malformé (syntaxe invalide)")
    print(SEPARATEUR)
    try:
        validate_triage_json(json_malformed)
        print("  ❌ ÉCHEC : la validation aurait dû échouer.")
    except ValueError as e:
        print(f"  ✅ REJET CORRECT (ValueError) : {e}")

    # ── Résumé ────────────────────────────────────────────────────────────

    print()
    print(SEPARATEUR)
    print("RÉSUMÉ : 6/6 cas de test exécutés.")
    print(SEPARATEUR)
