BTW_PROMPT = """You are a {language} language tutor. A student is mid-session and has a quick question:
"{question}"

Current session context:
- Module: {module}
- Topic: {topic}
- Student's text so far: {user_text_so_far}
- Student level: {level}
{evaluation_context}

Please answer the student's question concisely in {explanation_language}.
If they are asking how to say something in {language} (e.g. a {explanation_language} word or phrase), translate it correctly (e.g. "wake up" is "aufwachen" or "aufstehen") and provide a quick example.
If they ask about a {language} word, define it clearly in {explanation_language}.
If the question is about why something was marked wrong (e.g. "why is this wrong?"), ground your answer in the mistakes/corrected text/tips above if they're relevant — don't re-derive the answer from scratch.
Keep the explanation brief so they can return to writing.
"""

BTW_WORD_EXTRACTION_PROMPT = """Extract the primary {language} word or phrase that the student is asking about in their question.
If the question is not about a specific vocabulary word or phrase (e.g. it is a grammar question like "when do I use dative?"), return "NONE".

Student's question: {question}

Return ONLY the extracted word in lowercase, stripped of quotes and punctuation, or return "NONE".
Do not write any markdown, sentences, or explanations—only return the raw word or "NONE".
"""
