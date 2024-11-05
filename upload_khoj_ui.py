import os
import requests
import re
import time
import threading
import tkinter as tk
from tkinter import filedialog
from tkinter.ttk import Progressbar

# Configuration
KHOJ_URL = 'http://127.0.0.1:42110'
UPLOAD_API_URL = f'{KHOJ_URL}/api/content?client=web'
DEFAULT_FILE_TYPES = '.md,.pdf'
EXCLUDES = ".obsidian/,.trash/,plugins/,Template/"
BATCH_SIZE = 10
MODIFICATION_RECORD_FILE = 'file_modifications.txt'
SYNC_PATHS_FILE = 'sync_paths.txt'

# Load or initialize modification records
def load_modification_records():
    records = {}
    if os.path.exists(MODIFICATION_RECORD_FILE):
        with open(MODIFICATION_RECORD_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if len(line):
                    name, t = line.rsplit(':', maxsplit=1)
                    records[name.strip()] = float(t.strip())
    return records

def save_modification_records(paths):
    with open(MODIFICATION_RECORD_FILE, 'a', encoding='utf-8') as f:
        for p in paths:
            f.write(f'{p}:{os.path.getmtime(p)}\n')

modification_records = load_modification_records()

def my_filter(filename, content):
    if filename.endswith('.excalidraw.md'):
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        lines = content.splitlines()

        filtered_lines = []
        capturing = False

        for line in lines:
            if re.match(r'^\s*#+ Text Elements', line):
                capturing = True
                filtered_lines.append(line)
            elif re.match(r'^#+\s+', line) and capturing:
                capturing = False

            if capturing:
                filtered_lines.append(re.sub(r' \^[\w-]{8}$', '', line))
        return "\n".join(filtered_lines)

    return content

def fileExtensionToMimeType(extension: str):
    if extension == 'pdf':
        return 'application/pdf'
    if extension == 'png':
        return 'image/png'
    if extension in {'jpg', 'jpeg'}:
        return 'image/jpeg'
    if extension in {'md', 'markdown'}:
        return 'text/markdown'
    if extension == 'org':
        return 'text/org'
    return 'text/plain'

def upload_files(files, force_update):
    total_files = len(files)
    completed_files = 0
    for i in range(0, total_files, BATCH_SIZE):
        files_batch = files[i:i + BATCH_SIZE]
        form_data = []

        for file_path in files_batch:
            _, extension = os.path.splitext(file_path)
            extension = extension.lower().lstrip('.')
            mime_type = fileExtensionToMimeType(extension)
            is_text_file = mime_type.startswith('text/')
            mode = 'r' if is_text_file else 'rb'

            with open(file_path, mode, encoding='utf-8' if is_text_file else None) as f:
                content = f.read()
                if is_text_file:
                    content = my_filter(file_path, content)
                form_data.append(('files', (os.path.normpath(file_path), content, mime_type)))

            # Update log in the main thread
            log_message = f"Uploading: {file_path}\n"
            root.after(0, update_log, log_message)

        headers = {
            'Authorization': 'Bearer ',
        }
        request_method = requests.put if force_update else requests.patch
        response = request_method(UPLOAD_API_URL, headers=headers, files=form_data)

        if response.status_code == 200:
            print(f"Uploaded batch {i//BATCH_SIZE + 1} successfully!")
        else:
            print(f"Error: Failed to upload batch {i//BATCH_SIZE + 1}. Status code: {response.status_code}")
            print(response.text)

        # Update progress bar and completed files count
        completed_files += len(files_batch)
        progress_percentage = (completed_files / total_files) * 100
        progress_message = f"Progress: {completed_files}/{total_files} files uploaded."
        root.after(0, update_progress, progress_percentage)
        root.after(0, update_log, progress_message + "\n")
        save_modification_records(files_batch)
        time.sleep(10)

    root.after(0, update_log, "Upload completed.\n")

def is_excluded(path, exclude_patterns):
    path = os.path.normpath(path)
    path = path.replace('\\', '/')
    return any(pattern in path for pattern in exclude_patterns)

def find_files(directory, extensions, exclude_patterns):
    matched_files = []
    for root, dirs, files in os.walk(directory):
        root = os.path.normpath(root)
        root = root.replace('\\', '/')
        dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d), exclude_patterns)]
        for file in files:
            if file.endswith(extensions):
                file_path = os.path.normpath(os.path.join(root, file))
                file_path = file_path.replace('\\', '/')
                mod_time = os.path.getmtime(file_path)
                if file_path not in modification_records or modification_records[file_path] < mod_time:
                    matched_files.append(file_path)
                    modification_records[file_path] = mod_time
    return matched_files

