"""Optional desktop companion; run at home. Tk widgets remain on the main thread."""
import asyncio
import json
import queue
import threading
from pathlib import Path

from .companion import atomic_json, link, upload
from .formatting import norwegian
from .locking import FileLock


def launch():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        raise SystemExit('Tk is unavailable. Install your Python distribution’s Tk support or use the CLI.')

    directory = Path.home() / '.wow-status'
    credentials = directory / 'credentials.json'
    state = directory / 'upload-state.json'
    preferences = directory / 'desktop.json'
    root = tk.Tk()
    root.title('WoW Status companion')
    root.geometry('720x510')
    container = ttk.Frame(root, padding=20)
    container.pack(fill='both', expand=True)
    changes = queue.Queue()
    stopped = threading.Event()
    worker = None
    saved = {}
    if preferences.exists():
        try:
            saved = json.loads(preferences.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    url = tk.StringVar(value=saved.get('url', ''))
    path = tk.StringVar(value=saved.get('path', ''))
    code = tk.StringVar()
    connection = tk.StringVar(value='Stopped. Link your Discord account, then start watching exports.')
    last_export = tk.StringVar(value='No export observed in this session')
    last_upload = tk.StringVar(value='No upload confirmed in this session')
    ttk.Label(container, text='WoW Status — your characters, your choices',
              font=('', 15, 'bold')).pack(anchor='w')
    ttk.Label(container, text='The addon exports on /reload or logout. This app uploads selected data.',
              wraplength=660).pack(anchor='w', pady=(8, 16))
    ttk.Label(container, text='Service URL (HTTPS, or localhost for home tests)').pack(anchor='w')
    ttk.Entry(container, textvariable=url).pack(fill='x')
    ttk.Label(container, text='Private code from Discord /link (one use; expires in 10 minutes)').pack(
        anchor='w', pady=(10, 0))
    entry = ttk.Entry(container, textvariable=code, show='•')
    entry.pack(fill='x')

    def busy():
        return worker is not None and worker.is_alive()

    def persist():
        atomic_json(preferences, {'url': url.get().strip(), 'path': path.get().strip()})

    def link_account():
        nonlocal worker
        if busy():
            messagebox.showinfo('Stop first', 'Stop the uploader before linking another installation.')
            return
        service, private_code = url.get().strip(), code.get().strip()
        if not service or not private_code:
            messagebox.showinfo('Linking', 'Enter your service URL and the private code from /link.')
            return
        code.set('')
        connection.set('Linking…')
        persist()

        def enroll():
            try:
                asyncio.run(link(service, private_code, credentials))
                changes.put({'connection': 'Linked to your Discord account. Select the addon file and Start.'})
            except Exception as exc:
                changes.put({'connection': f'Linking failed ({type(exc).__name__}). Check URL/code and try again.'})

        worker = threading.Thread(target=enroll, daemon=True)
        worker.start()

    ttk.Button(container, text='Link my Discord account', command=link_account).pack(anchor='w', pady=8)
    ttk.Label(container, text='This addon’s SavedVariables file (WoWStatus.lua)').pack(anchor='w')
    file_row = ttk.Frame(container)
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
            messagebox.showinfo('Select addon export', 'Choose only this addon’s WoWStatus.lua SavedVariables file.')
            return
        if not credentials.exists():
            messagebox.showinfo('Link first', 'Link your Discord account before starting uploads.')
            return
        persist()
        stopped.clear()
        connection.set('Watching exports; waiting for changes…')

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

    def stop():
        stopped.set()
        connection.set('Stopping uploads…')

    buttons = ttk.Frame(container)
    buttons.pack(anchor='w', pady=12)
    ttk.Button(buttons, text='Start uploading', command=start).pack(side='left')
    ttk.Button(buttons, text='Stop uploading', command=stop).pack(side='left', padx=8)
    ttk.Label(container, textvariable=connection, wraplength=660).pack(anchor='w', pady=5)
    ttk.Label(container, textvariable=last_export).pack(anchor='w')
    ttk.Label(container, textvariable=last_upload).pack(anchor='w')
    ttk.Label(container, text='Stopping this app stops uploads. For immediate server-side pause or '
              'deletion, use /privacy in Discord. Keep your credentials file private.',
              wraplength=660).pack(anchor='w', pady=12)

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
            if 'last_upload' in change:
                last_upload.set('Last uploaded: ' + norwegian(change['last_upload']))
            if change.get('worker_finished') and stopped.is_set():
                connection.set('Uploads stopped. Previously shared server data remains.')
        root.after(150, poll)

    closing = False

    def close():
        nonlocal closing
        closing = True
        stopped.set()
        connection.set('Waiting for the current upload/link request to finish before closing…')
        finish_close()

    def finish_close():
        if closing and busy():
            root.after(150, finish_close)
        elif closing:
            root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()
