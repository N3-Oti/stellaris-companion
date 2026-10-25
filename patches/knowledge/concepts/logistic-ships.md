---
terms:
  en: [logistic ship, collection, harvest, strip mine]
  ja: [補給艦, ロジスティック船, 回収, 採取, 露天採掘]
  zh-Hans: [后勤舰, 收集, 采集, 露天开采]
  de: [Logistikschiff, Sammlung, Ernte, Tagebau]
  fr: [vaisseau logistique, collecte, récolte]
  es: [nave logística, recolección, cosecha]
  pt-BR: [nave logística, coleta, colheita]
verified_through: 4.4.6
---
# Logistic Ships

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md) -->

- **Logistic Ships:** Logistic Ships collect network stockpiles for Arkships and perform central Nomad economic tasks. A collection problem may be an automation-setting issue rather than a need for another ship. {since: 4.4.6}

- **Logistic Defaults:** Logistic Ship automation defaults to Harvest Resources enabled and Waystation collection disabled. An uncollected stockpile may require enabling collection; collecting it replenishes reserves but does not prove the underlying monthly flow will become positive. {since: 4.4.6}

- **Per-Action Automation:** Arkships and Logistic Ships have per-action automation controls for tasks such as harvesting, strip mining, deep scanning, collection, and target rules. {since: 4.4.6}

- **System Orders:** Arkship and Logistic Ship system-wide harvest or strip-mine orders prioritize higher-value planets rather than merely the nearest target. {since: 4.4.6}

Related: [[Waystations]], [[Operational Reserves]], [[Arkships]]