def upload(force_update):
    if not os.path.exists(SYNC_PATHS_FILE):
        print(f"Error: {SYNC_PATHS_FILE} not found.")
        return

    with open(SYNC_PATHS_FILE, 'r', encoding='utf-8') as f:
        paths = [os.path.normpath(line.strip()) for line in f if line.strip()]
    
    if not paths:
        print("Error: No paths specified in sync_paths.txt.")
        return

    file_types = tuple(DEFAULT_FILE_TYPES.split(','))
    exclude_patterns = [pattern.strip() for pattern in EXCLUDES.split(',')]

    files_to_upload = []
    for path in paths:
        if os.path.isdir(path):
            files_to_upload.extend(find_files(path, file_types, exclude_patterns))
        elif os.path.isfile(path) and path.endswith(file_types) and not is_excluded(path, exclude_patterns):
            mod_time = os.path.getmtime(path)
            if path not in modification_records or modification_records[path] < mod_time:
                files_to_upload.append(path)
                modification_records[path] = mod_time
        else:
            print(f"Error: Invalid directory or file type for path: {path}")

    with open('files_to_upload.log', 'w', encoding='utf-8') as f:
        f.write('\n'.join(files_to_upload))

    if files_to_upload:
        # progress_bar.start()  # Start the progress bar animation
        upload_files(files_to_upload, force_update)
        # progress_bar.stop()  # Stop the progress bar animation
        save_modification_records(modification_records)
    else:
        print("No new or modified files to upload.")

def browse_files():
    paths = filedialog.askopenfilenames()
    for path in paths:
        path_entry.insert(tk.END, path + '\n')

def browse_directory():
    directory = filedialog.askdirectory()
    if directory:
        path_entry.insert(tk.END, directory + '\n')

def start_upload():
    force_update = force_update_var.get()
    progress.set(0)  # Reset progress to 0
    log_text.delete(1.0, tk.END)  # Clear previous log messages
    thread = threading.Thread(target=upload, args=(force_update,))
    thread.start()

def update_progress(value):
    progress.set(value)

def update_log(message):
    log_text.insert(tk.END, message)
    log_text.see(tk.END)  # Scroll to the end of the text widget

# Initialize Tkinter
root = tk.Tk()
root.title("File Sync")

# Configure grid expansion
root.columnconfigure(1, weight=1)
root.rowconfigure(0, weight=1)

# Path Entry
tk.Label(root, text="Paths:").grid(row=0, column=0, sticky=tk.NW)
path_entry = tk.Text(root, height=10, width=50)
path_entry.grid(row=0, column=1, sticky=tk.NW+tk.SE, padx=5, pady=5)
if os.path.exists(SYNC_PATHS_FILE):
    with open(SYNC_PATHS_FILE, 'r', encoding='utf-8') as f:
        path_entry.insert(tk.END, f.read())

# Buttons for browsing files and directories
browse_file_button = tk.Button(root, text="Browse Files", command=browse_files)
browse_file_button.grid(row=0, column=2, sticky=tk.W)

browse_dir_button = tk.Button(root, text="Browse Directory", command=browse_directory)
browse_dir_button.grid(row=0, column=3, sticky=tk.W)

# File Types Entry
tk.Label(root, text="File Types:").grid(row=1, column=0, sticky=tk.W)
file_types_entry = tk.Entry(root, width=50)
file_types_entry.insert(0, DEFAULT_FILE_TYPES)
file_types_entry.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)

# Exclude Patterns Entry
tk.Label(root, text="Excludes:").grid(row=2, column=0, sticky=tk.W)
exclude_entry = tk.Entry(root, width=50)
exclude_entry.insert(0, EXCLUDES)
exclude_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)

# Force Update Checkbox
force_update_var = tk.BooleanVar()
force_update_check = tk.Checkbutton(root, text="Force Update", variable=force_update_var)
force_update_check.grid(row=3, column=0, sticky=tk.W)

# Upload Button
upload_button = tk.Button(root, text="Upload", command=start_upload)
upload_button.grid(row=4, column=0, sticky=tk.W)

# Progress Bar
progress = tk.DoubleVar()
progress_bar = Progressbar(root, orient='horizontal', mode='determinate', length=400, variable=progress)
progress_bar.grid(row=5, column=0, columnspan=4, sticky=tk.EW, padx=5, pady=5)

# Log Text
log_text = tk.Text(root, height=10, width=50)
log_text.grid(row=6, column=0, columnspan=4, sticky=tk.EW, padx=5, pady=5)

root.mainloop()
