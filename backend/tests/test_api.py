"""API contract tests: status codes, response shape, and error format."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.factories import employee_api_payload, salary_api_payload

V1 = "/api/v1"


class TestHealth:
    def test_liveness(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readiness_reports_database(self, client: TestClient) -> None:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "reachable"}


class TestEmployeeEndpoints:
    def test_create_returns_201_and_the_employee(self, client: TestClient) -> None:
        response = client.post(f"{V1}/employees", json=employee_api_payload())

        assert response.status_code == 201
        body = response.json()
        assert body["employee_number"] == "E-000001"
        assert body["full_name"] == "Priya Raman"
        assert "id" in body

    def test_duplicate_create_returns_409_problem_detail(self, client: TestClient) -> None:
        client.post(f"{V1}/employees", json=employee_api_payload())

        response = client.post(f"{V1}/employees", json=employee_api_payload())

        assert response.status_code == 409
        problem = response.json()
        assert problem["type"] == "/errors/duplicate-employee"
        assert problem["status"] == 409
        assert problem["instance"] == f"{V1}/employees"

    def test_invalid_payload_returns_422_with_field_errors(self, client: TestClient) -> None:
        # Built as a raw dict: the typed factory would reject this before it
        # ever reached the API, which is not what this test is exercising.
        response = client.post(
            f"{V1}/employees", json=employee_api_payload() | {"work_email": "nope"}
        )

        assert response.status_code == 422
        problem = response.json()
        assert problem["type"] == "/errors/request-validation-error"
        assert any(error["field"] == "work_email" for error in problem["errors"])

    def test_get_missing_employee_returns_404_problem_detail(self, client: TestClient) -> None:
        response = client.get(f"{V1}/employees/9999")

        assert response.status_code == 404
        assert response.json()["type"] == "/errors/not-found"

    def test_list_returns_paginated_envelope(self, client: TestClient) -> None:
        client.post(f"{V1}/employees", json=employee_api_payload())

        response = client.get(f"{V1}/employees", params={"limit": 10, "offset": 0})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["limit"] == 10
        assert len(body["items"]) == 1

    def test_list_limit_is_capped(self, client: TestClient) -> None:
        """An uncapped list over 10,000 employees is a real hazard."""
        response = client.get(f"{V1}/employees", params={"limit": 5000})
        assert response.status_code == 422

    def test_list_filters_by_department(self, client: TestClient) -> None:
        client.post(f"{V1}/employees", json=employee_api_payload())
        client.post(
            f"{V1}/employees",
            json=employee_api_payload(
                employee_number="E-000002",
                work_email="sam@acme.com",
                department="Product",
            ),
        )

        response = client.get(f"{V1}/employees", params={"department": "Product"})

        assert response.json()["total"] == 1

    def test_patch_updates_employee(self, client: TestClient) -> None:
        created = client.post(f"{V1}/employees", json=employee_api_payload()).json()

        response = client.patch(
            f"{V1}/employees/{created['id']}", json={"job_title": "Staff Engineer"}
        )

        assert response.status_code == 200
        assert response.json()["job_title"] == "Staff Engineer"


class TestSalaryRecordEndpoints:
    def _create_employee(self, client: TestClient) -> int:
        response = client.post(f"{V1}/employees", json=employee_api_payload())
        return int(response.json()["id"])

    def test_create_salary_record_returns_201(self, client: TestClient) -> None:
        employee_id = self._create_employee(client)

        response = client.post(
            f"{V1}/employees/{employee_id}/salary-records", json=salary_api_payload()
        )

        assert response.status_code == 201
        body = response.json()
        assert body["amount"]["amount_minor"] == 8_500_000
        assert body["amount"]["currency_code"] == "GBP"
        assert body["amount"]["amount"] == "85000.00"
        assert body["amount"]["minor_unit_digits"] == 2
        assert body["is_open_ended"] is True

    def test_unsupported_currency_returns_422(self, client: TestClient) -> None:
        employee_id = self._create_employee(client)

        response = client.post(
            f"{V1}/employees/{employee_id}/salary-records",
            json=salary_api_payload() | {"currency_code": "XXX"},
        )

        assert response.status_code == 422
        assert response.json()["type"] == "/errors/request-validation-error"

    def test_non_positive_amount_returns_422(self, client: TestClient) -> None:
        employee_id = self._create_employee(client)

        response = client.post(
            f"{V1}/employees/{employee_id}/salary-records",
            json=salary_api_payload() | {"amount_minor": 0},
        )

        assert response.status_code == 422

    def test_overlapping_period_returns_409(self, client: TestClient) -> None:
        employee_id = self._create_employee(client)
        client.post(
            f"{V1}/employees/{employee_id}/salary-records",
            json=salary_api_payload() | {"effective_to": "2023-01-01"},
        )

        response = client.post(
            f"{V1}/employees/{employee_id}/salary-records",
            json=salary_api_payload()
            | {"effective_from": "2022-01-01", "effective_to": "2022-06-01"},
        )

        assert response.status_code == 409
        assert response.json()["type"] == "/errors/overlapping-salary-period"

    def test_records_for_unknown_employee_return_404(self, client: TestClient) -> None:
        response = client.get(f"{V1}/employees/9999/salary-records")
        assert response.status_code == 404

    def test_employee_detail_includes_salary_history(self, client: TestClient) -> None:
        employee_id = self._create_employee(client)
        client.post(f"{V1}/employees/{employee_id}/salary-records", json=salary_api_payload())

        response = client.get(f"{V1}/employees/{employee_id}")

        assert response.status_code == 200
        records = response.json()["salary_records"]
        assert len(records) == 1
        assert records[0]["amount"]["currency_code"] == "GBP"
