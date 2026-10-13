import asyncio
import csv
import json
from io import StringIO
import logging
import sys
from unittest.mock import AsyncMock

import httpx
import pytest

from workload import generator
from workload.generator import invoke_worker


def _function():
    return {"id": "f01", "service_name": "f01-hello-world"}


def test_request_log_uses_actual_http_status():
    client = AsyncMock()
    client.get.return_value = httpx.Response(418, request=httpx.Request("GET", "http://test"))
    output = StringIO()

    asyncio.run(invoke_worker(
        client,
        "http://test",
        _function(),
        output,
        asyncio.Lock(),
    ))

    row = next(csv.reader(StringIO(output.getvalue())))
    assert row[1:3] == ["f01", "f01-hello-world"]
    assert row[4] == "418"
    assert row[5] == ""


def test_request_failure_is_recorded_as_error_not_fake_status(caplog):
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("connection refused")
    output = StringIO()

    asyncio.run(invoke_worker(
        client,
        "http://test",
        _function(),
        output,
        asyncio.Lock(),
    ))

    row = next(csv.reader(StringIO(output.getvalue())))
    assert row[4] == ""
    assert row[5] == "connection refused"
    assert "Request failed for service=f01-hello-world" in caplog.text


def test_cancellation_closes_workload_csv(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"functions": []}), encoding="utf-8")
    output = tmp_path / "workload.csv"

    async def cancel_sleep(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(generator.asyncio, "sleep", cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(generator.run_workload(
            profile_name="W1",
            duration=60,
            seed=42,
            base_url="http://127.0.0.1:8080",
            config_path=str(config),
            output_path=str(output),
        ))

    assert output.read_text(encoding="utf-8").startswith(
        "timestamp,function_id,service_name,latency_ms,status_code,error"
    )
    output.rename(tmp_path / "workload-closed.csv")


def test_main_handles_keyboard_interrupt(monkeypatch, caplog):
    monkeypatch.setattr(sys, "argv", ["generator.py"])

    def interrupt(coroutine):
        coroutine.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(generator.asyncio, "run", interrupt)

    with caplog.at_level(logging.INFO):
        generator.main()

    assert "Workload generation interrupted by user." in caplog.text
