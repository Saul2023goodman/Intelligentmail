# Follow-up automation stops at the Ready Pool

Status: accepted

An enabled, versioned Follow-up configuration confirms only deterministic trigger evaluation and creation of one linked Ready Preparation. When due, Follow-up hands that Preparation to the global Ready Pool and stops; Batch execution alone owns plan placement, exact sending Confirmation, Execution Attempts and mailbox writes. We chose this separation so one substantive module performs each transition exactly once and Follow-up cannot become a second execution system.
