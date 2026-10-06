# WHAT THIS FILE DOES: keeps the Lyapunov "virtual queues" Q_i (eq. 20), one per RSU,
#   and computes the drift-plus-penalty score (eq. 31) used to judge migrations.
# WHY WE NEED IT: migration lowers delay but costs money. Q_i is a "debt counter" that grows
#   when RSU i spends more than budget C on migration, so the algorithm stops overspending
#   in the long run without needing to know the future.
# WHO CALLS IT: simulator.py creates one MigrationQueues object (s.queues) and calls update()
#   once per slot; vima.py calls objective() to score every candidate set of moves.

import config  # our parameter file: MIG_BUDGET_C (budget C) and DELTA (delay weight) live there


class MigrationQueues:
    # "class" defines a new type of object. Each object bundles data (here self.Q) and
    # functions that work on it (called methods). "self" = the object the method is called on.
    """Virtual migration-cost queue Q_i(t) per RSU (eq. 20)."""

    def __init__(self, n):
        # __init__ runs automatically when the object is created: MigrationQueues(n).
        # n = number of RSUs.
        self.Q = [0.0] * n                 # list of n zeros: every RSU starts with zero debt

    def update(self, R):                   # R[i] = migration cost charged to RSU i this slot
        # eq. 20: Q_i(t+1) = max(Q_i(t) + R_i(t) - C, 0).
        # Spend more than C -> debt grows. Spend less -> debt shrinks. Never below 0.
        # This line is a list comprehension: [expr for items in iterable] builds a new list.
        # zip(self.Q, R) walks two lists side by side, giving pairs (q, r) = (Q_i, R_i).
        self.Q = [max(q + r - config.MIG_BUDGET_C, 0.0) for q, r in zip(self.Q, R)]

    def drift_term(self, R):               # sum_i Q_i (R_i - C)   (eq. 30 / 32)
        # Upper-bound part of the Lyapunov drift: how much this slot's spending R
        # would push the debts up. Big existing debt Q_i makes more spending at RSU i look worse.
        return sum(q * (r - config.MIG_BUDGET_C) for q, r in zip(self.Q, R))

    def objective(self, R, delay):         # eq. 31 drift-plus-penalty (constant zeta dropped)
        # eq. 31: sum_i Q_i (R_i - C) + delta * delay. LOWER is better.
        # First part: penalty for overspending on migration. Second part: service delay.
        # DELTA sets the trade-off (larger DELTA -> care more about delay).
        # We use eq. 31, not eq. 32: eq. 32 drops the delay term, so a migration could never
        # look beneficial (it only adds cost). Keeping delay lets a move "pay for itself".
        # The constant zeta in the paper is the same for every choice, so it is dropped.
        return self.drift_term(R) + config.DELTA * delay

    def lyapunov(self):                    # eq. 26
        # eq. 26: L = 1/2 * sum Q_i^2. One number for "total debt size"; used for reporting.
        return 0.5 * sum(q * q for q in self.Q)
