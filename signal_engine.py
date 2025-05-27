# signal_engine.py

from typing import List, Dict
from market_context import get_market_context  # Or your real-time data functions

def generate_alerts_for_symbol(symbol: str) -> List[str]:
    alerts = []
    context = get_market_context(f"${symbol}")
    
    if "Funding Rate" in context and "Long/Short" in context:
        # Example: Add funding warning
        if "0." in context and "Funding Rate" in context:
            alerts.append(f"{symbol}: Elevated funding detected. Watch for potential squeeze setups.")

    if "Fear" in context and "Greed" in context:
        alerts.append(f"{symbol}: Market sentiment extreme. Traders should proceed with caution.")

    # Add your custom logic here...
    # This is just a placeholder logic — you'll want to extract real metrics from parsed JSON or API calls.

    return alerts
