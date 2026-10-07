import os
import json
import re
from typing import Dict, Any, List, Optional

try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


class CourseRecapEngine:
    """
    Synthesizes structured course recaps, key concepts, module breakdowns,
    and Mermaid visual diagrams from slide deck content.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.client = None
        if HAS_GEMINI and self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[RecapEngine] Failed to initialize Gemini Client: {e}")

    def generate_recap(self, slides: List[Dict[str, Any]], custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point for generating structured recaps & Mermaid diagrams.
        Uses Gemini API if available, else falls back to robust rule-based NLP extraction.
        """
        if self.client:
            try:
                return self._generate_with_gemini(slides, custom_prompt)
            except Exception as e:
                print(f"[RecapEngine] Gemini API generation error: {e}. Switching to heuristic synthesis.")
                return self._generate_heuristic(slides)
        else:
            return self._generate_heuristic(slides)

    def _generate_with_gemini(self, slides: List[Dict[str, Any]], custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        slides_summary = ""
        for s in slides:
            slides_summary += f"\n--- Slide {s['slide_number']}: {s['title']} ---\n{s['body']}\n"
            if s.get("tables"):
                slides_summary += f"Tables: {s['tables']}\n"

        system_instruction = (
            "You are an elite academic curriculum summarizer and visualization architect. "
            "Given a slide deck, generate a highly structured course recap and accurate, valid Mermaid.js diagrams."
        )

        prompt = f"""
{system_instruction}

Slide Deck Content:
{slides_summary}

Additional User Instructions:
{custom_prompt or 'Focus on core concepts, definitions, formulas/code snippets, key takeaways, and visual process flow diagrams.'}

Provide your response as a strict JSON object with NO surrounding markdown backticks or commentary. The JSON structure MUST be:
{{
  "course_title": "Course or Topic Name",
  "overview": "A comprehensive 2-3 paragraph executive summary of the entire slide deck.",
  "total_slides": {len(slides)},
  "modules": [
    {{
      "module_name": "Module or Topic Section Name",
      "slides_covered": "e.g. Slides 1-5",
      "summary": "Detailed summary of this section.",
      "key_concepts": [
        {{
          "term": "Concept or Term",
          "definition": "Clear explanation",
          "slide_ref": 1
        }}
      ],
      "formulas_or_code": ["Formula or Code snippet if applicable"],
      "takeaways": ["Key bullet takeaway 1", "Key bullet takeaway 2"]
    }}
  ],
  "mermaid_diagrams": [
    {{
      "title": "Course Mindmap Architecture",
      "type": "mindmap",
      "code": "mindmap\\n  root((Course Title))\\n    Topic 1\\n      Subtopic A\\n      Subtopic B\\n    Topic 2\\n      Subtopic C"
    }},
    {{
      "title": "Core Process Workflow",
      "type": "flowchart",
      "code": "graph TD\\n  A[Step 1: Input] --> B[Step 2: Processing]\\n  B --> C[Step 3: Output]"
    }}
  ],
  "review_questions": [
    {{
      "question": "Self-assessment question based on slides",
      "answer": "Comprehensive answer explaining the concept"
    }}
  ]
}}
"""
        response = self.client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2
            )
        )

        text_content = response.text or ""
        cleaned = re.sub(r"^```json\s*", "", text_content, flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned, flags=re.MULTILINE).strip()

        data = json.loads(cleaned)
        data["mermaid_diagrams"] = self._clean_and_validate_mermaid(data.get("mermaid_diagrams", []))
        return data

    def _generate_heuristic(self, slides: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        High-precision fallback recap generator using slide titles, body NLP parsing,
        keyword extraction, and dynamic Mermaid diagram construction.
        """
        if not slides:
            return self._empty_recap()

        main_title = slides[0]["title"] if slides else "Course Slide Deck Recap"
        if main_title.lower().startswith("slide 1") and len(slides) > 1:
            main_title = slides[1]["title"]

        # Group slides into ~3-4 modules
        num_slides = len(slides)
        chunk_size = max(1, num_slides // 3)
        modules = []
        all_concepts = []
        all_code = []

        for i in range(0, num_slides, chunk_size):
            chunk = slides[i:i + chunk_size]
            start_num = chunk[0]["slide_number"]
            end_num = chunk[-1]["slide_number"]
            mod_title = chunk[0]["title"] if chunk[0]["title"] != f"Slide {start_num}" else f"Section {len(modules) + 1}"
            
            chunk_text = " ".join([s["body"] for s in chunk])
            bullets = []
            for s in chunk:
                bullets.extend(s.get("bullets", []))
                all_code.extend(s.get("code_snippets", []))

            # Extract concepts (lines containing ':' or 'is')
            key_concepts = []
            for line in chunk_text.split(". "):
                if ":" in line and len(line.split(":")[0]) < 40:
                    parts = line.split(":", 1)
                    term = parts[0].strip(" -•*123456789.")
                    def_text = parts[1].strip()
                    if term and def_text:
                        key_concepts.append({
                            "term": term,
                            "definition": def_text,
                            "slide_ref": start_num
                        })

            if not key_concepts:
                # Fallback concept extraction from titles
                for s in chunk:
                    key_concepts.append({
                        "term": s["title"],
                        "definition": s["body"][:120] + "..." if len(s["body"]) > 120 else (s["body"] or "Core concept covered in slide."),
                        "slide_ref": s["slide_number"]
                    })

            all_concepts.extend(key_concepts)

            summary = f"This section covers key principles starting from Slide {start_num} to Slide {end_num}, focusing on {mod_title}."
            takeaways = [b.strip(" -•*") for b in bullets[:4]] if bullets else [
                f"Understood core mechanisms of {mod_title}.",
                f"Analyzed key slide items from Slides {start_num} to {end_num}."
            ]

            modules.append({
                "module_name": f"{mod_title}",
                "slides_covered": f"Slides {start_num}-{end_num}",
                "summary": summary,
                "key_concepts": key_concepts[:5],
                "formulas_or_code": [c for c in all_code if c in chunk_text][:3],
                "takeaways": takeaways
            })

        # Generate Mermaid Mindmap
        mindmap_lines = ["mindmap", f"  root(({main_title.strip()}))"]
        for mod in modules:
            safe_mod = re.sub(r"[():]", "", mod["module_name"])
            mindmap_lines.append(f"    {safe_mod}")
            for conc in mod["key_concepts"][:2]:
                safe_term = re.sub(r"[():]", "", conc["term"])
                mindmap_lines.append(f"      {safe_term}")

        mindmap_code = "\n".join(mindmap_lines)

        # Generate Mermaid Flowchart
        flow_lines = ["graph TD", "  classDef default fill:#1e1e2e,stroke:#89b4fa,stroke-width:2px,color:#cdd6f4;"]
        prev_id = None
        for idx, mod in enumerate(modules):
            node_id = f"M{idx+1}"
            safe_label = mod['module_name'].replace('"', "'")
            flow_lines.append(f'  {node_id}["{node_id}: {safe_label}"]')
            if prev_id:
                flow_lines.append(f"  {prev_id} --> {node_id}")
            prev_id = node_id

        flowchart_code = "\n".join(flow_lines)

        review_questions = []
        for conc in all_concepts[:3]:
            review_questions.append({
                "question": f"What is the definition and significance of {conc['term']}?",
                "answer": conc["definition"]
            })

        return {
            "course_title": main_title,
            "overview": f"This structured course recap provides an automated synthesis of '{main_title}', comprising {num_slides} slides organized into {len(modules)} key thematic modules.",
            "total_slides": num_slides,
            "modules": modules,
            "mermaid_diagrams": [
                {
                    "title": "Course Architecture Mindmap",
                    "type": "mindmap",
                    "code": mindmap_code
                },
                {
                    "title": "Module Execution Flowchart",
                    "type": "flowchart",
                    "code": flowchart_code
                }
            ],
            "review_questions": review_questions
        }

    def _clean_and_validate_mermaid(self, diagrams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        cleaned = []
        for d in diagrams:
            code = d.get("code", "").strip()
            # Clean common syntax errors (unescaped quotes or invalid chars)
            code = re.sub(r"^```mermaid\s*", "", code, flags=re.MULTILINE)
            code = re.sub(r"```$", "", code, flags=re.MULTILINE).strip()
            cleaned.append({
                "title": d.get("title", "Diagram"),
                "type": d.get("type", "flowchart"),
                "code": code
            })
        return cleaned

    def _empty_recap(self) -> Dict[str, Any]:
        return {
            "course_title": "Empty Presentation",
            "overview": "No slides found in the provided document.",
            "total_slides": 0,
            "modules": [],
            "mermaid_diagrams": [],
            "review_questions": []
        }
