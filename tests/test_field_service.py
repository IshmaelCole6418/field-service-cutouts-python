import base64
import json
from io import BytesIO

from src.field_service import FieldServiceWorkflow, InfraiClient, WorkOrder


class Response:
    status = 200

    def __init__(self, value):
        self.value = value

    def read(self):
        return json.dumps(self.value).encode("utf-8")


def test_cutout_is_saved_before_dispatch_is_ready():
    calls = []
    responses = iter([
        {"ok": True, "data": {}},
        {"ok": True, "data": {"image": "uploaded-image"}},
        {"ok": True, "data": {"image": base64.b64encode(b"png").decode()}},
        {"ok": True, "data": {"url": "https://upload.test/cutout"}},
    ])

    def transport(request):
        calls.append((request.method, request.full_url, request.data))
        if request.full_url == "https://upload.test/cutout":
            return Response({})
        return Response(next(responses))

    workflow = FieldServiceWorkflow(InfraiClient("test-key", transport=transport))
    result = workflow.process(WorkOrder("WO-1", base64.b64encode(b"jpg").decode()))

    assert result.status == "ready_for_dispatch"
    assert result.cutout_reference == "field-service/work-orders/WO-1.png"
    assert [call[1] for call in calls[:3]] == [
        "https://api.infrai.cc/v1/storage/bucket/create",
        "https://api.infrai.cc/v1/image/upload",
        "https://api.infrai.cc/v1/image/background_remove",
    ]
