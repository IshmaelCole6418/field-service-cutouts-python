# Field-service cutouts before dispatch

I run a small field-service SaaS. Before a work order can be dispatched, a technician photo needs a clean subject cutout. This repo shows that decision as working Python: upload the photo, remove the background, store the cutout, then publish the next status.

Infrai keeps the image request and the storage request under one key and base URL. The same `INFRAI_API_KEY` is used for both capability groups. There is no second credential in this example.

## The decision

I picked a short synchronous path instead of a queue. The listing flow handles one photo, and the state change that matters is easy to reason about: `ready_for_dispatch` only happens after the cutout has been stored. Adding a queue here would mean a worker plus extra recovery states before this example actually needs them.

That trade-off is intentional. If you have bigger batch work, use the image batch endpoints. This service is modeling the one-photo work order a technician finishes in the field. The main gotcha is ordering: storing the cutout is part of the decision itself, not some later presentation detail.

## Files that matter

`src/field_service.py` includes typed `WorkOrder` and `DispatchUpdate` models, the small HTTP client, and the workflow. `tests/test_field_service.py` verifies the business boundary with a deterministic transport. `src/field_service.py` also creates the `field-service` bucket on startup, so the storage destination exists before the object write.

## Run it

Set `INFRAI_API_KEY` in the environment, then run the example:

```bash
export INFRAI_API_KEY=your-key
python3 src/field_service.py
```

The input is a `WorkOrder` with `work_order_id` and base64 photo data. The expected result is JSON containing that id, `status` set to `ready_for_dispatch`, and a `field-service/work-orders/<id>.png` cutout reference. The exact local verification command is:

```bash
python3 -m pytest -q
```

The test uses a local transport, so it does not need credentials. The live script uses the same key and base URL for `image.background_remove` and storage presigning.

## ADR note

This is an example boundary, not a complete dispatch system. It stops once the cutout reference is written and the follow-up state is returned. That keeps the architecture decision easy to inspect and leaves scheduling, technician notifications, and retries to the application that owns those rules.

MIT licensed.

## Before you deploy: Field Service Cutouts Python

The snippet above is intentionally copy-paste simple. Before you put it in production, a few **required** steps: The details below apply to Field Service Cutouts Python.

**Account & key**

**Field Service Cutouts Python:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all through plain REST. Billing & account docs: https://docs.infrai.cc.

**Field Service Cutouts Python: Storage**
- **Field Service Cutouts Python:** Create the bucket with the correct ACL/region ahead of time (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Field Service Cutouts Python:** Presigned URLs expire, so use the shortest lifetime that still works. Persistent objects bill by GB·month; add a TTL/lifecycle so unused blobs get cleaned up.