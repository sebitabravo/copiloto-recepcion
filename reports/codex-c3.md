# Codex C3 — Live stack end-to-end checks

## Status
PASS. Implemented `scripts/e2e.py` and ran it once against the existing local stack. Exit code: 0. All checks passed, including service restoration.

## Files
- `scripts/e2e.py` — standard-library/httpx runner using the web widget API for independent guests and the account API for staff assertions; asynchronous response polling and latency measurement; normal, out-of-hours and PMS-down flows; cumulative metrics checks; independent try/finally restoration; final secret-safe PASS/FAIL table.
- `reports/codex-c3.md` — this requested report.

No other source/configuration files were modified and no git commands were run. Comments are Spanish; identifiers are English. AST parsing and the 120-character line limit passed. Tokens, credentials, response bodies and subprocess output are never printed by the script.

## Run
Command: `uv run --with httpx python scripts/e2e.py`

Full captured output (including uv's dependency-installation message):

```text
Installed 7 packages in 7ms
case         | check                             | result | detail                                                     
setup        | services ready                    | PASS   | PMS available; reception forced in shift                   
FAQ          | answer latency                    | PASS   | 0.69 s; limit 10 s                                         
FAQ          | conversation status               | PASS   | Expected pending                                           
availability | reply to quiero reservar          | PASS   | Expected response visible in 0.67 s                        
availability | reply to 15/03/2027 al 18/03/2027 | PASS   | Expected response visible in 0.17 s                        
availability | reply to 2                        | PASS   | Expected response visible in 0.32 s                        
availability | pending confirmation              | PASS   | Availability visible in 0.29 s; human confirmation required
availability | handoff closing                   | PASS   | Closing visible in 0.19 s                                  
availability | location before dates             | PASS   | Guest-visible outgoing message order                       
availability | conversation status               | PASS   | Expected open                                              
availability | commercial label                  | PASS   | Expected comercial                                         
availability | reception team                    | PASS   | Expected recepción                                         
availability | private dated note                | PASS   | Private pre-information includes 2027-03-15                
out of hours | reply to quiero reservar          | PASS   | Expected response visible in 0.67 s                        
out of hours | reply to 15/03/2027 al 18/03/2027 | PASS   | Expected response visible in 0.19 s                        
out of hours | reply to 2                        | PASS   | Expected response visible in 0.24 s                        
out of hours | pending confirmation              | PASS   | Availability visible in 0.34 s; human confirmation required
out of hours | handoff closing                   | PASS   | Closing visible in 0.21 s                                  
out of hours | opening hour                      | PASS   | Expected opening hour 19:36                                
out of hours | location before dates             | PASS   | Guest-visible outgoing message order                       
out of hours | conversation status               | PASS   | Expected open                                              
out of hours | commercial label                  | PASS   | Expected comercial                                         
out of hours | reception team                    | PASS   | Expected recepción                                         
out of hours | private dated note                | PASS   | Private pre-information includes 2027-03-15                
out of hours | night label                       | PASS   | Expected nocturna                                          
PMS down     | reply to quiero reservar          | PASS   | Expected response visible in 0.67 s                        
PMS down     | reply to 15/03/2027 al 18/03/2027 | PASS   | Expected response visible in 0.19 s                        
PMS down     | reply to 2                        | PASS   | Expected response visible in 0.23 s                        
PMS down     | PMS fallback                      | PASS   | Fallback visible in 0.29 s                                 
PMS down     | location before dates             | PASS   | Guest-visible outgoing message order                       
PMS down     | conversation status               | PASS   | Expected open                                              
PMS down     | commercial label                  | PASS   | Expected comercial                                         
PMS down     | reception team                    | PASS   | Expected recepción                                         
PMS down     | private dated note                | PASS   | Private pre-information includes 2027-03-15                
metrics      | faq_answered                      | PASS   | Expected cumulative count >= 1                             
metrics      | handoff                           | PASS   | Expected cumulative count >= 3                             
metrics      | queries                           | PASS   | Expected cumulative count >= 1                             
restore      | copiloto                          | PASS   | Default shift / SIMULATE_DOWN=0 restored; health 200       
restore      | pms-mock                          | PASS   | Default shift / SIMULATE_DOWN=0 restored; health 200       
```

## Restoration
The run recreated copiloto without SHIFT overrides and pms-mock with `SIMULATE_DOWN=0`; both health endpoints returned 200. The test creates guest conversations and events in the running stack as requested.

## Notes
Engram tools were unavailable; no memory persistence is claimed.

