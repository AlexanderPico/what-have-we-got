# web UI flow

Primary browser flow:
1. open `/`
2. choose mode: single-image or multi-item image
3. upload photos and/or paste text descriptions
4. optionally run price lookup
5. optionally use LLM listing-title generation
6. review resulting item table sorted by heuristic triage value
7. inspect listing draft cards
8. export CSV or JSON
9. reopen later from saved session path under `~/.whgot/sessions/`

Current UI posture:
- desktop-first
- local-only
- thin FastAPI + Jinja stack
- session artifacts stored to disk for re-openability
