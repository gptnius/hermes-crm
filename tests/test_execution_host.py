"""Opt-in admission semantics against an actual Hermes source checkout.

This test inspects the host's real runtime store and receipt serializer. Private
host imports below are test-only inspection, not a production plugin API or an
execution adapter. No agent turn, scheduler job, provider call, or user account
is involved. This does not claim to test full process-restart execution.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
def test_host_admission_sequence_and_owner_epoch(tmp_path):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    assert (source / 'gateway' / 'session_authority.py').is_file(), 'Invalid HERMES_SOURCE'
    home = tmp_path / 'home'
    home.mkdir()
    # Deliberately construct, rather than copy, the environment: no credentials,
    # provider selection, account home, or ambient Hermes configuration survives.
    env = {
        'HOME': str(home),
        'USERPROFILE': str(home),
        'HERMES_HOME': str(home),
        'HERMES_ENABLE_PROJECT_PLUGINS': '0',
        'HERMES_BUNDLED_PLUGINS': str(home / 'no-bundled-plugins'),
        'PYTHONPATH': str(source),
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    result = subprocess.run(
        [sys.executable, '-P', '-c', HOST_CHECK], cwd=tmp_path, env=env,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS: admission sequence is stable; receipt owner epoch is not runtime epoch' in result.stdout
    assert not list(home.rglob('jobs.json')), 'Admission inspection must not create scheduler jobs'


HOST_CHECK = r'''
import json
import socket
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch


def deny_network(*args, **kwargs):
    raise AssertionError('Network is forbidden in admission contract validation')


with patch.object(socket, 'getaddrinfo', deny_network), \
     patch.object(socket, 'create_connection', deny_network), \
     patch.object(socket.socket, 'connect', deny_network), \
     patch.object(socket.socket, 'connect_ex', deny_network):
    from hermes_state import SessionDB
    from hermes_state_runtime import (
        admit_session_input, begin_runtime_epoch, cancel_session_input,
        claim_session_input, get_session_admission, recover_session_inputs,
        settle_session_input,
    )
    from gateway.session_authority import SessionAuthority

    db = SessionDB()
    try:
        first_epoch = begin_runtime_epoch(db, instance_id='fixture-first')
        original = {}
        for name in ('finished', 'queued', 'lost', 'later-claim'):
            db.create_session(name, source='cli')
            original[name] = admit_session_input(
                db, epoch=first_epoch, principal_id='fixture-owner',
                session_id=name, request_id='input-' + name,
                payload={'text': 'Synthetic store fixture; never executed.'},
            )

        # Synthetic store transitions only: no execution runner or model exists.
        finished = claim_session_input(db, epoch=first_epoch, session_id='finished')
        settle_session_input(
            db, epoch=first_epoch, admission_id=finished['admission_id'],
            generation=finished['generation'], outcome='failed',
        )
        lost = claim_session_input(db, epoch=first_epoch, session_id='lost')

        second_epoch = begin_runtime_epoch(db, instance_id='fixture-second')
        assert second_epoch > first_epoch
        assert recover_session_inputs(db, epoch=second_epoch) == 1

        # Invoke the actual serializer, not a reimplementation. Only its profile
        # identity and current epoch are needed; this is not a plugin context.
        serializer_owner = SimpleNamespace(profile_id='synthetic-profile', epoch=second_epoch)

        def receipt(name):
            row = get_session_admission(db, admission_id=original[name]['admission_id'])
            value = asdict(SessionAuthority._receipt(serializer_owner, row))
            assert value['admission_id'] == original[name]['admission_id']
            assert value['sequence'] == original[name]['seq']
            assert value['ref'] == {'profile_id': 'synthetic-profile', 'session_id': name}
            return value

        terminal = receipt('finished')
        queued = receipt('queued')
        unknown = receipt('lost')
        assert (terminal['status'], terminal['outcome']) == ('terminal', 'failed')
        assert queued['status'] == 'queued' and queued['execution_generation'] is None
        assert unknown['status'] == 'unknown'
        assert unknown['execution_generation'] == lost['generation']
        for value in (terminal, queued, unknown):
            assert value['authority_epoch'] == first_epoch < serializer_owner.epoch

        # Cancellation by the new owner does not rewrite an old queued row's
        # owner epoch. An observation high-water across runtime/receipt kinds
        # would wrongly reject this conclusive terminal receipt.
        cancel_session_input(db, epoch=second_epoch, admission_id=original['queued']['admission_id'])
        cancelled = receipt('queued')
        assert (cancelled['status'], cancelled['outcome']) == ('terminal', 'cancelled')
        assert cancelled['authority_epoch'] == first_epoch
        assert cancelled['execution_generation'] is None

        # Starting a previously queued input updates owner epoch and assigns a
        # claim generation, but its insertion sequence/admission ID stay fixed.
        claim_session_input(db, epoch=second_epoch, session_id='later-claim')
        started = receipt('later-claim')
        assert started['status'] == 'started'
        assert started['authority_epoch'] == second_epoch
        assert isinstance(started['execution_generation'], int)
        assert started['execution_generation'] > 0
        assert len({row['seq'] for row in original.values()}) == len(original)

        # An exact terminal request replay still identifies the original row.
        replayed = admit_session_input(
            db, epoch=second_epoch, principal_id='fixture-owner', session_id='finished',
            request_id='input-finished', payload={'text': 'Synthetic store fixture; never executed.'},
        )
        assert replayed['admission_id'] == original['finished']['admission_id']
        assert replayed['seq'] == original['finished']['seq']
        assert replayed['owner_epoch'] == first_epoch

        print(json.dumps({
            'runtime_epoch': second_epoch,
            'terminal_owner_epoch': terminal['authority_epoch'],
            'queued_owner_epoch': queued['authority_epoch'],
            'unknown_owner_epoch': unknown['authority_epoch'],
            'cancelled_owner_epoch': cancelled['authority_epoch'],
            'new_claim_owner_epoch': started['authority_epoch'],
            'sequences_preserved': True,
            'model_turns': 0,
        }, sort_keys=True))
        print('PASS: admission sequence is stable; receipt owner epoch is not runtime epoch')
    finally:
        db.close()
'''
