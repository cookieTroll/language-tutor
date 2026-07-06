# Competitive Landscape & Positioning

This document compares Wharf against commercial, academic, and general-purpose alternatives for language learning. It highlights how Wharf's architecture resolves the trade-offs between feedback quality, competency integration, language extensibility, and pricing.

---

## The Landscape: Where Competitors Fall Short

- **Gamified, Canned Curricula:** Apps like Duolingo prioritize engagement over depth, offering simple recognition tasks (matching, sorting) rather than free-text production. While they track your streak and progression through a linear, pre-authored lesson tree, they lack the ability to adapt their actual curriculum or exercises dynamically based on your free-form writing errors.
- **Siloed Competency Apps:** Corrective writing tools (e.g., Cambridge Write & Improve) or grammar apps operate in isolation, lacking a shared memory of the user's strengths and weaknesses across skills.
- **High Subscription Barriers:** Platforms that offer deep corrective feedback (e.g., Grammarly Premium, Duolingo Max, or premium human tutors) are locked behind high subscription paywalls ($10 to $30 per month).

---

## Detailed Competitor Comparison

| Tool Class / Example | Core Focus & Depth | Language Support & Setup | Pricing Model | Gaps vs. Wharf |
|---|---|---|---|---|
| **Passive Drill Apps**<br>(e.g., Duolingo, Memrise) | **Shallow Recognition:** Mostly multiple-choice, reordering, and short translation drills. Duolingo Max offers "Roleplay" and "Video Call," but its "Explain My Answer" is restricted to pre-authored lesson prompts. | **Pre-authored Courses:** Limited language pairs. Adding a target language requires manually authoring an entire pedagogical tree. | Free basic (ad-supported); Super Duolingo (€10.25/mo annual); Duolingo Max (~€14.99/mo). Max is iOS/Android only. | No open free-text evaluation; rigid linear paths; no cross-competency adaptive memory. |
| **Corrective Writing Engines**<br>(e.g., Cambridge Write & Improve) | **Deep Writing Feedback:** CEFR-aligned scoring, spelling/grammar corrections on free-text writing. | **English Only:** Built on a static, hand-annotated 30M-word English learner corpus. Cannot be extended to other target languages. | Free basic tier; paid packages for specialized exam preparation (e.g., IELTS, B2 First). | English-only; no grammar instruction; no session-to-session memory or personalization; no local execution. |
| **General Proofreaders**<br>(e.g., Grammarly, LanguageTool Premium) | **Correction, Not Pedagogy:** Identifies grammatical and stylistic errors for native or professional writing. Does not explain the L2 rules or align feedback to the user's CEFR level. | **Fixed Major Languages:** Supports standard lists (LanguageTool supports ~30 languages). Cannot configure the explanation language independently. | Subscription-based. Grammarly Premium is $12–$30/mo; LanguageTool Premium is ~$19.90/mo (or ~$4.99/mo annual). | No pedagogical explanation; no CEFR-targeted feedback; no integrated curriculum or active memory. |
| **Peer Correction Platforms**<br>(e.g., Busuu Community, Lang-8) | **Human Accuracy:** Native speakers verify and correct user-submitted writing. | **Any Language:** Dependent on active native speakers in the community. | Included in Busuu's free tier and premium plans ($6 to $15/month). | **Slow loop:** Feedback takes minutes to days. Quality is unstructured, variable, and relies on user reciprocity. |
| **Raw LLM Prompting**<br>(e.g., ChatGPT / Claude Web App) | **High Versatility:** Strong translation, explanation, and error correction capabilities. | **Extremely Flexible:** Supports a vast array of target and explanation languages out of the box. | Free tiers (with data sharing/limits) or $20/mo subscription. | **No persistence:** Every chat starts from zero. Lacks persistent error tracking, progress statistics, and local execution. |

---

## Wharf's Four Pillars of Differentiation

### 1. Unified Competency Memory
Commercial platforms typically silo different skills (e.g., vocabulary drills in one app, grammar in another, writing elsewhere). While some premium AI tiers (like Duolingo Max's review rounds or Busuu's vocabulary lists) track your history, their persistence is shallow. A mistake in a writing prompt does not trigger the app to automatically rewrite your curriculum, generate a targeted grammar theory sheet, and compose custom drills on the fly. Wharf solves this with a **Three-Grain Architecture** where all competencies share a single orchestrator and storage layer. 
- *Bridged Competencies:* Today, the writing and grammar modules are bridged. If a user consistently struggles with "adjective endings" in writing, the Orchestrator automatically intercepts the error taxonomy and routes them to a targeted grammar session on that rule.
- *Extensible Profile:* As reading, listening, and speaking modules are introduced post-submission, they will share the exact same user profile, vocabulary flags, and historical trend data.

### 2. Pedagogy & Structured Production Depth
Rather than gamifying learning with quick recognition loops, Wharf forces learners to actively produce language:
- **Writing Module:** Learner-composed free text is evaluated through a structured 7-step pipeline (estimate text level → detect mistakes → verify to eliminate false positives → classify against taxonomy → explain rules → write corrections → summarize session).
- **Grammar Module:** Rather than serving static, pre-written exercises, Wharf generates a tailored grammatical theory explanation and custom exercises on the fly based on the learner's historic error tags.

### 3. Language & Explanation Personalization (Validation, Not Rewrite)
For target and explanation languages using Latin-based alphabets and supported by major LLM pretraining:
- **Target Language Independence:** Adding a target language is data-driven. `scripts/generate_language.py` runs a 3-step self-correcting LLM chain (taxonomy → CEFR hints → grammar topics) and validates it against Pydantic schemas. Spot-checks on a smaller target language (Czech) verified that the generated assets are highly accurate out of the box, requiring only minor validation rather than manual development.
- **Explanation Personalization:** The user can configure the `explanation_language` (e.g., getting Czech explanations for German grammar). UI strings are dynamically translated via message catalogs (`lang/messages/{language}.yaml`).

### 4. Cost Disruption & Privacy
Wharf shifts the economic model of language tutoring:
- **Offline / Local Path (Ollama):** Run completely offline and free on local hardware. Note that this requires suitable hardware (a dedicated GPU with ~6–8 GB VRAM to run models like `gemma2:9b` or `qwen2.5:7b` at acceptable speeds). Furthermore, local models represent the lower end of grading and pedagogical accuracy compared to hosted commercial models, though they provide complete privacy.
- **Hosted Path (Gemini / Vertex):** By leveraging the learner's own API keys (Gemini 2.5 Flash), a complete session (100-word writing evaluation or custom grammar drill) costs a fraction of a cent. A full study monthly load of 60 sessions (2 sessions/day) runs **roughly €1 per month**. The prompt overhead (system instructions and context) represents the bulk of the cost, making the price highly flat and predictable. Furthermore, as a local library of generated lessons and exercises is gradually compiled, subsequent study sessions on those cached topics bypass the LLM entirely, reducing upkeep costs even further.
- This is a structural cost difference compared to automated correctors or AI features (like Duolingo Max at ~$15/mo or Grammarly Premium at $12–$30/mo) which charge fixed, high monthly subscription fees regardless of actual study volume.
