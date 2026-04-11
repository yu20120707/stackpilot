Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path

$requiredFiles = @(
    "rd-incident-ai-assistant-prd.md",
    "evolving-agent-architecture.md",
    "tech-spec.md",
    "schema.md",
    "api-contracts.md",
    "prompts.md",
    "feature-list.md",
    "test-cases.md",
    "evolution-policy.md",
    "session-playbook.md",
    "decision-log.md",
    "agent.md",
    "task-board.json",
    "progress.md"
)

Write-Host "== Harness Init =="
Write-Host "Workspace: $workspace"

$missing = @()
foreach ($file in $requiredFiles) {
    $path = Join-Path $workspace $file
    if (Test-Path $path) {
        Write-Host "[OK ] $file"
    } else {
        Write-Host "[MISS] $file"
        $missing += $file
    }
}

if ($missing.Count -gt 0) {
    throw "Missing required files: $($missing -join ', ')"
}

$taskBoardPath = Join-Path $workspace "task-board.json"
$taskBoard = Get-Content -Raw -Encoding UTF8 $taskBoardPath | ConvertFrom-Json

$doneIds = @{}
foreach ($task in $taskBoard.tasks) {
    if ($task.status -eq "done") {
        $doneIds[$task.id] = $true
    }
}

$nextTask = $null
foreach ($task in $taskBoard.tasks) {
    if ($task.status -ne "not_started") {
        continue
    }

    $depsReady = $true
    foreach ($dep in $task.depends_on) {
        if (-not $doneIds.ContainsKey($dep)) {
            $depsReady = $false
            break
        }
    }

    if ($depsReady) {
        $nextTask = $task
        break
    }
}

Write-Host ""
if (Test-Path (Join-Path $workspace ".git")) {
    Write-Host "Git repo: yes"
} else {
    Write-Host "Git repo: no"
}

if ($null -ne $nextTask) {
    Write-Host "Next task: $($nextTask.id) - $($nextTask.title)"
    Write-Host "Milestone: $($nextTask.milestone)"
    Write-Host "Priority: $($nextTask.priority)"
} else {
    Write-Host "Next task: none"
}

Write-Host ""
Write-Host "Startup checklist:"
Write-Host "1. Read rd-incident-ai-assistant-prd.md"
Write-Host "2. Read evolving-agent-architecture.md"
Write-Host "3. Read tech-spec.md"
Write-Host "4. Read schema.md"
Write-Host "5. Read api-contracts.md"
Write-Host "6. Read prompts.md"
Write-Host "7. Read feature-list.md"
Write-Host "8. Read test-cases.md"
Write-Host "9. Read evolution-policy.md"
Write-Host "10. Read session-playbook.md"
Write-Host "11. Read decision-log.md"
Write-Host "12. Read task-board.json and confirm the primary task"
Write-Host "13. Read the latest session in progress.md"
Write-Host "14. Implement only one primary task"
Write-Host "15. Record evidence before marking any task done"
