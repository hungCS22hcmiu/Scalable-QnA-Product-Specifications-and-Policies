# Mutations — design.md §6

Each mutation was applied to a fresh copy of `gateway/` (the working tree with the fix, base
`47da81e`), never to the working tree itself. Two runs each: the **existing suite** alone
(`abandon_test.go` removed), and the **new tests**. A build error is not a catch.

| # | Mutation | New tests that fail | Existing suite |
| :---: | :--- | :--- | :---: |
| (none) | the fix as written | — | passes |
| M1 | condition dropped | T7, T2, T1 | passes |
| M2 | keyed on the gRPC status code (Canceled / DeadlineExceeded) instead of ctx.Err() | T6, T3 | passes |
| M3 | `err != nil` guard dropped | T5 | passes |
| M4 | classified in the closure from the leader's context; switch as today | T6 | passes |
| M4b | M4 plus the new switch case | T6 | passes |
| M5 | ragclient.Answer returns ctx.Err() (Option B); switch as today | T6 | passes |
| M5b | ragclient maps status Canceled to context.Canceled; switch as today | T6, T3 | passes |
| M6 | new case placed above ErrShed | T4 | passes |

**Every mutation caught by the new tests, none by a build error, and every one passing the existing suite: yes.**
