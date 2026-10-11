---
layout: default
title: "CKAD Preparation — Define Resource Requirements"
date: 2026-10-11
categories: [ckad, kubernetes]
author: Hiro
image: "https://supaahiro.github.io/schwifty-lab/blog-posts/20261011-ckad/article.webp"
summary: "Turn application needs into Kubernetes resource declarations. Calculate budgets for multiple containers and init containers, verify Pod QoS classes, update a Deployment's resources, and account for local ephemeral storage in a runnable lab."
---

## Introduction

This article continues our [*CKAD preparation series*](https://supaahiro.github.io/schwifty-lab/blog-posts/20251019-ckad/article_EN.html), in the **Application Environment, Configuration and Security** domain:

> Define resource requirements

The [previous chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261010-ckad/article_EN.html) supplied application settings with ConfigMaps. Earlier, we explored how [requests, limits and quotas](https://supaahiro.github.io/schwifty-lab/blog-posts/20261009-ckad/article_EN.html) affect admission, scheduling and runtime failures. Now we will turn a workload description into concrete resource declarations and check the resulting Pods.

Our example has a short initialization step, an HTTP server and a helper container. We will calculate its resource budget, inspect the QoS class Kubernetes assigns, change the server's requirements through the Deployment, and add a separate worker with temporary disk storage.

The numbers in this lab are deliberately small teaching values. They make the arithmetic visible; they are not measurements or production sizing recommendations for BusyBox.

## Start with the Workload, Then Write the YAML

Before choosing numbers, identify the processes that run, which run together, and what happens during startup and updates. A helper, proxy or log collector consumes resources alongside the main application. An init container can need more resources than the service it prepares.

A useful sizing exercise records the following:

| Question | Evidence to collect | Declaration or deployment decision |
|---|---|---|
| How much CPU is needed at the expected traffic level? | Throughput, latency, CPU use and throttling during representative load | CPU request and any CPU limit |
| What is the memory working set and peak? | Startup, sustained traffic, caches, native allocations and failure history | Memory request and limit |
| Which containers overlap? | Pod design and initialization sequence | Effective Pod budget |
| How much scratch data and logging is produced? | Temporary file growth, writable layers and log retention | Local ephemeral-storage budget |
| How many instances can coexist? | Replica count, rollout strategy and termination time | Capacity and namespace budget |

There is no universal request-to-limit ratio. Start with representative measurements, include the headroom the application needs, test the resulting behavior, and revise the declarations as the workload changes. An idle `kubectl top` snapshot is not enough to characterize a service's startup or traffic peaks.

For a short syntax refresher, `100m` CPU is `0.1` CPU, and `64Mi` memory is 64 mebibytes. CPU requests influence scheduling and CPU sharing; limits constrain CPU time. A memory request is used for placement, while a memory limit can lead to an OOM kill when exceeded. The [resource management documentation](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/) describes these mechanisms.

## Prerequisites and Resources

Use a disposable cluster with Linux nodes and enough spare capacity for the small workloads below. You need `kubectl` and permission to create a namespace, Pods and a Deployment, plus read access to Nodes for the scheduling inspection. The namespace `ckad-requirements` must not already exist.

The lab uses container-level CPU and memory declarations, ordinary init containers that run to completion, and no RuntimeClass overhead. Pod-level resource budgets and restartable init sidecars need additional accounting rules; they are outside this exercise. See [Pod-level resources](https://kubernetes.io/docs/tasks/configure-pod-container/assign-pod-level-resources/) and [sidecar resource sharing](https://kubernetes.io/docs/concepts/workloads/pods/sidecar-containers/#resource-sharing-within-containers) when working with those features.

Namespace defaults, quotas, injected containers and extra admission policies can alter the results. Metrics Server is optional and is needed only for the `kubectl top` commands near the end.

The lab was tested on **Kubernetes 1.35.1**, including HTTP responses, init-container accounting, QoS assignment, the rejected request, the Deployment rollout and the temporary file write. Metrics Server was not available on the test cluster, so the optional usage measurements were not collected.

Commands with `\` continuations use Bash syntax; in PowerShell, put those commands on one line. Commands executed inside the containers use Linux tools.

```bash
git clone https://github.com/SupaaHiro/schwifty-lab.git
cd schwifty-lab/blog-posts/20261011-ckad
kubectl config current-context
```

Check that the context is your lab cluster. Follow the files in the order shown; `rejected/` contains an intentional validation failure and `patches/` contains a partial object for patching.

## Step 1: Declare Resources for Every Part of the Workload

Our Deployment runs two replicas. In each Pod:

1. `prepare` writes a small HTML response into a shared `emptyDir` and exits.
2. `app` serves that file on port 8080.
3. `helper` periodically checks the local HTTP endpoint.

The two regular containers run concurrently. The helper retries if it starts before the HTTP server is listening; the server also has a readiness probe.

The `app` container's budget in `manifests/02-deployment.yaml` is:

```yaml
resources:
  requests:
    cpu: 100m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

The location depends on the workload resource:

| Object | Container resource field |
|---|---|
| Pod | `spec.containers[].resources` |
| Deployment, StatefulSet, DaemonSet or Job | `spec.template.spec.containers[].resources` |
| CronJob | `spec.jobTemplate.spec.template.spec.containers[].resources` |

Init containers have their own `resources` entry under `initContainers[]` in the same Pod spec. Setting a budget for `app` does not also configure `helper` or `prepare`.

The complete starting values are:

| Container | CPU request | CPU limit | Memory request | Memory limit |
|---|---:|---:|---:|---:|
| `prepare` (init) | `600m` | `800m` | `64Mi` | `128Mi` |
| `app` | `100m` | `200m` | `64Mi` | `128Mi` |
| `helper` | `50m` | `100m` | `32Mi` | `64Mi` |

Deploy and check the application:

```bash
kubectl apply -f manifests/01-namespace.yaml
kubectl apply -f manifests/02-deployment.yaml
kubectl rollout status deployment/requirements-web -n ckad-requirements --timeout=120s
kubectl exec -n ckad-requirements deployment/requirements-web -c app -- wget -q -O - http://127.0.0.1:8080/
```

Expected HTTP response body:

```text
Resource requirements lab
```

Inspect the live Pod specifications too:

```bash
kubectl get pods -n ckad-requirements -l app=requirements-web -o yaml
kubectl explain deployment.spec.template.spec.containers.resources
kubectl explain deployment.spec.template.spec.initContainers.resources
```

Always compare the submitted template with the admitted Pod when troubleshooting defaults or injected containers.

## Step 2: Calculate the Effective Pod Budget

For this lab's ordinary init containers, compute each resource independently:

```text
regular-container total = sum of the regular containers' requests
init requirement        = largest request among the ordinary init containers
effective Pod request   = max(regular-container total, init requirement)
```

The same comparison applies to limits when all relevant limits are defined, as they are here. These are the [init-container resource sharing rules](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/#resource-sharing-within-containers).

For one of our Pods:

| Resource | Regular containers together | Init container | Effective Pod value |
|---|---:|---:|---:|
| CPU request | `100m + 50m = 150m` | `600m` | **`600m`** |
| Memory request | `64Mi + 32Mi = 96Mi` | `64Mi` | **`96Mi`** |
| CPU limit | `200m + 100m = 300m` | `800m` | **`800m`** |
| Memory limit | `128Mi + 64Mi = 192Mi` | `128Mi` | **`192Mi`** |

CPU and memory have different winners. Summing all three containers would incorrectly count initialization and steady operation as simultaneous. Counting only the running containers would miss the larger initialization CPU request.

The effective Pod limit also does not replace the individual limits: the `app` container still has its own `200m` CPU and `128Mi` memory limits.

With two replicas, the Deployment accounts for **`1200m` CPU requests and `192Mi` memory requests**, before adding any other workloads. The higher init CPU request continues to affect accounting after `prepare` finishes; it is not automatically reduced to `150m`.

Inspect placement and node accounting:

```bash
kubectl get pods -n ckad-requirements -l app=requirements-web -o wide
kubectl get nodes -o custom-columns='NAME:.metadata.name,CPU:.status.allocatable.cpu,MEMORY:.status.allocatable.memory'
kubectl describe node <node-name>
```

Replace `<node-name>` with a node hosting one of the lab Pods. In the node description's non-terminated Pods table, each `requirements-web` Pod should show requests of `600m` CPU and `96Mi` memory, even though its init container has completed.

`Allocatable` is the node budget available to Pods. Existing scheduled requests consume that budget, and each entire Pod must fit on a suitable node. Spare CPU spread across several nodes cannot be combined to place one Pod. Actual CPU usage being low does not erase declared requests. Other constraints such as selectors, taints and volume topology must also permit placement; requests are one part of the scheduling decision.

## Step 3: Catch an Invalid Declaration Before Deployment

The intentionally invalid Pod in `manifests/rejected/03-request-above-limit.yaml` declares:

```yaml
resources:
  requests:
    cpu: 300m
    memory: 16Mi
  limits:
    cpu: 200m
    memory: 32Mi
```

Submit a server-side dry-run:

```bash
kubectl create --dry-run=server -f manifests/rejected/03-request-above-limit.yaml
```

Expect an error explaining that the CPU request must be less than or equal to the CPU limit. This is a successful negative test: no Pod is created.

Do not confuse this with an oversized but valid request. The former fails validation; the latter can create a Pod that remains `Pending` because no node can accommodate it. The [requests, limits and quotas chapter](https://supaahiro.github.io/schwifty-lab/blog-posts/20261009-ckad/article_EN.html) demonstrates that scheduling failure separately.

Check what admission actually supplies when fields are omitted. A limit without an explicit request can become an equal request, and a LimitRange can supply defaults. Omitting `requests` is therefore not a reliable way to request zero capacity.

## Step 4: Verify the Resulting QoS Class

Kubernetes derives a Pod's QoS class from its resource declarations. For the container-level CPU and memory model used here:

| Class | Declarations |
|---|---|
| `Guaranteed` | Every regular and init container has CPU and memory requests and limits, with request equal to limit for each resource |
| `BestEffort` | No container declares CPU or memory requests or limits |
| `Burstable` | At least one CPU or memory request or limit exists, but the Pod does not qualify as Guaranteed |

See [Configure Quality of Service for Pods](https://kubernetes.io/docs/tasks/configure-pod-container/quality-service-pod/). Different containers can have different values and still qualify as Guaranteed; equality is checked within each container and resource.

Create three small Pods:

```bash
kubectl apply -f manifests/04-qos-pods.yaml
kubectl wait -n ckad-requirements --for=condition=Ready pod -l exercise=qos --timeout=120s
kubectl get pods -n ckad-requirements -l exercise=qos -o custom-columns='NAME:.metadata.name,QOS:.status.qosClass'
```

Expected classes:

```text
NAME              QOS
qos-best-effort    BestEffort
qos-guaranteed     Guaranteed
qos-mixed          Burstable
```

`qos-guaranteed` assigns `100m`/`32Mi` to its app and `50m`/`16Mi` to its helper, using equal requests and limits for both. In `qos-mixed`, the app still has matching values, but its helper has no resource declarations. Inspecting just the main container would lead to the wrong conclusion.

Our HTTP Deployment is also Burstable because its requests and limits differ:

```bash
kubectl get pods -n ckad-requirements -l app=requirements-web -o custom-columns='NAME:.metadata.name,QOS:.status.qosClass'
```

Guaranteed is not a promise of uninterrupted service or exclusive CPU cores. A container can still exceed its own memory limit, and eviction decisions involve resource pressure, usage relative to requests and Pod priority. See [node-pressure eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/#pod-selection-for-kubelet-eviction). We inspect classification here without inducing node pressure.

## Step 5: Change the Deployment's Requirements

Suppose a new workload assessment calls for the app's request to become `200m` CPU and `96Mi` memory, with limits of `400m` and `192Mi`. The helper and init container retain their existing values.

Preview a modified manifest locally:

```bash
kubectl set resources --local -f manifests/02-deployment.yaml -c app \
  --requests=cpu=200m,memory=96Mi --limits=cpu=400m,memory=192Mi -o yaml
```

`--local` prints the result without changing the cluster. The `-c app` selector matters: applying the same budget to every container would also change our accounting. See [kubectl set resources](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_set/kubectl_set_resources/).

For the actual update, the repository supplies the same resource change as a strategic merge patch:

```bash
kubectl patch deployment requirements-web -n ckad-requirements --type=strategic \
  --patch-file=manifests/patches/05-app-budget.yaml
kubectl rollout status deployment/requirements-web -n ckad-requirements --timeout=120s
kubectl get pods -n ckad-requirements -l app=requirements-web
kubectl get deployment requirements-web -n ckad-requirements -o yaml
```

The patch matches the container by its `name`, preserving `helper`. Because it changes the Deployment's Pod template, a new ReplicaSet replaces the old Pods. In a repository-managed application, record the final desired values in its maintained manifests too, so a later apply does not restore the old budget.

Our revised per-Pod calculation is:

```text
CPU request    = max(200m + 50m, 600m) = 600m
memory request = max(96Mi + 32Mi, 64Mi) = 128Mi
```

Increasing the app's CPU request has not changed the Pod's effective CPU request: the init container still determines it. The two steady replicas now account for `1200m` CPU and `256Mi` memory requests. Check the node description again and repeat the HTTP request from Step 1.

### Allow for the rollout

The Deployment explicitly uses:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0
```

The controller can add one new Pod while keeping the existing replicas available. Budgeting three Pods at the larger old/new per-Pod request gives `1800m` CPU and `384Mi` memory for that active rollout set. Terminating Pods can continue consuming resources until they exit, so this is not a strict upper bound on transient usage. Namespace quotas, node placement and termination time can all affect progress. See [Deployment rolling updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment).

We update the controller here. Direct edits to one managed Pod do not update the Deployment's desired state. Kubernetes also provides a dedicated mechanism for [in-place CPU and memory resizing](https://kubernetes.io/docs/tasks/configure-pod-container/resize-container-resources/) on supported clusters; that is a separate workflow from this template-driven rollout.

## Step 6: Include Local Ephemeral Storage

CPU and memory are not the only budgets an application can need. A worker that expands archives, buffers uploads or generates temporary files also needs disk space.

`manifests/06-scratch-pod.yaml` includes the following entries alongside its CPU and memory resources:

```yaml
resources:
  requests:
    cpu: 10m
    memory: 16Mi
    ephemeral-storage: 16Mi
  limits:
    cpu: 100m
    memory: 32Mi
    ephemeral-storage: 64Mi
```

It mounts this disk-backed volume at `/scratch`:

```yaml
volumes:
  - name: scratch
    emptyDir:
      sizeLimit: 32Mi
```

Create it and write a small file within the declared budget:

```bash
kubectl apply -f manifests/06-scratch-pod.yaml
kubectl wait -n ckad-requirements --for=condition=Ready pod/scratch-worker --timeout=120s
kubectl exec -n ckad-requirements scratch-worker -- dd if=/dev/zero of=/scratch/sample.bin bs=1M count=4
kubectl exec -n ckad-requirements scratch-worker -- wc -c /scratch/sample.bin
```

The file size should be `4194304` bytes, or 4 MiB.

The storage request is used for scheduling. The `64Mi` limit contributes to the Pod's local storage budget, which also accounts for writable container layers and logs; it is not all reserved for `/scratch`. The `32Mi` size limit applies specifically to that `emptyDir`. It does not preallocate space or guarantee that the node has that much free disk.

Local storage enforcement depends on kubelet accounting and a supported node filesystem layout. Exceeding these budgets can result in eviction after detection; do not expect `emptyDir.sizeLimit` to behave like an immediate filesystem write quota. The small write above verifies the mounted workspace, not storage-limit enforcement. See [local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/).

Changing the volume to `emptyDir.medium: Memory` changes the budget to watch: tmpfs writes count as memory use, rather than local ephemeral-storage use. Account for them together with the writing container's other memory needs. These [memory-backed emptyDir considerations](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#considerations-for-memory-backed-emptydir-volumes) matter even if the application itself has a small heap.

## Check the Declaration Against the Observed Workload

If Metrics Server is installed, these commands help inspect current use:

```bash
kubectl top pods -n ckad-requirements --containers
kubectl top nodes
```

Our tiny HTTP response and sleeping containers will not exercise the declared budgets. Use meaningful traffic and long enough observation windows when sizing a real service. Correlate resource measurements with latency, throughput, errors, restarts and throttling, and repeat the checks after tuning.

For an exam exercise, verify the requested state directly:

| Check | What to inspect |
|---|---|
| Correct workload and container | Resource fields inside the right Pod template, matched by container name |
| Valid quantities | CPU units, memory units, and request no greater than its limit |
| Complete Pod budget | Concurrent containers, ordinary init containers, and any additional overhead |
| Expected QoS | The live Pod's `status.qosClass` |
| Successful update | Rollout status, new Pod resources and application response |
| Storage requirements | Local scratch versus memory-backed storage versus persistent data |

## Cleanup

Remove the namespace created exclusively for this lab:

```bash
kubectl delete namespace ckad-requirements
```

This deletes the Deployment, its Pods, the three QoS Pods and the scratch worker. The `emptyDir` data disappears with its Pod; the rejected Pod was never stored.

The next chapter will cover **creating and consuming Secrets**, building on the configuration patterns introduced with ConfigMaps.
