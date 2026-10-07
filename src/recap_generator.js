/**
 * Recap & Mermaid Diagram Generator Service
 * Groups slides per PDF file and synthesizes individual per-deck recaps & diagrams.
 */

const API_BASE_URL = "http://127.0.0.1:8000/api";

export async function generateCourseRecap(slides, apiKey = "", customPrompt = "") {
  try {
    const response = await fetch(`${API_BASE_URL}/generate-recap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slides: slides,
        api_key: apiKey,
        custom_prompt: customPrompt
      })
    });

    if (response.ok) {
      const data = await response.json();
      console.log("[RecapGenerator] Recap received from FastAPI backend.");
      return data;
    }
  } catch (err) {
    console.log("[RecapGenerator] Backend server not active, using client-side per-deck synthesis engine.", err);
  }

  return generateClientSideMultiDeckRecap(slides, customPrompt);
}

function generateClientSideMultiDeckRecap(slides, customPrompt = "") {
  if (!slides || slides.length === 0) {
    return {
      course_title: "Empty Slide Decks",
      overview: "No slide content available to analyze.",
      total_slides: 0,
      deck_recaps: []
    };
  }

  // Group slides by source_file
  const slidesByFile = {};
  slides.forEach(s => {
    const fileKey = s.source_file || "Deck 1";
    if (!slidesByFile[fileKey]) {
      slidesByFile[fileKey] = [];
    }
    slidesByFile[fileKey].push(s);
  });

  const fileNames = Object.keys(slidesByFile);
  const deckRecaps = fileNames.map(fileName => {
    const deckSlides = slidesByFile[fileName];
    return generateSingleDeckRecap(fileName, deckSlides);
  });

  // Calculate overall stats
  let totalModules = 0;
  deckRecaps.forEach(d => totalModules += d.modules.length);

  const mainTitle = fileNames.length > 1 
    ? `Course Recap: ${fileNames.length} Slide Decks (${fileNames.join(", ")})`
    : deckRecaps[0].deck_title;

  return {
    course_title: mainTitle,
    overview: `Synthesized recaps for ${fileNames.length} PDF slide deck(s) total matching ${slides.length} slides across ${totalModules} modules.`,
    total_slides: slides.length,
    deck_recaps: deckRecaps,
    // Flattened fallbacks for single view components
    modules: deckRecaps.flatMap(d => d.modules),
    mermaid_diagrams: deckRecaps.flatMap(d => d.mermaid_diagrams),
    review_questions: deckRecaps.flatMap(d => d.review_questions)
  };
}

function cleanSlideTitle(rawTitle, bodyText = "") {
  if (!rawTitle) return "Core Topic";
  
  // Remove generic prefixes like "PART 1  ·  CORE MECHANICS", "THE HOOK", "RECAP", "NEXT UP", "Stage 1", "Case 1"
  let cleaned = rawTitle
    .replace(/^PART\s+\d+\s*[·•-]\s*/i, "")
    .replace(/^(THE HOOK|LIVE\s*\/|\s*HANDS-ON|RECAP|NEXT UP|PRODUCTION NOTE)/i, "")
    .replace(/^(Stage|Case|Step|Part)\s+\d+:?\s*/i, "")
    .trim();

  // If title was only a generic header, pick the first meaningful line from body
  if (!cleaned || cleaned.length < 3 || /^(Slide \d+|Stage \d+|Case \d+|Part \d+)$/i.test(cleaned)) {
    const lines = bodyText.split("\n").map(l => l.trim()).filter(l => l.length > 3 && !/^(PART|deboistech|DAY \d+)/i.test(l));
    if (lines.length > 0) {
      cleaned = lines[0].replace(/^[-•*1-9.\s]+/, "").trim();
    }
  }

  return cleaned || rawTitle || "Core Concept";
}

function generateSingleDeckRecap(fileName, slides) {
  const firstMeaningfulTitle = slides.find(s => s.title && !s.title.toLowerCase().startsWith("slide 1"))?.title;
  const deckTitle = cleanSlideTitle(firstMeaningfulTitle || fileName.replace(/\.pdf$/i, ''));
  const numSlides = slides.length;

  const chunkSize = Math.max(1, Math.ceil(numSlides / 3));
  const modules = [];
  const allConcepts = [];
  const allCode = [];

  for (let i = 0; i < numSlides; i += chunkSize) {
    const chunk = slides.slice(i, i + chunkSize);
    const startNum = chunk[0].slide_number;
    const endNum = chunk[chunk.length - 1].slide_number;
    
    const rawModTitle = chunk[0].title !== `Slide ${startNum}` ? chunk[0].title : `Module ${modules.length + 1}`;
    const modTitle = cleanSlideTitle(rawModTitle, chunk[0].body);

    const chunkBody = chunk.map(s => s.body).join("\n");
    const keyConcepts = [];

    chunkBody.split("\n").forEach(line => {
      if (line.includes(":") && line.indexOf(":") < 35) {
        const parts = line.split(":");
        const term = cleanSlideTitle(parts[0]);
        const def = parts.slice(1).join(":").trim();
        if (term && def.length > 5) {
          keyConcepts.push({
            term: term,
            definition: def,
            slide_ref: startNum
          });
        }
      }
    });

    if (keyConcepts.length === 0) {
      chunk.forEach(s => {
        keyConcepts.push({
          term: cleanSlideTitle(s.title, s.body),
          definition: s.body.length > 100 ? s.body.substring(0, 100) + "..." : (s.body || "Core slide concept."),
          slide_ref: s.slide_number
        });
      });
    }

    allConcepts.push(...keyConcepts);

    const chunkCode = [];
    chunk.forEach(s => {
      if (s.code_snippets) chunkCode.push(...s.code_snippets);
    });
    allCode.push(...chunkCode);

    modules.push({
      module_name: modTitle,
      source_file: fileName,
      slides_covered: `Slides ${startNum}-${endNum}`,
      summary: `Covers key concepts presented in ${fileName} (Slides ${startNum}-${endNum}), focusing on ${modTitle}.`,
      key_concepts: keyConcepts.slice(0, 5),
      formulas_or_code: chunkCode.slice(0, 3),
      takeaways: [
        `Mastered core principles of ${modTitle} in ${fileName}`,
        `Analyzed key slide items across Slides ${startNum}-${endNum}`
      ]
    });
  }

  // Construct Mermaid Mindmap per PDF deck with crisp clean labels
  const safeDeckName = deckTitle.replace(/[()":;]/g, '');
  const mindmapLines = [
    "mindmap",
    `  root(("${safeDeckName}"))`
  ];
  modules.forEach(mod => {
    const safeMod = mod.module_name.replace(/[()":;]/g, '');
    mindmapLines.push(`    ${safeMod}`);
    mod.key_concepts.slice(0, 3).forEach(c => {
      const safeTerm = c.term.replace(/[()":;]/g, '');
      if (safeTerm && safeTerm !== safeMod) {
        mindmapLines.push(`      ${safeTerm}`);
      }
    });
  });

  // Construct Mermaid Flowchart per PDF deck
  const flowLines = [
    "graph TD",
    "  classDef default fill:#1e293b,stroke:#818cf8,stroke-width:2px,color:#ffffff;"
  ];
  let prevId = null;
  modules.forEach((mod, idx) => {
    const id = `D${fileName.replace(/[^a-zA-Z0-9]/g, '').slice(0, 4)}M${idx + 1}`;
    const safeName = mod.module_name.replace(/["';]/g, '');
    flowLines.push(`  ${id}["Module ${idx + 1}: ${safeName}"]`);
    if (prevId) {
      flowLines.push(`  ${prevId} --> ${id}`);
    }
    prevId = id;
  });

  const reviewQuestions = allConcepts.slice(0, 3).map(c => ({
    question: `[${fileName}] Explain '${c.term}' and its significance in this deck.`,
    answer: c.definition
  }));

  return {
    source_file: fileName,
    deck_title: deckTitle,
    overview: `Recap of '${fileName}' containing ${numSlides} slides across ${modules.length} modules.`,
    slides_count: numSlides,
    modules: modules,
    mermaid_diagrams: [
      {
        title: `${fileName} - Concept Mindmap`,
        type: "mindmap",
        code: mindmapLines.join("\n")
      },
      {
        title: `${fileName} - Workflow Flowchart`,
        type: "flowchart",
        code: flowLines.join("\n")
      }
    ],
    review_questions: reviewQuestions
  };
}
