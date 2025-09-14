import uuid

def generate_id(type_: str, class_name: str) -> str:
    """
    Generate an ID string based on the specified type and class name.
    type_: 'n' (node), 'e' (edge), 'w' (walker), 'o' (object)
    class_name: Name of the class (e.g., 'City', 'Highway')
    """
    hex_id = uuid.uuid4().hex[:24]
    return f"{type_}:{class_name}:{hex_id}"