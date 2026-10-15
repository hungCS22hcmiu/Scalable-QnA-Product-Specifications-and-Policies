# Hand mutants of `build_pqa.py` (plan step 10, repeated after `/ai-review`)

**Final run:** 2026-10-15, on the final builder and the final tests. Each row is ONE small edit to
`experiments/scripts/build_pqa.py`; the whole of `experiments/tests/test_build_pqa.py` (103 tests) runs after it;
the original is restored every time (checked byte for byte at the end). A mutant that survives means a test is
missing. A mutant whose snippet no longer matches is reported as NOT APPLIED and counted as a failure, so the
suite cannot rot into no-ops. Reproduce with `python3 evidence/mutants.py <repo root>`.

## History of this file (nothing here was written after the fact)

| Run | Mutants | Caught | What it showed |
| :--- | ---: | ---: | :--- |
| Step 10, first run | 40 | 39 | Survivor: the long-file check of Stop 0 (the hash still refused the file, but with the false message "has the pinned size"). A test was added |
| Step 10, second run | 40 | 40 | |
| After the report lines were added | 45 | 44, then 45 | Survivor: the label of the shared-asins line was not asserted. Tightened |
| `/ai-review`, by the reviewer | 48 | 44 | Four survivors: `build()` ignored `check_output`, never called it, or raised only on some stops. **None of my 40 touched `build()`'s wiring or `leaf_entry`**, so "every mutant is caught" had overstated what was tested (review finding 5) |
| **Final run (this file)** | **75** | **75** | The 4 wiring mutants, the manifest-field mutants, the guards, the round trip and the up-front Stop 0 were added, with tests for each. Two round-trip mutants survived once more ("repeated asin", "missing products") because the aggregate pins cover the same cases at build level; direct tests of `check_round_trip` were added |

Test names are cut to the first three per mutant; "caught by N" counts all.

