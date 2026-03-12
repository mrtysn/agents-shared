# Question Handling Rule

**When the user asks a question, answer it. Nothing else.**

## What counts as a question

- Sentences ending with `?`
- "What does…", "How does…", "Why is…", "Where is…", "Can you explain…"
- "What would happen if…", "Is it possible to…"
- Requests for explanation, clarification, or information

## What to do

- **Answer the question** with the relevant information
- **Read code** if needed to give an accurate answer
- **Search the codebase** if needed to locate the relevant code

## What NOT to do

- Do NOT edit files
- Do NOT propose code changes
- Do NOT suggest improvements or refactors
- Do NOT run commands that modify state
- Do NOT treat the question as an implicit request to fix, change, or implement anything

## When to take action

Only when the user **explicitly instructs** you to act:
- "Fix this", "Change this", "Implement X", "Add Y", "Remove Z"
- "Go ahead", "Do it", "Make that change"
- Any clear imperative directing you to modify something

## Why this rule exists

Questions are requests for information. Treating them as implicit action requests wastes time, creates unwanted changes, and forces the user to course-correct. Answer first — the user will tell you if they want action taken.
