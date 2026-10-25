---
terms:
  en: [guardrails, mods, dlc, evidence, l-gate]
  ja: [MOD, DLC, 証拠, Lゲート]
  zh-Hans: [模组, DLC, 证据, L星门]
  de: [Mods, DLC, Beweise, L-Tor]
  fr: [mods, DLC, preuves, portail L]
  es: [mods, DLC, pruebas, puerta L]
  pt-BR: [mods, DLC, evidências, portal L]
verified_through: 4.4.6
always: true
version_independent: true
---
# Interpretation Guardrails

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md) -->

- **Save Evidence First:** Supplied save fields and recorded events describe the actual campaign. Mechanics explain those observations but cannot create missing facts. {since: 4.4.6}

- **DLC and Settings:** A mechanic may require DLC or depend on galaxy settings. Do not promise availability when those inputs are missing or contradictory. {since: 4.4.6}

- **Mods:** Mods can replace baseline rules. Prefer observed campaign data when it conflicts with this unmodded baseline. {since: 4.4.6}

- **Contacts:** Diplomatic relations may include ordinary empires, enclaves, pirates, marauders, space fauna, primitives, and Fallen Empires. Use country type and the extracted ordinary-empire count rather than counting every contact as a peer empire. {since: 4.4.6}

- **L-Gates:** Clue progress, technologies, or related events do not by themselves prove that the L-Gates are open. Use the extracted L-Gate state as the campaign observation. {since: 4.4.6}

- **Chronicle Evidence:** Mechanics can make recorded history intelligible, but they are never evidence that an event, motive, cause, outcome, unlock, or encounter occurred. {since: 4.4.6}
