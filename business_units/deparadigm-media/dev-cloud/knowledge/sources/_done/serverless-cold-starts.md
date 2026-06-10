Serverless Cold Starts — Mitigation

A cold start happens when a serverless platform spins up a new instance to handle
a request because no warm instance is available. Latency comes from container
init, runtime boot, and your app's startup code.

GCP Cloud Run: set min-instances > 0 to keep warm instances; enable startup CPU
boost; keep the container image small; lazy-load heavy deps; use 2nd-gen execution
environment for faster boots. Concurrency > 1 means one instance serves multiple
requests, reducing the number of cold starts.

AWS Lambda: use Provisioned Concurrency for predictable latency; keep the package
small; avoid heavy work outside the handler; SnapStart (Java) restores a snapshot
to skip init. Reserved concurrency caps scaling but does not pre-warm.

Rule of thumb: cold starts hurt p99 latency, not throughput. Measure before paying
for always-on capacity.
