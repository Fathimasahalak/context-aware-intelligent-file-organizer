COLORS = {
    "very_high": "#C8E6C9",   # pastel green
    "high": "#BBDEFB",        # pastel blue
    "medium": "#FFF9C4",      # pastel yellow
    "low": "#F8BBD0"          # pastel pink
}


def get_color(score):
    if score >= 0.75:
        return COLORS["very_high"]
    elif score >= 0.5:
        return COLORS["high"]
    elif score >= 0.25:
        return COLORS["medium"]
    else:
        return COLORS["low"]
