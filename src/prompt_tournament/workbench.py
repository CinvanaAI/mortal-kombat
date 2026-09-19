"""Local desktop workbench. Importing this module starts no UI or network work."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import queue
import re
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError:  # Non-GUI use and helper tests do not require a Tk installation.
    tk = filedialog = messagebox = simpledialog = ttk = None


MODES = {
    'single': 'One candidate; collect its responses without judging.',
    'batch': 'Selected candidates; collect their responses without judging.',
    'battle': 'Exactly two candidates; compare them across the examples.',
    'tournament': 'Two or more candidates; build a judged ranking.',
}


def select_task(raw: dict, candidate_ids: list[str], mode: str) -> dict:
    """Freeze an explicit selection without mutating the editable task."""
    if mode not in MODES:
        raise ValueError('Choose Single, Batch, Battle or Tournament.')
    if not candidate_ids or len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError('Select at least one candidate, without duplicate IDs.')
    task = copy.deepcopy(raw)
    available = {model['id']: model for model in task.get('models', [])}
    if len(available) != len(task.get('models', [])):
        raise ValueError('Candidate IDs must be unique.')
    if set(candidate_ids) - set(available):
        raise ValueError('The selected candidate is no longer in this task.')
    if mode == 'single' and len(candidate_ids) != 1:
        raise ValueError('Single needs exactly one selected candidate.')
    if mode == 'battle' and len(candidate_ids) != 2:
        raise ValueError('Battle needs exactly two selected candidates.')
    if mode == 'tournament' and len(candidate_ids) < 2:
        raise ValueError('Tournament needs at least two selected candidates.')
    task['models'] = [available[name] for name in candidate_ids]
    return task


def execute_preview(task: dict, mode: str, output_parent: Path, *, allow_network: bool,
                    transport=None) -> tuple[dict, Path]:
    """Reserve a fresh result directory, then execute one immutable preview."""
    from .task import validate_task, plan_task
    from .workflow import run_task
    from .report import save_report
    task = validate_task(task, mode=mode)
    plan = plan_task(task, mode=mode)
    if plan['network_required'] and not allow_network:
        raise ValueError('Enable provider calls for this preview before running it.')
    parent = Path(output_parent).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r'[^A-Za-z0-9_-]+', '-', task['id']).strip('-')[:40] or 'task'
    out = parent / f'{datetime.now():%Y%m%d-%H%M%S}-{stem}-{uuid.uuid4().hex[:8]}'
    out.mkdir(exist_ok=False)
    kwargs = {'mode': mode, 'allow_network': allow_network}
    if transport is not None:
        kwargs['transport'] = transport
    result = run_task(task, **kwargs)
    save_report(result, out)
    return result, out


def replace_candidate(raw: dict, candidate_id: str, replacement: dict) -> dict:
    """Validate a complete replacement before changing the editor's task."""
    from .task import validate_task
    if not isinstance(replacement, dict) or replacement.get('id') != candidate_id:
        raise ValueError('Keep the existing candidate ID. Remove/add a candidate to change its identity.')
    candidate = copy.deepcopy(raw)
    index = next((i for i, model in enumerate(candidate['models']) if model['id'] == candidate_id), None)
    if index is None:
        raise ValueError('The candidate no longer exists.')
    candidate['models'][index] = copy.deepcopy(replacement)
    return validate_task(candidate, mode='batch')


def execute_research(target: str, source: str, url: str, provider: dict,
                     researcher: dict, output_parent: Path, *, research, transport=None):
    """Reserve evidence storage before a potentially billed research request."""
    parent = Path(output_parent).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / f'{datetime.now():%Y%m%d-%H%M%S}-model-research-{uuid.uuid4().hex[:8]}'
    folder.mkdir(exist_ok=False)
    path = folder / 'model-research.json'
    # Opening the intended output catches an unwritable destination before a call.
    with path.open('x', encoding='utf-8') as stream:
        kwargs = {'transport': transport} if transport is not None else {}
        try:
            result = research(target, source, url, provider, researcher, **kwargs)
        except Exception as exc:
            json.dump({'status': 'failed', 'error': safe_worker_error(exc)}, stream, indent=2)
            stream.write('\n')
            raise
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return result, path


def execute_probes(connection: str, provider: dict, model_ids: list[str], output_parent: Path,
                   *, probe=None, transport=None):
    """Probe an explicit selection sequentially, preserving each result locally."""
    from .providers import probe_model
    if not model_ids or len(model_ids) != len(set(model_ids)):
        raise ValueError('Select model IDs without duplicates.')
    probe = probe or probe_model
    parent = Path(output_parent).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    folder = parent / f'{datetime.now():%Y%m%d-%H%M%S}-model-probes-{uuid.uuid4().hex[:8]}'
    folder.mkdir(exist_ok=False)
    records = []
    for index, model_id in enumerate(model_ids, 1):
        path = folder / f'probe-{index:04d}.json'
        with path.open('x', encoding='utf-8') as stream:
            record = {'schema': 'mortal-kombat.model-probe.v1',
                      'recorded_at': datetime.now(timezone.utc).isoformat(),
                      'connection': {'name': connection, 'kind': provider['kind'],
                                     'base_url': provider['base_url'],
                                     'endpoint': provider.get('endpoint', 'responses' if provider['kind'] == 'openai' else 'chat')},
                      'requested_model_id': model_id}
            try:
                kwargs = {'transport': transport} if transport is not None else {}
                record['result'] = probe(provider, {'model': model_id}, **kwargs)
            except Exception as exc:
                record['result'] = {'status': 'failed', 'text': '', 'error': safe_worker_error(exc)}
            json.dump(record, stream, indent=2, ensure_ascii=False); stream.write('\n')
        records.append(record)
    return records, folder


