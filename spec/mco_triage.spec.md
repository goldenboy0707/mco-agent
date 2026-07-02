# MCO Triage — Spécification Immuable

> **Version** : `1.0.0-immutable`
> **Statut** : `VERROUILLÉE` — Toute modification requiert une revue formelle et un incrément de version.
> **Auteur** : Architecte SDD
> **Date de gel** : 2026-06-25

---

## 1. Objet

Ce document constitue la **source de vérité unique** du module de triage MCO.
Il définit les règles de qualification, les critères de périmètre et les comportements
attendus de l'agent de triage selon le paradigme **Spec-Driven Development (SDD)**.

Aucun code d'implémentation ne doit être produit avant validation intégrale
de cette spécification.

---

## 2. Glossaire

| Terme               | Définition                                                                                     |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| **MCO**              | Maintien en Conditions Opérationnelles — périmètre d'intervention sur incidents d'exploitation |
| **RUN**              | Activités récurrentes d'exploitation et de supervision                                         |
| **MCO_OK**           | Verdict : l'incident relève du périmètre MCO, la trajectoire de traitement se poursuit         |
| **HORS_PERIMETRE**   | Verdict : l'incident ne relève pas du MCO, la trajectoire est immédiatement interrompue        |
| **Criticité**        | Niveau de priorité opérationnelle attribué à un incident qualifié MCO_OK                       |
| **Trajectoire**      | Chaîne de traitement séquentielle déclenchée par le triage                                     |

---

## 3. Configuration du moteur de triage

```yaml
# ── Identité du module ──────────────────────────────────
module:
  nom: mco_triage
  version: "1.0.0"
  type: qualification

# ── Périmètre MCO autorisé ──────────────────────────────
perimetre:
  inclus:
    - infrastructure_cloud
    - pipeline_data
    - supervision_applicative
    - reseau_exploitation
  exclus:
    - gestion_identites
    - support_poste_travail
    - demandes_acces

# ── Matrice de criticité ────────────────────────────────
criticite:
  P1:
    sla_minutes: 30
    impact: critique
    description: "Rupture de service ou perte de données en production"
  P2:
    sla_minutes: 120
    impact: majeur
    description: "Dégradation significative sans perte de données"
  P3:
    sla_minutes: 480
    impact: mineur
    description: "Anomalie sans impact utilisateur immédiat"

# ── Verdicts possibles ──────────────────────────────────
verdicts:
  - MCO_OK
  - HORS_PERIMETRE

# ── Comportement à l'arrêt ──────────────────────────────
arret:
  verdict: HORS_PERIMETRE
  action: stop_trajectoire
  notification: true
```

---

## 4. Règles de qualification

### 4.1 Critères d'inclusion (MCO_OK)

Un incident est qualifié **MCO_OK** si et seulement si :

1. Le domaine technique appartient à `perimetre.inclus`.
2. L'incident porte sur un composant **en production** (environnement `PROD` ou `PRE-PROD`).
3. L'impact est mesurable sur la **continuité de service** ou l'**intégrité des flux de données**.

### 4.2 Critères d'exclusion (HORS_PERIMETRE)

Un incident est qualifié **HORS_PERIMETRE** si au moins une condition est remplie :

1. Le domaine technique appartient à `perimetre.exclus`.
2. L'incident concerne un poste utilisateur, une demande d'accès ou un changement de mot de passe.
3. Aucun composant d'infrastructure ou de pipeline n'est impliqué.

> [!IMPORTANT]
> Un verdict **HORS_PERIMETRE** provoque l'**arrêt immédiat** de la trajectoire.
> Aucune étape de remédiation ne doit être déclenchée.

---

## 5. Scénarios comportementaux (Gherkin)

### 5.1 Scénario positif — Rupture de flux AWS / Logstash

```gherkin
Feature: Qualification MCO d'un incident de pipeline de données

  Contexte:
    L'agent de triage reçoit un ticket d'incident provenant du système
    de supervision. Le ticket signale une rupture dans le pipeline
    d'ingestion de données suite à un changement de format côté AWS.

  Scenario: Rupture de flux de données qualifiée MCO_OK en criticité P1
    Given un ticket d'incident avec les attributs suivants :
      | champ              | valeur                                          |
      | source             | supervision_cloudwatch                           |
      | composant          | pipeline_data::logstash_ingest                   |
      | environnement      | PROD                                             |
      | description        | Échec de parsing Logstash — format JSON invalide |
      | cause_identifiee   | Changement de schéma des events AWS CloudTrail   |
      | impact             | Perte totale d'ingestion des logs de sécurité    |
      | timestamp          | 2026-06-25T10:15:00Z                             |

    When l'agent de triage évalue le domaine technique du ticket
    Then le domaine "pipeline_data" est reconnu dans "perimetre.inclus"

    When l'agent de triage évalue l'environnement cible
    Then l'environnement "PROD" est confirmé comme éligible

    When l'agent de triage évalue l'impact opérationnel
    Then l'impact est qualifié comme "Rupture de service ou perte de données en production"

    When l'agent de triage rend son verdict
    Then le verdict est "MCO_OK"
      And la criticité attribuée est "P1"
      And le SLA de prise en charge est de 30 minutes
      And la trajectoire de remédiation est déclenchée
      And le ticket est enrichi avec les métadonnées de triage suivantes :
        | métadonnée         | valeur                       |
        | verdict            | MCO_OK                       |
        | criticite          | P1                           |
        | domaine            | pipeline_data                |
        | composant_impacte  | logstash_ingest              |
        | trajectoire        | ACTIVE                       |
```

