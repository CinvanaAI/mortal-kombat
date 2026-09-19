"""Workbench selection, immutable execution and private-save boundaries."""
import copy
import json

import pytest

from prompt_tournament.workflow_cli import demo_task
from prompt_tournament.workbench import (
    execute_preview, execute_probes, execute_research, replace_candidate, safe_worker_error, select_task,
)
from prompt_tournament.providers import ProviderFailure
from prompt_tournament import workbench


@pytest.mark.parametrize('mode,count', [('single', 1), ('batch', 1), ('batch', 3), ('battle', 2), ('tournament', 3)])
def test_explicit_selection_is_a_deep_snapshot(mode, count):
    task = demo_task()
    before = copy.deepcopy(task)
    selected = select_task(task, [m['id'] for m in task['models'][:count]], mode)
    assert len(selected['models']) == count
    selected['models'][0]['fixture_outputs']['review'] = 'edited'
    assert task == before


@pytest.mark.parametrize('mode,count', [('single', 2), ('battle', 1), ('battle', 3), ('tournament', 1)])
def test_mode_does_not_silently_drop_or_add_candidates(mode, count):
    task = demo_task()
    with pytest.raises(ValueError):
        select_task(task, [m['id'] for m in task['models'][:count]], mode)


def test_missing_or_duplicate_selection_rejected():
    task = demo_task()
    name = task['models'][0]['id']
    for selected in ([], [name, name], ['missing']):
        with pytest.raises(ValueError):
            select_task(task, selected, 'batch')


def test_invalid_candidate_settings_leave_original_intact():
    task = demo_task()
    before = copy.deepcopy(task)
    model = copy.deepcopy(task['models'][0])
    model.pop('provider')
    with pytest.raises((ValueError, KeyError)):
        replace_candidate(task, model['id'], model)
    assert task == before


def test_unknown_secret_field_is_not_accepted_by_settings():
    task = demo_task()
    model = copy.deepcopy(task['models'][0])
    model['api_key'] = 'not-a-real-secret'
    with pytest.raises(ValueError):
        replace_candidate(task, model['id'], model)
    assert 'api_key' not in task['models'][0]


def test_worker_masks_untrusted_exception_details():
    secret = 'Authorization: Bearer should-never-appear'
    assert secret not in safe_worker_error(RuntimeError(secret))
    assert secret not in safe_worker_error(ValueError(secret))
    assert safe_worker_error(ProviderFailure('Provider returned HTTP 401.')) == 'Provider returned HTTP 401.'


def test_network_refused_before_output_reservation(tmp_path):
    task = demo_task()
    task['providers'] = {'remote': {'kind': 'openai', 'base_url': 'https://example.invalid/v1', 'api_key_env': 'MK_TEST_ONLY'}}
    task['models'] = [{'id': 'one', 'provider': 'remote', 'model': 'one'}]
    destination = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match='Enable provider calls'):
        execute_preview(task, 'single', destination, allow_network=False)
    assert not destination.exists()


def test_two_offline_runs_keep_separate_evidence(tmp_path):
    task = demo_task()
    task = select_task(task, [task['models'][0]['id']], 'single')
    original = copy.deepcopy(task)
    first, first_path = execute_preview(task, 'single', tmp_path, allow_network=False)
    second, second_path = execute_preview(task, 'single', tmp_path, allow_network=False)
    assert first_path != second_path
    assert first['status'] == second['status'] == 'completed'
    assert first['provider_calls_attempted'] == second['provider_calls_attempted'] == 0
    assert (first_path / 'result.json').is_file()
    assert (first_path / 'report.html').is_file()
    assert (second_path / 'result.json').is_file()
    assert task == original


def test_research_output_reserved_before_provider_call(tmp_path):
    occupied = tmp_path / 'occupied'; occupied.write_text('keep original')
    calls = []
    with pytest.raises(OSError):
        execute_research('target', 'source', 'https://example.invalid/', {}, {}, occupied,
                         research=lambda *args: calls.append(args))
    assert calls == []
    assert occupied.read_text() == 'keep original'


def test_research_failure_preserves_sanitized_evidence(tmp_path):
    def fail(*args):
        raise RuntimeError('Authorization: do not expose')
    with pytest.raises(RuntimeError):
        execute_research('target', 'source', 'https://example.invalid/', {}, {}, tmp_path, research=fail)
    files = list(tmp_path.glob('*/model-research.json'))
    assert len(files) == 1
    evidence = json.loads(files[0].read_text())
    assert evidence['status'] == 'failed'
    assert 'Authorization' not in evidence['error']


def test_multiple_probes_preserve_each_status_and_continue_after_failure(tmp_path):
    calls = []
    def probe(provider, model):
        calls.append(model['model'])
        if model['model'] == 'first':
            raise RuntimeError('private provider body')
        return {'status': 'text-response', 'text': 'hi'}
    records, folder = execute_probes('synthetic', {'kind': 'ollama', 'base_url': 'http://localhost:11434'},
                                    ['first', 'second'], tmp_path, probe=probe)
    assert calls == ['first', 'second']
    assert [r['result']['status'] for r in records] == ['failed', 'text-response']
    assert len(list(folder.glob('probe-*.json'))) == 2
    for index, record in enumerate(records, 1):
        assert json.loads((folder / f'probe-{index:04d}.json').read_text()) == record
        assert record['connection']['endpoint'] == 'chat'
        assert 'private provider body' not in json.dumps(record)


def test_probes_reject_output_failure_before_any_call(tmp_path):
    occupied = tmp_path / 'occupied'; occupied.write_text('original')
    calls = []
    with pytest.raises(OSError):
        execute_probes('test', {}, ['first', 'second'], occupied,
                       probe=lambda *args: calls.append(args))
    assert not calls and occupied.read_text() == 'original'


def test_missing_tk_has_clear_launch_error_and_helpers_still_work(monkeypatch):
    monkeypatch.setattr(workbench, 'tk', None)
    with pytest.raises(ValueError, match='Tkinter'):
        workbench.launch_workbench()
    assert select_task(demo_task(), ['complete-fixture'], 'single')['models'][0]['id'] == 'complete-fixture'


def test_no_display_has_clear_launch_error(monkeypatch):
    class MissingDisplay:
        class TclError(Exception):
            pass
        @staticmethod
        def Tk():
            raise MissingDisplay.TclError('display unavailable')
    monkeypatch.setattr(workbench, 'tk', MissingDisplay)
    with pytest.raises(ValueError, match='graphical display'):
        workbench.launch_workbench()
