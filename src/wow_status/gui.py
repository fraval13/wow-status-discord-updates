"""Optional desktop companion. Group IDs and your name are entered in WoW."""
import asyncio
import json
import queue
import threading
from pathlib import Path

from .companion import upload
from .formatting import norwegian
from .group_client import configure, privacy_action
from .locking import FileLock


def launch():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        raise SystemExit('Tk is unavailable. Install Tk support or use the command-line companion.')
    directory = Path.home() / '.wow-status'
    credentials, state = directory / 'credentials.json', directory / 'upload-state.json'
    preferences = directory / 'desktop.json'
    saved = {}
    if preferences.exists():
        try:
            saved = json.loads(preferences.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    config = {}
    if credentials.exists():
        try:
            config = json.loads(credentials.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    root = tk.Tk()
    root.title('WoW Status companion')
    root.geometry('760x540')
    box = ttk.Frame(root, padding=20)
    box.pack(fill='both', expand=True)
    changes, stopped = queue.Queue(), threading.Event()
    worker = None
    url = tk.StringVar(value=config.get('url', saved.get('url', '')))
    path = tk.StringVar(value=saved.get('path', ''))
    selected_group = tk.StringVar()
    group_lookup = {}
    connection = tk.StringVar(value='Select your groups in WoW using /wstatus groups. No /link code needed.')
    last_export = tk.StringVar(value='No export observed in this session')
    last_upload = tk.StringVar(value='No upload confirmed in this session')
    ttk.Label(box, text='WoW Status — your groups, your characters', font=('', 15, 'bold')).pack(anchor='w')
    ttk.Label(box, text='Enter your shared service address once. Group IDs and your name come from the addon.',
              wraplength=710).pack(anchor='w', pady=(8, 16))
    ttk.Label(box, text='Shared service URL (HTTPS; localhost allowed for home tests)').pack(anchor='w')
    ttk.Entry(box, textvariable=url).pack(fill='x')

    def busy():
        return worker is not None and worker.is_alive()

    def persist():
        from .companion import atomic_json
        atomic_json(preferences, {'url': url.get().strip(), 'path': path.get().strip()})

    def save_service():
        if busy():
            messagebox.showinfo('Stop first', 'Stop uploading before changing the service address.')
            return
        try:
            configure(url.get().strip(), credentials)
            persist()
            connection.set('Service saved. Add one or more group IDs in WoW, then /reload and Start.')
        except (OSError, ValueError):
            messagebox.showinfo('Check address', 'Use a valid HTTPS service URL (or localhost for home tests).')

    ttk.Button(box, text='Save service address', command=save_service).pack(anchor='w', pady=8)
    ttk.Label(box, text='Only this addon’s SavedVariables file (WoWStatus.lua)').pack(anchor='w')
    file_row = ttk.Frame(box)
    file_row.pack(fill='x')
    ttk.Entry(file_row, textvariable=path).pack(side='left', fill='x', expand=True)

    def browse():
        selected = filedialog.askopenfilename(title='Select WTF/Account/.../SavedVariables/WoWStatus.lua',
                                             filetypes=[('WoW Status export', 'WoWStatus.lua')])
        if selected:
            path.set(selected)
            persist()

    ttk.Button(file_row, text='Browse…', command=browse).pack(side='right', padx=(8, 0))

    def start():
        nonlocal worker
        if busy():
            return
        selected = Path(path.get().strip())
        if selected.name != 'WoWStatus.lua' or not selected.is_file():
            messagebox.showinfo('Choose file', 'Select only this addon’s WoWStatus.lua SavedVariables file.')
            return
        if not credentials.exists():
            messagebox.showinfo('Save address first', 'Save the shared service address before starting.')
            return
        persist()
        stopped.clear()
        connection.set('Watching exports; only groups selected in WoW will receive data.')

        def watch():
            try:
                with FileLock(state):
                    asyncio.run(upload([selected], credentials, state,
                        status=lambda **values: changes.put(values), stop_event=stopped))
            except Exception as exc:
                changes.put({'connection': f'Uploader stopped ({type(exc).__name__}); check configuration.'})
            finally:
                changes.put({'worker_finished': True})

        worker = threading.Thread(target=watch, daemon=True)
        worker.start()

    buttons = ttk.Frame(box)
    buttons.pack(anchor='w', pady=12)
    ttk.Button(buttons, text='Start uploading', command=start).pack(side='left')

    def stop():
        stopped.set()
        connection.set('Stopping uploads…')

    ttk.Button(buttons, text='Stop uploading', command=stop).pack(side='left', padx=8)
    ttk.Label(box, textvariable=connection, wraplength=710).pack(anchor='w', pady=5)
    ttk.Label(box, textvariable=last_export).pack(anchor='w')
    ttk.Label(box, textvariable=last_upload).pack(anchor='w')
    ttk.Label(box, text='Your group data — stop uploading before using these controls:').pack(anchor='w', pady=(14, 3))
    group_box = ttk.Combobox(box, textvariable=selected_group, state='readonly', width=30)
    group_box.pack(anchor='w')

    def load_groups():
        try:
            data = json.loads(credentials.read_text(encoding='utf-8'))
            group_lookup.clear()
            for key, route in data.get('groups', {}).items():
                group_lookup[route.get('label', key)] = key
            groups = sorted(group_lookup)
            group_box['values'] = groups
            if selected_group.get() not in groups:
                selected_group.set(groups[0] if groups else '')
        except (OSError, ValueError):
            pass

    def privacy(action):
        nonlocal worker
        if busy():
            messagebox.showinfo('Stop first', 'Stop uploading and wait for it to finish before changing group privacy.')
            return
        target = group_lookup.get(selected_group.get())
        if not target:
            messagebox.showinfo('Choose group', 'Groups appear here after their first accepted enrollment.')
            return
        if action == 'delete' and not messagebox.askyesno('Delete your group data?',
                'Delete your characters, histories and upload credential from this group? '
                'Old Discord messages remain. Resume later requires a fresh enrollment.'):
            return

        def apply():
            try:
                with FileLock(state):
                    asyncio.run(privacy_action(credentials, target, action))
                changes.put({'connection': f'Group privacy action completed: {action}. Export current data with /reload before restarting.',
                             'groups_changed': True})
            except Exception as exc:
                changes.put({'connection': f'Privacy action not completed ({type(exc).__name__}); retry before removing credentials.'})

        worker = threading.Thread(target=apply, daemon=True)
        worker.start()

    privacy_buttons = ttk.Frame(box)
    privacy_buttons.pack(anchor='w', pady=6)
    for title, action in [('Pause group', 'pause'), ('Resume group', 'resume'), ('Delete my group data', 'delete')]:
        ttk.Button(privacy_buttons, text=title, command=lambda a=action: privacy(a)).pack(side='left', padx=(0, 8))
    ttk.Label(box, text='Remove an ID in WoW to stop that character sharing with that group after export/upload. '
              'Keep group IDs within their friend group. Bot credentials stay on the service.',
              wraplength=710).pack(anchor='w', pady=10)

    def poll():
        while True:
            try:
                change = changes.get_nowait()
            except queue.Empty:
                break
            if 'connection' in change:
                connection.set(change['connection'])
            if 'last_export' in change:
                last_export.set('Last exported: ' + norwegian(change['last_export']))
            if change.get('groups_changed'):
                load_groups()
            if 'last_upload' in change:
                last_upload.set('Last uploaded: ' + norwegian(change['last_upload']))
                load_groups()
            if change.get('worker_finished') and stopped.is_set():
                connection.set('Uploads stopped. Existing server data remains until changed or deleted.')
        root.after(150, poll)

    def close():
        stopped.set()
        if busy():
            connection.set('Waiting for the current request to finish before closing…')
            root.after(150, close)
        else:
            root.destroy()

    load_groups()
    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()
