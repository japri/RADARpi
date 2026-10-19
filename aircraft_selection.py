"""Selection retains a locked identity across temporary feed gaps."""
def resolve_selection(rows,selected,locked_target):
    target=locked_target if locked_target is not None else selected
    fallback=None if locked_target is not None else (rows[0] if rows else None)
    current=next((row for row in rows if row.get('hex')==target),fallback)
    return current, (locked_target if locked_target is not None else current.get('hex') if current else None)
