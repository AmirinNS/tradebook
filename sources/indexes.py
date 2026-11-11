"""Database index management across application modules."""

import modules.imports as imports
import modules.portfolios as portfolios
import modules.prices as prices
import modules.progress as progress
import modules.screener as screener
import modules.trades as trades
import modules.users as users


def ensure_all_indexes(db):
    """Ensure indexes across all modules."""
    users.ensure_indexes(db)
    prices.ensure_indexes(db)
    portfolios.ensure_indexes(db)
    trades.ensure_indexes(db)
    imports.ensure_indexes(db)
    screener.ensure_indexes(db)
    progress.ensure_indexes(db)


# Alias for callers expecting ensure_indexes
ensure_indexes = ensure_all_indexes
