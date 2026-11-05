import json

import pytest
import requests

from finanze_app import assistant


@pytest.fixture(autouse=True)
def usage():
    assistant._USAGE.clear()


def config():
    return {'api_key': 'not-a-real-key', 'free_plan_confirmed': True}


def test_missing_or_unconfirmed_key_never_calls_network(monkeypatch):
    monkeypatch.setattr(requests, 'post', lambda *a, **k: pytest.fail('Network must not be called'))
    for cfg in ({}, {'api_key': 'test'}):
        with pytest.raises(assistant.AssistantError):
            assistant.interpret('Ciao', {}, [], cfg)


@pytest.mark.parametrize('status', [429, 401, 403, 500, 302])
def test_http_errors_stop_without_retry_or_raw_secrets(monkeypatch, status):
    calls = []
    class Response:
        status_code = status
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'post', post)
    with pytest.raises(assistant.AssistantError) as error:
        assistant.interpret('Ciao', {}, [], config())
    assert len(calls) == 1
    assert 'not-a-real-key' not in str(error.value)
    assert calls[0]['allow_redirects'] is False


def test_model_request_is_bounded_and_valid_response_parsed(monkeypatch):
    calls = []
    class Response:
        status_code = 200
        def json(self):
            return {'choices': [{'message': {'content': json.dumps({'intent': 'simulate', 'amount': 40, 'answer': ''})}}]}
    def post(url, **kwargs):
        assert url == assistant.ENDPOINT
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'post', post)
    result = assistant.interpret('Posso spendere 40?', {'margine': 100}, [{'role': 'user', 'content': 'x'*3000}]*30, config())
    assert result['amount'] == 40
    assert len(calls[0]['json']['messages']) == 9
    assert len(calls[0]['json']['messages'][2]['content']) == 2000
    with pytest.raises(assistant.AssistantError, match='secondo'):
        assistant.interpret('Ancora', {}, [], config())
    assert len(calls) == 1


def test_invalid_json_and_timeout_are_safe(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {'choices': [{'message': {'content': 'not-json'}}]}
    monkeypatch.setattr(requests, 'post', lambda *a, **k: Response())
    with pytest.raises(assistant.AssistantError, match='risposta valida'):
        assistant.interpret('Ciao', {}, [], config())
    assistant._USAGE.clear()
    def fail(*a, **k):
        raise requests.Timeout('secret content')
    monkeypatch.setattr(requests, 'post', fail)
    with pytest.raises(assistant.AssistantError) as error:
        assistant.interpret('Ciao', {}, [], config())
    assert 'secret content' not in str(error.value)
