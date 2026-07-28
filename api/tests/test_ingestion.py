import uuid
from datetime import datetime, timedelta, timezone


def _valid_payload(**overrides):
    payload = {
        "transaction_id": str(uuid.uuid4()),
        "account_id": "acc-001",
        "amount_minor_units": 1500,
        "currency": "USD",
        "client_timestamp": datetime.now(timezone.utc).isoformat(),
        "location": {"latitude": 4.6097, "longitude": -74.0817},
        "merchant": {"merchant_id": "merch-001", "category": "grocery"},
    }
    payload.update(overrides)
    return payload


def test_valid_transaction_is_accepted(client):
    response = client.post("/transactions", json=_valid_payload())
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


def test_missing_required_field_is_rejected(client):
    payload = _valid_payload()
    del payload["account_id"]
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


def test_wrong_type_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(amount_minor_units="mil quinientos"))
    assert response.status_code == 400


def test_negative_amount_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(amount_minor_units=-100))
    assert response.status_code == 400


def test_zero_amount_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(amount_minor_units=0))
    assert response.status_code == 400


def test_amount_over_configured_max_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(amount_minor_units=999_999_999))
    assert response.status_code == 400


def test_future_timestamp_is_rejected(client):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    response = client.post("/transactions", json=_valid_payload(client_timestamp=future))
    assert response.status_code == 400


def test_out_of_range_latitude_is_rejected(client):
    payload = _valid_payload()
    payload["location"]["latitude"] = 200
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


def test_out_of_range_longitude_is_rejected(client):
    payload = _valid_payload()
    payload["location"]["longitude"] = -200
    response = client.post("/transactions", json=payload)
    assert response.status_code == 400


def test_unknown_field_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(unexpected_field="x"))
    assert response.status_code == 400


def test_invalid_currency_is_rejected(client):
    response = client.post("/transactions", json=_valid_payload(currency="dollars"))
    assert response.status_code == 400


def test_error_response_does_not_leak_internal_details(client):
    payload = _valid_payload()
    del payload["account_id"]
    response = client.post("/transactions", json=payload)
    body_text = response.text.lower()
    assert "traceback" not in body_text
    assert "site-packages" not in body_text
    assert ".py" not in body_text


def test_duplicate_transaction_is_idempotent(client):
    payload = _valid_payload()
    first = client.post("/transactions", json=payload)
    second = client.post("/transactions", json=payload)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["status"] == "already_accepted"


def test_persisted_transaction_is_retrievable_by_id(client):
    payload = _valid_payload()
    client.post("/transactions", json=payload)
    response = client.get(f"/transactions/{payload['transaction_id']}")
    assert response.status_code == 200
    assert response.json()["transaction"]["transaction_id"] == payload["transaction_id"]


def test_unknown_transaction_id_returns_404(client):
    response = client.get(f"/transactions/{uuid.uuid4()}")
    assert response.status_code == 404
