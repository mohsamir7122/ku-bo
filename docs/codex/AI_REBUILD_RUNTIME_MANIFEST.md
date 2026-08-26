# AI Rebuild Runtime Manifest for KU-BO

Status: logical contract only; private identifiers and private bytes excluded.

## Root

```text
AI Rebuild
```

The runtime must discover the root through the authorized Google Drive connector.
It must not persist folder IDs, file IDs, OAuth material, signed links, or account
metadata in Git.

## Required logical paths

```text
00_Indexes/KU_BO
02_Google_Drive/KU_BO/PRIVATE_CONVERSATION_ARCHIVE
02_Google_Drive/KU_BO/AUTHORIZED_EXPORTS
04_Curated_Core/KU_BO/00_Manifests
04_Curated_Core/KU_BO/01_Factor9_Research
04_Curated_Core/KU_BO/02_Event_Evidence
04_Curated_Core/KU_BO/03_Market_Data
04_Curated_Core/KU_BO/04_Model_Freezes
04_Curated_Core/KU_BO/05_Daily_Reports
90_Quarantine_Duplicates/KU_BO
99_Reports/KU_BO
```

## Admission rule

Index first.  For every candidate, record its logical source path, SHA-256, byte
size, modified time when available, original source, capture or export method,
rights status, evidence role, point-in-time availability, and review status.

Canonical admission requires an immutable manifest and all applicable KU-BO
evidence gates.  Duplicate candidates go to Quarantine before any deletion
proposal.  Files are versioned and never overwritten in place.

## Git boundary

Git may contain schemas, validators, empty templates, aggregate counts, and
sanitized technical conclusions.  Drive retains raw conversations, authorized
exports, private market evidence, model artifacts, freezes, and daily reports.

Drive storage alone proves neither source authority nor reuse rights.  Factor 9
remains `RESEARCH_ASSET_PENDING_ADMISSION` until its seven admission gates pass.
