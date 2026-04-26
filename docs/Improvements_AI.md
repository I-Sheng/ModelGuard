# Lessons Learned: Collaborating with AI

1. **Automate verification, don't review manually.** AI can generate a large volume of output (e.g. dozens of security tests) that is impractical to check one by one. A better approach is to write automated tests or scripts so the output can be validated in a single pass.

2. **Understand AI's perspective.** AI has no context beyond what you provide in the prompt. When it makes mistakes, it's usually because the intent wasn't explicit enough. Thinking from AI's point of view — what does it actually know? — leads to better prompts and fewer misunderstandings.

3. **Work in smaller, reviewable chunks.** Breaking tasks into smaller pieces makes it easier to verify each step thoroughly before moving on. Large, multi-part tasks accumulate errors that are harder to catch at the end.

4. **Consolidate context into a single reference document.** Instead of spreading intent across multiple prompts (where misunderstanding compounds), write a comprehensive `.md` file upfront. This gives AI a stable, complete picture of what you want.
