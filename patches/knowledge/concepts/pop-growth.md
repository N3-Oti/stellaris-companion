---
terms:
  en: [growth, pop growth, assembly, hedonist]
  ja: [人口増加, 成長, 増殖, 組立, 組み立て, 快楽主義]
  zh-Hans: [人口增长, 增长, 组装, 享乐主义]
  de: [Wachstum, Bevölkerungswachstum, Montage, Hedonisten]
  fr: [croissance, assemblage, hédonistes]
  es: [crecimiento, ensamblaje, hedonistas]
  pt-BR: [crescimento, montagem, hedonistas]
verified_through: 4.4.6
---
# Pop Growth

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md); patches/4.5.md (stable 4.5 release notes, Dev Diary #433) -->

- **Simultaneous Growth:** Every eligible Pop Group on a planet grows simultaneously each month using Logistic Growth. Do not describe one species as occupying a single planet-wide growth slot. {since: 4.4.6}

- **Growth Resolution:** Underrepresented Pop Groups receive no universal baseline growth bonus. Fractional monthly growth is resolved as a proportional chance to gain 1 pop rather than being carried into a single shared growth bar. {since: 4.4.6}

- **Logistic Growth Floor:** For the logistic curve, populations below 10 are treated as 10 and logistic pressure cannot reduce growth below 10% of its pre-curve value. This multiplier floor does not guarantee one whole pop per month. {since: 4.4.6}

- **Growth and Assembly:** Organic Pop Groups handle their growth independently while mechanical assembly targets eligible mechanical templates. Machine and Organic Assembly can occur simultaneously; do not describe them as mutually exclusive or as competing for a single planet-wide growth slot. {since: 4.4.6}

- **Hedonists:** Their Pop Growth and Assembly contribution scales with their share of a Colony's population, up to +30%. Their Pop Growth requires free Housing and Amenities and disappears during a Consumer Goods deficit. {since: 4.5}

Related: [[Pop Groups]], [[Gaia and Ecumenopolis]], [[Migration]]
