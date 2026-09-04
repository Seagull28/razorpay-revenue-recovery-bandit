"""
test_recovery_action.py
Focused unit tests for the RecoveryAction domain abstraction (Step 1).
Verifies structural construction, attribute preservation, immutability,
equality/hashing, dictionary serialization, and structural validation rules.
"""

import pytest
from dataclasses import FrozenInstanceError
from bandit_retry_scheduler.core.recovery_action import RecoveryAction


class TestRecoveryActionAbstraction:
    """Test suite evaluating the RecoveryAction value object."""

    def test_timed_retry_action_construction(self):
        """Verify construction and attribute preservation for a timed retry action."""
        action = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )

        assert action.action_id == "same_method_1d"
        assert action.action_type == "TIMED_RETRY"
        assert action.source_method == "card"
        assert action.target_method == "card"
        assert action.delay == "1d"

    def test_method_switch_action_construction(self):
        """Verify construction and attribute preservation for a method switch action."""
        action = RecoveryAction(
            action_id="switch_to_upi",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="upi",
            delay="0",
        )

        assert action.action_id == "switch_to_upi"
        assert action.action_type == "METHOD_SWITCH"
        assert action.source_method == "card"
        assert action.target_method == "upi"
        assert action.delay == "0"

    def test_action_distinguishability_and_equality(self):
        """Verify that two actions with different action_ids remain distinguishable and equal when identical."""
        action_a = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )
        action_a_copy = RecoveryAction(
            action_id="same_method_1d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="1d",
        )
        action_b = RecoveryAction(
            action_id="same_method_3d",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="3d",
        )

        # Equality checks
        assert action_a == action_a_copy
        assert action_a != action_b

        # Hashability checks (usable in sets and dictionary keys)
        action_set = {action_a, action_b}
        assert len(action_set) == 2
        assert action_a_copy in action_set

    def test_action_immutability(self):
        """Verify that RecoveryAction is immutable and raises FrozenInstanceError on attribute mutation."""
        action = RecoveryAction(
            action_id="same_method_6hr",
            action_type="TIMED_RETRY",
            source_method="card",
            target_method="card",
            delay="6hr",
        )

        with pytest.raises(FrozenInstanceError):
            action.delay = "1d"

        with pytest.raises(FrozenInstanceError):
            action.action_id = "mutated_id"

    def test_to_dict_and_from_dict_roundtrip(self):
        """Verify serialization and deserialization via to_dict() and from_dict()."""
        original = RecoveryAction(
            action_id="switch_to_netbanking",
            action_type="METHOD_SWITCH",
            source_method="card",
            target_method="netbanking",
            delay="0",
        )

        serialized = original.to_dict()
        assert serialized == {
            "action_id": "switch_to_netbanking",
            "action_type": "METHOD_SWITCH",
            "source_method": "card",
            "target_method": "netbanking",
            "delay": "0",
        }

        reconstructed = RecoveryAction.from_dict(serialized)
        assert reconstructed == original

    @pytest.mark.parametrize(
        "action_id, action_type, source_method, target_method, delay, expected_exception",
        [
            ("", "TIMED_RETRY", "card", "card", "1d", ValueError),
            ("   ", "TIMED_RETRY", "card", "card", "1d", ValueError),
            (123, "TIMED_RETRY", "card", "card", "1d", ValueError),
            ("act_1", "", "card", "card", "1d", ValueError),
            ("act_1", "TIMED_RETRY", "", "card", "1d", ValueError),
            ("act_1", "TIMED_RETRY", "card", "", "1d", ValueError),
            ("act_1", "TIMED_RETRY", "card", "card", "", ValueError),
            ("act_1", "TIMED_RETRY", "card", "card", None, ValueError),
        ],
    )
    def test_structural_validation_failures(
        self, action_id, action_type, source_method, target_method, delay, expected_exception
    ):
        """Verify structural validation fails clearly on invalid/empty inputs."""
        with pytest.raises(expected_exception):
            RecoveryAction(
                action_id=action_id,
                action_type=action_type,
                source_method=source_method,
                target_method=target_method,
                delay=delay,
            )
