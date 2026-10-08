"""Known private credential values retained for participant export redaction."""

def credential_values(value):
    """Known runtime secrets for report redaction; retained only in private state."""
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if (isinstance(item, str) and len(item) >= 4
                    and (normalized.endswith("token") or any(word in normalized for word in
                         ("apikey", "password", "secret", "authorization")))):
                found.add(item)
            if isinstance(item, (dict, list)):
                found.update(credential_values(item))
    elif isinstance(value, list):
        for item in value:
            found.update(credential_values(item))
    return found
