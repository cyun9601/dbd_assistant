// 키워드 + 유의어 기반 검색  (window.DBDSearch 로 노출 — file:// 더블클릭에서도 동작)
// 한국어는 띄어쓰기/조사가 불규칙하므로 "부분 문자열 포함" 매칭을 기본으로 한다.
// (예: 검색어 "속도" 가 설명문 "이동 속도 증가" 안에 그대로 들어있는지)
(function () {
  const STOP = ["살인마", "퍽", "관련", "있는", "되는", "하는", "같아", "같은", "거", "것", "내", "나",
    "을", "를", "이", "가", "은", "는", "에", "의", "도", "과", "와", "랑", "이랑", "어", "음"];

  function cleanQuery(q) {
    return (q || "").toLowerCase().replace(/[^가-힣a-z0-9% ]/g, " ").replace(/\s+/g, " ").trim();
  }

  // 검색어 -> 매칭에 쓸 토큰 집합 (원문 토큰 + 유의어 확장)
  function expandedQueryTerms(q, syn) {
    const cq = cleanQuery(q);
    if (!cq) return [];
    const words = cq.split(" ").filter((w) => w.length >= 2 && !STOP.includes(w));
    const terms = new Set(words);
    terms.add(cq); // 전체 구절도 토큰으로
    for (const group of syn) {
      const hit = group.some((g) => cq.includes(g) || words.some((w) => w.includes(g) || g.includes(w)));
      if (hit) group.forEach((g) => terms.add(g));
    }
    return [...terms].filter((t) => t.length >= 2);
  }

  function rankKeyword(q, perks, syn) {
    const cq = cleanQuery(q);
    if (!cq) return [];
    const words = cq.split(" ").filter((w) => w.length >= 2 && !STOP.includes(w));
    const terms = expandedQueryTerms(q, syn);
    const userWords = new Set([...words, cq]); // 유저가 직접 친 단어

    const scored = [];
    for (const perk of perks) {
      const name = perk.name.toLowerCase();
      const owner = (perk.owner || "").toLowerCase();
      const desc = perk.desc_text.toLowerCase();
      let score = 0;
      const matched = new Set();

      for (const t of terms) {
        const w = userWords.has(t) ? 2 : 1; // 원문 단어 가중
        if (name.includes(t)) { score += 12 * w; matched.add(t); }
        if (owner.includes(t)) { score += 3 * w; }
        if (desc.includes(t)) {
          const cnt = Math.min(3, desc.split(t).length - 1);
          score += (4 + (cnt - 1)) * w;
          matched.add(t);
        }
      }
      const distinctUserHits = [...matched].filter((t) => userWords.has(t)).length;
      if (distinctUserHits >= 2) score += distinctUserHits * 6;

      if (score > 0) scored.push({ perk, score });
    }
    scored.sort((a, b) => b.score - a.score || a.perk.name.localeCompare(b.perk.name, "ko"));
    return scored.slice(0, 30);
  }

  // 결과 설명문에서 매칭 토큰을 하이라이트 (HTML 태그 밖 텍스트에만 적용)
  function highlightMatches(html, terms) {
    if (!terms || !terms.length) return html;
    const ts = [...new Set(terms)].filter((t) => t.length >= 2).sort((a, b) => b.length - a.length);
    if (!ts.length) return html;
    const esc = ts.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const re = new RegExp("(" + esc.join("|") + ")", "gi");
    return html.replace(/>([^<]+)</g, (m, txt) => ">" + txt.replace(re, '<span class="hl">$1</span>') + "<")
               .replace(/^([^<]+)</, (m, txt) => txt.replace(re, '<span class="hl">$1</span>') + "<");
  }

  window.DBDSearch = { rankKeyword, expandedQueryTerms, highlightMatches };
})();
