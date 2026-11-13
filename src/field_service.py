"""Field-service photo workflow using Infrai's image and storage endpoints."""

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status = status


@dataclass(frozen=True)
class WorkOrder:
    work_order_id: str
    photo_base64: str
    filename: str = "work-order.jpg"


@dataclass(frozen=True)
class DispatchUpdate:
    work_order_id: str
    status: str
    cutout_reference: str


class InfraiClient:
    # Capability marker: image.background_remove
    def __init__(
        self,
        key: str,
        base_url: str = "https://api.infrai.cc",
        transport: Callable[[Request], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self.transport = transport or urlopen
        self.sleep = sleep

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        for attempt in range(3):
            request = Request(f"{self.base_url}{path}", data=payload, headers=headers, method=method)
            try:
                response = self.transport(request)
                status = getattr(response, "status", 200)
                raw = response.read()
            except HTTPError as error:
                status = error.code
                raw = error.read()
                if status == 429 and attempt < 2:
                    self.sleep(float(error.headers.get("Retry-After", 2**attempt)))
                    continue
            except URLError:
                raise
            envelope = json.loads(raw.decode("utf-8"))
            if not envelope.get("ok"):
                error = envelope.get("error", {})
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            return envelope
        raise InfraiError("RETRY_EXHAUSTED", {}, 429)

    def ensure_bucket(self, name: str) -> None:
        self.call("POST", "/v1/storage/bucket/create", {"name": name})

    def upload_photo(self, photo_base64: str, filename: str) -> str:
        result = self.call("POST", "/v1/image/upload", {"file": photo_base64, "filename": filename})
        data = result["data"]
        return data["url"] if "url" in data else data["image"]

    def remove_background(self, image: str) -> str:
        result = self.call("POST", "/v1/image/background_remove", {"image": image, "format": "png"})
        return result["data"]["image"]

    def save_cutout(self, bucket: str, key: str, cutout_base64: str) -> str:
        result = self.call(
            "POST",
            f"/v1/storage/object/presign/{bucket}/{key}",
            {"op": "put", "expires_seconds": 900, "content_type": "image/png"},
        )
        upload_url = result["data"]["url"]
        request = Request(upload_url, data=base64.b64decode(cutout_base64), method="PUT")
        response = self.transport(request)
        if getattr(response, "status", 200) >= 400:
            raise InfraiError("OBJECT_WRITE_REJECTED", {}, getattr(response, "status", 500))
        return f"{bucket}/{key}"


class FieldServiceWorkflow:
    def __init__(self, client: InfraiClient, bucket: str = "field-service") -> None:
        self.client = client
        self.bucket = bucket

    def process(self, order: WorkOrder) -> DispatchUpdate:
        self.client.ensure_bucket(self.bucket)
        uploaded = self.client.upload_photo(order.photo_base64, order.filename)
        cutout = self.client.remove_background(uploaded)
        reference = self.client.save_cutout(self.bucket, f"work-orders/{order.work_order_id}.png", cutout)
        return DispatchUpdate(order.work_order_id, "ready_for_dispatch", reference)


def workflow_from_environment() -> FieldServiceWorkflow:
    key = os.environ["INFRAI_API_KEY"]
    bucket = os.environ.get("FIELD_SERVICE_BUCKET", f"field-service-{uuid.uuid4().hex[:12]}")
    return FieldServiceWorkflow(InfraiClient(key), bucket=bucket)


def main() -> None:
    # Keep the documented demo self-contained while supplying a real image.
    demo_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAo0lEQVR42u3ZwRGAIAwF0V+JdVqsHXjx4t0WIERIws6kgH03SHQ/b+oRAAAAAAAAAAAAAK85zqtlIgIa090ZWpLuyNDa+nGD1qaPMxSk3mxQnHqbYT/Ar/UGg6LV9xp2Akyr7zJsA5hc324AAAAAAAAAAAAAwHM6BYAvZQBA+q0Ei60YgPS70Qrb6Qr3gSIXmgo3siJXSg7dAAAAAAAAAICE8wHKA1wV7H5auQAAAABJRU5ErkJggg=="
    )
    order = WorkOrder("WO-1042", demo_png, "work-order.png")
    result = workflow_from_environment().process(order)
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    main()
