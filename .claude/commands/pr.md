Compare the current branch to `main` and open a pull request using the standard project template.

## Steps

1. Run `git log main..HEAD --oneline` to list commits not yet in main.
2. Run `git diff main..HEAD --stat` to see which files changed and by how much.
3. Analyse the commits and diff to fill in the PR template below accurately.
4. Run `gh pr create` with `--base main` and the completed template as the body.

## PR template

```
## Summary

**What changed?**
<Concise description of every meaningful change: new features, removals, fixes, refactors.>

**Why was this needed?**
<The motivation — business need, bug, security concern, tech debt, etc.>

---

## Validation

- [ ] `docker compose up -d` starts all services successfully
- [ ] <Specific endpoint or behaviour to verify for each changed feature>
- [ ] OE dashboard loads without errors
- [ ] If dashboard changed: Streamlit app loads without errors
- [ ] Docs updated if user-facing behaviour changed

---

## Risk

**Potential regressions:** <What existing behaviour could break and why.>

**Rollback plan:** <How to undo — revert commit, env var toggle, etc.>
```

## Rules

- Derive the PR title from the dominant change type and a short imperative description (≤ 70 chars).
- Check `[x]` a validation item if it applies and passes; leave `[ ]` if it does not apply or was not verified.
- Do not push or merge — only create the PR.
