"""
test_action_registry.py
Focused unit tests for the V2 ActionRegistry (Step 2 & 3C).
Verifies registration, stable IDs, action semantics, candidate filtering for all source channels,
deterministic ordering, lookup, KeyError handling, and registry isolation.
"""

import pytest
from bandit_retry_scheduler.core.action_registry import ActionRegistry
from bandit_retry_scheduler.core.recovery_action import RecoveryAction


class TestActionRegistry:
    """Test suite evaluating the V2 ActionRegistry."""

    def test_registration_count_types_and_uniqueness(self):
        """Verify exactly 16 V2 actions exist across channels, all are RecoveryAction, and all IDs are unique."""
        registry = ActionRegistry()
        actions = registry.get_all_actions()

        assert len(actions) == 16
        assert all(isinstance(act, RecoveryAction) for act in actions)

        action_ids = [act.action_id for act in actions]
        assert len(action_ids) == len(set(action_ids)), "Action IDs must be unique."

    def test_stable_card_action_ids(self):
        """Verify the exact stable card action IDs defined in V2 specification."""
        registry = ActionRegistry()
        expected_card_ids = (
            "same_method_1d",
            "same_method_3d",
            "same_method_7d",
            "switch_to_upi",
            "switch_to_netbanking",
            "switch_to_card",
        )

        all_ids = tuple(act.action_id for act in registry.get_all_actions())
        for expected_id in expected_card_ids:
            assert expected_id in all_ids

    def test_action_semantics_definitions(self):
        """Verify registered semantic properties for sample actions across channels."""
        registry = ActionRegistry()

        act_1d = registry.get_action("same_method_1d")
        assert act_1d.action_type == "TIMED_RETRY"
        assert act_1d.source_method == "card"
        assert act_1d.target_method == "card"
        assert act_1d.delay == "1d"

        act_upi = registry.get_action("switch_to_upi")
        assert act_upi.action_type == "METHOD_SWITCH"
        assert act_upi.source_method == "card"
        assert act_upi.target_method == "upi"
        assert act_upi.delay == "0"

        act_upi_retry = registry.get_action("upi_same_method_1d")
        assert act_upi_retry.action_type == "TIMED_RETRY"
        assert act_upi_retry.source_method == "upi"
        assert act_upi_retry.target_method == "upi"
        assert act_upi_retry.delay == "1d"

        act_nb_switch = registry.get_action("nb_switch_to_upi")
        assert act_nb_switch.action_type == "METHOD_SWITCH"
        assert act_nb_switch.source_method == "netbanking"
        assert act_nb_switch.target_method == "upi"
        assert act_nb_switch.delay == "0"

    def test_candidate_filtering_for_card_source_method(self):
        """
        Verify get_candidates('card') returns 5 candidates and excludes switch_to_card.
        """
        registry = ActionRegistry()
        candidates = registry.get_candidates("card")

        candidate_ids = tuple(act.action_id for act in candidates)
        expected_ids = (
            "same_method_1d",
            "same_method_3d",
            "same_method_7d",
            "switch_to_upi",
            "switch_to_netbanking",
        )

        assert candidate_ids == expected_ids
        assert "switch_to_card" not in candidate_ids

    def test_candidate_filtering_for_upi_source_method(self):
        """Verify get_candidates('upi') returns 5 candidates and excludes upi_switch_to_upi."""
        registry = ActionRegistry()
        candidates = registry.get_candidates("upi")

        candidate_ids = tuple(act.action_id for act in candidates)
        expected_ids = (
            "upi_same_method_1d",
            "upi_same_method_3d",
            "upi_same_method_7d",
            "upi_switch_to_card",
            "upi_switch_to_netbanking",
        )

        assert candidate_ids == expected_ids

    def test_candidate_filtering_unsupported_source_method(self):
        """Verify get_candidates returns empty tuple for source methods without registered actions."""
        registry = ActionRegistry()
        candidates = registry.get_candidates("crypto")
        assert candidates == ()

    def test_lookup_valid_and_unknown_action_ids(self):
        """Verify get_action returns exact action object for valid ID and raises KeyError for unknown ID."""
        registry = ActionRegistry()

        action = registry.get_action("switch_to_upi")
        assert action.action_id == "switch_to_upi"
        assert action.target_method == "upi"

        with pytest.raises(KeyError) as exc_info:
            registry.get_action("unknown_action_xyz")

        assert "unknown_action_xyz" in str(exc_info.value)

    def test_registry_isolation_and_immutability(self):
        """Verify that returned collections are tuples and internal registry state cannot be mutated."""
        registry = ActionRegistry()
        actions = registry.get_all_actions()
        candidates = registry.get_candidates("card")

        assert isinstance(actions, tuple)
        assert isinstance(candidates, tuple)