def safe_worker_error(error: Exception) -> str:
    """Only the provider boundary's deliberately sanitized messages are displayed."""
    from .providers import ProviderFailure
    if isinstance(error, ProviderFailure):
        return str(error)
    if isinstance(error, ValueError):
        return 'Invalid task, reference or provider response. Review the configuration and try again.'
    return f'Job failed ({type(error).__name__}). Check the task and connection settings.'


class Workbench:
    """Tk widgets stay on the main thread; discovery and execution use workers."""

    def __init__(self, root: tk.Tk, task: dict | None = None, *, discovery=None, transport=None, research=None):
        from .workflow_cli import demo_task
        self.root = root
        self.discovery = discovery
        self.transport = transport
        self.research = research
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.preview = None
        self.last_output: Path | None = None
        self.artifact_index: int | None = None
        self.discovered_provider: str | None = None
        self.start_time = 0.0
        self.mode = tk.StringVar(value='tournament')
        self.status = tk.StringVar(value='Start with the offline demo, or load your own task.')
        self.task_id = tk.StringVar()
        self.call_limit = tk.StringVar(value='100')
        self.output_parent = tk.StringVar(value=str(Path.cwd() / 'rubric-rumble-results'))
        self.allow_network = tk.BooleanVar(value=False)
        self.judge_kind = tk.StringVar(value='rules')
        self.judge_label = tk.StringVar(value='No provider judge selected')
        self.rubric_kind = tk.StringVar(value='exact_fields')
        self.rubric_fields = tk.StringVar()
        self.artifact_id = tk.StringVar()
        self.connection_name = tk.StringVar()
        self.connection_kind = tk.StringVar(value='openai')
        self.connection_url = tk.StringVar(value='https://api.openai.com/v1')
        self.connection_env = tk.StringVar(value='OPENAI_API_KEY')
        self.connection_endpoint = tk.StringVar(value='responses')
        self.manual_model = tk.StringVar()
        self.research_target = tk.StringVar()
        self.research_provider = tk.StringVar()
        self.research_model_id = tk.StringVar()
        self.research_url = tk.StringVar()
        self.root.title('Rubric Rumble · Model Workbench')
        self.root.geometry('1280x880')
        self.root.minsize(1040, 760)
        self._build()
        self._load(copy.deepcopy(task if task is not None else demo_task()))
        self.root.after(100, self._poll)
        self.root.protocol('WM_DELETE_WINDOW', self._close)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#f5f3ec', foreground='#21352f')
        style.configure('TNotebook.Tab', padding=(17, 9))
        style.configure('TButton', padding=(10, 6))
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
        style.configure('Muted.TLabel', foreground='#5c6e61')
        style.map('TButton', background=[('active', '#e4e8de')])
        style.map('TNotebook.Tab', background=[('selected', '#e4e8de')])
        style.configure('Treeview', rowheight=27, background='white', fieldbackground='white')
        style.map('Treeview', background=[('selected', '#32614d')], foreground=[('selected', 'white')])
        self.root.configure(background='#f5f3ec')
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill='both', expand=True)
        top = ttk.Frame(outer)
        top.pack(fill='x')
        ttk.Label(top, text='Rubric Rumble', style='Title.TLabel').pack(side='left')
        for label, command in [('Save task…', self._save), ('Load task…', self._load_file), ('Offline demo', self._demo)]:
            ttk.Button(top, text=label, command=lambda fn=command: self._guard(fn)).pack(side='right', padx=4)
        ttk.Label(outer, text='Connect models. Choose a task. Inspect every result.', style='Muted.TLabel').pack(anchor='w', pady=(4, 14))
        footer = ttk.Frame(outer)
        footer.pack(side='bottom', fill='x')
        ttk.Separator(footer).pack(fill='x', pady=(12, 9))
        status_label = ttk.Label(footer, textvariable=self.status, wraplength=980, style='Muted.TLabel')
        status_label.pack(anchor='w', fill='x')
        status_label.bind('<Configure>', lambda event: status_label.configure(wraplength=max(200, event.width)))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill='both', expand=True)
        self.pages = {}
        for name in ('Task', 'Connections & candidates', 'Examples', 'Judge & rubric', 'Model research', 'Run & results'):
            page = ttk.Frame(self.tabs, padding=16)
            self.tabs.add(page, text=name)
            self.pages[name] = page
        self._build_task()
        self._build_connections()
        self._build_examples()
        self._build_judge()
        self._build_research()
        self._build_run()

    def _text(self, parent, height=8):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, pady=(5, 10))
        text = tk.Text(frame, height=height, wrap='word', font=('Segoe UI', 10), undo=True,
                       padx=10, pady=10, relief='solid', bd=1, background='white', foreground='#21352f')
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text.pack(side='left', fill='both', expand=True)
        return text

    @staticmethod
    def _put(widget, value):
        widget.delete('1.0', 'end')
        widget.insert('1.0', value)

    def _entry(self, parent, label, variable, width=None):
        ttk.Label(parent, text=label).pack(anchor='w', pady=(7, 3))
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.pack(fill='x')
        return entry

    def _build_task(self):
        p = self.pages['Task']
        self._entry(p, 'Task name', self.task_id)
        ttk.Label(p, text='What should each candidate do?', font=('Segoe UI', 12, 'bold')).pack(anchor='w', pady=(20, 0))
        self.instructions = self._text(p, 15)
        ttk.Label(p, text='The same instructions accompany each example. Examples and judging criteria have their own tabs.', wraplength=980, style='Muted.TLabel').pack(anchor='w')
        self._entry(p, 'Maximum provider calls for this run', self.call_limit)

    def _build_connections(self):
        p = self.pages['Connections & candidates']
        p.columnconfigure(0, weight=2)
        p.columnconfigure(1, weight=3)
        p.rowconfigure(0, weight=1)
        left = ttk.Frame(p, padding=(0, 0, 18, 0)); left.grid(row=0, column=0, sticky='nsew')
        right = ttk.Frame(p); right.grid(row=0, column=1, sticky='nsew')
        ttk.Label(left, text='Connections', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.connections = tk.Listbox(left, height=3, exportselection=False, font=('Segoe UI', 10))
        self.connections.pack(fill='x', pady=6)
        self.connections.bind('<<ListboxSelect>>', lambda _: self._connection_selected())
        self._entry(left, 'Connection name', self.connection_name)
        ttk.Label(left, text='Protocol').pack(anchor='w', pady=(7, 3))
        kind = ttk.Combobox(left, textvariable=self.connection_kind, values=('openai', 'ollama'), state='readonly')
        kind.pack(fill='x'); kind.bind('<<ComboboxSelected>>', lambda _: self._protocol_changed())
        self._entry(left, 'Base URL', self.connection_url)
        self._entry(left, 'API key environment variable name (never the key)', self.connection_env)
        ttk.Label(left, text='Generation endpoint').pack(anchor='w', pady=(7, 3))
        self.endpoint = ttk.Combobox(left, textvariable=self.connection_endpoint, values=('responses', 'chat-completions'), state='readonly')
        self.endpoint.pack(fill='x')
        buttons = ttk.Frame(left); buttons.pack(fill='x', pady=10)
        ttk.Button(buttons, text='Save connection', command=lambda: self._guard(self._save_connection)).pack(side='left')
        ttk.Button(buttons, text='Discover models', command=lambda: self._guard(self._discover)).pack(side='left', padx=6)
        ttk.Label(left, text='Discovery contacts only this configured provider. Listed IDs are visible models; task compatibility has not been verified.', wraplength=390, style='Muted.TLabel').pack(anchor='w')
        ttk.Label(right, text='Available models', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.available = tk.Listbox(right, height=6, selectmode='extended', exportselection=False, font=('Segoe UI', 10),
                                    selectbackground='#32614d', selectforeground='white')
        self.available.pack(fill='both', expand=True, pady=6)
        self.available.bind('<Control-a>', lambda _: (self.available.selection_set(0, 'end'), 'break')[-1])
        actions = ttk.Frame(right); actions.pack(fill='x')
        ttk.Button(actions, text='Add selected candidates', command=lambda: self._guard(self._add_discovered)).pack(side='left')
        ttk.Button(actions, text='Use selected as judge', command=lambda: self._guard(self._choose_judge)).pack(side='left', padx=6)
        ttk.Button(actions, text='Probe selected…', command=lambda: self._guard(self._probe)).pack(side='left')
        manual = ttk.Frame(right); manual.pack(fill='x', pady=7)
        ttk.Entry(manual, textvariable=self.manual_model).pack(side='left', fill='x', expand=True)
        ttk.Button(manual, text='Add model ID', command=lambda: self._guard(self._add_manual)).pack(side='left', padx=(6, 0))
        ttk.Button(manual, text='Use as judge', command=lambda: self._guard(self._manual_judge)).pack(side='left', padx=(6, 0))
        ttk.Label(right, text='Candidates — select the models to include in the next run', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(8, 4))
        self.candidates = ttk.Treeview(right, columns=('provider', 'model'), show='tree headings', height=5, selectmode='extended')
        self.candidates.heading('#0', text='Candidate'); self.candidates.column('#0', width=175)
        self.candidates.heading('provider', text='Connection'); self.candidates.column('provider', width=95)
        self.candidates.heading('model', text='Model / fixture'); self.candidates.column('model', width=175)
        self.candidates.pack(fill='both', expand=True)
        actions = ttk.Frame(right); actions.pack(fill='x', pady=(7, 0))
        for label, fn in [('Select all', lambda: self.candidates.selection_set(self.candidates.get_children())), ('Remove', self._remove_candidates), ('Settings…', self._candidate_settings)]:
            ttk.Button(actions, text=label, command=lambda action=fn: self._guard(action)).pack(side='left', padx=(0, 6))

    def _build_examples(self):
        p = self.pages['Examples']
        left = ttk.Frame(p, width=230); left.pack(side='left', fill='y', padx=(0, 18))
        right = ttk.Frame(p); right.pack(side='left', fill='both', expand=True)
        ttk.Label(left, text='Input examples', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        self.examples = tk.Listbox(left, width=27, exportselection=False, font=('Segoe UI', 10))
        self.examples.pack(fill='both', expand=True, pady=8)
        self.examples.bind('<<ListboxSelect>>', lambda _: self._guard(self._example_selected))
        for name, fn in [('Add example', self._add_example), ('Remove example', self._remove_example)]:
            ttk.Button(left, text=name, command=lambda action=fn: self._guard(action)).pack(fill='x', pady=3)
        self._entry(right, 'Example ID', self.artifact_id)
        ttk.Label(right, text='Source text').pack(anchor='w', pady=(13, 0))
        self.example_text = self._text(right, 12)
        ttk.Label(right, text='Expected fields for rules judging (JSON object; optional for a provider judge)').pack(anchor='w')
        self.expected_text = self._text(right, 4)

    def _build_judge(self):
        p = self.pages['Judge & rubric']
        ttk.Label(p, text='How should responses be compared?', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        for label, value in [('Transparent rules against expected fields', 'rules'), ('A configured provider model', 'provider')]:
            ttk.Radiobutton(p, text=label, variable=self.judge_kind, value=value).pack(anchor='w', pady=5)
        ttk.Label(p, textvariable=self.judge_label, style='Muted.TLabel').pack(anchor='w', pady=5)
        ttk.Label(p, text='Choose a provider judge from the available-model list in Connections & candidates. Single and Batch do not call a judge.', wraplength=1020, style='Muted.TLabel').pack(anchor='w', pady=(0, 10))
        ttk.Label(p, text='Rubric type').pack(anchor='w')
        ttk.Combobox(p, textvariable=self.rubric_kind, values=('exact_fields', 'pairwise'), state='readonly').pack(fill='x', pady=5)
        self._entry(p, 'Exact field names, separated by commas (rules only)', self.rubric_fields)
        ttk.Label(p, text='Judging criteria — include any weighting and tie-break instructions').pack(anchor='w', pady=(16, 0))
        self.rubric_text = self._text(p, 12)

    def _build_run(self):
        p = self.pages['Run & results']
        for mode, description in MODES.items():
            ttk.Radiobutton(p, text=f'{mode.title()} — {description}', variable=self.mode, value=mode).pack(anchor='w', pady=5)
        self._entry(p, 'Results parent folder — each run creates a new subfolder', self.output_parent)
        ttk.Button(p, text='Choose folder…', command=self._choose_output).pack(anchor='w', pady=6)
        row = ttk.Frame(p); row.pack(fill='x', pady=(7, 5))
        ttk.Button(row, text='Preview selected run', command=lambda: self._guard(self._preview)).pack(side='left')
        ttk.Checkbutton(row, text='Allow this run to call configured providers', variable=self.allow_network).pack(side='left', padx=14)
        self.run_button = ttk.Button(row, text='Run preview', command=lambda: self._guard(self._run)); self.run_button.pack(side='right')
        self.preview_text = self._text(p, 9)
        self.progress = ttk.Progressbar(p, mode='indeterminate'); self.progress.pack(fill='x', pady=5)
        row = ttk.Frame(p); row.pack(fill='x', pady=7)
        ttk.Button(row, text='Open latest report', command=lambda: self._guard(self._open_report)).pack(side='left')
        ttk.Button(row, text='Open saved report…', command=self._open_saved).pack(side='left', padx=7)
        ttk.Label(p, text='Preview makes no provider calls. Run executes the frozen preview. Existing results are never overwritten.', wraplength=1040, style='Muted.TLabel').pack(anchor='w')

    def _build_research(self):
        p = self.pages['Model research']
        ttk.Label(p, text='Documented model capabilities', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
        ttk.Label(p, text='Extract evidence from supplied official text; the URL is a reference, not fetched. Findings stay separate from probes and task settings.', wraplength=1000, style='Muted.TLabel').pack(anchor='w', pady=(4, 8))
        row = ttk.Frame(p); row.pack(fill='x')
        for label, variable in [('Target model ID', self.research_target), ('Researcher model ID', self.research_model_id)]:
            frame = ttk.Frame(row, padding=(0, 0, 12, 0)); frame.pack(side='left', fill='x', expand=True)
            self._entry(frame, label, variable)
        frame = ttk.Frame(row); frame.pack(side='left', fill='x', expand=True)
        ttk.Label(frame, text='Researcher connection').pack(anchor='w', pady=(7, 3))
        self.research_connections = ttk.Combobox(frame, textvariable=self.research_provider, state='readonly')
        self.research_connections.pack(fill='x')
        self._entry(p, 'Official source URL', self.research_url)
        ttk.Label(p, text='Paste the official source text to inspect').pack(anchor='w', pady=(12, 0))
        self.research_source = self._text(p, 7)
        ttk.Button(p, text='Preview research request…', command=lambda: self._guard(self._start_research)).pack(anchor='w', pady=4)
        ttk.Label(p, text='Recorded findings and source evidence').pack(anchor='w', pady=(8, 0))
        self.research_result = self._text(p, 5)
        self.research_result.configure(state='disabled')

    def _start_research(self):
        from .model_research import research_model
        name = self.research_provider.get().strip()
        if name not in self.task['providers']:
            raise ValueError('Choose a saved researcher connection.')
        target = self.research_target.get().strip(); model_id = self.research_model_id.get().strip()
        source = self.research_source.get('1.0', 'end-1c'); url = self.research_url.get().strip()
        if not target or not model_id or not source.strip() or not url:
            raise ValueError('Supply a target, researcher model, official source URL and source text.')
        if not messagebox.askokcancel('Preview one research request',
                f'Target: {target}\nResearcher: {name} / {model_id}\n\n'
                f'One generation request containing {len(source):,} characters of pasted reference text.\n'
                'This may be billed by your provider. Unsubstantiated capabilities must remain unknown.\n\nRun research?', parent=self.root):
            return
        provider = copy.deepcopy(self.task['providers'][name]); researcher = {'model': model_id, 'max_output_tokens': 2048}
        output = self.output_parent.get().strip()
        if not output:
            raise ValueError('Choose a results parent folder on Run & results.')
        research = self.research or research_model
        def run():
            return execute_research(target, source, url, provider, researcher, Path(output),
                                    research=research, transport=self.transport)
        self._background('research', run, f'Researching documented capabilities for {target}…')

    def _guard(self, action):
        if self.busy:
            self.status.set('A job is in progress. Its frozen selection will finish before another starts.')
            return
        try:
            return action()
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.status.set(str(exc))
            messagebox.showerror('Cannot continue', str(exc), parent=self.root)

    def _load(self, task):
        from .task import validate_task
        if not isinstance(task, dict) or task.get('schema') != 'mortal-kombat.task.v1':
            raise ValueError('Choose a mortal-kombat.task.v1 task file.')
        task = validate_task(task, mode='batch')
        self.task = task
        self.artifact_index = None
        self.task_id.set(task.get('id', ''))
        self.call_limit.set(str(task.get('max_calls', 100)))
        self._put(self.instructions, task.get('instructions', ''))
        rubric = task.get('rubric') or {}
        self.rubric_kind.set(rubric.get('kind', 'pairwise'))
        self.rubric_fields.set(', '.join(rubric.get('fields', [])))
        self._put(self.rubric_text, rubric.get('description', ''))
        self.judge_kind.set((task.get('judge') or {}).get('kind', 'rules'))
        self._refresh_judge()
        self._refresh_connections()
        self._refresh_candidates()
        self._refresh_examples()
        self.available.delete(0, 'end'); self.discovered_provider = None
        self.preview = None; self.allow_network.set(False)
        self._put(self.preview_text, 'Select candidates, choose a run mode, then preview the call counts.')

    def _collect(self):
        self._commit_example()
        raw = copy.deepcopy(self.task)
        raw['id'] = self.task_id.get().strip()
        raw['instructions'] = self.instructions.get('1.0', 'end-1c')
        raw['max_calls'] = int(self.call_limit.get())
        raw['rubric'] = {'kind': self.rubric_kind.get(), 'description': self.rubric_text.get('1.0', 'end-1c')}
        fields = [x.strip() for x in self.rubric_fields.get().split(',') if x.strip()]
        if fields:
            raw['rubric']['fields'] = fields
        if self.mode.get() in ('single', 'batch') and not raw['rubric']['description'].strip():
            raw.pop('rubric')
        raw['judge'] = {'kind': self.judge_kind.get()}
        if self.judge_kind.get() == 'provider':
            raw['judge']['model'] = copy.deepcopy((self.task.get('judge') or {}).get('model'))
        return raw

    def _demo(self):
        from .workflow_cli import demo_task
        self._load(demo_task()); self.status.set('Offline demo loaded: three synthetic candidates, two examples, no credentials needed.')

    def _load_file(self):
        name = filedialog.askopenfilename(parent=self.root, filetypes=[('Task JSON', '*.json')])
        if name:
            if Path(name).stat().st_size > 8_000_000:
                raise ValueError('Task file exceeds the 8 MB workbench limit.')
            self._load(json.loads(Path(name).read_text(encoding='utf-8-sig')))
            self.status.set('Task loaded. Review its connections and selection before running.')

    def _save(self):
        from .task import validate_task
        raw = validate_task(self._collect(), mode='batch')
        name = filedialog.asksaveasfilename(parent=self.root, defaultextension='.json', filetypes=[('Task JSON', '*.json')])
        if name:
            Path(name).write_text(json.dumps(raw, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
            self.status.set('Task saved. Credentials were not read or written.')

    def _refresh_connections(self):
        self.connections.delete(0, 'end')
        for name in self.task.setdefault('providers', {}):
            self.connections.insert('end', name)
        self.research_connections.configure(values=list(self.task['providers']))

    def _connection_selected(self):
        if self.busy or not self.connections.curselection():
            return
        name = self.connections.get(self.connections.curselection()[0]); p = self.task['providers'][name]
        self.connection_name.set(name); self.connection_kind.set(p['kind']); self.connection_url.set(p['base_url'])
        self.connection_env.set(p.get('api_key_env', ''))
        self.endpoint.configure(values=('responses', 'chat-completions') if p['kind'] == 'openai' else ('chat',))
        self.connection_endpoint.set(p.get('endpoint', 'responses' if p['kind'] == 'openai' else 'chat'))

    def _protocol_changed(self):
        ollama = self.connection_kind.get() == 'ollama'
        self.endpoint.configure(values=('chat',) if ollama else ('responses', 'chat-completions'))
        self.connection_endpoint.set('chat' if ollama else 'responses')
        self.connection_url.set('http://localhost:11434' if ollama else 'https://api.openai.com/v1')
        self.connection_env.set('' if ollama else 'OPENAI_API_KEY')

    def _save_connection(self):
        from .task import validate_task
        from .workflow_cli import demo_task
        name = self.connection_name.get().strip()
        if not name or name == 'fixture':
            raise ValueError('Choose a connection name other than fixture.')
        provider = {'kind': self.connection_kind.get(), 'base_url': self.connection_url.get().strip(), 'endpoint': self.connection_endpoint.get()}
        if self.connection_env.get().strip():
            provider['api_key_env'] = self.connection_env.get().strip()
        previous = self.task['providers'].get(name, {})
        if 'timeout_seconds' in previous:
            provider['timeout_seconds'] = previous['timeout_seconds']
        sample = demo_task(); sample['providers'] = {name: provider}
        validate_task(sample, mode='tournament')
        if self.discovered_provider == name and previous != provider:
            self.discovered_provider = None
            self.available.delete(0, 'end')
        self.task['providers'][name] = provider
        self._refresh_connections(); self.status.set(f'Connection {name} saved. No network request made.')
        return name, copy.deepcopy(provider)

    def _discover(self):
        name, provider = self._save_connection()
        from .providers import list_models
        discover = self.discovery or list_models
        self._background('discover', lambda: (name, discover(provider)), f'Discovering visible models from {name}…')

    def _add_models(self, connection, model_ids):
        if not connection or connection not in self.task['providers']:
            raise ValueError('Save a connection first.')
        added = []
        for model in model_ids:
            model = model.strip()
            if not model:
                continue
            existing = next((m for m in self.task['models'] if m.get('provider') == connection and m.get('model') == model), None)
            if existing:
                added.append(existing['id']); continue
            identity = f'{connection}:{model}'
            if any(m['id'] == identity for m in self.task['models']):
                identity += ':' + uuid.uuid4().hex[:6]
            self.task['models'].append({'id': identity, 'provider': connection, 'model': model, 'max_output_tokens': 1024})
            added.append(identity)
        if not added:
            raise ValueError('Select or enter at least one model ID.')
        self._refresh_candidates(added)
        self.status.set(f'{len(added)} candidate(s) selected. Discovery does not certify task compatibility.')

    def _add_discovered(self):
        self._add_models(self.discovered_provider, [self.available.get(i) for i in self.available.curselection()])

    def _add_manual(self):
        name, _ = self._save_connection()
        self._add_models(name, [self.manual_model.get()])

    def _choose_judge(self):
        selected = self.available.curselection()
        if len(selected) != 1 or not self.discovered_provider:
            raise ValueError('Select exactly one discovered model to use as judge.')
        model = self.available.get(selected[0]); provider = self.discovered_provider
        self._set_judge(provider, model)

    def _manual_judge(self):
        model = self.manual_model.get().strip()
        if not model:
            raise ValueError('Enter the judge model ID first.')
        provider, _ = self._save_connection()
        self._set_judge(provider, model)

    def _set_judge(self, provider, model):
        self.task['judge'] = {'kind': 'provider', 'model': {'id': f'judge:{provider}:{model}', 'provider': provider, 'model': model, 'max_output_tokens': 1024}}
        self.judge_kind.set('provider'); self.rubric_kind.set('pairwise'); self._refresh_judge()
        self.status.set('Provider judge selected. Review the rubric before running.')

    def _probe(self):
        selected = self.available.curselection()
        if not selected or not self.discovered_provider:
            raise ValueError('Select one or more discovered models to probe.')
        name = self.discovered_provider
        models = [self.available.get(index) for index in selected]
        provider = copy.deepcopy(self.task['providers'][name])
        output = self.output_parent.get().strip()
        if not output:
            raise ValueError('Choose a results parent folder on Run & results.')
        if not messagebox.askokcancel(
            'Preview greeting requests',
            f'Connection: {name}\nSelected models: {len(models)}\n\n'
            f'{len(models)} generation request(s), one per selected model, in sequence.\nMaximum output: 32 tokens per request.\n'
            'Prompt: Reply with exactly: hi\n\n'
            'Each result is saved in a new folder. Requests may be billed by your provider. Run the probes?', parent=self.root):
            return
        self._background('probe', lambda: execute_probes(name, provider, models, Path(output), transport=self.transport),
                         f'Checking {len(models)} selected model(s) with one greeting each…')

    def _refresh_judge(self):
        model = (self.task.get('judge') or {}).get('model')
        self.judge_label.set(f'Provider judge: {model.get("provider")} / {model.get("model")}' if isinstance(model, dict) else 'No provider judge selected')

    def _refresh_candidates(self, selected=None):
        self.candidates.delete(*self.candidates.get_children())
        for model in self.task.setdefault('models', []):
            self.candidates.insert('', 'end', iid=model['id'], text=model['id'], values=(model['provider'], model.get('model', 'synthetic fixture')))
        self.candidates.selection_set(selected if selected is not None else self.candidates.get_children())

    def _remove_candidates(self):
        selected = set(self.candidates.selection())
        self.task['models'] = [m for m in self.task['models'] if m['id'] not in selected]
        self._refresh_candidates()

    def _candidate_settings(self):
        selected = self.candidates.selection()
        if len(selected) != 1:
            raise ValueError('Select exactly one candidate for settings.')
        model = next(m for m in self.task['models'] if m['id'] == selected[0])
        dialog = tk.Toplevel(self.root); dialog.title('Candidate settings'); dialog.geometry('700x540'); dialog.transient(self.root); dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16); frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Candidate settings', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Edit output limits, explicit rates, or synthetic fixture responses. No API keys belong here.', wraplength=650).pack(anchor='w', pady=7)
        editor = self._text(frame, 18); self._put(editor, json.dumps(model, indent=2, ensure_ascii=False))
        def save():
            try:
                changed = json.loads(editor.get('1.0', 'end-1c'))
                candidate = replace_candidate(self._collect(), model['id'], changed)
                self.task = candidate; self._refresh_candidates([changed['id']]); dialog.destroy()
            except (ValueError, TypeError, KeyError) as exc:
                messagebox.showerror('Cannot save settings', str(exc), parent=dialog)
        ttk.Button(frame, text='Save settings', command=save).pack(anchor='e')

    def _refresh_examples(self):
        self.examples.delete(0, 'end')
        for artifact in self.task.setdefault('artifacts', []):
            self.examples.insert('end', artifact['id'])
        if self.task['artifacts']:
            self.examples.selection_set(0); self._show_example(0)
        else:
            self.artifact_index = None; self.artifact_id.set(''); self._put(self.example_text, ''); self._put(self.expected_text, '')

    def _commit_example(self):
        if self.artifact_index is None:
            return
        expected = self.expected_text.get('1.0', 'end-1c').strip()
        artifact = {'id': self.artifact_id.get().strip(), 'text': self.example_text.get('1.0', 'end-1c')}
        if expected:
            artifact['expected'] = json.loads(expected)
        self.task['artifacts'][self.artifact_index] = artifact

    def _show_example(self, index):
        self.artifact_index = index; artifact = self.task['artifacts'][index]
        self.artifact_id.set(artifact['id']); self._put(self.example_text, artifact['text'])
        self._put(self.expected_text, json.dumps(artifact['expected'], indent=2, ensure_ascii=False) if 'expected' in artifact else '')

    def _example_selected(self):
        if not self.examples.curselection():
            return
        index = self.examples.curselection()[0]
        self._commit_example(); self._show_example(index)

    def _add_example(self):
        self._commit_example()
        name = simpledialog.askstring('New example', 'Example ID', parent=self.root)
        if name:
            if any(a['id'] == name for a in self.task['artifacts']):
                raise ValueError('Example IDs must be unique.')
            self.task['artifacts'].append({'id': name, 'text': 'Replace this with your example.'})
            self._refresh_examples(); self.examples.selection_clear(0, 'end'); self.examples.selection_set('end'); self._show_example(len(self.task['artifacts'])-1)

    def _remove_example(self):
        if self.artifact_index is not None:
            self.task['artifacts'].pop(self.artifact_index)
            self.artifact_index = None; self._refresh_examples()

    def _selected_task(self):
        return select_task(self._collect(), list(self.candidates.selection()), self.mode.get())

    def _preview(self):
        from .task import validate_task, plan_task
        mode = self.mode.get(); task = validate_task(self._selected_task(), mode=mode); plan = plan_task(task, mode=mode)
        self.preview = (copy.deepcopy(task), mode, copy.deepcopy(plan))
        lines = [f'{mode.title()} · {plan["candidate_count"]} candidate(s) · {plan["artifact_count"]} example(s)', '',
                 f'Maximum candidate provider calls: {plan["maximum_candidate_calls"]}',
                 f'Maximum judge provider calls: {plan["maximum_judge_calls"]}',
                 f'Configured call limit: {plan["configured_call_limit"]}',
                 'Provider access: required' if plan['network_required'] else 'Provider access: none — offline fixture', '',
                 'Candidates: ' + ', '.join(m['id'] for m in task['models']), '',
                 'Ready. Run executes this selection; changing the task or mode requires a fresh preview.']
        self._put(self.preview_text, '\n'.join(lines)); self.status.set('Preview ready. No provider calls were made.')

    def _choose_output(self):
        name = filedialog.askdirectory(parent=self.root)
        if name:
            self.output_parent.set(name)

    def _run(self):
        from .task import validate_task
        if self.preview is None:
            raise ValueError('Preview the selected run first.')
        task, mode, plan = self.preview
        current = validate_task(self._selected_task(), mode=self.mode.get())
        if current != task or self.mode.get() != mode:
            self.preview = None
            raise ValueError('The task, mode or selection changed. Preview it again before running.')
        if plan['network_required'] and not self.allow_network.get():
            raise ValueError('This preview needs provider calls. Enable them explicitly to run.')
        output = self.output_parent.get().strip()
        if not output:
            raise ValueError('Choose a results parent folder.')
        allow = self.allow_network.get()
        self._background('run', lambda: execute_preview(copy.deepcopy(task), mode, Path(output), allow_network=allow, transport=self.transport), f'Running {mode} from the frozen preview…')

    def _background(self, kind, action, status):
        self.busy = True; self.start_time = time.monotonic(); self.status.set(status); self.progress.start(12)
        def worker():
            try:
                self.events.put((kind, True, action()))
            except Exception as exc:
                self.events.put((kind, False, safe_worker_error(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            kind, ok, payload = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False; self.progress.stop()
            if not ok:
                self.status.set(f'Job stopped: {payload}')
                messagebox.showerror('Job stopped', payload, parent=self.root)
            elif kind == 'discover':
                name, models = payload; self.discovered_provider = name; self.available.delete(0, 'end')
                for model in models:
                    self.available.insert('end', model)
                self.status.set(f'{len(models)} visible model IDs returned by {name}. Select candidates or one judge.')
            elif kind == 'probe':
                records, folder = payload
                dialog = tk.Toplevel(self.root); dialog.title('Greeting probe results'); dialog.geometry('860x620'); dialog.transient(self.root)
                frame = ttk.Frame(dialog, padding=16); frame.pack(fill='both', expand=True)
                ttk.Label(frame, text=f'{len(records)} greeting result(s)', font=('Segoe UI', 12, 'bold')).pack(anchor='w')
                ttk.Label(frame, text='Each status describes this request. It does not certify broader model capabilities.', wraplength=810).pack(anchor='w', pady=8)
                listing = ttk.Treeview(frame, columns=('model', 'status'), show='headings', height=5, selectmode='browse')
                listing.heading('model', text='Requested model'); listing.column('model', width=480)
                listing.heading('status', text='Recorded status'); listing.column('status', width=220)
                listing.pack(fill='x')
                for index, record in enumerate(records):
                    listing.insert('', 'end', iid=str(index), values=(record['requested_model_id'], record['result']['status']))
                text = self._text(frame, 12)
                def inspect(_event=None):
                    selected = listing.selection()
                    if selected:
                        text.configure(state='normal')
                        self._put(text, json.dumps(records[int(selected[0])], indent=2, ensure_ascii=False))
                        text.configure(state='disabled')
                listing.bind('<<TreeviewSelect>>', inspect); listing.selection_set('0'); inspect()
                ttk.Label(frame, text=f'Saved: {folder}', wraplength=810, style='Muted.TLabel').pack(anchor='w', pady=5)
                ttk.Button(frame, text='Close', command=dialog.destroy).pack(anchor='e')
                self.status.set(f'{len(records)} greeting result(s) saved with individual statuses. No broader capability claim is implied.')
            elif kind == 'research':
                result, path = payload
                catalog = result.get('catalog') or {}
                def tokens(name):
                    value = catalog.get(name)
                    return f'{value:,} tokens' if isinstance(value, int) else 'unknown'
                identity = result.get('model_identification') or {}
                summary = (f'Documented context: {tokens("context_window_tokens")}\n'
                           f'Documented output limit: {tokens("max_output_tokens")}\n'
                           f'Input: {", ".join(catalog.get("input_modalities") or []) or "unknown"} · '
                           f'Output: {", ".join(catalog.get("output_modalities") or []) or "unknown"}\n'
                           + ('Target ID appears in the quoted source.' if identity.get('exact_identifier_in_quote') else
                              'Review the researcher’s target association; the exact ID is absent from its quote.')
                           + '\n\nRecorded evidence:\n')
                self.research_result.configure(state='normal')
                self._put(self.research_result, summary+json.dumps(result, indent=2, ensure_ascii=False)+f'\n\nSaved evidence: {path}')
                self.research_result.configure(state='disabled')
                self.status.set('Model research saved with its source evidence. Review quoted support and unknowns.')
            else:
                result, out = payload; self.last_output = out
                self._put(self.preview_text, f'Status: {result["status"]}\n\nSaved results: {out}\n\nProvider calls attempted: {result.get("provider_calls_attempted", 0)}\n\nOpen the report to inspect candidate outputs, failures, judging and any available cost estimates.')
                self.status.set(f'Run {result["status"]}. Results preserved in a new folder.')
        self.root.after(100, self._poll)

    def _open_report(self):
        if self.last_output is None:
            raise ValueError('Complete a run first, or choose an existing report.')
        webbrowser.open((self.last_output/'report.html').resolve().as_uri())

    def _open_saved(self):
        name = filedialog.askopenfilename(parent=self.root, filetypes=[('HTML report', '*.html')])
        if name:
            webbrowser.open(Path(name).resolve().as_uri())

    def _close(self):
        if self.busy:
            messagebox.showinfo('Job in progress', 'Let the current job finish so its evidence can be saved before closing.', parent=self.root)
            return
        self.root.destroy()


def launch_workbench(task_path: str | Path | None = None) -> None:
    """Launch the desktop UI; optional task path replaces the bundled offline demo."""
    task = None
    if task_path is not None:
        path = Path(task_path)
        if path.stat().st_size > 8_000_000:
            raise ValueError('Task file exceeds the 8 MB workbench limit.')
        task = json.loads(path.read_text(encoding='utf-8-sig'))
    if tk is None:
        raise ValueError('The desktop workbench needs Python with Tkinter installed. CLI commands remain available.')
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise ValueError('The desktop workbench needs an available graphical display and Python Tk support.') from exc
    Workbench(root, task)
    root.mainloop()


if __name__ == '__main__':
    launch_workbench()
