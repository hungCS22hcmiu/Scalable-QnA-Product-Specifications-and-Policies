# Mutations — design.md §5

Each mutation was applied to a fresh **copy** of `gateway/` (the working tree with the change,
never the working tree itself). Two runs each: the **existing suite** alone (the three new test
files removed), and the **full suite**. A mutation counts as caught only when a **new** test
fails by assertion; a build error is not a catch.

| # | Mutation | New tests that fail | Existing suite |
| :---: | :--- | :--- | :---: |
| (none) | the change as written | — | passes |
| M1 | write the answer only on a MISS (hits never write) | TestEveryServedAnswerIsRecoverableFromRawAlone | passes |
| M2 | the line is written before the file | TestTheFileIsVisibleBeforeTheLineThatNamesIt | passes |
| M3 | the Tier-1 call site left on the old assignment (hash set, text not) | TestEveryServedAnswerIsRecoverableFromRawAlone | passes |
| M4 | `seen` is set before the write succeeds | TestAFailedLinkIsCountedAndALaterRecordRetries | passes |
| M5 | `missing` is never cleared by a successful retry | TestAFailedLinkIsCountedAndALaterRecordRetries, TestTheGuardRefusesAMismatchAndNeverForgets | passes |
| M6 | no dedupe (every record tries to publish) | TestIdenticalAnswersAreWrittenOnce | passes |
| M7 | the hash is taken over the TRIMMED text (the shared helper changes, so the guard agrees with it) | TestAnswerTextRoundTripsByteExact | passes |
| M8 | a failed write is not counted missing | TestAFailedLinkIsCountedAndALaterRecordRetries, TestAFailedTempWriteNeverPublishesAFile, TestAnUnwritableAnswersDirectoryIsCountedMissing | passes |
| M9 | the guard is removed | TestFinishRunReadsTheCountersAfterTheBufferHasDrained, TestTheGuardRefusesAMismatchAndNeverForgets | passes |
| M10 | the temp file is left behind after a failed Link | TestAFailedLinkIsCountedAndALaterRecordRetries | passes |
| M11 | Rename instead of Link (overwrites an existing file) | TestAnExistingAnswerFileIsNeverRewritten | passes |
| M12 | Open makes answers/ BEFORE the exclusive create, and tolerates it already existing | TestOpenOnAnExistingRunFileCreatesNothingInsideIt, TestOpenRefusesAPreexistingAnswersDirectoryAndRemovesOnlyWhatItMade | passes |
| M13 | a failed line write is not counted | TestAnEncodeFailureIsCountedAndLeavesAnUnnamedFile, TestFinishRunNamesAFailedLineWrite | passes |
| M14 | a failed temp removal AFTER a successful Link marks the hash missing | TestAFailedTempRemovalAfterALinkIsNotAMissingAnswer | passes |
| M15 | EEXIST from Link is treated as an error | TestAnExistingAnswerFileIsNeverRewritten | passes |
| M16 | a guard refusal is cleared by a later successful write | TestTheGuardRefusesAMismatchAndNeverForgets | passes |
| M17 | `incomplete` ignores AnswersMissing | TestFinishRunReadsTheCountersAfterTheBufferHasDrained, TestIncompleteNamesTheConditionThatFired, TestIncompleteReportsTheCounts | passes |
| M18 | `incomplete` reports WriteErrors under the Dropped condition's count (fields crossed) | TestFinishRunNamesAFailedLineWrite, TestIncompleteNamesTheConditionThatFired | passes |
| M19 | a failed temp write/chmod/close is ignored: the (possibly truncated) temp is linked under {sha}.txt | TestAFailedTempWriteNeverPublishesAFile | passes |
| M20 | finishRun reads the counters BEFORE Close (a queued record is not yet counted) | TestFinishRunNamesAFailedLineWrite, TestFinishRunReadsTheCountersAfterTheBufferHasDrained | passes |
| M21 | finishRun does not pass the guard-refusal count to `incomplete` | TestFinishRunReadsTheCountersAfterTheBufferHasDrained | passes |
| M22 | the Tier-2 call site left on the old assignment (hash set, text not) | TestEveryServedAnswerIsRecoverableFromRawAlone | passes |
| M23 | the MISS call site left on the old assignment (hash set, text not) | TestAMissWhoseClientLeftStillStoresItsAnswer, TestEveryServedAnswerIsRecoverableFromRawAlone | passes |
| M24 | the Tier-1 site stores a consistent but WRONG text (the served answer plus a space) | TestEveryServedAnswerIsRecoverableFromRawAlone | FAILS: TestBoundedCacheTouchesTheServedEntryAndTrimsToCapacity, TestMissGeneratesOnceAndWritesBothTiersUnderOneIdentity, TestTier1HitServesTheStoredAnswer, TestTier2HitInsideTheNamespaceAndPromotesToTier1 |
| M25 | the MISS site skips SetAnswer when the client has left (a completed generation is dropped) | TestAMissWhoseClientLeftStillStoresItsAnswer | FAILS: TestACompletedGenerationIsStillAMissWhenTheClientHasLeft |

**Every mutation caught by a new test, none by a build error: yes.**
