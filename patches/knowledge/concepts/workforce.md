---
terms:
  en: [workforce, jobs, job efficiency, employment]
  ja: [労働力, 職業, ジョブ, 職, 雇用, 職務効率]
  zh-Hans: [劳动力, 岗位, 工作, 就业, 岗位效率]
  de: [Arbeitskraft, Jobs, Arbeitsplatz, Effizienz]
  fr: [main-d'œuvre, emplois, efficacité]
  es: [fuerza laboral, empleos, eficiencia]
  pt-BR: [força de trabalho, empregos, eficiência]
verified_through: 4.4.6
---
# Workforce

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md) -->

- **Workforce:** Each pop normally supplies 1 Workforce, while a typical displayed job consumes about 100 Workforce. Population, Workforce, jobs, and filled jobs are distinct values. {since: 4.4.6}

- **Economic Hierarchy:** Planets produce and consume resources through jobs; Pops provide Workforce; and Workforce can partially fill those jobs. Do not map current planets back to one discrete pop occupying one discrete job. {since: 4.4.6}

- **Partial Employment:** Jobs can be partly filled when insufficient Workforce is available. Added job capacity is not the same as added production, and the supplied Workforce and efficiency evidence should decide whether more capacity is useful. {since: 4.4.6}

- **Job Efficiency Meaning:** Job Efficiency changes how much job capacity a given amount of Workforce can fill; it does not directly multiply resource output. It can nevertheless increase total output when more of the planet's job capacity becomes effectively staffed. {since: 4.4.6}

- **Job Efficiency:** Job Efficiency changes effective job capacity. It is not a direct output multiplier and should not be described as one. {since: 4.4.6}

Related: [[Districts & Buildings]], [[Civilian Stratum]], [[Job Automation]]
