---
name: mco_triage
description: >
  Compétence de triage MCO — Analyse, qualifie et classifie les incidents
  du périmètre RUN (Logstash, AWS, Elasticsearch, Kibana, dashboards EDF).
  Produit un verdict structuré (MCO_OK | HORS_PERIMETRE) avec payload Jira
  et notification client.
version: "1.0.0"
spec_source: spec/mco_triage.spec.md
---

# Skill — MCO Triage

> **Rôle** : Qualifier un incident entrant et produire une partition JSON normalisée.
> **Spec de référence** : `spec/mco_triage.spec.md v1.0.0-immutable`

---

## 1. Trigger Rule — Règle de déclenchement

L'agent **DOIT** activer cette compétence si et seulement si le ticket entrant
satisfait **au moins une** des conditions suivantes :

```yaml
trigger:
  match: ANY
  conditions:
    - composant contient "logstash"
    - composant contient "elasticsearch"
    - composant contient "kibana"
    - composant contient "aws"
    - description mentionne "pipeline" ET ("parsing" OU "ingestion" OU "flux")
    - description mentionne "dashboard" ET ("EDF" OU "kibana")
    - description mentionne "OOM" ET "elasticsearch"
    - description mentionne "saturation" ET ("heap" OU "disque" OU "cluster")
    - source correspond à "supervision_cloudwatch"
    - source correspond à "supervision_elastic"
```

> [!WARNING]
> Si **aucune** condition de déclenchement n'est satisfaite, l'agent **NE DOIT PAS**
> exécuter cette compétence. Le ticket doit être redirigé vers le dispatcher
> générique sans traitement.

### Contre-conditions d'exclusion immédiate

L'agent **DOIT** court-circuiter le déclenchement et rendre immédiatement
le verdict `HORS_PERIMETRE` si l'une des conditions suivantes est détectée,
**même si** une condition de déclenchement est satisfaite par ailleurs :

```yaml
exclusion:
  match: ANY
  conditions:
    - composant commence par "gestion_identites"
    - composant commence par "support_poste_travail"
    - composant commence par "demandes_acces"
    - description mentionne "mot de passe" ET ("réinitialisation" OU "reset")
    - description mentionne "droits" ET "Active Directory"
    - environnement est "CORPORATE" ET composant absent de perimetre.inclus
```

---

## 2. Core Logic — Instructions de raisonnement

L'agent exécute les trois étapes suivantes **séquentiellement et sans omission**.
Chaque étape produit un résultat intermédiaire consommé par l'étape suivante.
Si une étape échoue ou déclenche un rejet, la trajectoire s'arrête immédiatement.

---

### Étape 1 — EXTRACTION

**Objectif** : Isoler les données structurées du ticket brut.

**Instructions** :

1. Extraire le champ `composant` et le décomposer selon le format `domaine::sous_composant`.
   - Le segment avant `::` est le **domaine technique**.
   - Le segment après `::` est le **composant impacté**.
   - Si le format `::` est absent, inférer le domaine à partir des mots-clés
     (`logstash` → `pipeline_data`, `elasticsearch` → `infrastructure_cloud`,
     `kibana` → `supervision_applicative`, `aws` → `infrastructure_cloud`).
2. Extraire l'`environnement` et le normaliser en majuscules (`PROD`, `PRE-PROD`, `CORPORATE`, `DEV`).
3. Extraire l'`impact` brut et identifier les marqueurs de sévérité :
   - Marqueurs **critiques** : `rupture`, `perte totale`, `indisponibilité`, `OOM`, `crash`, `saturation`.
   - Marqueurs **majeurs** : `dégradation`, `incompatibilité`, `identifiants modifiés`, `credentials`.
   - Marqueurs **mineurs** : `affichage`, `visuel`, `dashboard`, `droits`, `accès`.
4. Produire un objet intermédiaire `extraction` :

```yaml
extraction:
  domaine: string
  sous_composant: string
  environnement: string
  marqueurs_severite: list[string]
  mots_cles_detectes: list[string]
```

---

### Étape 2 — QUALIFICATION

**Objectif** : Déterminer le verdict `MCO_OK` ou `HORS_PERIMETRE`.

**Instructions** :

1. Vérifier si `extraction.domaine` appartient à la liste `perimetre.exclus`
   définie dans la spécification.
   - **SI OUI** → Verdict `HORS_PERIMETRE`. **STOP.** Aller directement à la production de la sortie.
