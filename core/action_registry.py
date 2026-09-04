"""
action_registry.py
Deterministic Action Registry for RecoverFlow V2.

=============================================================================
SYNTHETIC V2 SIMULATION ACTION VOCABULARY NOTICE:
=============================================================================
The recovery actions defined in this registry represent a synthetic V2 simulation
action vocabulary introduced strictly for architectural research and experimentation.
They do NOT represent confirmed Razorpay production payment rails, live payment API
integrations, or production recovery SLA guarantees.
=============================================================================
"""

from typing import Dict, Tuple
from bandit_retry_scheduler.core.recovery_action import RecoveryAction


class ActionRegistry:
    """
    Deterministic registry defining concrete V2 recovery actions.
    
    Provides static lookup and source-method candidate filtering without inspecting
    transaction-level context features (failure codes, banks, amounts, attempt numbers, etc.).
    SINGLE SOURCE OF TRUTH for all registered V2 actions across payment channels.
    """

    def __init__(self) -> None:
        # Define synthetic V2 recovery actions across payment channels in deterministic order
        self._actions_list: Tuple[RecoveryAction, ...] = (
            # --- 1. Card Source Actions ---
            RecoveryAction(
                action_id="same_method_1d",
                action_type="TIMED_RETRY",
                source_method="card",
                target_method="card",
                delay="1d",
            ),
            RecoveryAction(
                action_id="same_method_3d",
                action_type="TIMED_RETRY",
                source_method="card",
                target_method="card",
                delay="3d",
            ),
            RecoveryAction(
                action_id="same_method_7d",
                action_type="TIMED_RETRY",
                source_method="card",
                target_method="card",
                delay="7d",
            ),
            RecoveryAction(
                action_id="switch_to_upi",
                action_type="METHOD_SWITCH",
                source_method="card",
                target_method="upi",
                delay="0",
            ),
            RecoveryAction(
                action_id="switch_to_netbanking",
                action_type="METHOD_SWITCH",
                source_method="card",
                target_method="netbanking",
                delay="0",
            ),
            RecoveryAction(
                action_id="switch_to_card",
                action_type="METHOD_SWITCH",
                source_method="card",
                target_method="card",
                delay="0",
            ),
            # --- 2. UPI Source Actions ---
            RecoveryAction(
                action_id="upi_same_method_1d",
                action_type="TIMED_RETRY",
                source_method="upi",
                target_method="upi",
                delay="1d",
            ),
            RecoveryAction(
                action_id="upi_same_method_3d",
                action_type="TIMED_RETRY",
                source_method="upi",
                target_method="upi",
                delay="3d",
            ),
            RecoveryAction(
                action_id="upi_same_method_7d",
                action_type="TIMED_RETRY",
                source_method="upi",
                target_method="upi",
                delay="7d",
            ),
            RecoveryAction(
                action_id="upi_switch_to_card",
                action_type="METHOD_SWITCH",
                source_method="upi",
                target_method="card",
                delay="0",
            ),
            RecoveryAction(
                action_id="upi_switch_to_netbanking",
                action_type="METHOD_SWITCH",
                source_method="upi",
                target_method="netbanking",
                delay="0",
            ),
            # --- 3. Netbanking Source Actions ---
            RecoveryAction(
                action_id="nb_same_method_1d",
                action_type="TIMED_RETRY",
                source_method="netbanking",
                target_method="netbanking",
                delay="1d",
            ),
            RecoveryAction(
                action_id="nb_same_method_3d",
                action_type="TIMED_RETRY",
                source_method="netbanking",
                target_method="netbanking",
                delay="3d",
            ),
            RecoveryAction(
                action_id="nb_same_method_7d",
                action_type="TIMED_RETRY",
                source_method="netbanking",
                target_method="netbanking",
                delay="7d",
            ),
            RecoveryAction(
                action_id="nb_switch_to_card",
                action_type="METHOD_SWITCH",
                source_method="netbanking",
                target_method="card",
                delay="0",
            ),
            RecoveryAction(
                action_id="nb_switch_to_upi",
                action_type="METHOD_SWITCH",
                source_method="netbanking",
                target_method="upi",
                delay="0",
            ),
        )

        # Build stable lookup index by action_id
        self._actions_by_id: Dict[str, RecoveryAction] = {
            act.action_id: act for act in self._actions_list
        }

    def get_all_actions(self) -> Tuple[RecoveryAction, ...]:
        """
        Returns all registered V2 recovery actions in deterministic order.
        Returns an immutable tuple to preserve registry isolation.
        """
        return self._actions_list

    def get_candidates(self, source_method: str) -> Tuple[RecoveryAction, ...]:
        """
        Returns candidate recovery actions valid for the supplied source payment method.
        
        Applies static semantic action-definition filtering:
        1. Filters actions where action.source_method matches source_method.
        2. Excludes redundant method-switch actions where action_type == 'METHOD_SWITCH'
           and target_method == source_method (e.g. switch_to_card when source_method is 'card').
        
        Does NOT inspect transaction-level eligibility context features.
        Every returned action is a pre-registered instance from ActionRegistry.
        """
        candidates = []
        for act in self._actions_list:
            if act.source_method != source_method:
                continue
            # Exclude non-meaningful method switches where target equals source
            if act.action_type == "METHOD_SWITCH" and act.target_method == source_method:
                continue
            candidates.append(act)

        return tuple(candidates)

    def get_action(self, action_id: str) -> RecoveryAction:
        """
        Retrieves a registered RecoveryAction by its stable action_id.
        Raises KeyError if the action_id is not registered.
        """
        if action_id not in self._actions_by_id:
            raise KeyError(f"Action '{action_id}' is not registered in ActionRegistry.")
        return self._actions_by_id[action_id]
