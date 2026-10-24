"""History removal is a DB operation; exports and recordings retain ownership."""

import sqlite3
from concurrent.futures import Future
from contextlib import closing, contextmanager

import pytest

from bilibili_downloader.core.live_models import LiveExport
from bilibili_downloader.core.live_repository import LiveRepository
from tests.test_live_exports import controller as controller
from tests.test_live_exports import recording
from tests.test_workspaces import workspace as workspace


def test_history_removal_and_restore_preserve_all_files_and_metadata(tmp_path):
    repository = LiveRepository(tmp_path / 'live.sqlite3')
    session = recording(tmp_path / 'media', export=LiveExport(status='completed', path=str(tmp_path / 'done.mp4')))
    session.warnings = ['一个提示']
    session.gaps = [{'start': 'one', 'end': 'two', 'reason': '中断'}]
    repository.save_session(session)
    (tmp_path / 'done.mp4').write_bytes(b'mp4')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file() and p.suffix != '.sqlite3'}
    revision = repository.history_revision
    removed = repository.remove_session(session.id)
    assert removed == session and repository.session(session.id) is None
    assert repository.history_revision == revision + 1
    assert LiveRepository(repository.path).sessions() == []
    with pytest.raises(ValueError, match='已移除'):
        repository.save_session(session)
    assert repository.restore_session(removed)
    assert repository.session(session.id) == session
    assert repository.history_revision == revision + 2
    assert all(path.read_bytes() == content for path, content in before.items())
    with closing(sqlite3.connect(repository.path)) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1


@pytest.mark.parametrize('status,export', [('recording', None), ('unknown', None), ('completed', 'queued'), ('stopped', 'running')])
def test_repository_rechecks_protected_state_in_transaction(tmp_path, status, export):
    repository = LiveRepository(tmp_path / 'live.sqlite3')
    session = recording(tmp_path / 'media', export=LiveExport(path='out.mp4', status=export) if export else None)
    session.status = status
    repository.save_session(session)
    with pytest.raises(ValueError):
        repository.remove_session(session.id)
    assert repository.session(session.id) == session


@pytest.mark.parametrize('status', ['completed', 'stopped', 'failed', 'interrupted'])
def test_terminal_records_can_be_removed_even_with_missing_media(tmp_path, status):
    repository = LiveRepository(tmp_path / 'live.sqlite3')
    session = recording(tmp_path / 'media')
    session.status = status
    repository.save_session(session)
    for path in (tmp_path / 'media').iterdir():
        path.unlink()
    (tmp_path / 'media').rmdir()
    assert repository.remove_session(session.id) == session
    assert repository.restore_session(session)
    assert not (tmp_path / 'media').exists()


def test_delete_failure_is_atomic_and_restore_never_overwrites(tmp_path):
    repository = LiveRepository(tmp_path / 'live.sqlite3')
    session = recording(tmp_path / 'media')
    repository.save_session(session)
    with closing(sqlite3.connect(repository.path)) as db, db:
        db.execute("CREATE TRIGGER deny_delete BEFORE DELETE ON sessions BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    with pytest.raises(sqlite3.Error):
        repository.remove_session(session.id)
    assert repository.session(session.id) == session
    assert repository.history_revision == 1
    with closing(sqlite3.connect(repository.path)) as db, db:
        db.execute('DROP TRIGGER deny_delete')
    removed = repository.remove_session(session.id)
    replacement = session.model_copy(deep=True)
    replacement.warnings = ['new record']
    assert repository.restore_session(replacement)
    assert not repository.restore_session(removed)
    assert repository.session(session.id).warnings == ['new record']


def test_removal_locks_state_before_another_database_writer_can_change_it(tmp_path, monkeypatch):
    repository = LiveRepository(tmp_path / 'live.sqlite3')
    session = recording(tmp_path / 'media')
    repository.save_session(session)
    active = session.model_copy(update={'status': 'recording'})
    attempts = []

    class CompetingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            cursor = super().execute(sql, parameters)
            if sql.startswith('SELECT payload FROM sessions WHERE id='):
                with closing(sqlite3.connect(repository.path, timeout=0)) as other:
                    try:
                        with other:
                            other.execute('UPDATE sessions SET payload=? WHERE id=?',
                                          (active.model_dump_json(), session.id))
                        attempts.append('updated')
                    except sqlite3.OperationalError:
                        attempts.append('locked')
            return cursor

    @contextmanager
    def competing_db():
        with repository._lock, closing(sqlite3.connect(repository.path, factory=CompetingConnection)) as db, db:
            yield db

    with monkeypatch.context() as patch:
        patch.setattr(repository, '_db', competing_db)
        assert repository.remove_session(session.id) == session
    assert attempts == ['locked']
    assert repository.session(session.id) is None


@pytest.mark.parametrize('owner', ['recording', 'session-export', 'segment-export'])
def test_controller_blocks_runtime_owners_of_target_session(controller, tmp_path, owner):
    session = recording(tmp_path / 'media')
    controller.repository.save_session(session)
    if owner == 'recording':
        controller.service.snapshot = lambda: [{'active_output_dir': session.directory}]
    else:
        controller._export = Future()
        if owner == 'session-export':
            controller._active_session = session.id
        else:
            controller.export_source = session.segments[0].path
    assert not controller.remove_history(session.id)
    assert controller.repository.session(session.id) == session
    controller._export = None


def test_controller_undo_survives_write_failure_and_updates_history(controller, tmp_path):
    session = recording(tmp_path / 'media')
    controller.repository.save_session(session)
    messages = []
    controller.history_feedback.connect(lambda text, undo: messages.append((text, undo)))
    assert controller.remove_history(session.id)
    assert controller.sessions == []
    with closing(sqlite3.connect(controller.repository.path)) as db, db:
        db.execute("CREATE TRIGGER deny_restore BEFORE INSERT ON sessions BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    assert not controller.undo_remove_history()
    assert controller._removed_history == session
    with closing(sqlite3.connect(controller.repository.path)) as db, db:
        db.execute('DROP TRIGGER deny_restore')
    assert controller.undo_remove_history()
    assert controller.sessions == [session]
    assert controller._removed_history is None
    assert [undo for _, undo in messages] == [True, False]


def test_history_menu_removes_whole_session_from_segment_and_undoes(workspace, tmp_path, qtbot):
    controller = workspace._live_controller
    session = recording(tmp_path / 'media')
    controller.repository.save_session(session)
    controller.refresh()
    workspace._show_tasks(2)
    workspace.show()
    page = workspace._task_page
    page.history.setCurrentItem(page.history.topLevelItem(0).child(0))
    assert page.remove_history_action.text() == '移除所属场次记录'
    assert page.remove_history_action.isEnabled()
    page.remove_history_action.trigger()
    assert controller.repository.sessions() == []
    assert page.history.topLevelItemCount() == 0
    assert page.undo_history_action.isEnabled()
    assert workspace._status_bar.action.text() == '撤销'
    page.undo_history_action.trigger()
    assert page.history.currentItem().data(0, 259) == session.id
    assert controller.repository.session(session.id) == session
    assert not page.undo_history_action.isEnabled()
