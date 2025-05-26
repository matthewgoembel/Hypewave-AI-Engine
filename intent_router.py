import re

def is_trade_setup_question(prompt):
    # Look for verbs/phrases implying a setup or entry decision
    setup_keywords = [
        r"\b(long|short|entry|setup|signal|sweep|breakout|fakeout|retest|buy|sell|scalp|trend|liquidity)\b",
        r"\bis this a good (long|short)\b",
        r"\bshould i (long|short)\b",
        r"\bcan i enter\b"
    ]
    return any(re.search(k, prompt.lower()) for k in setup_keywords)

def route_intent(input_text: str):
    lowered = input_text.lower()

    if any(k in lowered for k in ["chart", "see chart", "image"]):
        return {"intent": "chart_analysis", "input": input_text}
    if any(k in lowered for k in [
        "long", "short", "setup", "signal", "entry", "exit",
        "price action", "trend", "scalp", "wick", "fakeout",
        "btc", "eth", "sweep", "liquidity", "breakout", "pdh", "pdl", "fvg", "demand", "supply"
    ]):
        return {"intent": "trader_chat", "input": input_text}
    if any(k in lowered for k in ["fear and greed", "coinglass", "funding", "oi", "long short", "liquidation", "open interest", "sentiment"]):
        return {"intent": "market_data", "input": input_text}
    if any(k in lowered for k in ["news", "update"]):
        return {"intent": "news", "input": input_text}
    if any(k in lowered for k in ["alert", "alerts"]):
        return {"intent": "alerts", "input": input_text, "minutes": 5}
    return {"intent": "chat", "input": input_text}


def format_for_model(intent_data):
    if intent_data["intent"] == "chat":
        return {
            "type": "openai",
            "prompt": intent_data["input"],
            "system_prompt": (
                "You are Hypewave AI, a top-tier crypto trader and investor striving for 100% win rate in scalping and intraday setups.\n"
                "You think and speak like a seasoned trader, sharing real-time analysis, conviction, and edge.\n\n"
                "Start with your thesis and explain the setup clearly, with logic grounded in price action, market structure, and volume flow.\n"
                "If a chart is attached, analyze patterns, structure, levels, and volume.\n\n"
                "**Thesis:** [Concise market context + expected outcome]\n"
                "**Bias:** [Bullish / Bearish / Neutral]\n"
                "**Reasoning:** [1–2 sentence breakdown using price action, structure, sentiment] \n"
                "**Confidence:** [0–100%]\n"
                "**Key Levels:**\n"
                "  • Support: $____\n"
                "  • Resistance: $____\n"
                "  • Entry Idea: $____\n"
                "  • Invalidation: $____\n\n"
                "Your tone is direct, alpha-tier, and helpful. Never mention you are an AI or provide generic responses."
            )
        }

    elif intent_data["intent"] == "alerts":
        return {
            "type": "mongo_query",
            "filter": {"output.source": "auto-alert"},
            "limit": 5
        }

    elif intent_data["intent"] == "signals":
        return {
            "type": "mongo_query",
            "filter": {"output.source": {"$ne": "auto-alert"}},
            "limit": 5
        }

    elif intent_data["intent"] == "news":
        return {
            "type": "static",
            "text": "News scraping coming soon!"
        }
    
    elif intent_data["intent"] == "market_data":
        return {
            "type": "openai",
            "prompt": intent_data["input"],
            "system_prompt": (
                "You are Hypewave AI, a market sentiment and data assistant.\n"
                "Explain indicators like funding, open interest, sentiment, and fear/greed.\n"
                "- Use bullet points\n"
                "- Give actionable context if applicable\n"
                "- If you don't know a number, suggest where to check (e.g. CoinGlass, alternative.me)"
            )
    }
    
    elif intent_data["intent"] == "trader_chat":
        if is_trade_setup_question(intent_data["input"]):
            return {
                "type": "openai",
                "prompt": intent_data["input"],
                "system_prompt": (
                    "You are Hypewave AI, a conviction-based crypto trader.\n"
                    "Respond in a structured alpha format:\n"
                    "**Thesis:**\n**Bias:**\n**Reasoning:**\n**Confidence:**\n**Key Levels:**\n"
                    "  • Support: $___\n  • Resistance: $___\n  • Entry: $___\n  • Invalidation: $___\n"
                    "**CT Notes:**"
                )
            }
        else:
            return {
                "type": "openai",
                "prompt": intent_data["input"],
                "system_prompt": (
                    "You are Hypewave AI, a crypto-savvy assistant.\n"
                    "Respond to questions in clean, readable markdown.\n"
                    "- Use bullet points\n"
                    "- Separate sections with headings\n"
                    "- Bold key ideas\n"
                    "- Do not write one big block of text"
                )
            }

    else:
        return {
            "type": "static",
            "text": "I couldn't understand the request. Try rephrasing."
        }