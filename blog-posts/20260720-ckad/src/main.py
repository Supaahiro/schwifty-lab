"""Minimal Kubernetes operator for the FlightBooking custom resource.

Watches every FlightBooking object cluster-wide (training.example.com/v1alpha1)
and reconciles the ones sitting in the "Pending" phase: it calls a (simulated)
external airline reservation system to obtain a booking reference, then
patches the object's status subresource to "Booked" with that reference and a
confirmation message. Objects already past "Pending" are left untouched, so
reconciliation is naturally idempotent across watch restarts.

This is demo/teaching code for the CKAD blog post on CRDs and operators -- it
intentionally keeps error handling, retries and backoff minimal so the
control loop (watch -> reconcile -> patch status) stays easy to follow.

Version: 1.3.0 (2026-07-20)

Changelog:
  1.3.0 (2026-07-20) - Run the watch/reconcile loop on a background thread
      so Ctrl+C is noticed even while the socket is idle: the main thread's
      Thread.join(timeout=...) wakes up promptly on KeyboardInterrupt and
      calls watch.Watch.stop(), which force-closes the socket from the
      outside to unblock the worker thread (a same-thread `except
      KeyboardInterrupt` around a blocking SSL read never fires until that
      read itself returns, which may not happen for a long time when idle).
  1.2.1 (2026-07-20) - Catch KeyboardInterrupt around the watch stream so
      Ctrl+C stops the operator cleanly instead of dumping a traceback from
      the middle of a blocking socket read.
  1.2.0 (2026-07-20) - Build the status subresource patch from a
      FlightBookingStatus instance (model_dump(mode="json", by_alias=True))
      instead of a hand-written dict, so the patch body stays in sync with
      the typed model.
  1.1.0 (2026-07-20) - Parse watch events into strongly-typed Pydantic models
      (FlightBooking / FlightBookingSpec / FlightBookingStatus) mirroring
      manifests/01-crd.yaml, instead of indexing into raw dicts.
  1.0.0 (2026-07-20) - Initial release: watch-based reconcile loop moving
      FlightBooking objects from Pending to Booked via a simulated booking
      call and a status subresource patch.
"""

import logging
import random
import string
import threading
import time
from datetime import date, datetime, timezone
from typing import Any, Literal, cast

from kubernetes import client, config, watch
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

GROUP = "training.example.com"
VERSION = "v1alpha1"
PLURAL = "flightbookings"

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("flightbooking-operator")


class FlightBookingSpec(BaseModel):
    """Mirrors `spec` in manifests/01-crd.yaml -- the user-authored booking
    request. Field names are camelCase on the wire; alias_generator maps them
    to/from the snake_case attributes below."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    passenger: str
    flight_number: str = Field(pattern=r"^[A-Z]{2}[0-9]{2,4}$")
    origin: str | None = None
    destination: str | None = None
    departure_date: date
    seat_class: Literal["economy", "business", "first"] = "economy"


class FlightBookingStatus(BaseModel):
    """Mirrors `status` in manifests/01-crd.yaml -- written only by this
    operator via the status subresource."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    phase: Literal["Pending", "Booked", "Failed"] = "Pending"
    booking_reference: str | None = None
    message: str | None = None
    processed_at: datetime | None = None


class FlightBookingMetadata(BaseModel):
    """The subset of the standard Kubernetes ObjectMeta this operator
    actually needs; unrecognized fields (uid, resourceVersion, labels, ...)
    are ignored rather than rejected."""

    name: str
    namespace: str


class FlightBooking(BaseModel):
    """Strongly-typed view of a training.example.com/v1alpha1 FlightBooking
    object, as delivered by the watch stream (a plain dict from the generic
    CustomObjectsApi)."""

    metadata: FlightBookingMetadata
    spec: FlightBookingSpec
    status: FlightBookingStatus = Field(default_factory=FlightBookingStatus)