| # | Mutant | Result |
| :-: | :--- | :--- |
| 1 | bullets: range(1, 5) instead of (1, 6) | caught by 53: test_a_clean_fixture_parses_fully, test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2] ... |
| 2 | parser swaps question_type and answer_aggregated | caught by 33: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] ... |
| 3 | product re-created on every record (last record wins) | caught by 33: test_a_clean_fixture_parses_fully, test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2] ... |
| 4 | blank question_text no longer skipped | caught by 3: test_every_line_is_parsed_or_skipped_for_a_named_reason, test_product_fields_come_from_the_first_parsed_record_not_the_first_line, test_the_build_prints_why_lines_were_skipped |
| 5 | empty asin no longer skipped | caught by 1: test_every_line_is_parsed_or_skipped_for_a_named_reason |
| 6 | surrogates are not replaced | caught by 14: test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[answer_text-high], test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[answer_text-low], test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[asin-high] ... |
| 7 | low surrogates (DC00-DFFF) not covered by the pattern | caught by 6: test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[answer_text-low], test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[asin-low], test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[brand_name-low] ... |
| 8 | the asin is not cleaned of surrogates | caught by 2: test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[asin-high], test_a_lone_surrogate_in_any_text_field_is_replaced_and_the_file_is_writable[asin-low] |
| 9 | a non-string field is coerced with str() | caught by 2: test_a_non_string_field_is_counted_not_coerced, test_the_manifest_counts_equal_hand_counted_numbers |
| 10 | line_no starts at 0 | caught by 2: test_line_no_counts_every_source_line_including_skipped_ones, test_the_interim_is_sorted_by_asin_and_carries_leaf_and_department |
| 11 | duplicate question ids not counted | caught by 2: test_duplicate_question_ids_are_counted_and_kept, test_the_manifest_counts_equal_hand_counted_numbers |
| 12 | key census not kept | caught by 6: test_build_stops_on_an_unlisted_key_and_writes_nothing, test_build_stops_on_readme_field_names_and_writes_nothing, test_stop_1_readme_field_names_parse_zero_and_the_message_names_the_field ... |
| 13 | first parsed record no longer wins (prose conflicts not seen) | caught by 2: test_product_fields_come_from_the_first_parsed_record_not_the_first_line, test_the_manifest_counts_equal_hand_counted_numbers |
| 14 | bytes lines replaced by str.splitlines() | caught by 1: test_every_line_is_parsed_or_skipped_for_a_named_reason |
| 15 | invalid UTF-8 raises instead of being counted | caught by 1: test_every_line_is_parsed_or_skipped_for_a_named_reason |
| 16 | Stop 1 never trips | caught by 3: test_build_stops_on_readme_field_names_and_writes_nothing, test_stop_1_an_empty_file_stops, test_stop_1_readme_field_names_parse_zero_and_the_message_names_the_field |
| 17 | Stop 2(a) never trips | caught by 3: test_build_stops_on_misnamed_bullets_and_writes_nothing, test_stop_2a_a_field_empty_in_every_record_stops, test_stop_2a_misnamed_bullets_pass_stop_1_but_not_stop_2 |
| 18 | Stop 2(b) never trips | caught by 2: test_build_stops_on_an_unlisted_key_and_writes_nothing, test_stop_2b_a_key_outside_the_real_set_stops_and_is_named |
| 19 | Stop 3 input: skipped pin removed | caught by 1: test_stop_3_a_wrong_parsed_products_or_skipped_count_stops |
| 20 | Stop 3 input: products pin removed | caught by 1: test_stop_3_a_wrong_parsed_products_or_skipped_count_stops |
| 21 | Stop 3 output: prose_median pin removed | caught by 3: test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin2], test_stop_3_catches_a_writer_that_drops_the_fifth_bullet, test_stop_3_catches_a_writer_that_empties_the_description |
| 22 | Stop 3 output: question_type pin removed | caught by 2: test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin0], test_stop_3_catches_a_writer_that_swaps_question_type_and_answer_aggregated |
| 23 | Stop 3 output: answer_aggregated pin removed | caught by 2: test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin1], test_stop_3_catches_a_writer_that_swaps_question_type_and_answer_aggregated |
| 24 | Stop 0: hash check disabled | caught by 2: test_stop_0_a_changed_byte_of_the_same_size_is_caught, test_stop_0_a_full_size_file_with_a_wrong_hash_says_to_delete_it |
| 25 | Stop 0: short-file check disabled | caught by 1: test_stop_0_a_short_file_is_a_partial_download_and_says_to_resume |
| 26 | Stop 0: long-file check disabled | caught by 1: test_stop_0_a_longer_file_says_it_is_longer_and_to_delete_it |
| 27 | build: Stop 0 skipped altogether | caught by 3: test_a_source_mismatch_stops_before_any_parsing, test_every_source_is_checked_before_any_leaf_is_parsed, test_the_command_line_exits_2_and_writes_nothing_when_the_sources_are_missing |
| 28 | build: Stop 0 per leaf, after earlier leaves were parsed | caught by 1: test_every_source_is_checked_before_any_leaf_is_parsed |
| 29 | build: input checks (Stops 1, 2, 3 input) skipped | caught by 3: test_build_stops_on_an_unlisted_key_and_writes_nothing, test_build_stops_on_misnamed_bullets_and_writes_nothing, test_build_stops_on_readme_field_names_and_writes_nothing |
| 30 | build: raises only on a Stop 3 failure of the input | caught by 3: test_build_stops_on_an_unlisted_key_and_writes_nothing, test_build_stops_on_misnamed_bullets_and_writes_nothing, test_build_stops_on_readme_field_names_and_writes_nothing |
| 31 | build: never raises on a Stop 1 failure | caught by 1: test_build_stops_on_readme_field_names_and_writes_nothing |
| 32 | build: never raises on a Stop 2 failure | caught by 2: test_build_stops_on_an_unlisted_key_and_writes_nothing, test_build_stops_on_misnamed_bullets_and_writes_nothing |
| 33 | build: aggregate output pins skipped | caught by 3: test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin0], test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin1], test_build_stops_when_consistent_data_contradicts_an_aggregate_pin[pin2] |
| 34 | build: field-by-field round trip skipped | caught by 7: test_build_stops_on_any_field_the_writer_changes[_blank_brand], test_build_stops_on_any_field_the_writer_changes[_blank_question_text], test_build_stops_on_any_field_the_writer_changes[_keep_one_answer] ... |
| 35 | round trip: digest comparison disabled | caught by 7: test_build_stops_on_any_field_the_writer_changes[_blank_brand], test_build_stops_on_any_field_the_writer_changes[_blank_question_text], test_build_stops_on_any_field_the_writer_changes[_keep_one_answer] ... |
| 36 | round trip: unknown asin not noticed | caught by 1: test_build_stops_on_any_field_the_writer_changes[_rename_the_asin] |
| 37 | round trip: repeated asin not noticed | caught by 1: test_the_round_trip_notices_a_repeated_product_line |
| 38 | round trip: missing products not noticed | caught by 1: test_the_round_trip_notices_a_missing_product |
| 39 | digest ignores the questions | caught by 3: test_build_stops_on_any_field_the_writer_changes[_blank_question_text], test_build_stops_on_any_field_the_writer_changes[_keep_one_answer], test_build_stops_on_any_field_the_writer_changes[_shift_line_numbers] |
| 40 | digest taken after the writer ran | caught by 34: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] ... |
| 41 | writer swaps the department for the leaf | caught by 35: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] ... |
| 42 | writer iterates a set (hash-seed order) | caught by 3: test_iter_interim_yields_every_product_in_manifest_order, test_the_interim_is_sorted_by_asin_and_carries_leaf_and_department, test_two_builds_under_different_hash_seeds_are_byte_identical |
| 43 | writer iterates in file order (no sort) | caught by 1: test_the_interim_is_sorted_by_asin_and_carries_leaf_and_department |
| 44 | writer hash ignores the data | caught by 10: test_a_good_build_round_trips_every_field_through_the_interim_file, test_a_good_build_writes_the_interim_files_and_the_manifest, test_build_and_verify_print_the_sha256_of_the_manifest_file ... |
| 45 | manifest replaced BEFORE the interim swap | caught by 1: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] |
| 46 | rollback does not restore the old directory | caught by 2: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] |
| 47 | stale temp dirs not removed | caught by 1: test_stale_temp_directories_from_a_crashed_run_are_removed |
| 48 | work dir not cleaned after a failure | caught by 21: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] ... |
| 49 | build swallows unexpected errors | caught by 4: test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[1], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[2], test_a_failure_during_the_swap_leaves_the_old_files_and_the_old_manifest[3] ... |
| 50 | the stale-product warning is not issued | caught by 1: test_the_stale_files_of_the_retired_script_are_reported_on_every_build |
| 51 | manifest stage changed | caught by 14: test_a_good_build_round_trips_every_field_through_the_interim_file, test_a_good_build_writes_the_interim_files_and_the_manifest, test_a_rebuild_replaces_the_previous_interim_files_and_manifest ... |
| 52 | cross_leaf uses union | caught by 3: test_a_good_build_writes_the_interim_files_and_the_manifest, test_the_build_prints_the_counts_a_human_should_look_at, test_two_builds_under_different_hash_seeds_are_byte_identical |
| 53 | distinct total is the sum | caught by 2: test_a_good_build_writes_the_interim_files_and_the_manifest, test_the_build_prints_the_counts_a_human_should_look_at |
| 54 | builder hash is not recorded correctly | caught by 1: test_the_manifest_carries_the_builder_hash_and_no_pqa_text |
| 55 | manifest: lines_read zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 56 | manifest: prose_median_chars zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 57 | manifest: question_type emptied | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 58 | manifest: answer_aggregated emptied | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 59 | manifest: bad_type emptied | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 60 | manifest: answers_bad zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 61 | manifest: prose_conflicts zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 62 | manifest: duplicate_question_ids zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 63 | manifest: surrogate_replacements zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 64 | manifest: field_nonempty zeroed | caught by 1: test_the_manifest_counts_equal_hand_counted_numbers |
| 65 | manifest: skip reasons zeroed | caught by 2: test_the_build_prints_why_lines_were_skipped, test_the_manifest_counts_equal_hand_counted_numbers |
| 66 | iter_interim does not verify first | caught by 3: test_iter_interim_raises_before_yielding_when_any_file_was_changed, test_iter_interim_raises_on_a_cut_short_file, test_iter_interim_raises_on_a_missing_file |
| 67 | load_manifest: stage guard removed | caught by 1: test_load_manifest_rejects_a_wrong_stage_and_a_wrong_version |
| 68 | load_manifest: version guard removed | caught by 1: test_load_manifest_rejects_a_wrong_stage_and_a_wrong_version |
| 69 | verify warns never (builder drift silent) | caught by 1: test_verify_only_warns_when_the_builder_script_changed |
| 70 | --verify falls through to a rebuild | caught by 1: test_verify_does_not_rebuild_a_missing_interim_file |
| 71 | build does not print the manifest hash | caught by 1: test_build_and_verify_print_the_sha256_of_the_manifest_file |
| 72 | verify prints a wrong manifest hash | caught by 1: test_build_and_verify_print_the_sha256_of_the_manifest_file |
| 73 | report no longer lists skip reasons | caught by 1: test_the_build_prints_why_lines_were_skipped |
| 74 | report no longer lists shared asins | caught by 1: test_the_build_prints_the_counts_a_human_should_look_at |
| 75 | report drops the prose_conflicts column | caught by 1: test_the_build_prints_the_counts_a_human_should_look_at |

75 of 75 caught. Survived or not applied: none
