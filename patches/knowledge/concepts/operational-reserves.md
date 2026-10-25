---
terms:
  en: [operational reserves, reserves, resource silo]
  ja: [作戦備蓄, 運用備蓄, 備蓄, 資源サイロ]
  zh-Hans: [作战储备, 储备, 资源仓库]
  de: [Einsatzreserven, Reserven, Ressourcensilo]
  fr: [réserves opérationnelles, réserves, silo]
  es: [reservas operativas, reservas, silo]
  pt-BR: [reservas operacionais, reservas, silo]
verified_through: 4.4.6
---
# Operational Reserves

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md); patches/4.5.md (stable 4.5 release notes, Dev Diary #433) -->

- **Reserve Conversion:** Operational Reserves track Energy and Minerals one-to-one in 4.4.6. {since: 4.4.6}

- **Base Capacity:** Operational Reserves start with 15,000 capacity. {since: 4.4.6}

- **Arkship Capacity:** A Tier I Arkship adds 5,000 capacity, plus another 2,500 if Civilian; Tier II adds 7,500, plus another 5,000 if Civilian; Tier III adds 10,000, plus another 7,500 if Civilian. For example, one Tier II Civilian Arkship with no other modifiers has 15,000 + 7,500 + 5,000 = 27,500 capacity. {since: 4.4.6}

- **Additional Capacity:** Resource Silo variants can raise Operational Reserve capacity beyond the base and Arkship contributions. Use the reported tooltip rather than treating the formula above as an absolute cap. {since: 4.4.6}

- **Reserve Health:** A negative ordinary Energy or Mineral flow is not by itself proof of a Nomad crisis. Judge reserves, collected stockpiles, contracts, routes, and Arkship actions together. {since: 4.4.6}

- **Critical Reserves:** The Critical stage occupies the lowest 5% of current reserve capacity, so it begins above zero and carries severe economic penalties. Prefer the campaign's reported stage or tooltip when available, especially with capacity modifiers. {since: 4.4.6}

- **Strategic Harvesting:** Relevant mining technologies improve Nomad harvesting of strategic resources. Do not infer that a technology is researched without save evidence. {since: 4.4.6}

- **Operational Reserves:** When a Nomad empire's Operational Reserves are critical, ships and cloned space fauna with a Mineral cost cannot be built. {since: 4.5}

- **Conserve Approach:** The Conserve approach for Operational Reserves grants -50% Specialist Job Efficiency. {since: 4.5.2}

Related: [[Arkships]], [[Logistic Ships]]