def load_kube_config() -> None:
    """Load kube config from inside a cluster (ServiceAccount) first, falling
    back to the local kubeconfig (~/.kube/config) when running out-of-cluster
    (e.g. for local development against a kind/minikube cluster)."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def book_flight(spec: FlightBookingSpec) -> str:
    """Simulate a call to an external airline reservation system.

    The sleep stands in for real network latency, and the random suffix
    stands in for a reference issued by that external system.
    """
    time.sleep(2)
    suffix = "".join(random.choices(
        string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"


def reconcile(api: client.CustomObjectsApi, booking: FlightBooking) -> None:
    """Move a single FlightBooking object from Pending to Booked.

    A no-op for any object not currently in the Pending phase, which makes
    this safe to call repeatedly for the same object (e.g. after a watch
    reconnect re-delivers ADDED/MODIFIED events).
    """
    name, namespace = booking.metadata.name, booking.metadata.namespace

    if booking.status.phase != "Pending":
        return

    log.info("Reconciling FlightBooking %s/%s", namespace, name)
    reference = book_flight(booking.spec)

    # Only the status subresource is patched -- the operator never touches
    # spec, keeping status updates isolated from user-authored fields.
    new_status = FlightBookingStatus(
        phase="Booked",
        booking_reference=reference,
        message=f"Booking confirmed for flight {booking.spec.flight_number}",
        processed_at=datetime.now(timezone.utc),
    )
    status_patch = {"status": new_status.model_dump(
        mode="json", by_alias=True)}
    api.patch_namespaced_custom_object_status(
        group=GROUP,
        version=VERSION,
        namespace=namespace,
        plural=PLURAL,
        name=name,
        body=status_patch,
    )
    log.info("FlightBooking %s/%s booked as %s", namespace, name, reference)


def _watch_loop(w: watch.Watch, api: client.CustomObjectsApi, stop_event: threading.Event) -> None:
    """Blocking watch/reconcile cycle, meant to run on its own thread.

    The Kubernetes watch API times out server-side after a while (here
    capped client-side at 60s), so the watch is wrapped in a loop that
    simply reopens the stream. A dropped/error connection (ApiException) is
    logged and retried after a short backoff instead of crashing the
    operator. Any other exception is only expected once `stop_event` is set
    -- it means `w.stop()` force-closed the socket to unblock this thread
    from a read that was sitting idle (see the note on `run()` below) -- so
    it is swallowed in that case and re-raised otherwise.
    """
    while not stop_event.is_set():
        try:
            stream = w.stream(
                api.list_cluster_custom_object,
                GROUP,
                VERSION,
                PLURAL,
                timeout_seconds=60,
            )
            for raw_event in stream:
                event = cast(dict[str, Any], raw_event)
                if event["type"] not in ("ADDED", "MODIFIED"):
                    continue
                try:
                    booking = FlightBooking.model_validate(event["object"])
                except ValidationError as exc:
                    log.error(
                        "Skipping FlightBooking that failed validation: %s", exc)
                    continue
                reconcile(api, booking)
        except client.ApiException as exc:
            if stop_event.is_set():
                break
            log.error("Watch stream error: %s", exc)
            time.sleep(5)
        except Exception:
            if stop_event.is_set():
                break
            raise


def run() -> None:
    """Start the watch loop on a background thread and block the main thread
    until Ctrl+C.

    A single-threaded blocking read can sit idle in the SSL socket for a
    long time (up to `timeout_seconds`) waiting for the next watch event,
    and on that same thread a signal is only ever noticed once the blocking
    call returns -- so a lone `except KeyboardInterrupt` around the loop
    just never runs while idle. Running the watch on a background thread
    lets the main thread's `Thread.join(timeout=...)` -- which *does* wake up
    promptly on Ctrl+C -- call `watch.Watch.stop()`, which force-shuts the
    underlying socket from the outside to unblock the worker thread
    immediately, exactly as documented in `Watch.stop()`'s docstring.
    """
    load_kube_config()
    api = client.CustomObjectsApi()
    w = watch.Watch()
    stop_event = threading.Event()

    log.info("FlightBooking operator started, watching %s/%s/%s",
             GROUP, VERSION, PLURAL)
    watch_thread = threading.Thread(
        target=_watch_loop, args=(w, api, stop_event), daemon=True)
    watch_thread.start()

    try:
        while watch_thread.is_alive():
            watch_thread.join(timeout=1)
    except KeyboardInterrupt:
        log.info("Shutdown requested, stopping watch.")
        stop_event.set()
        w.stop()
        watch_thread.join()


if __name__ == "__main__":
    run()
