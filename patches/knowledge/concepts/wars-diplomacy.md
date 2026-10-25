---
terms:
  en: [war, war exhaustion, join war, subject, vassal]
  ja: [戦争, 厭戦, 参戦, 従属国, 属国]
  zh-Hans: [战争, 厌战, 参战, 附属国, 附庸]
  de: [Krieg, Kriegsmüdigkeit, Kriegseintritt, Vasall]
  fr: [guerre, lassitude de guerre, vassal]
  es: [guerra, agotamiento bélico, vasallo]
  pt-BR: [guerra, exaustão de guerra, vassalo]
verified_through: 4.4.6
---
# Wars & Diplomacy

<!-- Sources: patches/snapshots/4.4.6.md (audit: patches/audits/4.4.6.md); patches/4.5.md (stable 4.5 release notes, Dev Diary #433) -->

- **Joining and Leaving Wars:** A non-primary participant can negotiate through trade terms to join an ongoing war with a side's leader or leave by negotiating with the opposing leader. Leaving creates a truce and a diplomatic penalty, and acceptance is not guaranteed. {since: 4.4.6}

- **Hopeless War:** Any empire with every colony occupied adds one +5 percentage-point stack each month to its multiplier on other War Exhaustion gain: +5% after the first month, +10% after the second, rather than +5% per occupied colony. Only when that fully occupied empire is its side's primary participant does the side also gain 1% monthly Attrition and pass the normal 100% ceiling; a fully occupied secondary participant does not trigger that side-wide Attrition. These effects end when any colony is liberated. {since: 4.4.6}

- **Joining Wars:** Joining an ongoing war counts as offensive for subject agreement terms, and federation voting laws apply when members join or leave ongoing wars. {since: 4.5}

Related: [[Federations]], [[Ground Warfare]], [[Nomad Warfare]]