---

### 5.2 Scénario négatif — Demande hors périmètre

```gherkin
Feature: Rejet d'une demande hors périmètre MCO

  Contexte:
    L'agent de triage reçoit un ticket classé par erreur dans la file
    MCO. Le ticket concerne une demande de réinitialisation de mot de
    passe Windows pour un utilisateur du back-office.

  Scenario: Demande de réinitialisation mot de passe rejetée HORS_PERIMETRE
    Given un ticket d'incident avec les attributs suivants :
      | champ              | valeur                                                  |
      | source             | portail_self_service                                     |
      | composant          | gestion_identites::active_directory                      |
      | environnement      | CORPORATE                                                |
      | description        | Réinitialisation du mot de passe Windows — utilisateur   |
      | cause_identifiee   | Mot de passe expiré après 90 jours                       |
      | impact             | Utilisateur bloqué sur son poste de travail              |
      | timestamp          | 2026-06-25T11:42:00Z                                     |

    When l'agent de triage évalue le domaine technique du ticket
    Then le domaine "gestion_identites" est reconnu dans "perimetre.exclus"

    When l'agent de triage rend son verdict
    Then le verdict est "HORS_PERIMETRE"
      And la trajectoire est immédiatement stoppée
      And aucune criticité n'est attribuée
      And aucune action de remédiation n'est déclenchée
      And une notification de rejet est émise avec le motif :
        """
        REJET — Le ticket ne relève pas du périmètre MCO.
        Domaine détecté : gestion_identites (exclu).
        Action requise : réorienter vers le support poste de travail / IAM.
        """
      And le ticket est enrichi avec les métadonnées de triage suivantes :
        | métadonnée         | valeur                          |
        | verdict            | HORS_PERIMETRE                  |
        | criticite          | N/A                             |
        | domaine            | gestion_identites               |
        | composant_impacte  | active_directory                |
        | trajectoire        | STOPPEE                         |
        | motif_rejet        | Domaine exclu du périmètre MCO  |
```

---

## 6. Contrat d'interface

### 6.1 Entrée (Payload incident)

```yaml
payload:
  id: string           # Identifiant unique du ticket
  source: string       # Système émetteur
  composant: string    # Format "domaine::sous_composant"
  environnement: string # PROD | PRE-PROD | CORPORATE | DEV
  description: string  # Description libre de l'incident
  impact: string       # Description de l'impact observé
  timestamp: string    # ISO 8601
```

### 6.2 Sortie (Verdict de triage)

```yaml
verdict:
  triage_id: string       # Identifiant de la décision de triage
  ticket_id: string       # Référence au ticket source
  resultat: string        # MCO_OK | HORS_PERIMETRE
  criticite: string       # P1 | P2 | P3 | N/A
  domaine: string         # Domaine technique extrait
  composant_impacte: string
  trajectoire: string     # ACTIVE | STOPPEE
  motif_rejet: string     # Vide si MCO_OK
  timestamp_verdict: string
```

---

## 7. Invariants

> [!CAUTION]
> Les règles suivantes sont **non négociables** et doivent être respectées par toute implémentation.

1. **Immutabilité du verdict** — Une fois rendu, un verdict de triage ne peut être modifié
   que par un nouveau passage complet dans le moteur de triage.
2. **Arrêt immédiat** — Un verdict `HORS_PERIMETRE` interdit toute exécution ultérieure
   dans la trajectoire. Aucun contournement n'est autorisé.
3. **Traçabilité** — Chaque décision de triage produit un enregistrement horodaté et
   immuable dans le journal d'audit.
4. **Déterminisme** — Pour un même jeu d'attributs en entrée, le moteur de triage
   **doit** produire systématiquement le même verdict et la même criticité.
5. **Séparation spec/code** — Ce fichier de spécification ne contient aucune
   implémentation. Le code est dérivé de la spec, jamais l'inverse.

---

> **Fin de spécification** — `mco_triage.spec.md v1.0.0-immutable`
