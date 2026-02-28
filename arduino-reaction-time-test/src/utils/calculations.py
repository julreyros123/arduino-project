def calculate_reaction_time(start_time, end_time):
    """Calculate the reaction time in seconds."""
    return end_time - start_time

def average_reaction_time(reaction_times):
    """Calculate the average reaction time from a list of reaction times."""
    if not reaction_times:
        return 0
    return sum(reaction_times) / len(reaction_times)

def min_reaction_time(reaction_times):
    """Return the minimum reaction time from a list of reaction times."""
    if not reaction_times:
        return None
    return min(reaction_times)

def max_reaction_time(reaction_times):
    """Return the maximum reaction time from a list of reaction times."""
    if not reaction_times:
        return None
    return max(reaction_times)