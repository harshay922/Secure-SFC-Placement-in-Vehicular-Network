import config


class MigrationQueues:
    """Virtual migration-cost queue Q_i(t) per RSU (eq. 20)."""

    def __init__(self, n):
        self.Q = [0.0] * n

    def update(self, R):                   # R[i] = migration cost charged to RSU i this slot
        self.Q = [max(q + r - config.MIG_BUDGET_C, 0.0) for q, r in zip(self.Q, R)]

    def drift_term(self, R):               # sum_i Q_i (R_i - C)   (eq. 30 / 32)
        return sum(q * (r - config.MIG_BUDGET_C) for q, r in zip(self.Q, R))

    def objective(self, R, delay):         # eq. 31 drift-plus-penalty (constant zeta dropped)
        return self.drift_term(R) + config.DELTA * delay

    def lyapunov(self):                    # eq. 26
        return 0.5 * sum(q * q for q in self.Q)
