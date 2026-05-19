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
            node["icon"] = "jstree-file"  # Visual cue for locked folder

        return node

    def save_selected_config(self, paths):
        """
        Placeholder for when you want to save the 'watched' directories
        to a JSON or database.
        """
        print(f"DEBUG: Saving {len(paths)} paths to watch list...")
        # For now, we just return True
        return True

    def get_all_files_from_paths(self, paths):
        """
        Recursively walks through a list of directory paths and returns a
        flat list of all absolute file paths found inside them.
        """
        all_files = []

        for path in paths:
            if not os.path.exists(path):
                print(f"Warning: Path does not exist - {path}")
                continue

            # If the path is a direct file, just add it
            if os.path.isfile(path):
                all_files.append(path)

            # If the path is a directory, walk through it recursively
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Ignore hidden folders (like .git, .venv, .idea) to save processing time
                    dirs[:] = [d for d in dirs if not d.startswith('.')]

                    for file in files:
                        # Ignore hidden files
                        if not file.startswith('.'):
                            full_file_path = os.path.join(root, file)
                            all_files.append(full_file_path)

        return all_files