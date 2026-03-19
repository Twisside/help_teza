import os

class FileManager:
    def __init__(self, base_path=None):
        # Default to the current project directory if no path is provided
        self.base_path = base_path or os.path.abspath(os.path.dirname(__file__))

    def get_directory_json(self, current_path=None):
        """
        Recursively builds a nested dictionary of directories.
        """
        if current_path is None:
            current_path = self.base_path

        # Create the node for the current directory
        node = {
            "text": os.path.basename(current_path) or current_path,
            "id": current_path,
            "state": {"opened": False},
            "children": [],
            "type": "default"
        }

        try:
            # List only directories, ignoring hidden folders (like .git or __pycache__)
            items = sorted(os.listdir(current_path))
            for item in items:
                full_path = os.path.join(current_path, item)
                if os.path.isdir(full_path) and not item.startswith('.'):
                    # Recursive call to get subdirectories
                    node["children"].append(self.get_directory_json(full_path))
        except PermissionError:
            # Handle folders where the user doesn't have read access
            node["text"] += " (Access Denied)"
            node["icon"] = "jstree-file" # Visual cue for locked folder

        return node

    def save_selected_config(self, paths):
        """
        Placeholder for when you want to save the 'watched' directories
        to a JSON or database.
        """
        print(f"DEBUG: Saving {len(paths)} paths to watch list...")
        # For now, we just return True
        return True