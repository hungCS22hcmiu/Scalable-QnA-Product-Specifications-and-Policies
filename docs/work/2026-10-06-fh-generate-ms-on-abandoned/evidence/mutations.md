# Mutations — design.md §4

Each mutation was applied to a fresh **copy** of `gateway/` (the working tree with the fix, never the
working tree itself). Two runs each: the **existing suite** alone (`generatems_test.go` removed), and the
**full suite**. A mutation counts as caught only when a **new** test fails by assertion; a build error is
not a catch.

| # | Mutation | New tests that fail | Existing suite |
| :---: | :--- | :--- | :---: |
| (none) | the fix as written | — | passes |
| F1 | revert the fix: copy `generateMS` only on the success path | TestAFailedGenerationRecordsHowLongItTook, TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot, TestClientLeavingDuringAnswerRecordsHowLongItWasHeld, TestClientLeftBeforeTheRPCStillRecordsAnAttempt, TestTheSpansNest | passes |
| F2 | copy only for GENERATION_FAILED (and the success path) | TestClientLeavingDuringAnswerRecordsHowLongItWasHeld, TestClientLeftBeforeTheRPCStillRecordsAnAttempt | passes |
| F3 | copy only for ABANDONED (and the success path) | TestAFailedGenerationRecordsHowLongItTook, TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot, TestTheSpansNest | passes |
| F4 | assign a constant non-nil value before the switch (followers, queued and SHED carry it) | TestACoalescedMissFollowerCarriesNoGenerationTime, TestAFailedGenerationRecordsHowLongItTook, TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot, TestClientLeavingDuringAnswerRecordsHowLongItWasHeld, TestClientLeavingWhileQueuedRecordsNoAttempt, TestTheSpansNest | FAILS: TestShedWhenPermitAndQueueAreBothFull |
| F5 | copy only inside the success branch of the closure | TestAFailedGenerationRecordsHowLongItTook, TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot, TestClientLeavingDuringAnswerRecordsHowLongItWasHeld, TestClientLeftBeforeTheRPCStillRecordsAnAttempt, TestTheSpansNest | passes |
| F6 | record the time since Ask began instead of the generation's own span | TestACoalescedMissFollowerCarriesNoGenerationTime, TestAFailedLeaderRecordsAnAttemptButItsFollowerDoesNot, TestAMissGenerationTimeExcludesItsWriteBack, TestClientLeavingWhileQueuedRecordsNoAttempt, TestTheSpansNest | FAILS: TestShedWhenPermitAndQueueAreBothFull |
| F7 | `genStart` moved above Acquire (the span includes the permit wait) | TestTheSpansNest | passes |
| F8 | the MISS span runs to the END of the closure (it includes write-back) | TestAMissGenerationTimeExcludesItsWriteBack | passes |
| F9 | a coalesced MISS follower is given a generation time (a copied or shared span) | TestACoalescedMissFollowerCarriesNoGenerationTime | passes |

**Every mutation caught by a new test, none by a build error: yes.**
