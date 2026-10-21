# CLAUDE.md

## Single commit

This repo only ever has one commit on `main`. Never create a new commit on top of it. To publish any
change, including a card refresh, amend the existing commit and force-push:

```bash
git add -A
git commit --amend --no-edit
git push --force-with-lease
```

No AI attribution in the commit message.
