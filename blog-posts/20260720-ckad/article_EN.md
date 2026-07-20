---
layout: default
title: "CKAD Preparation — Discover and Use Resources That Extend Kubernetes (CRDs and Operators)"
date: 2026-07-20
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20260720-ckad/article.webp"
summary: "Learn how Custom Resource Definitions extend the Kubernetes API and how a minimal Operator reconciles them, through a hands-on flight-booking example that moves a resource from Pending to Booked."
link: "blog-posts/20260720-ckad/article_EN.html"
---

## Introduction

This article is part of an ongoing series designed to help you prepare for the [*Certified Kubernetes Application Developer (CKAD)*](https://training.linuxfoundation.org/certification/certified-kubernetes-application-developer-ckad/) exam through small, focused labs.

This article opens a new domain: **"Application Environment, Configuration and Security"**. We're covering the first requirement:

> Discover and use resources that extend Kubernetes (CRD, Operators)

Everything we've used so far in this series — Pods, Deployments, Services — is a *built-in* resource, shipped with the Kubernetes API server. But the API server is extensible: anyone can register a brand-new resource type, complete with its own schema and validation, and Kubernetes will store, version and serve it exactly like a native one. That's what a **Custom Resource Definition (CRD)** does.

On its own, a CRD is just structured storage — creating a custom object doesn't *do* anything. Behavior comes from an **Operator**: a controller that watches your custom resources and reconciles the cluster (or the outside world) to match what they declare. That's the pattern behind most "Kubernetes-native" tools you've probably already used — cert-manager, Prometheus Operator, ArgoCD — they're all CRDs plus a controller watching them.

You can start from the beginning of the series here: [*CKAD Preparation — What is Kubernetes*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html).

## Prerequisites

A running Kubernetes cluster with a local image registry story — [kind](https://kind.sigs.k8s.io/) or [Minikube](https://minikube.sigs.k8s.io/) both work well here, since we'll build a container image locally and load it straight into the cluster without pushing it anywhere. You'll also need Docker (or another OCI builder) and `kubectl`.

If you'd rather not set up a local cluster, one of the [KillerCoda Kubernetes Playgrounds](https://killercoda.com/playgrounds/course/kubernetes-playgrounds) works too — Docker is already installed there, so Steps 6-7 (build and load the operator image) work exactly the same.

## Getting the Resources

Clone the lab repository and navigate to this article's folder:

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20260720-ckad
```

## The Scenario: A Flight Booking API

To keep things concrete, we'll model a tiny flight-booking system as a Kubernetes resource:

- Users (or another system) create a `FlightBooking` object describing a passenger, a flight number and a departure date.
- The object starts with no status at all. A small **operator** notices it, initializes `status` to `Pending`, then "books" the flight (in our demo, that just means generating a reference code) and moves `status` to `Booked`.

No airline was harmed in the making of this demo — the "booking system" is a two-second `sleep` and a random reference code. The point is the *pattern*, not the business logic.

## Step 1: Install the CRD

A CRD is itself a cluster-scoped Kubernetes resource — you install it once with `kubectl apply`, just like anything else. The relevant part of `manifests/01-crd.yaml` is the versioned schema:

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: flightbookings.training.example.com
spec:
  group: training.example.com
  names:
    kind: FlightBooking
    plural: flightbookings
    shortNames: ["fb"]
  scope: Namespaced
  versions:
    - name: v1alpha1
      served: true
      storage: true
      subresources:
        status: {}
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [passenger, flightNumber, departureDate]
              properties:
                passenger: { type: string }
                flightNumber:
                  type: string
                  pattern: "^[A-Z]{2}[0-9]{2,4}$"
                departureDate: { type: string, format: date }
                seatClass:
                  type: string
                  enum: ["economy", "business", "first"]
                  default: "economy"
            status:
              type: object
              properties:
                phase:
                  type: string
                  enum: ["Pending", "Booked", "Failed"]
                  default: "Pending"
                bookingReference: { type: string }
```

The full file also declares `additionalPrinterColumns` (what `k get fb` shows as table columns — you'll see them in Step 3) and a couple more optional `status`/`spec` fields; nothing that changes the concepts below.

A few details worth calling out, since they map directly to CKAD-style questions:

- `group` + `version` + `plural` together form the API path Kubernetes exposes: `/apis/training.example.com/v1alpha1/flightbookings`.
- `scope: Namespaced` means `FlightBooking` objects live inside a namespace, like Pods or Deployments — the alternative is `Cluster`, like Nodes or the CRD itself.
- The `schema` block is standard OpenAPI v3 — `kubectl` and the API server both use it for validation, defaulting and `kubectl explain`.

Apply it:

```bash
k apply -f manifests/01-crd.yaml
```

## Step 2: Discover the New Resource

This is the "discover" half of the CKAD requirement — the exam expects you to be able to work with a CRD you've never seen before, using nothing but `kubectl`.

Confirm it registered, and check whether it's namespaced or cluster-scoped:

```bash
k api-resources | grep flightbooking
```

Read its schema, exactly like you would for a built-in resource:

```bash
k explain flightbooking
k explain flightbooking.spec
k explain flightbooking.status
```

You can also go straight to the source:

```bash
k get crd flightbookings.training.example.com -o yaml
```

## Step 3: Create a Booking — and Notice Nothing Happens

Let's create our first `FlightBooking`, before deploying any operator:

`manifests/04-sample-flightbooking.yaml`:

```yaml
apiVersion: training.example.com/v1alpha1
kind: FlightBooking
metadata:
  name: fb-sample-001
spec:
  passenger: "Ada Lovelace"
  flightNumber: "AZ204"
  origin: "FCO"
  destination: "LHR"
  departureDate: "2026-08-01"
  seatClass: "business"
```

```bash
k apply -f manifests/04-sample-flightbooking.yaml
k get fb
```

```text
NAME            FLIGHT   PASSENGER      PHASE   BOOKING REF   AGE
fb-sample-001   AZ204    Ada Lovelace                         3s
```

Notice `PHASE` is blank, not `Pending` — even though we declared `default: "Pending"` on `status.phase`.

This is because status is a separate *subresource*, and the main resource endpoint (the one hit by k apply/k create) always ignores and clears status on create/update — so even if you wrote status: in the manifest by hand, it would be discarded before persistence. For that reason, status does not exist at all until someone explicitly writes to /status.

You can push a status update yourself, the same way the operator will in a moment — you just have to target the subresource explicitly:

```bash
k patch fb fb-sample-001 --subresource=status --type=merge \
  -p '{"status":{"phase":"Pending","bookingReference":"BK-MANUAL01"}}'
```

> Note: On Windows Command Prompt, the single quotes around the JSON payload above won't work. Use double quotes for the outer string and escape the inner quotes with backslashes, like this:

```cmd
k patch fb fb-sample-001 --subresource=status --type=merge -p "{\"status\":{\"phase\":\"Pending\",\"bookingReference\":\"BK-MANUAL01\"}}"
```

```text
NAME            FLIGHT   PASSENGER      PHASE     BOOKING REF   AGE
fb-sample-001   AZ204    Ada Lovelace   Pending   BK-MANUAL01   3s
```

Recreate the resource to reset it back to empty status — `--force` deletes and re-creates the object, so `status` is wiped again rather than reset to `Pending`:

```bash
k replace --force -f manifests/04-sample-flightbooking.yaml
```

## Step 4: What the Operator Actually Does

Our operator is intentionally minimal — no framework, just the official Kubernetes Python client (`kubernetes` on PyPI) watching the custom resource directly. It's the same mechanism `kubectl get -w` uses under the hood.

The full script is in `src/main.py`; here are the two parts worth reading closely.

First, a typed view of the resource that mirrors the CRD schema from Step 1, built with [Pydantic](https://docs.pydantic.dev/):

```python
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

    phase: Literal["Pending", "Booked", "Failed"] | None = None
    booking_reference: str | None = None
    message: str | None = None
    processed_at: datetime | None = None
```

`alias_generator=to_camel` is doing the actual work here: the CRD schema speaks camelCase (`flightNumber`, `bookingReference`), but idiomatic Python is snake_case. Pydantic converts both ways automatically, so the rest of the code just works with `booking.spec.flight_number` instead of raw dict indexing. Note that pydantic here is only doing typed parsing and validation of the watch payloads — it doesn't know anything about Kubernetes or reconciliation; the control loop itself is still entirely hand-rolled.

Notice `phase` has no default — it's `None` until something sets it. That's deliberate, and matches what we saw in Step 3: a fresh object has no `status` at all, so defaulting `phase` to `"Pending"` here in Python would paper over that and make the operator think an untouched object was already `Pending`.

Second, `reconcile()`, which now has to distinguish "no status yet" from "already Pending" instead of treating them as the same thing:

```python
def reconcile(api: client.CustomObjectsApi, booking: FlightBooking) -> None:
    name, namespace = booking.metadata.name, booking.metadata.namespace

    if booking.status.phase is None:
        log.info("Initializing FlightBooking %s/%s", namespace, name)
        _patch_status(api, name, namespace, FlightBookingStatus(phase="Pending"))
        return

    if booking.status.phase != "Pending":
        return

    log.info("Reconciling FlightBooking %s/%s", namespace, name)
    reference = book_flight(booking.spec)

    new_status = FlightBookingStatus(
        phase="Booked",
        booking_reference=reference,
        message=f"Booking confirmed for flight {booking.spec.flight_number}",
        processed_at=datetime.now(timezone.utc),
    )
    _patch_status(api, name, namespace, new_status)
    log.info("FlightBooking %s/%s booked as %s", namespace, name, reference)
```

`_patch_status()` is a small helper shared by both branches — it just wraps `patch_namespaced_custom_object_status` with `new_status.model_dump(mode="json", by_alias=True)`, turning the typed model back into the camelCase dict the API server expects. Because both the initialization and the booking patch go through it, the patch body always stays in sync with the typed model instead of being hand-written twice. In the watch loop, each raw event is parsed with `FlightBooking.model_validate(event["object"])` inside a `try/except ValidationError` — a malformed or unexpected object gets logged and skipped instead of crashing the operator with a raw `KeyError`.

One consequence worth calling out: initializing to `Pending` is itself a write to `/status`, which the watch stream reports back as a `MODIFIED` event — so `reconcile()` runs on the same object twice in quick succession, once to set `Pending` and once (a moment later, now seeing `phase == "Pending"`) to book it. That's exactly the same control loop, just fed back into itself.

The remaining piece, `run()`/`_watch_loop()`, is mostly plumbing rather than anything specific to Operators: the watch/reconcile cycle runs on a background thread, with the main thread just joining it and waiting for `Ctrl+C`. That's needed because a single-threaded version would sit blocked inside the SSL socket read for up to `timeout_seconds` between events, and Python only checks for pending signals once a blocking call returns — so `Ctrl+C` would appear to do nothing until the next watch reconnect. Running the socket read on its own thread lets the main thread's `Thread.join(timeout=1)`, which does wake up promptly, call `watch.Watch.stop()` on `Ctrl+C`, force-closing the socket from the outside to unblock the worker thread immediately. Worth knowing it's there, not worth reading line by line — see `src/main.py` for the full implementation.

Altogether, this still boils down to the same **control loop** pattern every built-in Kubernetes controller uses:

1. **Watch** the API server for changes to a resource (`watch.Watch().stream(...)`).
2. **Compare** desired state against observed state — here, "is `phase` still `Pending`?".
3. **Act** to reconcile the difference, and only ever write back through the `status` subresource (`patch_namespaced_custom_object_status`), never `spec`.

That's genuinely all an Operator is. Frameworks like [Kopf](https://kopf.readthedocs.io/), [Kubebuilder](https://book.kubebuilder.io/), the [Operator SDK](https://sdk.operatorframework.io/), or .NET's [KubeOps](https://buehler.github.io/dotnet-operator-sdk/) exist to remove boilerplate around this loop — event de-duplication, retries with backoff, leader election, CRD/RBAC code generation — which matters a lot for a production-grade operator, but obscures the mechanism when you're trying to *learn* it. For this lab, plain `watch` keeps every moving part visible.

## Step 5: RBAC for the Operator

The operator needs permission to watch `flightbookings` and to patch their `status` subresource — nothing more.

`manifests/02-rbac.yaml`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: flightbooking-operator
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: flightbooking-operator
rules:
  - apiGroups: ["training.example.com"]
    resources: ["flightbookings"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["training.example.com"]
    resources: ["flightbookings/status"]
    verbs: ["get", "patch", "update"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: flightbooking-operator
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: flightbooking-operator
subjects:
  - kind: ServiceAccount
    name: flightbooking-operator
    namespace: default
```

Notice the split rules: `flightbookings` only grants read access, `flightbookings/status` grants write access — mirroring the `subresources.status` boundary we declared in the CRD.

```bash
k apply -f manifests/02-rbac.yaml
```

> **Tip:** You can verify RBAC rules without deploying anything, using `kubectl auth can-i` with impersonation. For subresources, use `--subresource=<name>` rather than `type/subresource` — `flightbookings/status` is parsed as *resource `flightbookings`, name `status`*, not as the status subresource, and will silently check the wrong thing:
>
> ```bash
> k auth can-i patch flightbookings --subresource=status \
>   --as=system:serviceaccount:default:flightbooking-operator
> # yes
>
> k auth can-i get flightbookings \
>   --as=system:serviceaccount:default:flightbooking-operator
> # yes
> ```
>
> If you want to see everything an identity is allowed to do at once, `k auth can-i --list --as=system:serviceaccount:default:flightbooking-operator` is a good sanity check.

## Step 6: Build and Load the Operator Image

Build the image locally:

```bash
cd src
docker build -t flightbooking-operator:local .
cd ..
```

Since we're not pushing to a registry, load the image directly into your cluster's node(s):

```bash
# kind
kind load docker-image flightbooking-operator:local

# Minikube
minikube image load flightbooking-operator:local
```

If you're using Docker Desktop's built-in Kubernetes, skip this step entirely — it shares the same image daemon, so a locally built image is already visible to the cluster.

On a bare kubeadm cluster with no `kind`/`minikube` around to do this for you — including the KillerCoda Playground from the Prerequisites — the kubelet talks to containerd directly, which has its own image store completely separate from Docker's. `docker image ls` showing your build doesn't mean containerd can see it, and the kubelet will try (and fail) to pull `flightbooking-operator:local` from Docker Hub instead. Import it into containerd's `k8s.io` namespace by hand:

```bash
docker save flightbooking-operator:local | ctr -n k8s.io images import -
```

Kubernetes will pick it up on the kubelet's normal retry/backoff — no need to delete the Pod.

## Step 7: Deploy the Operator

`manifests/03-operator-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: flightbooking-operator
  namespace: default
  labels:
    app: flightbooking-operator
spec:
  replicas: 1
  selector:
    matchLabels:
      app: flightbooking-operator
  template:
    metadata:
      labels:
        app: flightbooking-operator
    spec:
      serviceAccountName: flightbooking-operator
      containers:
        - name: operator
          image: flightbooking-operator:local
          imagePullPolicy: IfNotPresent
          resources:
            limits:
              memory: 128Mi
              cpu: 100m
            requests:
              memory: 64Mi
              cpu: 50m
```

`imagePullPolicy: IfNotPresent` is important here — it tells the kubelet to use the image already loaded on the node instead of trying (and failing) to pull `flightbooking-operator:local` from a registry.

```bash
k apply -f manifests/03-operator-deployment.yaml
k rollout status deployment/flightbooking-operator
```

Check the logs to confirm it picked up the existing `fb-sample-001`:

```bash
k logs -l app=flightbooking-operator -f
```

## Step 8: Watch the Reconciliation

Back in another terminal:

```bash
k get fb --watch
```

Within a couple of seconds you should see the previously-empty `PHASE` column populate, passing through `Pending` on its way to `Booked`:

```text
NAME            FLIGHT   PASSENGER      PHASE     BOOKING REF   AGE
fb-sample-001   AZ204    Ada Lovelace                           4m12s
fb-sample-001   AZ204    Ada Lovelace   Pending                 4m13s
fb-sample-001   AZ204    Ada Lovelace   Booked    BK-7QQ2X1     4m15s
```

Inspect the full object to see every field the operator wrote:

```bash
k get fb fb-sample-001 -o yaml
```

Try creating a second booking to confirm the operator reconciles new objects too, not just the one it started with:

```bash
k apply -f - <<EOF
apiVersion: training.example.com/v1alpha1
kind: FlightBooking
metadata:
  name: fb-sample-002
spec:
  passenger: "Alan Turing"
  flightNumber: "BA118"
  origin: "LHR"
  destination: "JFK"
  departureDate: "2026-09-15"
EOF

k get fb
```

## Step 9: Debug from VS Code (Optional)

If you'd rather step through `reconcile()` than read logs, VS Code's Python debugger works with no special setup: `load_kube_config()` already falls back to your local kubeconfig whenever it can't find an in-cluster one, so running `main.py` from your machine talks to the cluster exactly like `kubectl` does.

Add a `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug FlightBooking operator",
      "type": "debugpy",
      "request": "launch",
      "program": "${workspaceFolder}/blog-posts/20260720-ckad/src/main.py",
      "cwd": "${workspaceFolder}/blog-posts/20260720-ckad/src",
      "console": "integratedTerminal",
      "justMyCode": true
    }
  ]
}
```

Set a breakpoint inside `reconcile()`, start debugging (F5), then from a separate terminal apply — or re-apply — a booking to trigger the watch event:

```bash
k apply -f manifests/04-sample-flightbooking.yaml
```

Execution should stop right inside `reconcile()`, with the full `FlightBooking` object available for inspection.

If you normally work out of a large, shared Python environment used across many unrelated projects, use a dedicated one for this lab instead — debugpy inspects everything installed before it even starts your script, and a big environment can be slow enough on the very first launch to trip the debugger's own startup timeout:

```bash
conda create -n ckad-crd-operator python=3.13.14
conda activate ckad-crd-operator
pip install kubernetes==36.0.3
pip install pydantic==2.13.4
```

This matches `src/requirements.txt`, so `pip install -r requirements.txt` from inside `src/` works just as well. Either way, point VS Code's interpreter (bottom-right of the window, or **Python: Select Interpreter** from the Command Palette) at the new environment before starting the debug session.

One more thing to keep in mind: a locally-run debug session authenticates as *your* kubeconfig user, not as the `flightbooking-operator` ServiceAccount. If you need to validate RBAC specifically, reuse the `k auth can-i ... --subresource=status --as=...` check from Step 5.

## Step 10: Clean-up

To remove everything created in this lab:

```bash
k delete -f manifests/03-operator-deployment.yaml
k delete -f manifests/02-rbac.yaml
k delete fb --all
k delete -f manifests/01-crd.yaml
```

Deleting the CRD also removes every `FlightBooking` object still on the cluster, since custom resources cannot outlive the type that defines them.

## Wrapping Up: What We've Covered

In this article we opened the **"Application Environment, Configuration and Security"** domain and covered the requirement:

> Discover and use resources that extend Kubernetes (CRD, Operators)

We saw that:

- A **CustomResourceDefinition** registers a new type in the Kubernetes API — schema, validation, defaulting and all — without a single line of Go compiled into the API server.
- `kubectl api-resources`, `kubectl explain` and `kubectl get <crd> -o yaml` are enough to **discover** and understand a resource you've never worked with before, which is exactly what the exam expects.
- A CRD by itself is inert storage. Behavior comes from an **Operator**: a control loop that watches, compares, and reconciles — the same pattern every built-in Kubernetes controller already uses.
- The `status` subresource lets you split *who can declare intent* (`spec`) from *who can report outcome* (`status`), enforced by RBAC.

We deliberately skipped operator frameworks (Kopf, Kubebuilder, Operator SDK, KubeOps) to keep the reconciliation loop fully visible. Once the pattern clicks, reaching for one of those to handle retries, leader election and code generation in a real project is a natural next step — but not a prerequisite for understanding what an operator *is*.
