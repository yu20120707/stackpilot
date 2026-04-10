# P0 Manual Validation Checklist

Run these commands from the workspace root:

```powershell
.\scripts\bootstrap.ps1
.\scripts\smoke.ps1
.\scripts\test.ps1
```

Confirm the following:

- `.\scripts\smoke.ps1` passes the happy-path and insufficient-context fixture flow.
- `.\scripts\test.ps1` passes the full automated suite.
- The happy-path rendered reply includes:
  - current assessment
  - known facts
  - impact scope
  - next actions
  - citations
- The insufficient-context rendered reply clearly lists missing information.
- Unsupported chatter still produces no accepted analysis request.

If all checks pass, P0 is ready for fixture-backed review.