2. Vérifier si `extraction.domaine` appartient à la liste `perimetre.inclus`.
   - **SI NON** → Verdict `HORS_PERIMETRE`. **STOP.**
3. Vérifier si `extraction.environnement` est `PROD` ou `PRE-PROD`.
   - **SI NON** → Verdict `HORS_PERIMETRE`. **STOP.**
4. Confirmer qu'au moins un marqueur de sévérité a été détecté à l'étape 1.
   - **SI AUCUN** → Verdict `HORS_PERIMETRE`. **STOP.**
5. **Si toutes les vérifications passent** → Verdict `MCO_OK`. Continuer vers l'étape 3.

> [!CAUTION]
> Chaque `STOP` ci-dessus est **définitif**. L'agent ne doit jamais tenter
> de « forcer » un ticket hors périmètre dans la trajectoire MCO.

---

### Étape 3 — CLASSIFICATION

**Objectif** : Attribuer la criticité et produire la partition JSON de sortie.

**Prérequis** : Le verdict de l'étape 2 est `MCO_OK`.

**Instructions** :

1. Appliquer la **matrice de criticité** (§3 ci-dessous) en croisant le composant
   impacté et les marqueurs de sévérité extraits.
2. Déterminer le SLA associé au niveau de criticité.
3. Construire le bloc `jira_payload` avec tous les champs requis.
4. Construire le bloc `client_notification` avec le message formaté.
5. Assembler la partition JSON finale conforme au schéma de sortie (§4).

---

## 3. Matrice de criticité — RUN MCO

La criticité est attribuée par correspondance **stricte** entre la situation
observée et les règles ci-dessous. En cas d'ambiguïté, la criticité la plus
haute l'emporte.

```yaml
matrice_criticite:

  P1:
    niveau: Bloquant
    sla_minutes: 30
    situations:
      - label: "Rupture de flux AWS/Logstash"
        condition: >
          Le composant est logstash OU le domaine est pipeline_data,
          ET un marqueur critique (rupture, perte totale, indisponibilité) est détecté,
          ET l'environnement est PROD.
        exemples:
          - "Échec de parsing Logstash suite à un changement de format AWS CloudTrail"
          - "Pipeline Logstash arrêté — plus aucun event ingéré depuis 15 min"
      - label: "Saturation / OOM Elasticsearch"
        condition: >
          Le composant est elasticsearch OU le domaine est infrastructure_cloud,
          ET un marqueur critique (OOM, saturation, crash, heap) est détecté,
          ET l'environnement est PROD.
        exemples:
          - "Cluster Elasticsearch en OOM — nœuds data indisponibles"
          - "Saturation disque à 98% sur le cluster ES de production"

  P2:
    niveau: Majeur
    sla_minutes: 120
    situations:
      - label: "Changement d'identifiants sans prévenir"
        condition: >
          La description mentionne un changement de credentials, clés d'API,
          tokens ou identifiants de service réalisé sans notification préalable,
          ET un impact de type dégradation ou interruption partielle est constaté.
        exemples:
          - "Credentials AWS IAM modifiés sans ticket de changement — Logstash rejette les connexions"
          - "Token d'API Elasticsearch régénéré — Kibana perd l'accès au cluster"
      - label: "Incompatibilité suite à mise à jour transverse"
        condition: >
          La description mentionne une mise à jour, upgrade ou changement de version
          d'un composant transverse (OS, JVM, bibliothèque partagée),
          ET une incompatibilité ou régression est constatée sur un composant MCO.
        exemples:
          - "Mise à jour JVM 17 → 21 provoquant un crash Elasticsearch au démarrage"
          - "Upgrade OpenSSL cassant les connexions TLS Logstash → Elasticsearch"

  P3:
    niveau: Mineur
    sla_minutes: 480
    situations:
      - label: "Bug d'affichage dashboard Kibana"
        condition: >
          Le composant est kibana OU la description mentionne un dashboard,
          ET le problème est limité à l'affichage, la visualisation ou le rendu,
          ET aucune perte de données ou rupture de flux n'est constatée.
        exemples:
          - "Dashboard EDF — graphique de consommation ne se charge plus après filtre date"
          - "Visualisation Kibana tronquée sur les écrans de supervision"
      - label: "Demande d'ouverture de droits"
        condition: >
          La description mentionne une demande d'accès, d'ouverture de droits
          ou de permissions sur un composant MCO (Kibana, Elasticsearch),
          ET aucun incident technique n'est associé.
        exemples:
          - "Ouverture de droits en lecture sur l'index logs-prod dans Kibana"
          - "Ajout d'un utilisateur au rôle monitoring_viewer sur Elasticsearch"
```

