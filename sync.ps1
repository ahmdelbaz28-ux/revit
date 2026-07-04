Write-Host "=== Step 1: Configure git remote with token ==="
git remote set-url origin https://GITHUB_PAT@github.com/ahmdelbaz28-ux/revit.git

Write-Host "`n=== Step 2: Fetch all from remote ==="
git fetch --all --prune

Write-Host "`n=== Step 3: Hard reset to origin/main ==="
git reset --hard origin/main

Write-Host "`n=== Step 4: Clean untracked files ==="
git clean -fd

Write-Host "`n=== Step 5: Status ==="
git status

Write-Host "`n=== Step 6: Recent commits ==="
git log --oneline -10

Write-Host "`n=== Step 7: Verify local/remote identical ==="
git diff origin/main

Write-Host "`n=== DONE ==="