---

## 4. Schéma de sortie — Partition JSON

L'agent **DOIT** produire exactement la structure JSON suivante, sans texte
explicatif périphérique. Tout champ marqué `required` est obligatoire.

```json
{
  "triage": {
    "triage_id":          "string   | required | UUID v4 généré par l'agent",
    "ticket_id":          "string   | required | ID du ticket source",
    "timestamp_verdict":  "string   | required | ISO 8601",
    "verdict":            "string   | required | MCO_OK | HORS_PERIMETRE",
    "criticite":          "string   | required | P1 | P2 | P3 | N/A",
    "sla_minutes":        "integer  | required | 30 | 120 | 480 | null",
    "domaine":            "string   | required | Domaine technique extrait",
    "composant_impacte":  "string   | required | Sous-composant extrait",
    "environnement":      "string   | required | PROD | PRE-PROD | CORPORATE | DEV",
    "trajectoire":        "string   | required | ACTIVE | STOPPEE",
    "motif_rejet":        "string   | optional | Vide si MCO_OK"
  },

  "jira_payload": {
    "project_key":        "string   | required | Clé du projet Jira cible",
    "issue_type":         "string   | required | Incident",
    "summary":            "string   | required | [<criticite>] <composant> — <résumé court>",
    "description":        "string   | required | Description enrichie avec contexte de triage",
    "priority":           "string   | required | Highest | High | Medium (mappé depuis P1|P2|P3)",
    "labels":             ["MCO", "RUN", "<domaine>", "<composant_impacte>"],
    "custom_fields": {
      "cf_verdict":       "string   | required | MCO_OK | HORS_PERIMETRE",
      "cf_criticite":     "string   | required | P1 | P2 | P3",
      "cf_sla_minutes":   "integer  | required | SLA en minutes",
      "cf_domaine":       "string   | required | Domaine technique",
      "cf_environnement": "string   | required | Environnement cible"
    }
  },

  "client_notification": {
    "canal":              "string   | required | email | teams | sms",
    "destinataires":      ["string  | required | Liste des destinataires"],
    "sujet":              "string   | required | [MCO-<criticite>] Incident <composant>",
    "corps": {
      "statut":           "string   | required | PRIS_EN_CHARGE | REJETE",
      "resume_incident":  "string   | required | Résumé en 2-3 phrases",
      "criticite":        "string   | required | P1 | P2 | P3 | N/A",
      "sla":              "string   | required | Prise en charge sous <N> minutes",
      "prochaines_etapes":"string   | required | Description de la suite du traitement",
      "reference_jira":   "string   | required | Lien ou clé du ticket Jira créé"
    }
  }
}
```

> [!IMPORTANT]
> - Si le verdict est `HORS_PERIMETRE`, le bloc `jira_payload` **DOIT** tout de même
>   être produit (pour traçabilité) mais avec `priority` = `Lowest` et
>   `summary` préfixé par `[HORS_PERIMETRE]`.
> - Le bloc `client_notification.corps.statut` **DOIT** être `REJETE` si
>   le verdict est `HORS_PERIMETRE`, et `PRIS_EN_CHARGE` si `MCO_OK`.
> - L'agent ne doit produire **aucun texte** en dehors de ce bloc JSON.

---

## 5. Invariants de la compétence

1. **Fidélité à la spec** — Cette compétence est dérivée de
   `spec/mco_triage.spec.md v1.0.0-immutable`. Toute divergence avec la spec
   constitue un défaut.
2. **Séquentialité stricte** — Les étapes Extraction → Qualification → Classification
   s'exécutent dans cet ordre. Aucune étape ne peut être sautée ou réordonnée.
3. **Sortie unique** — L'agent produit exactement **un** bloc JSON conforme au §4.
   Pas de texte libre, pas d'explication, pas de commentaire additionnel.
4. **Déterminisme** — Pour un même ticket en entrée, la compétence produit
   toujours la même partition JSON en sortie.
5. **Priorité au rejet** — En cas de doute sur l'appartenance au périmètre,
   le verdict par défaut est `HORS_PERIMETRE`.

---

> **Fin de compétence** — `skill.md v1.0.0` · dérivée de `mco_triage.spec.md v1.0.0-immutable`
